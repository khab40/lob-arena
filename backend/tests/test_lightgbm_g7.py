from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

pytest.importorskip("lightgbm", reason="Wave 1 G7 tests require the ml extra")

from app.ml.lightgbm import g7_candidate  # noqa: E402
from app.ml.lightgbm.cloud_contracts import (  # noqa: E402
    LightGbmCloudJobRequest,
    Wave1ExperimentSpec,
)
from app.ml.lightgbm.cloud_runner import FrozenCandidate, execute_wave1_request  # noqa: E402
from app.ml.lightgbm.contracts import LightGbmTrainingRun  # noqa: E402
from app.ml.lightgbm.g6_campaign import G6ValidationRecord  # noqa: E402
from app.ml.lightgbm.g7_candidate import (  # noqa: E402
    G7FinalEstimate,
    authorize_g7_candidate,
    create_g7_candidate_freeze,
    load_g7_authorization,
    load_g7_candidate_freeze,
)
from app.nebius.object_storage import sha256_file, verify_complete_result  # noqa: E402
from scripts import lightgbm_wave1 as wave1_script  # noqa: E402


CREATED_AT = datetime(2026, 9, 12, 10, 0, tzinfo=UTC)


def test_g7_freezes_exact_candidate_and_stays_closed_before_authorization(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_root, expected = _create_freeze(tmp_path, monkeypatch)

    observed = load_g7_candidate_freeze(freeze_root)
    assert observed == expected
    assert observed.status == "awaiting_manual_authorization"
    assert observed.final_identity_available is False
    assert observed.test_fold_accessed is False
    assert observed.development_jobs_consumed == observed.development_job_ceiling == 20
    assert observed.final_estimate.projected_campaign_spend_usd == 28.67
    assert observed.authorization_challenge.statement_template == (
        f"APPROVE WAVE1 FINAL TEST {observed.candidate_hash} <ISO-8601 timestamp>"
    )
    assert (freeze_root / observed.candidate.uri).is_file()
    verify_complete_result(freeze_root / "candidate")

    (freeze_root / observed.candidate.uri).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="inventory checksum mismatch"):
        load_g7_candidate_freeze(freeze_root)


def test_g7_requires_exact_operator_statement_and_verifies_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    freeze_root, freeze = _create_freeze(tmp_path, monkeypatch)
    authorization_root = tmp_path / "authorization"
    approval_statement = (
        f"APPROVE WAVE1 FINAL TEST {freeze.candidate_hash} "
        "2026-09-12T10:05:00+00:00"
    )

    with pytest.raises(ValueError, match="candidate hash"):
        authorize_g7_candidate(
            freeze_root=freeze_root,
            approval_statement=f"APPROVE WAVE1 FINAL TEST {'f' * 64} 2026-09-12T10:05:00+00:00",
            output=authorization_root,
        )
    with pytest.raises(ValueError, match="timezone-aware"):
        authorize_g7_candidate(
            freeze_root=freeze_root,
            approval_statement=(
                f"APPROVE WAVE1 FINAL TEST {freeze.candidate_hash} 2026-09-12T10:05:00"
            ),
            output=authorization_root,
        )
    with pytest.raises(ValueError, match="predates"):
        authorize_g7_candidate(
            freeze_root=freeze_root,
            approval_statement=(
                f"APPROVE WAVE1 FINAL TEST {freeze.candidate_hash} "
                "2026-09-12T09:59:59+00:00"
            ),
            output=authorization_root,
        )
    assert not authorization_root.exists()

    receipt = authorize_g7_candidate(
        freeze_root=freeze_root,
        approval_statement=approval_statement,
        output=authorization_root,
    )
    assert load_g7_authorization(authorization_root) == receipt
    assert receipt.status == "authorized"
    assert receipt.signature_verified is True
    assert receipt.final_identity_available is True
    assert receipt.candidate_hash == freeze.candidate_hash
    assert receipt.statement == approval_statement
    assert receipt.freeze_receipt_sha256 == sha256_file(
        freeze_root / "g7-candidate-freeze.json"
    )

    signature = authorization_root / receipt.authorization_signature.uri
    signature.write_bytes(b"invalid")
    with pytest.raises(ValueError, match="inventory checksum mismatch"):
        load_g7_authorization(authorization_root)


