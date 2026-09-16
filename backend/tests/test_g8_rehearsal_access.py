"""Regression checks for the reviewed synthetic-only operator policy package."""
import json
import hashlib
from copy import deepcopy
from datetime import datetime
from pathlib import Path


EVIDENCE = Path(__file__).resolve().parents[2] / "docs/evidence"
GROUP = "group-e00wb5ptvpq0q7dpaf"
CAMPAIGN = "g8-native-rehearsal-20260914"


def read(name):
    return json.loads((EVIDENCE / f"g8-native-rehearsal-{name}-20260914.json").read_text())


def test_applied_output_policy_matches_original_proposal():
    original = read("policy-grant")
    observed = read("output-access-readback")
    assert original["metadata"]["resource_version"] == "5"
    assert observed["results_bucket_resource_version"] == "6"
    assert original["spec"]["bucket_policy"]["rules"] == observed["output_policy_rules"]


def test_candidate_patch_preserves_applied_rules_and_adds_exact_read_only_source():
    patch = read("candidate-read")
    observed = read("output-access-readback")
    assert patch["metadata"] == {
        "id": observed["results_bucket_id"],
        "resource_version": observed["results_bucket_resource_version"],
    }
    assert set(patch) == {"metadata", "spec"}
    assert set(patch["spec"]) == {"bucket_policy"}
    rules = patch["spec"]["bucket_policy"]["rules"]
    assert rules[:-1] == observed["output_policy_rules"]
    assert rules[-1] == {
        "group_id": GROUP, "roles": ["storage.viewer"],
        "paths": [f"campaigns/{CAMPAIGN}/development/synthetic-development/*"],
    }


def test_input_patch_preserves_final_identity_without_granting_production_access():
    patch = read("input-read")
    observed = read("output-access-readback")
    assert patch["metadata"] == {
        "id": observed["final_bucket_id"],
        "resource_version": observed["final_bucket_resource_version"],
    }
    assert set(patch) == {"metadata", "spec"}
    assert set(patch["spec"]) == {"bucket_policy"}
    rules = patch["spec"]["bucket_policy"]["rules"]
    assert rules[:-1] == observed["final_bucket_policy_rules"]
    assert [rule for rule in rules if rule.get("group_id") == GROUP] == [{
        "group_id": GROUP, "roles": ["storage.viewer"],
        "paths": [f"releases/{CAMPAIGN}/staging/*"],
    }]


def test_output_permission_is_not_submission_or_source_readback_evidence():
    observed = read("output-access-readback")
    assert observed["output_policy_exact_match"] is True
    for gate in ("synthetic_candidate_read_granted", "synthetic_input_read_granted",
                 "synthetic_sources_staged", "authenticated_synthetic_source_readbacks_verified",
                 "ready_to_submit", "production_test_accessed"):
        assert observed[gate] is False
    assert observed["jobs_submitted"] == observed["filesystems_created"] == 0


def test_applied_source_policies_match_patches_but_do_not_claim_data_readiness():
    observed = read("source-access-readback")
    assert observed["original_output_grant_rerun"] is False
    assert observed["production_final_read_key_state_after_updates"] == "INACTIVE"
    for grant, patch_name, version in zip(
        observed["grants"], ("candidate-read", "input-read"), ("7", "4"), strict=True
    ):
        patch = read(patch_name)
        assert grant["bucket_id"] == patch["metadata"]["id"]
        assert grant["before_resource_version"] == patch["metadata"]["resource_version"]
        assert grant["after_resource_version"] == version
        assert grant["applied_rules"] == patch["spec"]["bucket_policy"]["rules"]
        assert grant["policy_exact_match"] and grant["other_bucket_settings_preserved"]
    for field in ("source_staging_verified", "authenticated_source_downloads_verified",
                  "ready_to_submit", "original_output_grant_rerun", "production_test_accessed"):
        assert observed[field] is False
    assert observed["jobs_submitted"] == observed["filesystems_created"] == observed["mlflow_runs_created"] == 0


def test_approved_input_writer_window_has_bound_grant_and_revocation_evidence():
    record = json.loads((EVIDENCE / "g8-input-staging-session-20260915.json").read_bytes())
    proposal = json.loads((EVIDENCE / record["proposal"]).read_bytes())

    def bound(reference):
        raw = (EVIDENCE / reference["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == reference["sha256"]
        return json.loads(raw)

    before = proposal["before"]
    granted = bound(record["snapshots"]["granted"])
    revoked = bound(record["snapshots"]["revoked"])
    expected = deepcopy(before["spec"])
    expected["bucket_policy"] = proposal["proposed_update"]["spec"]["bucket_policy"]
    assert granted["spec"] == expected
    assert revoked["spec"] == before["spec"]
    for snapshot in (granted, revoked):
        for field in ("id", "parent_id", "name", "created_at", "labels"):
            assert snapshot["metadata"][field] == before["metadata"][field]
    assert (int(before["metadata"]["resource_version"]) < int(granted["metadata"]["resource_version"])
            < int(revoked["metadata"]["resource_version"]))
    start, grant, end = (datetime.fromisoformat(record[key])
                         for key in ("window_started_at", "grant_verified_at", "revoked_at"))
    assert start <= datetime.fromisoformat(granted["metadata"]["updated_at"]) <= grant
    assert grant < datetime.fromisoformat(revoked["metadata"]["updated_at"]) <= end
    assert 0 < (end - start).total_seconds() < proposal["maximum_writer_window_seconds"] == 1800
    assert abs(record["writer_window_seconds"] - (end - start).total_seconds()) < 1
    assert record["cleanup_complete"] and record["baseline_spec_restored"]
    publication, readback = bound(record["publication"]), bound(record["readback"])
    assert publication["source_package_sha256"] == readback["source_package_sha256"] == record["source_package_sha256"]
    assert [release["object_count"] for release in publication["releases"]] == [25, 325]
    assert [release["put_attempts"] for release in publication["releases"]] == [0, 325]
    assert publication["credential_access_key_sha256"] == readback["credential_access_key_sha256"]
    assert readback["credential_access_key_sha256"] == record["credential_access_key_id_sha256"]
    assert publication["credential_source"] == readback["credential_source"] == "explicit_process_environment_not_version_attested"
    assert datetime.fromisoformat(publication["verified_at"]) < end < datetime.fromisoformat(readback["verified_at"])
    assert readback["remote_source_bytes_verified"] and readback["production_head_denial_verified"]
    assert readback["comparison_replay_domains_verified"] == 30
    assert len(readback["local_only_metadata"]) == 6
    assert record["source_staging_complete"] and record["cloud_jobs_created"] == 0
    for field in ("candidate_writer_granted", "production_body_downloaded", "credential_version_provenance_verified",
                  "pinned_job_credential_injection_verified",
                  "native_storage_verified", "mlflow_remote_verified", "production_g8_complete"):
        assert record[field] is False
