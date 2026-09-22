"""Inert provider receipts; no model, dataset rows or cloud operations."""
import copy
import hashlib
import json
from pathlib import Path
import runpy

import pytest

VERIFY = runpy.run_path(str(Path(__file__).resolve().parents[2]
                           / "scripts/verify_g8_comparison_execution.py"))["verify"]


def write(root, name, value):
    (root / name).write_text(json.dumps(value))


@pytest.fixture
def evidence(tmp_path):
    for name in ("worker.py", "supervisor.py", "expected-inventory.json", "comparison.json"):
        (tmp_path / name).write_bytes(b"inert")
    digest = hashlib.sha256(b"inert").hexdigest()
    scope = {"run_name": "fixture-r3", "deployment_image": "registry/image:fixture",
             "image": "registry/image@sha256:" + "1" * 64, "platform": "cpu-d3", "preset": "4vcpu-16gb",
             "filesystem_id": "filesystem-fixture", "comparison_relative_root": "comparison/fixture",
             "worker_sha256": digest, "supervisor_sha256": digest, "inventory_sha256": digest}
    write(tmp_path, "proposal.json", scope)
    anchor = hashlib.sha256((tmp_path / "proposal.json").read_bytes()).hexdigest()
    spec = {"image": scope["deployment_image"], "platform": "cpu-d3", "preset": "4vcpu-16gb",
            "timeout": "3600s", "container_command": "python", "args": "/g8-audit-supervisor.py fixture-r3",
            "subnet_id": "vpcsubnet-e00ppzc4353dxv210j", "disk": {"size_bytes": "107374182400"},
            "volumes": [{"source": "filesystem-fixture", "container_path": "/g8-package", "mode": "READ_ONLY"}],
            "injected_files": [{"container_path": "/g8-audit-supervisor.py"}],
            "environment_variables": [{"name": k, "value": v} for k, v in {
                "PYTHONDONTWRITEBYTECODE": "1", "AWS_EC2_METADATA_DISABLED": "true",
                "G8_SEMANTIC_APPROVED_PROPOSAL_SHA256": anchor, "G8_AUDIT_SUPERVISOR_SHA256": digest}.items()]}
    job = {"metadata": {"id": "job-fixture", "name": "fixture-r3", "parent_id": "project-e00g6zvxpr00waz8t3y51k"},
           "spec": spec, "status": {"state": "COMPLETED"}}
    for name in ("job-final.json", "job-first-readback.json"):
        write(tmp_path, name, job)
    write(tmp_path, "operator-approval.json", {"approved": True, "proposal_sha256": anchor})
    write(tmp_path, "registry-before.json", {"digest": "sha256:" + "1" * 64})
    staged = {name: {"sha256": hashlib.sha256((tmp_path / name).read_bytes()).hexdigest(),
                     "size_bytes": (tmp_path / name).stat().st_size}
              for name in ("worker.py", "proposal.json", "expected-inventory.json", "comparison.json")}
    write(tmp_path, "stage-readback.json", {"staged": staged, "corrected_files_rehashed": 377,
        "package_files_verified": 25, "original_tree_preserved": True, "free_bytes": 21474836480})
    write(tmp_path, "vm-after.json", {"metadata": {"id": "computeinstance-e00xq8hqrzks2pf3gn"}, "status": {"state": "STOPPED"}})
    write(tmp_path, "final-access-after.json", {"metadata": {"id": "accesskey-e00gy66k4xybsdyxqj"}, "status": {"state": "INACTIVE"}})
    write(tmp_path, "filesystem-after.json", {"metadata": {"id": "filesystem-fixture"}, "status": {}})
    write(tmp_path, "jobs-after.json", {"items": [job]})
    result = {"schema_version": "g8_comparison_semantics_result_v1", "proposal_sha256": anchor,
              "checkpoints_verified": 27, "canonical_replays_exhausted": 30, "inventoried_files_rehashed": 377,
              "protected_comparison_rows_parsed": True, "model_execution": False, "final_bucket_access": False,
              "prediction_join_verified": False, "snapshot_validation": "sha256_and_parquet_footer_row_count_only",
              "snapshot_rows_parsed": False, "snapshot_event_consistency_verified": False,
              "replacement_execution_authorized": False}
    records = [{"schema_version": "g8_audit_supervisor_v1", "stage": "launcher_started"}, result,
               {"schema_version": "g8_audit_supervisor_v1", "stage": "worker_exit", "return_code": 0}]
    write(tmp_path, "job-logs.json", "\n".join(json.dumps(r) for r in records))
    return tmp_path, anchor, job, records


def test_success_requires_all_results_and_retains_scope(evidence):
    root, anchor, _, _ = evidence
    result = VERIFY(root, anchor)
    assert result["semantic_verification_passed"] is True
    assert result["verified_result"]["canonical_replays_exhausted"] == 30
    assert result["verified_result"]["snapshot_rows_parsed"] is False
    assert result["final_evaluation_authorized"] is False


@pytest.mark.parametrize("case", ["duplicate", "count", "worker_failure", "supervisor", "no_launcher"])
def test_success_cannot_hide_incomplete_or_conflicting_results(evidence, case):
    root, anchor, _, records = evidence
    if case == "duplicate":
        records.append(copy.deepcopy(records[1]))
    elif case == "count":
        records[1]["canonical_replays_exhausted"] = 29
    elif case == "worker_failure":
        records.append({"audit_passed": False, "error_type": "ValueError"})
    elif case == "supervisor":
        records[-1]["return_code"] = 1
    else:
        records.pop(0)
    write(root, "job-logs.json", "\n".join(json.dumps(r) for r in records))
    with pytest.raises(ValueError):
        VERIFY(root, anchor)


@pytest.mark.parametrize("state", ["FAILED", "CANCELLED"])
def test_terminal_failure_never_becomes_a_semantic_pass(evidence, state):
    root, anchor, job, _ = evidence
    job["status"]["state"] = state
    write(root, "job-final.json", job)
    result = VERIFY(root, anchor)
    assert result["semantic_verification_passed"] is False and result["verified_result"] is None


def test_still_allocated_compute_and_wrong_anchors_fail(evidence):
    root, anchor, job, _ = evidence
    with pytest.raises(ValueError, match="anchor"):
        VERIFY(root, "0" * 64)
    job["status"]["instances"] = [{"compute_instance_id": "still-running"}]
    write(root, "job-final.json", job)
    with pytest.raises(ValueError, match="compute"):
        VERIFY(root, anchor)
