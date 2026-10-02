"""Host orchestration boundaries using inert subprocess responses only."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
spec = importlib.util.spec_from_file_location("readiness_window",
    Path(__file__).resolve().parents[2] / "scripts/mlflow_readiness_window.py")
window = importlib.util.module_from_spec(spec)
spec.loader.exec_module(window)
IMAGE, POSTGRES = "sha256:" + "a" * 64, "sha256:" + "b" * 64


def encode(value):
    return json.dumps(value, sort_keys=True).encode()


@pytest.fixture
def case(tmp_path, monkeypatch):
    root = tmp_path.resolve()
    source, inputs, output, env = [root / name for name in ("source", "inputs", "output", "deployment.env")]
    (source / "scripts").mkdir(parents=True)
    inputs.mkdir()
    (source / "scripts/mlflow_readiness_preflight.py").write_bytes(b"inert-preflight")
    restore = {"backup_sha256": "d" * 64, "postgres_image_id": POSTGRES}
    (inputs / "restore-receipt.json").write_bytes(encode(restore))
    env.write_bytes(b"MLFLOW_EXPORTER_EXPERIMENTS=existing\nMLFLOW_EXPORTER_MODEL_NAMES=existing\n")
    env.chmod(0o600)
    proposal = {"implementation_source_commit": "c" * 40, "output_directory": str(output),
        "env_file": "existing-compose-environment-file",
        "package_files_sha256": {"scripts/mlflow_readiness_preflight.py": hashlib.sha256(b"inert-preflight").hexdigest()},
        "input_files_sha256": {"restore-receipt.json": hashlib.sha256(encode(restore)).hexdigest()}}
    raw = encode(proposal)
    (inputs / "proposal.json").write_bytes(raw)
    c = NS(source=source, inputs=inputs, output=output, env=env, commit="c" * 40,
        sha=hashlib.sha256(raw).hexdigest(), calls=[], envs=[], label=str(env), cleanup_failed=[],
        client_timeout=False, cleanup_error=False, present=False, preflight_ok=True)
    monkeypatch.setattr(sys, "dont_write_bytecode", True)
    monkeypatch.setenv("PYTHONPATH", str(source))
    def process(args, **kwargs):
        c.calls.append(args)
        result = NS(returncode=0, stdout=b"")
        if args[:3] == ["docker", "inspect", window.APP]:
            result.stdout = encode([{"Image": IMAGE, "State": {"Running": True}, "Config": {
                "Labels": {"com.docker.compose.project.environment_file": c.label}}}])
            if len(args) == 4:
                result.stdout = encode([*json.loads(result.stdout), {"Config": {"Env": [
                    *[k + "=inert-test-value" for k in window.CREDENTIAL_KEYS], "AWS_ACCESS_KEY_ID=not-forwarded"]}}])
        elif "psql" in args:
            result.stdout = b"unchanged-private-users"
        elif args[:2] == ["docker", "exec"] and kwargs.get("input") == b"inert-preflight":
            result.stdout = encode({"status": "verified" if c.preflight_ok else "failed", "mlflow_version": "3.13.0"})
        elif args[:2] == ["docker", "exec"]:
            result.stdout = encode({"default_permission": "NO_PERMISSIONS", "grant_default_workspace_access": "false"})
        elif len(args) > 2 and args[2].endswith("mlflow_application_restore.py"):
            restored = output / "restore"
            restored.mkdir()
            (restored / "cleanup.json").write_bytes(encode({"attempted": ["owned-db", "owned-app"], "failed": c.cleanup_failed}))
            (restored / "application-receipt.json").write_bytes(encode({"status": "verified", "runtime_version": "3.13.0",
                "network_mode": "none", "startup_preserved_all_tables": True, **restore, "images": [POSTGRES, IMAGE]}))
        elif args[:2] == ["docker", "run"]:
            c.envs.append(kwargs["env"])
            if c.client_timeout:
                c.present = True
                raise TimeoutError("ambiguous container start")
            (output / "live/live-receipt.json").write_bytes(encode({"schema_version": "mlflow_live_readiness_phase_v1",
                "binding": {"proposal_sha256": c.sha, "source_commit": c.commit, "purpose": "mlflow-readiness-20261002"}}))
        elif args[:3] == ["docker", "ps", "-aq"]:
            result.stdout = b"f" * 64 if c.present else b""
        elif args[:3] == ["docker", "inspect", "--format"]:
            attempt = hashlib.sha256((c.sha + "\n" + str(output)).encode()).hexdigest()
            result.stdout = encode({"id": "f" * 64, "labels": {window.LABEL: attempt}})
        elif args[:2] == ["docker", "rm"]:
            result.returncode = 1 if c.cleanup_error else 0
            c.present = c.cleanup_error
        else:
            raise AssertionError("unexpected subprocess")
        return result
    monkeypatch.setattr(window.subprocess, "run", process)
    c.execute = lambda: window.run(source, inputs, output, env, c.sha, c.commit)
    return c


def test_complete_window_keeps_credentials_scoped_and_checks_cleanup(case):
    receipt = case.execute()
    assert receipt["model_jobs"] == 0 and receipt["live_users_and_credentials_unchanged"]
    assert receipt["status"].endswith("pending_independent_readback_and_vm_stop")
    assert (case.output / "client-cleanup.json").is_file()
    assert set(case.envs[0]) == {"PATH", *window.CREDENTIAL_KEYS, *window.TRANSPORT}
    assert "AWS_ACCESS_KEY_ID" not in case.envs[0]
    launch = next(args for args in case.calls if args[:2] == ["docker", "run"])
    assert ["--cpus", "1"] == launch[launch.index("--cpus"):launch.index("--cpus") + 2]
    assert launch[launch.index("--memory") + 1] == "512m"
    assert launch[launch.index("--network") + 1] == "host"
    assert window.LABEL + "=" in launch[launch.index("--label") + 1]


@pytest.mark.parametrize("failure", ["extra-source", "input-drift", "env-mode", "output", "bytecode"])
def test_local_boundary_failure_precedes_every_subprocess(case, monkeypatch, failure):
    if failure == "extra-source":
        (case.source / "mlflow.py").write_text("unreviewed")
    if failure == "input-drift":
        (case.inputs / "restore-receipt.json").write_text("{}")
    if failure == "env-mode":
        case.env.chmod(0o644)
    if failure == "bytecode":
        monkeypatch.setattr(sys, "dont_write_bytecode", False)
    if failure == "output":
        case.execute = lambda: window.run(case.source, case.inputs, case.output.parent / "other",
                                         case.env, case.sha, case.commit)
    with pytest.raises(ValueError):
        case.execute()
    assert case.calls == []


@pytest.mark.parametrize("failure", ["env-label", "runtime", "restore-cleanup"])
def test_remote_readiness_failure_prevents_live_mutations(case, failure):
    if failure == "env-label":
        case.label = "/other/file,/second/file"
    if failure == "runtime":
        case.preflight_ok = False
    if failure == "restore-cleanup":
        case.cleanup_failed = ["owned-app"]
    before = case.env.read_bytes()
    with pytest.raises(ValueError):
        case.execute()
    assert not case.envs and case.env.read_bytes() == before


def test_cleanup_uses_immutable_owned_id_and_rejects_foreign_name():
    calls = []
    answers = iter([b"f" * 64, encode({"id": "f" * 64, "labels": {window.LABEL: "owned"}}), b"", b""])
    def call(args):
        calls.append(args)
        return next(answers)
    assert window.cleanup_client("owned", call)["client_absent"]
    assert calls[2] == ["docker", "rm", "--force", "f" * 64]
    calls.clear()
    answers = iter([b"f" * 64, encode({"id": "f" * 64, "labels": {window.LABEL: "foreign"}})])
    with pytest.raises(ValueError, match="foreign"):
        window.cleanup_client("owned", call)
    assert not any(args[:2] == ["docker", "rm"] for args in calls)


def test_failed_cleanup_blocks_final_receipt_and_allowlist_change(case):
    before = case.env.read_bytes()
    case.client_timeout = case.cleanup_error = True
    with pytest.raises(RuntimeError, match="cleanup"):
        case.execute()
    assert not (case.output / "application-receipt.json").exists()
    assert case.env.read_bytes() == before


def test_automatic_removal_race_requires_positive_absence_readback():
    calls = []
    def call(args):
        calls.append(args)
        if args[:2] == ["docker", "inspect"]:
            return encode({"id": "f" * 64, "labels": {window.LABEL: "owned"}})
        if args[:2] == ["docker", "rm"]:
            raise RuntimeError("container already removed")
        return b"" if "id=" + "f" * 64 in args else b"f" * 64
    assert window.cleanup_client("owned", call)["client_absent"]
    assert calls[-1][-1] == "id=" + "f" * 64


def test_phase_budget_raises_and_restores_alarm_handler():
    previous = window.signal.getsignal(window.signal.SIGALRM)
    with pytest.raises(TimeoutError):
        with window.budget(1):
            window.signal.raise_signal(window.signal.SIGALRM)
    assert window.signal.getsignal(window.signal.SIGALRM) == previous
    assert window.signal.getitimer(window.signal.ITIMER_REAL) == (0.0, 0.0)


def test_client_runs_as_operator_without_root_capabilities(case, monkeypatch):
    monkeypatch.setattr(window.os, "geteuid", lambda: 1000)
    monkeypatch.setattr(window.os, "getegid", lambda: 1001)
    args = window.client_command(case.source, case.inputs, case.output, IMAGE,
                                 case.sha, case.commit, "e" * 64)
    assert args[args.index("--user") + 1] == "1000:1001"
    assert args[args.index("--cap-drop") + 1] == "ALL"
    assert "HOME=/tmp" in args


@pytest.mark.parametrize("target", ["root", "file"])
def test_foreign_staging_owner_rejected_before_subprocess(case, monkeypatch, target):
    original = Path.stat
    foreign = case.source if target == "root" else case.source / "scripts/mlflow_readiness_preflight.py"
    def changed_owner(path, *args, **kwargs):
        observed = original(path, *args, **kwargs)
        if path == foreign:
            fields = list(observed)
            fields[4] = observed.st_uid + 1
            return window.os.stat_result(fields)
        return observed
    monkeypatch.setattr(Path, "stat", changed_owner)
    with pytest.raises(ValueError, match="current operator"):
        case.execute()
    assert case.calls == []
