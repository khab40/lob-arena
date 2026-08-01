from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.ml.lightgbm.contracts import (
    CalibrationManifest,
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
    ModelBundleManifest,
)
from app.ml.lightgbm.artifacts import resolve_verified_artifact
from app.ml.lightgbm.release import verify_complete_lightgbm_v1_release
from app.ml.lightgbm.scoring import validate_prediction_parquet


DEVELOPMENT_EXPERIMENT = "lob-arena/lightgbm-development"
EVALUATION_EXPERIMENT = "lob-arena/governed-evaluation"


def log_development_run(
    *,
    artifact_root: Path,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    training_manifest_path: Path,
    calibration_manifest_path: Path,
    validation_metrics_path: Path,
    feature_importance_path: Path,
    reliability_bins_path: Path,
    reliability_diagram_path: Path,
    model_path: Path,
    tracking_uri: str | None = None,
) -> str:
    """Log permitted development evidence without weakening local governance."""

    _verify_development_evidence(
        artifact_root=artifact_root,
        training=training,
        calibration=calibration,
        training_manifest_path=training_manifest_path,
        calibration_manifest_path=calibration_manifest_path,
        model_path=model_path,
    )
    for path in (
        validation_metrics_path,
        feature_importance_path,
        reliability_bins_path,
        reliability_diagram_path,
    ):
        _require_artifact_root_file(path, artifact_root)
    mlflow = _mlflow(tracking_uri)
    mlflow.set_experiment(DEVELOPMENT_EXPERIMENT)
    with mlflow.start_run(run_name=training.binding.training_run_id) as run:
        mlflow.set_tags(_binding_tags(training, governance_state="validation_frozen"))
        parameters = {
            **training.hyperparameters.model_dump(mode="json"),
            "training_seed": training.training_seed,
            "preprocessing": training.preprocessing.mode,
            "class_weight_strategy": training.class_weights.strategy,
            "base_session_weighting": training.data_policy.base_session_weighting,
            "calibration_method": calibration.parameters.method,
        }
        mlflow.log_params(parameters)
        metrics: dict[str, float] = {
            "validation_binary_logloss": training.early_stopping.best_score,
            "best_iteration": float(training.early_stopping.best_iteration),
            "raw_brier_score": calibration.raw_metrics.brier_score,
            "raw_expected_calibration_error": calibration.raw_metrics.expected_calibration_error,
            "calibrated_brier_score": calibration.calibrated_metrics.brier_score,
            "calibrated_expected_calibration_error": calibration.calibrated_metrics.expected_calibration_error,
        }
        for point in calibration.operating_points:
            prefix = point.mode
            metrics.update(
                {
                    f"{prefix}_threshold": point.threshold,
                    f"{prefix}_precision": point.validation_metrics.precision,
                    f"{prefix}_recall": point.validation_metrics.recall,
                    f"{prefix}_f1": point.validation_metrics.f1,
                }
            )
        mlflow.log_metrics(metrics)
        for path in (
            training_manifest_path,
            calibration_manifest_path,
            validation_metrics_path,
            feature_importance_path,
            reliability_bins_path,
            reliability_diagram_path,
            model_path,
        ):
            mlflow.log_artifact(str(path), artifact_path="governed")
        return str(run.info.run_id)


