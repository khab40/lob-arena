import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ml.lightgbm.contracts import (
    ArtifactDigest,
    CalibrationManifest,
    CalibrationMetrics,
    CalibrationParameters,
    ClassWeightEvidence,
    DetectorPredictionsManifest,
    EarlyStoppingEvidence,
    FoldFeatureInput,
    GovernedModelBinding,
    LightGbmTrainingRun,
    LightGbmV1Hyperparameters,
    ModelBundleManifest,
    OperatingPoint,
    OperatingPointConstraints,
    OperatingPointMetrics,
    PreprocessingEvidence,
    validate_phase_zero_compatibility,
)
from app.ml.lightgbm.release import verify_phase_zero_release
from scripts.generate_governed_contracts import CONTRACTS, render_contract


ROOT = Path(__file__).resolve().parents[2]
HASH_A = "a" * 64
HASH_B = "b" * 64
CREATED_AT = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)


def _artifact(
    logical_name: str,
    *,
    uri: str | None = None,
    sha256: str = HASH_A,
    size_bytes: int = 128,
    schema_version: str | None = None,
) -> ArtifactDigest:
    return ArtifactDigest(
        logical_name=logical_name,
        uri=uri or f"artifacts/{logical_name}.json",
        sha256=sha256,
        size_bytes=size_bytes,
        schema_version=schema_version or f"{logical_name}_v1",
    )


def _manifest_artifact(logical_name: str, manifest: object) -> ArtifactDigest:
    content = manifest.canonical_bytes()
    return _artifact(
        logical_name,
        uri=f"artifacts/{logical_name}.json",
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        schema_version=manifest.schema_version,
    )


def _fold_input(
    fold: str,
    *,
    artifact: ArtifactDigest | None = None,
    row_count: int = 100,
) -> FoldFeatureInput:
    return FoldFeatureInput(
        fold=fold,
        artifact=artifact
        or _artifact(
            f"{fold}_features",
            schema_version="lob_features_v1",
        ),
        fold_membership_hash=HASH_A,
        session_count=3,
        row_count=row_count,
    )


def _binding(**overrides: str) -> GovernedModelBinding:
    payload = {
        "model_id": "lightgbm-attack-active-v1",
        "training_run_id": "training-run-001",
        "protocol_id": "governed-benchmark-v1",
        "protocol_hash": HASH_A,
        "corpus_id": "corpus-release-001",
        "corpus_hash": HASH_A,
        "split_id": "chronological-split-001",
        "assignment_hash": HASH_A,
        "feature_schema_version": "lob_features_v1",
        "feature_config_hash": HASH_A,
    }
    payload.update(overrides)
    return GovernedModelBinding.model_validate(payload)


def _training(
    binding: GovernedModelBinding | None = None,
    *,
    input_features: tuple[FoldFeatureInput, ...] | None = None,
    model_artifact: ArtifactDigest | None = None,
) -> LightGbmTrainingRun:
    return LightGbmTrainingRun(
        binding=binding or _binding(),
        feature_release_id="governed-feature-release-001",
        feature_release_sha256=HASH_A,
        model_artifact=model_artifact
        or _artifact(
            "model",
            uri="artifacts/model.txt",
            schema_version="lightgbm_text_v1",
        ),
        git_commit="c" * 40,
        created_at=CREATED_AT,
        training_seed=42,
        ordered_feature_columns=("spread_ticks", "depth_imbalance"),
        input_features=input_features or (_fold_input("train"), _fold_input("validation")),
        hyperparameters=LightGbmV1Hyperparameters(),
        class_weights=ClassWeightEvidence(
            negative_count=80,
            positive_count=20,
            negative_weight=0.625,
            positive_weight=2.5,
        ),
        preprocessing=PreprocessingEvidence(mode="none"),
        early_stopping=EarlyStoppingEvidence(
            stopping_rounds=30,
            best_iteration=120,
            best_score=0.18,
        ),
    )