def test_g7_final_estimate_cannot_understate_basis_or_exceed_ceiling() -> None:
    with pytest.raises(ValueError, match="runtime estimate"):
        G7FinalEstimate(
            predicted_runtime_seconds=99,
            predicted_cost_usd=0.02,
            basis_runtime_seconds=100,
            basis_cost_usd=0.01,
            campaign_spend_to_date_usd=28.65,
            projected_campaign_spend_usd=28.67,
        )
    with pytest.raises(ValueError, match="spend ceiling"):
        G7FinalEstimate(
            predicted_runtime_seconds=600,
            predicted_cost_usd=22,
            basis_runtime_seconds=100,
            basis_cost_usd=0.01,
            campaign_spend_to_date_usd=28.65,
            projected_campaign_spend_usd=50.65,
        )


def _create_freeze(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, g7_candidate.G7CandidateFreeze]:
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    selected_result = tmp_path / "development"
    development_request = wave1_script._request(
        campaign_id="wave1-g7-fixture",
        run_id="wave1-g7-development",
        mode="development",
        created_at=CREATED_AT,
        result=selected_result,
        experiment=Wave1ExperimentSpec(calibration_method="isotonic"),
    )
    request_path = inputs / "request.json"
    request_path.write_bytes(development_request.canonical_bytes())
    execute_wave1_request(request_path, input_root=inputs)
    request = LightGbmCloudJobRequest.model_validate_json(
        (selected_result / "request.json").read_text(encoding="utf-8")
    )
    candidate = FrozenCandidate.model_validate_json(
        (selected_result / "candidate.json").read_text(encoding="utf-8")
    )
    training = LightGbmTrainingRun.model_validate_json(
        (selected_result / "artifacts" / candidate.training_manifest.uri).read_text(
            encoding="utf-8"
        )
    )
    candidate_hash = sha256_file(selected_result / "candidate.json")
    record = G6ValidationRecord(
        trial_id="calibration-isotonic",
        run_id=request.run_id,
        group="calibration",
        experiment_hash=request.experiment.canonical_hash(),
        random_seed=request.random_seed,
        calibration_method="isotonic",
        mlflow_run_id="mlflow-g7-fixture",
        mlflow_dataset_input_count=1,
        image=request.image,
        git_commit=request.git_commit,
        input_identity_hash=request.input.canonical_hash(),
        model_sha256=training.model_artifact.sha256,
        validation_predictions_sha256="1" * 64,
        candidate_hash=candidate_hash,
        reproducibility_hash=candidate.reproducibility_hash,
        validation_binary_logloss=0.34,
        balanced_f1=0.69,
        family_recalls={"layering_like": 0.54, "quote_stuffing": 0.71},
        minimum_family_recall=0.54,
        raw_brier=0.02,
        raw_ece=0.08,
        calibrated_brier=0.006,
        calibrated_ece=0.001,
        test_fold_accessed=False,
        collection_receipt_verified=True,
    )
    monkeypatch.setattr(
        g7_candidate,
        "collect_validation_record",
        lambda **_kwargs: (record, request.experiment),
    )

    g6_comparison = tmp_path / "g6-comparison.json"
    g6_comparison.write_text(
        json.dumps(
            {
                "schema_version": "lightgbm_wave1_g6_campaign_comparison_v1",
                "status": "passed",
                "disposition": "g6_candidate_selected",
                "campaign_id": request.campaign_id,
                "selected_trial_id": record.trial_id,
                "selected_candidate_hash": candidate_hash,
                "selected_reproducibility_hash": candidate.reproducibility_hash,
                "test_fold_accessed": False,
                "job_count": 9,
                "development_jobs_consumed_after_g6": 20,
                "gates": {"all_selected_evidence_verified": True},
            }
        ),
        encoding="utf-8",
    )
    collection = tmp_path / "collection.json"
    collection.write_text(
        json.dumps(
            {
                "verified": True,
                "nebius_job_id": "aijob-g7fixture",
                "request_sha256": request.canonical_hash(),
                "estimated_cost_usd": 0.01,
                "campaign_spend_to_date_usd": 28.65,
                "actual_job_context": {"image": request.image},
            }
        ),
        encoding="utf-8",
    )
    monitor = tmp_path / "monitor.json"
    monitor.write_text(
        json.dumps(
            {
                "status": "COMPLETED",
                "job_id": "aijob-g7fixture",
                "request_sha256": request.canonical_hash(),
                "elapsed_seconds": 317,
            }
        ),
        encoding="utf-8",
    )
    freeze_root = tmp_path / "freeze"
    freeze = create_g7_candidate_freeze(
        g6_comparison_path=g6_comparison,
        selected_result=selected_result,
        selected_collection_path=collection,
        selected_monitor_path=monitor,
        output=freeze_root,
        tool_git_commit="a" * 40,
        created_at=CREATED_AT,
        predicted_final_runtime_seconds=600,
        predicted_final_cost_usd=0.02,
    )
    return freeze_root, freeze