def log_governed_evaluation_run(
    *,
    artifact_root: Path,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    predictions: DetectorPredictionsManifest,
    bundle: ModelBundleManifest,
    bundle_path: Path,
    checksum_path: Path,
    prediction_manifest_path: Path,
    benchmark_results_path: Path | None = None,
    tracking_uri: str | None = None,
) -> str:
    """Index an already-verified frozen-test release in MLflow."""

    verify_complete_lightgbm_v1_release(
        artifact_root,
        training=training,
        calibration=calibration,
        bundle=bundle,
        predictions=predictions,
    )
    validate_prediction_parquet(
        resolve_verified_artifact(predictions.predictions, artifact_root=artifact_root),
        manifest=predictions,
    )
    if bundle_path.read_bytes() != bundle.canonical_bytes():
        raise ValueError("MLflow model bundle path is not its canonical governed manifest")
    _require_artifact_root_file(checksum_path, artifact_root)
    if prediction_manifest_path.read_bytes() != predictions.canonical_bytes():
        raise ValueError("MLflow prediction manifest path is not canonical governed content")
    mlflow = _mlflow(tracking_uri)
    mlflow.set_experiment(EVALUATION_EXPERIMENT)
    with mlflow.start_run(run_name=predictions.prediction_run_id) as run:
        tags = _binding_tags(training, governance_state="release_verified")
        tags.update(
            {
                "calibration_id": calibration.calibration_id,
                "prediction_run_id": predictions.prediction_run_id,
                "model_bundle_hash": bundle.manifest_hash(),
                "operating_mode": predictions.operating_mode,
                "test_accessed": "true",
            }
        )
        mlflow.set_tags(tags)
        mlflow.log_metrics(
            {
                "test_alert_count": float(predictions.alert_count),
                "test_row_count": float(predictions.row_count),
                "frozen_threshold": predictions.threshold,
            }
        )
        if benchmark_results_path is not None:
            metrics = _benchmark_metrics(benchmark_results_path)
            if metrics:
                mlflow.log_metrics(metrics)
        for path in (bundle_path, checksum_path, prediction_manifest_path):
            mlflow.log_artifact(str(path), artifact_path="governed")
        if benchmark_results_path is not None:
            mlflow.log_artifact(str(benchmark_results_path), artifact_path="governed-evaluation")
        return str(run.info.run_id)


def _binding_tags(
    training: LightGbmTrainingRun,
    *,
    governance_state: str,
) -> dict[str, str]:
    binding = training.binding
    return {
        "model_id": binding.model_id,
        "training_run_id": binding.training_run_id,
        "protocol_id": binding.protocol_id,
        "protocol_hash": binding.protocol_hash,
        "corpus_id": binding.corpus_id,
        "corpus_hash": binding.corpus_hash,
        "split_id": binding.split_id,
        "assignment_hash": binding.assignment_hash,
        "feature_schema_version": binding.feature_schema_version,
        "feature_config_hash": binding.feature_config_hash,
        "feature_release_id": training.feature_release_id,
        "feature_release_sha256": training.feature_release_sha256,
        "git_commit": training.git_commit,
        "governance_state": governance_state,
        "test_accessed": str(training.data_policy.test_fold_accessed).lower(),
    }


def _verify_development_evidence(
    *,
    artifact_root: Path,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    training_manifest_path: Path,
    calibration_manifest_path: Path,
    model_path: Path,
) -> None:
    if calibration.binding.identity_tuple() != training.binding.identity_tuple():
        raise ValueError("MLflow calibration binding does not match the training run")
    if training_manifest_path.read_bytes() != training.canonical_bytes():
        raise ValueError("MLflow training manifest path is not canonical governed content")
    if calibration_manifest_path.read_bytes() != calibration.canonical_bytes():
        raise ValueError("MLflow calibration manifest path is not canonical governed content")
    governed_model = resolve_verified_artifact(
        training.model_artifact,
        artifact_root=artifact_root,
    )
    if governed_model != model_path.resolve():
        raise ValueError("MLflow model path does not match the governed model artifact")
    validation_predictions = resolve_verified_artifact(
        calibration.input_predictions,
        artifact_root=artifact_root,
    )
    validate_prediction_parquet(
        validation_predictions,
        expected_rows=calibration.row_count,
        expected_fold="validation",
        require_decisions=False,
    )


def _require_artifact_root_file(path: Path, artifact_root: Path) -> None:
    root = artifact_root.resolve()
    resolved = path.resolve()
    if not resolved.is_file() or resolved == root or root not in resolved.parents:
        raise ValueError("MLflow artifact is missing or outside the governed artifact root")


def _mlflow(tracking_uri: str | None) -> Any:
    try:
        import mlflow
    except ImportError as exception:
        raise RuntimeError("MLflow logging requires the backend ml optional dependency") from exception
    if tracking_uri is not None:
        mlflow.set_tracking_uri(tracking_uri)
    return mlflow


def _benchmark_metrics(path: Path) -> dict[str, float]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    metrics = payload.get("metrics", payload)
    if not isinstance(metrics, dict):
        raise ValueError("governed benchmark metrics artifact is invalid")
    allowed = {
        "precision",
        "recall",
        "f1",
        "false_alerts_per_million_events",
        "attack_level_recall",
        "detection_before_benefit_rate",
        "duplicate_alert_load",
    }
    return {
        f"test_{name}": float(value)
        for name, value in metrics.items()
        if name in allowed and isinstance(value, (int, float))
    }