def _operating_points() -> tuple[OperatingPoint, ...]:
    return (
        OperatingPoint(
            mode="high_precision",
            threshold=0.91,
            selection_policy="maximize_recall_at_precision_floor",
            validation_metrics=OperatingPointMetrics(
                precision=0.99,
                recall=0.52,
                f1=0.68,
            ),
            metric_constraints=OperatingPointConstraints(precision_floor=0.99),
        ),
        OperatingPoint(
            mode="balanced",
            threshold=0.63,
            selection_policy="maximize_f1",
            validation_metrics=OperatingPointMetrics(
                precision=0.85,
                recall=0.82,
                f1=0.83,
            ),
        ),
        OperatingPoint(
            mode="high_recall",
            threshold=0.27,
            selection_policy="maximize_precision_at_recall_floor",
            validation_metrics=OperatingPointMetrics(
                precision=0.61,
                recall=0.95,
                f1=0.74,
                false_alerts_per_million_events=2.4,
            ),
            metric_constraints=OperatingPointConstraints(recall_floor=0.95),
        ),
    )


def _calibration(
    binding: GovernedModelBinding | None = None,
    *,
    input_predictions: ArtifactDigest | None = None,
) -> CalibrationManifest:
    return CalibrationManifest(
        calibration_id="calibration-001",
        binding=binding or _binding(),
        created_at=CREATED_AT,
        input_predictions=input_predictions
        or _artifact(
            "validation_predictions",
            schema_version="detector_predictions_rows_v1",
        ),
        session_count=9,
        row_count=1_000,
        parameters=CalibrationParameters(
            method="platt",
            platt_slope=1.2,
            platt_intercept=-0.1,
        ),
        raw_metrics=CalibrationMetrics(
            brier_score=0.12,
            expected_calibration_error=0.08,
        ),
        calibrated_metrics=CalibrationMetrics(
            brier_score=0.09,
            expected_calibration_error=0.03,
        ),
        operating_points=_operating_points(),
    )


def _predictions(
    binding: GovernedModelBinding | None = None,
    *,
    input_features: tuple[FoldFeatureInput, ...] | None = None,
    predictions: ArtifactDigest | None = None,
    threshold: float = 0.63,
) -> DetectorPredictionsManifest:
    return DetectorPredictionsManifest(
        prediction_run_id="prediction-run-001",
        binding=binding or _binding(),
        calibration_id="calibration-001",
        created_at=CREATED_AT,
        fold="test",
        operating_mode="balanced",
        threshold=threshold,
        input_features=input_features or (_fold_input("test", row_count=200),),
        predictions=predictions
        or _artifact(
            "predictions",
            uri="artifacts/predictions.parquet",
            schema_version="detector_predictions_rows_v1",
        ),
        row_count=200,
        alert_count=17,
    )


def _bundle(
    *,
    training: LightGbmTrainingRun | None = None,
    calibration: CalibrationManifest | None = None,
    predictions: DetectorPredictionsManifest | None = None,
) -> ModelBundleManifest:
    training = training or _training()
    calibration = calibration or _calibration()
    predictions = predictions or _predictions()
    return ModelBundleManifest(
        binding=training.binding,
        calibration_id=calibration.calibration_id,
        created_at=CREATED_AT,
        artifacts=(
            training.model_artifact,
            _manifest_artifact("training_manifest", training),
            _manifest_artifact("calibration_manifest", calibration),
            _manifest_artifact("prediction_manifest", predictions),
            predictions.predictions,
            _artifact("feature_schema", schema_version="lob_features_v1"),
            _artifact("validation_metrics"),
            _artifact("feature_importance"),
            _artifact(
                "checksums",
                uri="artifacts/checksums.sha256",
                schema_version="sha256_inventory_v1",
            ),
        ),
    )


def _write_artifact(
    root: Path,
    logical_name: str,
    uri: str,
    content: bytes,
    schema_version: str,
) -> ArtifactDigest:
    path = root / uri
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return _artifact(
        logical_name,
        uri=uri,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        schema_version=schema_version,
    )


