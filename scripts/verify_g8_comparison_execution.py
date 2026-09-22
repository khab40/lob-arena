"""Independently inspect bounded R3 provider/evidence receipts; never parse rows."""
import argparse
import hashlib
import json
from pathlib import Path


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(directory, anchor):
    def read(name):
        return json.loads((directory / name).read_bytes())
    require(sha(directory / "proposal.json") == anchor, "proposal anchor mismatch")
    scope, job, first = read("proposal.json"), read("job-final.json"), read("job-first-readback.json")
    approval = read("operator-approval.json")
    require(approval["approved"] is True and approval["proposal_sha256"] == anchor, "approval mismatch")
    require(job["metadata"]["id"] == first["metadata"]["id"], "Job identity changed")
    require(job["metadata"]["name"] == scope["run_name"], "Job name mismatch")
    require(job["metadata"]["parent_id"] == "project-e00g6zvxpr00waz8t3y51k", "project mismatch")
    state = job["status"]["state"]
    require(state in {"COMPLETED", "FAILED", "CANCELLED"}, "Job is not terminal")
    require(not job["status"].get("instances"), "Job compute is not released")
    spec = job["spec"]
    require(spec == first["spec"], "Job specification changed")
    for key, expected in {
        "image": scope["deployment_image"], "platform": scope["platform"], "preset": scope["preset"],
        "timeout": "3600s", "container_command": "python",
        "args": "/g8-audit-supervisor.py " + scope["run_name"],
        "subnet_id": "vpcsubnet-e00ppzc4353dxv210j",
        "volumes": [{"source": scope["filesystem_id"], "container_path": "/g8-package", "mode": "READ_ONLY"}],
        "injected_files": [{"container_path": "/g8-audit-supervisor.py"}],
    }.items():
        require(spec.get(key) == expected, "unexpected Job " + key)
    require(spec["disk"]["size_bytes"] == "107374182400", "disk bound mismatch")
    env = spec["environment_variables"]
    expected_env = {"PYTHONDONTWRITEBYTECODE": "1", "AWS_EC2_METADATA_DISABLED": "true",
                    "G8_SEMANTIC_APPROVED_PROPOSAL_SHA256": anchor,
                    "G8_AUDIT_SUPERVISOR_SHA256": scope["supervisor_sha256"]}
    require(sorted(env, key=lambda x: x["name"]) == sorted(
                [{"name": key, "value": value} for key, value in expected_env.items()], key=lambda x: x["name"]),
            "unexpected Job environment")
    require(read("registry-before.json")["digest"] == scope["image"].split("@")[1], "image alias drift")
    for name, key in (("worker.py", "worker_sha256"), ("supervisor.py", "supervisor_sha256"),
                      ("expected-inventory.json", "inventory_sha256")):
        require(sha(directory / name) == scope[key], "staged source hash mismatch")
    stage = read("stage-readback.json")
    for name in ("worker.py", "proposal.json", "expected-inventory.json", "comparison.json"):
        path = directory / name
        require(stage["staged"][name] == {"sha256": sha(path), "size_bytes": path.stat().st_size},
                "staging readback mismatch")
    require(stage["corrected_files_rehashed"] == 377 and stage["package_files_verified"] == 25,
            "staging verification incomplete")
    require(stage["original_tree_preserved"] and stage["free_bytes"] >= 21474836480, "staging bounds failed")
    vm, key = read("vm-after.json"), read("final-access-after.json")
    require(vm["metadata"]["id"] == "computeinstance-e00xq8hqrzks2pf3gn"
            and vm["status"]["state"] == "STOPPED", "VM identity/state mismatch")
    require(key["metadata"]["id"] == "accesskey-e00gy66k4xybsdyxqj"
            and key["status"]["state"] == "INACTIVE", "final key identity/state mismatch")
    filesystem = read("filesystem-after.json")
    require(filesystem["metadata"]["id"] == scope["filesystem_id"], "filesystem identity mismatch")
    require(not filesystem["status"].get("read_only_attachments"), "audit filesystem still attached")
    jobs = [j for j in read("jobs-after.json")["items"] if j["metadata"]["name"] == scope["run_name"]]
    require(len(jobs) == 1 and jobs[0]["metadata"]["id"] == job["metadata"]["id"], "submission count mismatch")
    logs = read("job-logs.json")
    require(isinstance(logs, str) and len(logs.encode()) <= 2 * 1024**2, "log size bound")
    records = []
    for line in logs.splitlines():
        start = line.find("{")
        if start >= 0:
            try:
                records.append(json.loads(line[start:]))
            except json.JSONDecodeError:
                continue  # Provider progress text is not a worker assertion.
    results = [r for r in records if r.get("schema_version") == "g8_comparison_semantics_result_v1"]
    supervisors = [r for r in records if r.get("schema_version") == "g8_audit_supervisor_v1"]
    expected = {"schema_version": "g8_comparison_semantics_result_v1", "proposal_sha256": anchor,
        "checkpoints_verified": 27, "canonical_replays_exhausted": 30, "inventoried_files_rehashed": 377,
        "protected_comparison_rows_parsed": True, "model_execution": False, "final_bucket_access": False,
        "prediction_join_verified": False, "snapshot_validation": "sha256_and_parquet_footer_row_count_only",
        "snapshot_rows_parsed": False, "snapshot_event_consistency_verified": False,
        "replacement_execution_authorized": False}
    passed = state == "COMPLETED"
    if passed:
        require(not any(r.get("audit_passed") is False for r in records), "worker failure in successful log")
        require(results == [expected], "missing, duplicate or inconsistent successful worker result")
        require(sum(r.get("stage") == "launcher_started" for r in supervisors) == 1, "launcher count mismatch")
        exits = [r for r in supervisors if r.get("stage") == "worker_exit"]
        require(len(exits) == 1 and exits[0].get("return_code") == 0, "supervisor did not verify worker success")
        require(not any(r.get("stage") in {"deadline", "launcher_failure"} for r in supervisors), "supervisor failed")
    return {"schema_version": "g8_comparison_execution_verification_v1", "job_id": job["metadata"]["id"],
            "provider_state": state, "semantic_verification_passed": passed,
            "verified_result": expected if passed else None, "job_compute_released": True,
            "vm_final_state": "STOPPED", "final_access_key_state": "INACTIVE",
            "proposal_sha256": anchor, "comparison_sha256": sha(directory / "comparison.json"),
            "worker_sha256": scope["worker_sha256"], "supervisor_sha256": scope["supervisor_sha256"],
            "comparison_relative_root": scope["comparison_relative_root"], "jobs_submitted": 1,
            "free_bytes_after_staging": stage["free_bytes"], "final_evaluation_authorized": False,
            "evidence_sha256": {name: sha(directory / name) for name in (
                "job-final.json", "job-first-readback.json", "job-logs.json", "operator-approval.json",
                "stage-readback.json", "registry-before.json", "vm-after.json", "final-access-after.json",
                "filesystem-after.json", "jobs-after.json")}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = verify(args.directory, args.proposal_sha256)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"provider_state": result["provider_state"],
                      "semantic_verification_passed": result["semantic_verification_passed"]}))
