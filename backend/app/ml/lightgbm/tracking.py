from __future__ import annotations

import json
import math
import re
import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from app.ml.lightgbm.c4_evaluation import C4EvaluationInputs

from app.ml.lightgbm.contracts import (
    CalibrationManifest,
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
    ModelBundleManifest,
)
from app.ml.lightgbm.cloud_contracts import Wave1ExperimentSpec
from app.ml.lightgbm.artifacts import resolve_verified_artifact
from app.ml.lightgbm.release import verify_complete_lightgbm_v1_release
from app.ml.lightgbm.scoring import validate_prediction_parquet
from app.ml.dataset_lineage import feature_dataset_inputs, log_dataset_inputs


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
    dataset_source_uri: str | None = None,
    cloud_metadata: dict[str, str | int | float] | None = None,
    experiment: Wave1ExperimentSpec | None = None,
    campaign_id: str | None = None,
    request_run_id: str | None = None,
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
        tags = _binding_tags(training, governance_state="validation_frozen")
        tags["raw_rows_uploaded_to_mlflow"] = "false"
        if experiment is not None:
            tags["experiment_hash"] = experiment.canonical_hash()
        if campaign_id is not None:
            tags["campaign_id"] = campaign_id
        if request_run_id is not None:
            tags["request_run_id"] = request_run_id
        cloud_tags, cloud_metrics = _validated_cloud_metadata(cloud_metadata)
        tags.update(cloud_tags)
        mlflow.set_tags(tags)
        parameters = {
            **training.hyperparameters.model_dump(mode="json"),
            "training_seed": training.training_seed,
            "preprocessing": training.preprocessing.mode,
            "class_weight_strategy": training.class_weights.strategy,
            "base_session_weighting": training.data_policy.base_session_weighting,
            "calibration_method": calibration.parameters.method,
            "ordered_feature_count": len(training.ordered_feature_columns),
        }
        if experiment is not None:
            parameters.update(
                {
                    "excluded_features": json.dumps(
                        list(experiment.excluded_features), separators=(",", ":")
                    ),
                    "operating_mode": experiment.operating_mode,
                    "precision_floor": experiment.precision_floor,
                    "recall_floor": experiment.recall_floor,
                }
            )
        mlflow.log_params(parameters)
        log_dataset_inputs(
            mlflow,
            feature_dataset_inputs(
                training.input_features,
                source_root_uri=dataset_source_uri or artifact_root.resolve().as_uri(),
                feature_release_id=training.feature_release_id,
                feature_release_sha256=training.feature_release_sha256,
                expected_folds={"train", "validation"},
            ),
        )
        metrics: dict[str, float] = {
            "validation_binary_logloss": training.early_stopping.best_score,
            "best_iteration": float(training.early_stopping.best_iteration),
            "raw_brier_score": calibration.raw_metrics.brier_score,
            "raw_expected_calibration_error": calibration.raw_metrics.expected_calibration_error,
            "calibrated_brier_score": calibration.calibrated_metrics.brier_score,
            "calibrated_expected_calibration_error": calibration.calibrated_metrics.expected_calibration_error,
            "mlflow_dataset_input_count": float(len(training.input_features)),
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
        metrics.update(cloud_metrics)
        validation_metrics = json.loads(validation_metrics_path.read_text(encoding="utf-8"))
        for family, evidence in validation_metrics.get("challenge_cases", {}).items():
            recall = evidence.get("recall_by_operating_mode", {}).get("balanced")
            if isinstance(recall, (int, float)) and not isinstance(recall, bool):
                metrics[f"balanced_family_recall.{family}"] = float(recall)
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
    c4_evaluation_inputs: C4EvaluationInputs | None = None,
    tracking_uri: str | None = None,
    dataset_source_uri: str | None = None,
    cloud_metadata: dict[str, str | int | float] | None = None,
) -> str:
    """Index an already-verified frozen-test release in MLflow."""

    verify_complete_lightgbm_v1_release(
        artifact_root,
        training=training,
        calibration=calibration,
        bundle=bundle,
        predictions=predictions,
    )
    if bundle_path.read_bytes() != bundle.canonical_bytes():
        raise ValueError("MLflow model bundle path is not its canonical governed manifest")
    _require_artifact_root_file(checksum_path, artifact_root)
    if prediction_manifest_path.read_bytes() != predictions.canonical_bytes():
        raise ValueError("MLflow prediction manifest path is not canonical governed content")
    with _verified_benchmark_snapshot(
        benchmark_results_path, artifact_root=artifact_root,
        predictions=predictions, c4_inputs=c4_evaluation_inputs,
    ) as (benchmark_metrics, benchmark_tags, benchmark_snapshot):
        mlflow = _mlflow(tracking_uri)
        mlflow.set_experiment(EVALUATION_EXPERIMENT)
        with mlflow.start_run(run_name=predictions.prediction_run_id) as run:
            tags = _binding_tags(training, governance_state="release_verified")
            tags.update(benchmark_tags)
            tags.update(
                {
                    "calibration_id": calibration.calibration_id,
                    "prediction_run_id": predictions.prediction_run_id,
                    "model_bundle_hash": bundle.manifest_hash(),
                    "operating_mode": predictions.operating_mode,
                    "test_accessed": "true",
                }
            )
            cloud_tags, cloud_metrics = _validated_cloud_metadata(cloud_metadata)
            tags.update(cloud_tags)
            mlflow.set_tags(tags)
            log_dataset_inputs(
                mlflow,
                feature_dataset_inputs(
                    predictions.input_features,
                    source_root_uri=dataset_source_uri or artifact_root.resolve().as_uri(),
                    feature_release_id=training.feature_release_id,
                    feature_release_sha256=training.feature_release_sha256,
                    expected_folds={"test"},
                ),
            )
            mlflow.log_metrics(
                {
                    "test_alert_count": float(predictions.alert_count),
                    "test_row_count": float(predictions.row_count),
                    "frozen_threshold": predictions.threshold,
                    **cloud_metrics,
                }
            )
            if benchmark_metrics:
                mlflow.log_metrics(benchmark_metrics)
            for path in (bundle_path, checksum_path, prediction_manifest_path):
                mlflow.log_artifact(str(path), artifact_path="governed")
            if benchmark_snapshot is not None:
                mlflow.log_artifact(str(benchmark_snapshot), artifact_path="governed-evaluation")
            return str(run.info.run_id)


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("benchmark JSON contains duplicate keys")
        result[key] = value
    return result