def _release_fixture(
    root: Path,
    *,
    incomplete_checksum_inventory: bool = False,
) -> tuple[
    LightGbmTrainingRun,
    CalibrationManifest,
    ModelBundleManifest,
    DetectorPredictionsManifest,
]:
    train_features = _write_artifact(
        root,
        "train_features",
        "inputs/train.parquet",
        b"train-features",
        "lob_features_v1",
    )
    validation_features = _write_artifact(
        root,
        "validation_features",
        "inputs/validation.parquet",
        b"validation-features",
        "lob_features_v1",
    )
    model_artifact = _write_artifact(
        root,
        "model",
        "artifacts/model.txt",
        b"lightgbm-model",
        "lightgbm_text_v1",
    )
    training = _training(
        input_features=(
            _fold_input("train", artifact=train_features),
            _fold_input("validation", artifact=validation_features),
        ),
        model_artifact=model_artifact,
    )
    validation_predictions = _write_artifact(
        root,
        "validation_predictions",
        "inputs/validation-predictions.parquet",
        b"validation-predictions",
        "detector_predictions_rows_v1",
    )
    calibration = _calibration(input_predictions=validation_predictions)
    test_features = _write_artifact(
        root,
        "test_features",
        "inputs/test.parquet",
        b"test-features",
        "lob_features_v1",
    )
    prediction_rows = _write_artifact(
        root,
        "predictions",
        "artifacts/predictions.parquet",
        b"test-predictions",
        "detector_predictions_rows_v1",
    )
    predictions = _predictions(
        input_features=(_fold_input("test", artifact=test_features, row_count=200),),
        predictions=prediction_rows,
    )
    artifacts = [
        model_artifact,
        _write_artifact(
            root,
            "training_manifest",
            "artifacts/training-manifest.json",
            training.canonical_bytes(),
            training.schema_version,
        ),
        _write_artifact(
            root,
            "calibration_manifest",
            "artifacts/calibration-manifest.json",
            calibration.canonical_bytes(),
            calibration.schema_version,
        ),
        _write_artifact(
            root,
            "prediction_manifest",
            "artifacts/prediction-manifest.json",
            predictions.canonical_bytes(),
            predictions.schema_version,
        ),
        prediction_rows,
        _write_artifact(
            root,
            "feature_schema",
            "artifacts/feature-schema.json",
            b"feature-schema",
            "lob_features_v1",
        ),
        _write_artifact(
            root,
            "validation_metrics",
            "artifacts/validation-metrics.json",
            b"validation-metrics",
            "governed_benchmark_results_v2",
        ),
        _write_artifact(
            root,
            "feature_importance",
            "artifacts/feature-importance.json",
            b"feature-importance",
            "lightgbm_feature_importance_v1",
        ),
    ]
    checksum_entries = artifacts[:-1] if incomplete_checksum_inventory else artifacts
    checksum_content = "".join(
        f"{artifact.sha256}  {artifact.uri}\n" for artifact in sorted(checksum_entries, key=lambda item: item.uri)
    ).encode()
    artifacts.append(
        _write_artifact(
            root,
            "checksums",
            "artifacts/checksums.sha256",
            checksum_content,
            "sha256_inventory_v1",
        )
    )
    bundle = ModelBundleManifest(
        binding=training.binding,
        calibration_id=calibration.calibration_id,
        created_at=CREATED_AT,
        artifacts=tuple(artifacts),
    )
    return training, calibration, bundle, predictions


def test_phase_zero_manifests_bind_the_same_governed_identity() -> None:
    training = _training()
    calibration = _calibration()
    predictions = _predictions()
    bundle = _bundle(training=training, calibration=calibration, predictions=predictions)

    validate_phase_zero_compatibility(
        training=training,
        calibration=calibration,
        bundle=bundle,
        predictions=predictions,
    )

    for manifest in (training, calibration, bundle, predictions):
        assert len(manifest.manifest_hash()) == 64
        assert (
            manifest.manifest_hash() == type(manifest).model_validate(manifest.model_dump(mode="json")).manifest_hash()
        )


def test_phase_zero_manifests_and_nested_values_are_immutable() -> None:
    training = _training()
    predictions = _predictions()

    with pytest.raises(ValidationError, match="frozen"):
        training.data_policy.test_fold_accessed = True
    with pytest.raises(ValidationError, match="frozen"):
        predictions.threshold = 0.64
    with pytest.raises(AttributeError):
        training.input_features.append(_fold_input("test"))


