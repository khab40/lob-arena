"""Static validation-policy boundaries; no training, scoring or provider calls."""
from datetime import UTC, datetime
from typing import Literal, get_args, get_origin

import pytest

pytest.importorskip("lightgbm")
pytest.importorskip("mlflow")

from app.ml.lightgbm.g8_replacement import CODE_PATHS, ReplacementPlan  # noqa: E402
from app.ml.lightgbm.g8_production_transport import ARCHIVES, BOOTSTRAP  # noqa: E402


def replacement_values():
    values = {name: get_args(field.annotation)[0]
              for name, field in ReplacementPlan.model_fields.items()
              if get_origin(field.annotation) is Literal}
    files = set(CODE_PATHS) | set(ARCHIVES) | {BOOTSTRAP,
        "request.json", "profile.json", "frozen-root.json", "projection.json", "candidate.json",
        "c4-inputs.json", "dataset-lineage.json", "authorization.json", "authorization.sig",
        "authorization-public.pem", "native-durability.json", "remote-roundtrip.json",
        "comparison-inventory.json",
    }
    values.update(source_commit="a" * 40, run_id="replacement-new", request_sha256="a" * 64,
        filesystem_id="computefilesystem-example", mount_source="native", capacity_gib=10,
        max_checkpoint_bytes=1024, max_checkpoint_files=10,
        comparison_relative_path="comparison/original/comparison.json",
        evaluation_profile_sha256="b" * 64, comparison_sha256="c" * 64,
        candidate_release_uri="s3://example/candidate", verified_at=datetime(2026, 9, 16, tzinfo=UTC),
        secret_selectors={name: "mbsec-example@mbsecver-example" for name in (
            "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "MLFLOW_TRACKING_USERNAME", "MLFLOW_TRACKING_PASSWORD")},
        native_durability_receipt_sha256="d" * 64, authenticated_remote_receipt_sha256="e" * 64,
        comparison_inventory_receipt_sha256="f" * 64,
        files={name: {"sha256": "a" * 64, "size_bytes": 1} for name in files})
    return values


def test_replacement_has_no_billing_or_wall_clock_submission_gate():
    plan = ReplacementPlan.model_validate(replacement_values())
    assert plan.validation_policy == "lightgbm_transformers_validation_v1"
    assert plan.spend_monitoring == "operator_managed_alerts"
    assert not {"billing.json"} & set(plan.files)
    assert not {"expires_at", "cleanup_deadline", "campaign_spend_usd"} & set(plan.model_dump())


@pytest.mark.parametrize("key,value", [
    ("run_id", "nasdaq-g8-final-r4-20260913"), ("replacement_executions_allowed", 2),
    ("candidate_sha256", "0" * 64), ("no_retraining_recalibration_or_threshold_changes", False),
    ("prior_test_fold_accessed", False), ("max_checkpoint_bytes", 3 * 1024**3),
    ("validation_policy", "unrestricted"),
])
def test_relaxed_policy_preserves_final_evaluation_boundaries(key, value):
    with pytest.raises(ValueError):
        ReplacementPlan.model_validate({**replacement_values(), key: value})