def _has_c4_claims(value: Any) -> bool:
    """Do not let a schema downgrade/wrapper launder C4 evidence as legacy JSON."""
    if isinstance(value, dict):
        reserved = {"same_observations_verified", "evaluation_profile_sha256", "candidate_sha256",
                    "seven_date_benchmark_compliance"}
        return any(
            key in reserved or key.startswith(("c4.", "lightgbm.", "rules.", "delta.lightgbm_minus_rules."))
            or _has_c4_claims(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return any(_has_c4_claims(item) for item in value)
    return isinstance(value, str) and value.startswith(("g8_c4_", "c4.test."))


@contextmanager
def _verified_benchmark_snapshot(
    path: Path | None, *, artifact_root: Path, predictions: DetectorPredictionsManifest,
    c4_inputs: C4EvaluationInputs | None,
):
    if path is None:
        if c4_inputs is not None:
            raise ValueError("C4 evidence inputs require a benchmark report")
        yield {}, {}, None
        return
    _require_artifact_root_file(path, artifact_root)
    content = path.read_bytes()
    payload = json.loads(content, object_pairs_hook=_reject_duplicate_keys)
    if not isinstance(payload, dict):
        raise ValueError("governed benchmark report must be an object")
    is_c4 = payload.get("schema_version") == "g8_c4_observation_metrics_v1"
    if is_c4:
        if c4_inputs is None:
            raise ValueError("C4 report requires original evaluation evidence inputs")
        # Lazy import avoids the cloud_runner -> tracking -> evaluator cycle.
        from app.market_data.projections import FrozenPublicSampleRoot
        from app.ml.lightgbm.c4_evaluation import C4EvaluationProfile
        from app.ml.lightgbm.c4_replay_evidence import evaluate_c4_release

        expected = evaluate_c4_release(
            profile=C4EvaluationProfile.model_validate_json(c4_inputs.profile.read_bytes()),
            root=FrozenPublicSampleRoot.model_validate_json(c4_inputs.frozen_root.read_bytes()),
            projection_path=c4_inputs.projection, comparison_path=c4_inputs.comparison,
            candidate_path=c4_inputs.candidate, artifact_root=artifact_root, predictions=predictions,
        )
        source_fields = {"source_result_inventory_sha256", "source_request_sha256", "source_mlflow_run_id"}
        if source_fields & payload.keys():
            from app.ml.lightgbm.cloud_runner import verify_wave1_result
            from app.ml.lightgbm.artifacts import sha256_file

            source_root = c4_inputs.source_result or artifact_root.parent
            source_run = verify_wave1_result(source_root)
            if source_run.mode != "final-evaluation" or source_run.candidate_hash != expected["candidate_sha256"]:
                raise ValueError("C4 report source result differs from the evaluated candidate")
            source_predictions = DetectorPredictionsManifest.model_validate_json(
                (source_root / "artifacts/prediction/prediction-manifest.json").read_bytes()
            )
            if source_predictions.manifest_hash() != predictions.manifest_hash():
                raise ValueError("C4 report source result differs from the evaluated predictions")
            expected.update(
                source_result_inventory_sha256=sha256_file(source_root / "SUCCESS"),
                source_request_sha256=source_run.request_sha256,
                source_mlflow_run_id=source_run.mlflow_run_id,
            )
        def canonical(value):
            return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        if hashlib.sha256(canonical(payload)).digest() != hashlib.sha256(canonical(expected)).digest():
            raise ValueError("C4 report differs from verified evaluator output and candidate/profile evidence")
    elif c4_inputs is not None or _has_c4_claims(payload):
        raise ValueError("C4 evidence claims require the canonical C4 report schema and evaluation inputs")
    # Never reread the caller's mutable file for metrics, tags or artifact upload.
    with tempfile.TemporaryDirectory(prefix="mlflow-benchmark-") as temporary:
        snapshot = Path(temporary) / path.name
        snapshot.write_bytes(content)
        metrics = _benchmark_metrics(snapshot)
        tags = _c4_benchmark_tags(snapshot, predictions)
        if is_c4:
            tags["c4_evaluation_report_sha256"] = hashlib.sha256(content).hexdigest()
        yield metrics, tags, snapshot


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
    if payload.get("schema_version") == "g8_c4_observation_metrics_v1":
        from app.ml.lightgbm.c4_evaluation import C4_METRIC_NAMES

        metrics = payload.get("metrics")
        if not isinstance(metrics, dict) or set(metrics) != C4_METRIC_NAMES:
            raise ValueError("C4 benchmark must contain the exact observation metric inventory")
        result = {}
        for name, value in metrics.items():
            if value is None:
                continue  # Undefined precision/recall is never silently changed to zero.
            if type(value) not in (float, int) or not math.isfinite(value):
                raise ValueError("C4 benchmark metrics must be finite numbers or null")
            result[f"c4.test.{name}"] = float(value)
        return result
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


def _c4_benchmark_tags(path: Path, predictions: DetectorPredictionsManifest) -> dict[str, str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "g8_c4_observation_metrics_v1":
        return {}
    if (
        payload.get("same_observations_verified") is not True
        or payload.get("seven_date_benchmark_compliance") is not False
        or payload.get("observation_unit") != "supervised_projection_row"
        or payload.get("negative_label_source") != "research_control_assumption"
        or payload.get("prediction_manifest_sha256") != predictions.manifest_hash()
        or payload.get("model_binding") != predictions.binding.model_dump(mode="json")
        or payload.get("row_count") != predictions.row_count
        or payload.get("frozen_threshold") != predictions.threshold
    ):
        raise ValueError("C4 benchmark is not a verified comparison for this prediction release")
    for name in ("candidate_sha256", "evaluation_profile_sha256"):
        if not isinstance(payload.get(name), str) or re.fullmatch(r"[a-f0-9]{64}", payload[name]) is None:
            raise ValueError("C4 benchmark has no frozen candidate/profile identity")
    return {
        "evaluation_contract": "g8_c4_supervised_observations_v1",
        "evaluation_profile_sha256": payload["evaluation_profile_sha256"],
        "candidate_hash": payload["candidate_sha256"],
        "seven_date_benchmark_compliance": "false",
        "same_observations_verified": "true",
        "negative_label_source": "research_control_assumption",
    }


def _validated_cloud_metadata(
    values: dict[str, str | int | float] | None,
) -> tuple[dict[str, str], dict[str, float]]:
    if values is None:
        return {}, {}
    tag_names = {"cloud_provider", "cloud_region", "cloud_platform", "cloud_preset", "cloud_job_id", "image_digest"}
    metric_names = {
        "cloud_wall_seconds",
        "cloud_cpu_seconds",
        "cloud_peak_rss_bytes",
        "cloud_rows_per_second",
        "cloud_estimated_cost_usd",
    }
    unknown = set(values) - tag_names - metric_names
    if unknown:
        raise ValueError(f"unsupported cloud MLflow metadata: {', '.join(sorted(unknown))}")
    tags = {name: str(values[name]) for name in tag_names & values.keys()}
    metrics = {name: float(values[name]) for name in metric_names & values.keys()}
    return tags, metrics
