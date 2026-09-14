"""Regression checks for the reviewed synthetic-only operator policy package."""
import json
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
