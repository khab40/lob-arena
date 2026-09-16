"""Static submission orchestration checks; no Job, model, or cloud calls."""
import json
from types import SimpleNamespace

import pytest

from scripts import submit_g8_native_rehearsal as submitter


@pytest.fixture
def execution(tmp_path, monkeypatch):
    package = tmp_path / "package"
    package.mkdir()
    (package / "reviewer-public.pem").write_text("inert static key")
    plan = SimpleNamespace(source_commit="1" * 40, deployment_image="reviewed:alias", image="reviewed@digest",
                           identity=lambda: "package-identity")
    monkeypatch.setattr(submitter, "verify_package", lambda *a, **kw: plan)
    monkeypatch.setattr(submitter.subprocess, "check_output", lambda argv, **kw: plan.source_commit if "rev-parse" in argv else "")
    calls = []
    job = {"metadata": {"id": "aijob-test", "created_at": "2026-09-16T09:00:00Z"}}

    def before(*args):
        calls.append("before")
        return {"proof": "before"}

    def after(*args):
        calls.append("after")
        assert calls[-2] == "create"
        return plan.deployment_image, {"proof": "after"}

    def invoke(argv):
        action = "dry-run" if "--dry-run" in argv else argv[3]
        calls.append(action)
        return SimpleNamespace(returncode=0, stdout=json.dumps(job), stderr="")

    monkeypatch.setattr(submitter, "_verify_short_tag", before)
    monkeypatch.setattr(submitter, "_verify_created_short_tag_job", after)
    monkeypatch.setattr(submitter, "verify_registry", lambda *a, **kw: None)
    monkeypatch.setattr(submitter, "verify_readback", lambda *a, **kw: None)
    monkeypatch.setattr(submitter, "job_command", lambda *a, **kw: ["nebius", "ai", "job", "create"])
    monkeypatch.setattr(submitter, "invoke", invoke)
    return package, calls


def test_emitted_command_uses_verified_wrapper_and_single_intent(execution):
    package, calls = execution
    command = submitter.submission_command(package, "score")
    assert command[1].endswith("scripts/submit_g8_native_rehearsal.py")
    assert "nebius" not in command and "--image" not in command
    receipt = submitter.submit(package, "score")
    assert calls == ["dry-run", "before", "create", "after", "get"]
    assert receipt["job_id"] == "aijob-test"
    assert json.loads((package.parent / "score-submission/registry-after.json").read_text()) == {"proof": "after"}
    with pytest.raises(FileExistsError):
        submitter.submit(package, "score")
    assert calls.count("create") == 1


def test_pre_create_drift_never_submits(execution, monkeypatch):
    package, calls = execution
    monkeypatch.setattr(submitter, "_verify_short_tag", lambda *a: (_ for _ in ()).throw(SystemExit("drift")))
    with pytest.raises(SystemExit):
        submitter.submit(package, "score")
    assert calls == ["dry-run"]


def test_post_create_drift_cancels_returned_job(execution, monkeypatch):
    package, calls = execution
    monkeypatch.setattr(submitter, "_verify_created_short_tag_job", lambda *a: (_ for _ in ()).throw(RuntimeError("drift")))
    with pytest.raises(RuntimeError, match="drift"):
        submitter.submit(package, "score")
    assert calls == ["dry-run", "before", "create", "cancel"]
    assert (package.parent / "score-submission/cancel-process.json").is_file()


def test_ambiguous_create_is_retained_and_never_retried(execution, monkeypatch):
    package, _ = execution
    monkeypatch.setattr(submitter, "invoke", lambda argv: SimpleNamespace(
        returncode=0 if "--dry-run" in argv else 1, stdout="", stderr="timeout"))
    with pytest.raises(RuntimeError, match="ambiguous"):
        submitter.submit(package, "score")
    assert (package.parent / "score-submission/create-process.json").is_file()
    with pytest.raises(FileExistsError):
        submitter.submit(package, "score")


def test_dry_run_failure_stops_before_registry_and_create_intent(execution, monkeypatch):
    package, calls = execution
    observed = []

    def reject(argv):
        observed.append(argv)
        return SimpleNamespace(returncode=3, stdout="", stderr="invalid request")

    monkeypatch.setattr(submitter, "invoke", reject)
    with pytest.raises(RuntimeError, match="dry-run failed"):
        submitter.submit(package, "score")
    assert len(observed) == 1 and observed[0][-1] == "--dry-run"
    assert calls == []
    evidence = package.parent / "score-submission"
    assert json.loads((evidence / "dry-run-process.json").read_text())["returncode"] == 3
    assert not (evidence / "intent.json").exists()
    assert not (evidence / "create-process.json").exists()