def test_training_contract_fails_closed_on_leakage_and_contradictory_configuration() -> None:
    payload = _training().model_dump(mode="json")
    payload["data_policy"]["test_fold_accessed"] = True
    with pytest.raises(ValidationError, match="False"):
        LightGbmTrainingRun.model_validate(payload)

    payload = _training().model_dump(mode="json")
    payload["ordered_feature_columns"] = ["spread_ticks", "spread_ticks"]
    with pytest.raises(ValidationError, match="must be unique"):
        LightGbmTrainingRun.model_validate(payload)

    payload = _training().model_dump(mode="json")
    payload["input_features"][1]["fold"] = "test"
    with pytest.raises(ValidationError, match="train and validation folds only"):
        LightGbmTrainingRun.model_validate(payload)

    payload = _training().model_dump(mode="json")
    payload["hyperparameters"]["objective"] = "multiclass"
    with pytest.raises(ValidationError, match="binary"):
        LightGbmTrainingRun.model_validate(payload)

    payload = _training().model_dump(mode="json")
    payload["hyperparameters"]["learning_rate"] = float("nan")
    with pytest.raises(ValidationError, match="finite number"):
        LightGbmTrainingRun.model_validate(payload)

    payload = _training().model_dump(mode="json")
    payload["class_weights"]["positive_weight"] = 1.0
    with pytest.raises(ValidationError, match="derived from training-fold class counts"):
        LightGbmTrainingRun.model_validate(payload)

    payload = _training().model_dump(mode="json")
    payload["input_features"][0]["row_count"] = 101
    with pytest.raises(ValidationError, match="class counts must equal"):
        LightGbmTrainingRun.model_validate(payload)

    payload = _training().model_dump(mode="json")
    payload["input_features"][0]["artifact"]["schema_version"] = "lob_features_v2"
    with pytest.raises(ValidationError, match="bound feature schema"):
        LightGbmTrainingRun.model_validate(payload)

    payload = _training().model_dump(mode="json")
    payload["model_artifact"]["schema_version"] = "pickle_v1"
    with pytest.raises(ValidationError, match="governed LightGBM text format"):
        LightGbmTrainingRun.model_validate(payload)

    payload = _training().model_dump(mode="json")
    payload["feature_release_sha256"] = "not-a-sha256"
    with pytest.raises(ValidationError, match="String should match pattern"):
        LightGbmTrainingRun.model_validate(payload)


def test_calibration_requires_fitted_parameters_and_all_operating_modes() -> None:
    with pytest.raises(ValidationError, match="requires slope and intercept"):
        CalibrationParameters(method="platt")

    with pytest.raises(ValidationError, match="strictly increasing"):
        CalibrationParameters(
            method="isotonic",
            isotonic_x=(0.1, 0.1),
            isotonic_y=(0.2, 0.3),
        )

    payload = _calibration().model_dump(mode="json")
    payload["operating_points"][2] = payload["operating_points"][1]
    with pytest.raises(ValidationError, match="exactly one operating point"):
        CalibrationManifest.model_validate(payload)

    payload = _calibration().model_dump(mode="json")
    payload["test_fold_accessed"] = True
    with pytest.raises(ValidationError, match="False"):
        CalibrationManifest.model_validate(payload)


def test_operating_modes_require_measured_mode_specific_constraints() -> None:
    with pytest.raises(ValidationError, match="precision floor"):
        OperatingPoint(
            mode="high_precision",
            threshold=0.1,
            selection_policy="maximize_f1",
            validation_metrics=OperatingPointMetrics(
                precision=0.5,
                recall=0.9,
                f1=0.64,
            ),
        )

    with pytest.raises(ValidationError, match="violates its recall floor"):
        OperatingPoint(
            mode="high_recall",
            threshold=0.5,
            selection_policy="maximize_precision_at_recall_floor",
            validation_metrics=OperatingPointMetrics(
                precision=0.9,
                recall=0.8,
                f1=0.85,
            ),
            metric_constraints=OperatingPointConstraints(recall_floor=0.95),
        )


