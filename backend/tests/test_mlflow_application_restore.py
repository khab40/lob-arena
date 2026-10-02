"""Inert orchestration checks; no Docker process, database or network is used."""
import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import mlflow_application_restore as restore  # noqa: E402


@pytest.fixture
def case(tmp_path, monkeypatch):
    backup = tmp_path / "metadata.dump"
    backup.write_bytes(b"x" * 380475)
    monkeypatch.setattr(restore, "BACKUP_SHA256", hashlib.sha256(backup.read_bytes()).hexdigest())
    helper = tmp_path / "readiness_recovery.py"
    helper.write_text("# inert helper")
    tables = {str(i): {"rows": 0, "sha256": "a" * 64} for i in range(60)}
    receipt = {"backup_sha256": restore.BACKUP_SHA256, "tables": tables,
               "postgres_image_id": "sha256:" + "a" * 64}
    calls = []
    def command(args, **kwargs):
        calls.append((args, kwargs))
        if args[:3] == ["docker", "inspect", "--format"]:
            identity = ("a" if "-db-" in args[-1] else "b") * 64
            return json.dumps({"id": identity, "labels": {
                "lob-arena.restore-attempt": args[-1].rsplit("-", 1)[1]}}).encode()
        if args[:2] == ["docker", "inspect"]:
            env = ["MLFLOW_ADMIN_USERNAME=operator", "MLFLOW_ADMIN_PASSWORD=" + "p" * 32,
                   "MLFLOW_FLASK_SERVER_SECRET_KEY=" + "s" * 32, "AWS_SECRET_ACCESS_KEY=must-not-copy"]
            return json.dumps([{"Image": "sha256:" + "a" * 64, "Config": {"Env": env}}]).encode()
        if args[-1] == restore.PREFLIGHT:
            return b"runtime-compatible"
        if args[-1] == restore.PROBE:
            return b'{"status":"verified"}'
        return b""
    monkeypatch.setattr(restore.recovery, "command", command)
    monkeypatch.setattr(restore.recovery, "sql", lambda *a: b"1")
    monkeypatch.setattr(restore.recovery, "inventory", lambda *a: tables.copy())
    monkeypatch.setattr(restore, "baseline", lambda *a: {"backup_sha256": restore.BACKUP_SHA256})
    output = tmp_path / "new-attempt"
    return output, receipt, helper, backup, calls, command


def execute(case):
    output, receipt, helper, backup, _, _ = case
    return restore.run(output, receipt, helper, backup=backup)


def test_exact_isolation_bounds_credentials_and_cleanup(case):
    assert execute(case) == {"status": "verified"}
    output, _, _, _, calls, original = case
    runs = [a for a, _ in calls if a[:2] == ["docker", "run"]]
    assert len(runs) == 2
    for args in runs:
        assert args[args.index("--network") + 1] == "none"
        assert args[args.index("--pull") + 1] == "never"
        assert args[args.index("--cpus") + 1] == "1"
        assert "-p" not in args and "--publish" not in args
        assert all("AWS" not in arg for arg in args)
    assert [args[args.index("--memory") + 1] for args in runs] == ["1g", "2g"]
    private = next(kw["data"] for a, kw in calls if a[-1] == restore.RECEIVE)
    assert b"AWS" not in private
    assert all("must-not-copy" not in p.read_text() for p in output.glob("*.json"))
    cleanup = json.loads((output / "cleanup.json").read_bytes())
    assert len(cleanup["attempted"]) == 2 and cleanup["failed"] == []
    assert restore.recovery.command is original
    assert all(0 < kw["timeout"] <= 210 for _, kw in calls)
    assert output.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in output.glob("*.json"))
    # Even if the name changes ownership after inspection, only the observed ID
    # is removed and checked for absence.
    removed = [a[-1] for a, _ in calls if a[:3] == ["docker", "rm", "--force"]]
    assert removed == ["b" * 64, "a" * 64]
    assert [a[-1] for a, _ in calls if a[:3] == ["docker", "ps", "-aq"]] == [
        "id=" + identity for identity in removed]


@pytest.mark.parametrize("phase", ["restore", "startup"])
def test_table_drift_aborts_before_probe_and_cleans_only_attempt(case, monkeypatch, phase):
    tables = case[1]["tables"]
    readings = iter([{}] if phase == "restore" else [tables, {}])
    monkeypatch.setattr(restore.recovery, "inventory", lambda _: next(readings))
    with pytest.raises(ValueError, match="differ"):
        execute(case)
    assert not any(args[-1] == restore.PROBE for args, _ in case[4])
    cleanup = json.loads((case[0] / "cleanup.json").read_bytes())
    assert len(cleanup["attempted"]) == (1 if phase == "restore" else 2)
    assert cleanup["failed"] == []


def test_bad_backup_does_not_start_containers(case):
    case[3].write_bytes(b"wrong")
    with pytest.raises(ValueError, match="backup"):
        execute(case)
    assert case[4] == []


def test_existing_attempt_is_never_reused(case):
    case[0].mkdir()
    with pytest.raises(FileExistsError):
        execute(case)
    assert case[4] == []


def test_cleanup_never_removes_a_container_with_wrong_owner(case, monkeypatch):
    original = case[5]
    def wrong_owner(args, **kwargs):
        result = original(args, **kwargs)
        return b'{}' if args[:3] == ["docker", "inspect", "--format"] else result
    monkeypatch.setattr(restore.recovery, "command", wrong_owner)
    with pytest.raises(ValueError, match="cleanup incomplete"):
        execute(case)
    assert not any(a[:3] == ["docker", "rm", "--force"] for a, _ in case[4])


def test_ambiguous_app_start_is_not_retried_and_ownership_is_checked(case, monkeypatch):
    original = case[5]
    def failing(args, **kwargs):
        result = original(args, **kwargs)
        if args[:2] == ["docker", "run"] and "--read-only" in args:
            raise TimeoutError()
        return result
    monkeypatch.setattr(restore.recovery, "command", failing)
    with pytest.raises(TimeoutError):
        execute(case)
    assert len([a for a, _ in case[4] if a[:2] == ["docker", "run"]]) == 2
    assert len([a for a, _ in case[4] if a[:3] == ["docker", "rm", "--force"]]) == 2


def test_embedded_programs_parse_and_probe_clears_inherited_context():
    for name in ("BOOT", "RECEIVE", "PROBE", "PREFLIGHT"):
        compile(getattr(restore, name), name, "exec")
    assert "os.environ.clear()" in restore.PROBE
    assert "mlflow.get_active_model_id() is None" in restore.PROBE
    assert "--no-serve-artifacts" in restore.BOOT
    assert "upgrade" not in restore.BOOT
