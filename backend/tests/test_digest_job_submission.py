"""Submission metadata only; no model, provider, or registry operations."""
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("mlflow")

from scripts import submit_nebius_job as submit  # noqa: E402
from scripts import lightgbm_wave1 as wave1  # noqa: E402


IMAGE = "registry.example/jobs@sha256:" + "a" * 64


@pytest.mark.parametrize("args", [
    ["--deployment-image", "registry.example/jobs:latest"],
    ["--allow-short-tag-workaround"],
    ["--deployment-image", IMAGE, "--allow-short-tag-workaround"],
])
@pytest.mark.parametrize("dry_run", [True, False])
def test_new_alias_or_workaround_is_rejected_before_provider_access(monkeypatch, args, dry_run):
    monkeypatch.delenv("NEBIUS_WAVE1_RECOVER_EXISTING_JOB_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["submit", "--workload", "lightgbm-wave1", "--image", IMAGE,
                                    *args, *(["--dry-run"] if dry_run else [])])
    monkeypatch.setattr(submit.subprocess, "run", lambda *a, **kw: pytest.fail("provider accessed"))
    with pytest.raises(SystemExit, match="direct digest deployment"):
        submit.main()


@pytest.mark.parametrize("payload", [
    {"metadata": {"id": "aijob-other"}, "spec": {"image": IMAGE}},
    {"metadata": {"id": "aijob-test"}, "spec": {"image": "registry.example/jobs:latest"}},
    {"metadata": {"id": "aijob-test"}, "spec": {"image": IMAGE[:-1] + "b"}},
    {"metadata": {"id": "aijob-test"}, "image": IMAGE},
    {"metadata": {"id": "aijob-test"}, "spec": None},
    [],
])
def test_readback_requires_exact_job_and_spec_digest(monkeypatch, payload):
    monkeypatch.setattr(submit.subprocess, "run", lambda argv, **kw:
                        subprocess.CompletedProcess(argv, 0, stdout=json.dumps(payload)))
    with pytest.raises(RuntimeError, match="identity/image"):
        submit._verify_created_digest_job("aijob-test", IMAGE)


def test_exact_digest_readback_is_accepted(monkeypatch):
    def readback(argv, **kwargs):
        assert argv == ["nebius", "ai", "job", "get", "aijob-test", "--format", "json"]
        assert kwargs["timeout"] == 60
        return subprocess.CompletedProcess(argv, 0, stdout=json.dumps({
            "metadata": {"id": "aijob-test"}, "spec": {"image": IMAGE}}))
    monkeypatch.setattr(submit.subprocess, "run", readback)
    assert submit._verify_created_digest_job("aijob-test", IMAGE) == IMAGE


@pytest.mark.parametrize("returncode,body", [(1, ""), (0, "not JSON")])
def test_unavailable_or_malformed_readback_fails(monkeypatch, returncode, body):
    monkeypatch.setattr(submit.subprocess, "run", lambda argv, **kw:
                        subprocess.CompletedProcess(argv, returncode, stdout=body))
    with pytest.raises(RuntimeError):
        submit._verify_created_digest_job("aijob-test", IMAGE)


@pytest.mark.parametrize("deployment,workaround", [("mutable:tag", True), (IMAGE, True), ("mutable:tag", False)])
def test_collection_cannot_promote_alias_receipt_to_digest_evidence(tmp_path, monkeypatch, deployment, workaround):
    result_uri = "s3://example/result"
    submission = tmp_path / "submission.json"
    monitor = tmp_path / "monitor.json"
    submission.write_text(json.dumps({"schema_version": "lightgbm_wave1_g4_submission_v1",
        "job_id": "aijob-test", "result_uri": result_uri, "campaign_spend_usd": 1,
        "image": IMAGE, "deployment_image": deployment, "short_tag_workaround": workaround}))
    monitor.write_text(json.dumps({"schema_version": "lightgbm_wave1_g4_monitor_v1",
        "job_id": "aijob-test", "status": "COMPLETED", "observed_job_context": {"image": deployment}}))
    monkeypatch.setattr(wave1, "download_s3_release", lambda *a, **kw: pytest.fail("download attempted"))
    with pytest.raises(ValueError, match="deployment image"):
        wave1.collect_s3_result(result_uri, tmp_path / "result", tmp_path / "collection.json",
            submission_path=submission, monitor_path=monitor, estimated_cost_usd=0,
            campaign_spend_to_date_usd=1, endpoint_url=wave1.OBJECT_STORAGE_ENDPOINT_URL)


@pytest.mark.parametrize("args", [["--recover-existing-job-id", "aijob-existing"],
                                   ["--recover-job-readback", "historical.json"]])
def test_recovery_flags_never_fall_through_to_synthetic_creation(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", ["submit", "--subnet-id", "inert", *args])
    monkeypatch.setattr(submit.subprocess, "run", lambda *a, **kw: pytest.fail("create attempted"))
    with pytest.raises(SystemExit, match="recovery requires --workload"):
        submit.main()


@pytest.mark.parametrize("dry_run", [False, True])
def test_fresh_final_requests_require_the_signed_replacement_gate(monkeypatch, dry_run):
    for name in ("NEBIUS_WAVE1_RECOVER_EXISTING_JOB_ID", "NEBIUS_DEPLOYMENT_IMAGE",
                 "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID", "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
                 "NEBIUS_OBJECT_STORAGE_SESSION_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(sys, "argv", ["submit", "--workload", "lightgbm-wave1", "--subnet-id", "inert",
                                    "--image", IMAGE, *(["--dry-run"] if dry_run else [])])
    monkeypatch.setattr(submit, "_load_wave1_request", lambda *a: SimpleNamespace(mode="final-evaluation"))
    monkeypatch.setattr(submit, "verify_g8_preflight", lambda *a: pytest.fail("legacy preflight entered"))
    monkeypatch.setattr(submit.subprocess, "run", lambda *a, **kw: pytest.fail("provider accessed"))
    with pytest.raises(SystemExit, match="signed replacement-package runner"):
        submit.main()