def test_model_bundle_requires_checksums_unique_paths_and_bound_manifests() -> None:
    training = _training()
    calibration = _calibration()
    predictions = _predictions()
    bundle = _bundle(training=training, calibration=calibration, predictions=predictions)
    payload = bundle.model_dump(mode="json")
    payload["artifacts"] = [artifact for artifact in payload["artifacts"] if artifact["logical_name"] != "checksums"]
    with pytest.raises(ValidationError, match="missing required artifacts: checksums"):
        ModelBundleManifest.model_validate(payload)

    payload = bundle.model_dump(mode="json")
    payload["artifacts"][1]["uri"] = payload["artifacts"][0]["uri"]
    with pytest.raises(ValidationError, match="URIs must be unique"):
        ModelBundleManifest.model_validate(payload)

    payload = bundle.model_dump(mode="json")
    next(item for item in payload["artifacts"] if item["logical_name"] == "training_manifest")["sha256"] = HASH_B
    changed_bundle = ModelBundleManifest.model_validate(payload)
    with pytest.raises(ValueError, match="training manifest digest"):
        validate_phase_zero_compatibility(
            training=training,
            calibration=calibration,
            bundle=changed_bundle,
            predictions=predictions,
        )

    payload = bundle.model_dump(mode="json")
    next(item for item in payload["artifacts"] if item["logical_name"] == "model")["sha256"] = HASH_B
    changed_bundle = ModelBundleManifest.model_validate(payload)
    with pytest.raises(ValueError, match="does not match the training run"):
        validate_phase_zero_compatibility(
            training=training,
            calibration=calibration,
            bundle=changed_bundle,
            predictions=predictions,
        )


def test_release_compatibility_rejects_binding_or_threshold_drift() -> None:
    training = _training()
    calibration = _calibration()
    predictions = _predictions(_binding(corpus_hash=HASH_B))
    bundle = _bundle(training=training, calibration=calibration, predictions=_predictions())
    with pytest.raises(ValueError, match="predictions binding"):
        validate_phase_zero_compatibility(
            training=training,
            calibration=calibration,
            bundle=bundle,
            predictions=predictions,
        )

    predictions = _predictions(threshold=0.64)
    bundle = _bundle(training=training, calibration=calibration, predictions=predictions)
    with pytest.raises(ValueError, match="frozen calibration operating point"):
        validate_phase_zero_compatibility(
            training=training,
            calibration=calibration,
            bundle=bundle,
            predictions=predictions,
        )


def test_prediction_manifest_rejects_impossible_counts_and_fold_mismatch() -> None:
    payload = _predictions().model_dump(mode="json")
    payload["alert_count"] = payload["row_count"] + 1
    with pytest.raises(ValidationError, match="cannot exceed"):
        DetectorPredictionsManifest.model_validate(payload)

    payload = _predictions().model_dump(mode="json")
    payload["input_features"][0]["fold"] = "validation"
    with pytest.raises(ValidationError, match="must match the declared fold"):
        DetectorPredictionsManifest.model_validate(payload)


def test_release_verifier_checks_bytes_manifests_and_checksum_inventory(tmp_path: Path) -> None:
    training, calibration, bundle, predictions = _release_fixture(tmp_path)
    verify_phase_zero_release(
        tmp_path,
        training=training,
        calibration=calibration,
        bundle=bundle,
        predictions=predictions,
    )

    (tmp_path / bundle.artifact_map()["model"].uri).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="failed integrity validation: model"):
        verify_phase_zero_release(
            tmp_path,
            training=training,
            calibration=calibration,
            bundle=bundle,
            predictions=predictions,
        )


def test_release_verifier_rejects_incomplete_checksum_inventory(tmp_path: Path) -> None:
    training, calibration, bundle, predictions = _release_fixture(
        tmp_path,
        incomplete_checksum_inventory=True,
    )
    with pytest.raises(ValueError, match="checksum inventory does not match"):
        verify_phase_zero_release(
            tmp_path,
            training=training,
            calibration=calibration,
            bundle=bundle,
            predictions=predictions,
        )


def test_artifact_references_reject_unsafe_paths() -> None:
    for uri in ("../model.txt", "/tmp/model.txt", "artifacts\\model.txt"):
        with pytest.raises(ValidationError, match="normalized relative POSIX path"):
            _artifact("model", uri=uri)


def test_checked_in_phase_zero_schemas_match_runtime_contracts() -> None:
    filenames = {
        "lightgbm-training-run-v1.schema.json",
        "lightgbm-model-bundle-v1.schema.json",
        "model-calibration-v1.schema.json",
        "detector-predictions-v1.schema.json",
    }

    for filename in filenames:
        model, title = CONTRACTS[filename]
        rendered = render_contract(filename, model, title)
        assert (ROOT / "contracts" / filename).read_text(encoding="utf-8") == rendered
        schema = json.loads(rendered)
        assert schema["additionalProperties"] is False
        assert "binding" in schema["required"]
