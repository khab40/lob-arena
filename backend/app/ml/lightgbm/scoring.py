from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator, Literal

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from app.features.pipeline import FEATURE_COLUMNS
from app.ml.lightgbm.artifacts import (
    artifact_digest_for_destination,
    require_output_within_artifact_root,
    resolve_verified_artifact,
    write_canonical_json,
)
from app.ml.lightgbm.contracts import (
    ArtifactDigest,
    CalibrationManifest,
    CalibrationMetrics,
    CalibrationParameters,
    DetectorPredictionsManifest,
    FoldFeatureInput,
    GovernedModelBinding,
    LightGbmTrainingRun,
    OperatingMode,
    OperatingPoint,
    OperatingPointConstraints,
    OperatingPointMetrics,
    PREDICTION_ROWS_SCHEMA_VERSION,
)
from app.ml.lightgbm.data import (
    GovernedFeatureDataset,
    GovernedFeatureFold,
)


CALIBRATION_MANIFEST_FILE = "calibration-manifest.json"
VALIDATION_PREDICTIONS_FILE = "validation-predictions.parquet"
VALIDATION_METRICS_FILE = "validation-metrics.json"
FEATURE_IMPORTANCE_FILE = "feature-importance.json"
FEATURE_SCHEMA_FILE = "feature-schema.json"
RELIABILITY_BINS_FILE = "reliability-bins.json"
RELIABILITY_DIAGRAM_FILE = "reliability-diagram.svg"
PREDICTION_MANIFEST_FILE = "prediction-manifest.json"
PREDICTIONS_FILE = "predictions.parquet"
CONTRIBUTIONS_FILE = "feature-contributions.parquet"

VALIDATION_METRICS_SCHEMA_VERSION = "lightgbm_validation_metrics_v1"
FEATURE_IMPORTANCE_SCHEMA_VERSION = "lightgbm_feature_importance_v1"
FEATURE_SCHEMA_ARTIFACT_VERSION = "lightgbm_feature_schema_v1"
RELIABILITY_BINS_SCHEMA_VERSION = "reliability_bins_v1"
RELIABILITY_DIAGRAM_SCHEMA_VERSION = "reliability_diagram_svg_v1"
CONTRIBUTIONS_SCHEMA_VERSION = "lightgbm_feature_contributions_v1"
CHALLENGE_FAMILIES = ("liquidity_evaporation", "layering_like")


PREDICTION_ARROW_SCHEMA = pa.schema(
    [
        pa.field("prediction_row_id", pa.string(), nullable=False),
        pa.field("fold", pa.string(), nullable=False),
        pa.field("run_id", pa.string(), nullable=False),
        pa.field("base_session_id", pa.string(), nullable=False),
        pa.field("campaign_id", pa.string(), nullable=True),
        pa.field("instrument", pa.string(), nullable=False),
        pa.field("session_id", pa.string(), nullable=False),
        pa.field("source_type", pa.string(), nullable=False),
        pa.field("prediction_timestamp_ns", pa.int64(), nullable=False),
        pa.field("sequence", pa.int64(), nullable=False),
        pa.field("label", pa.int8(), nullable=False),
        pa.field("attack_family", pa.string(), nullable=True),
        pa.field("attack_phase", pa.string(), nullable=True),
        pa.field("raw_probability", pa.float64(), nullable=False),
        pa.field("calibrated_probability", pa.float64(), nullable=True),
        pa.field("threshold", pa.float64(), nullable=True),
        pa.field("alert", pa.bool_(), nullable=True),
    ],
    metadata={b"schema_version": PREDICTION_ROWS_SCHEMA_VERSION.encode("ascii")},
)

CONTRIBUTION_ARROW_SCHEMA = pa.schema(
    [
        pa.field("prediction_row_id", pa.string(), nullable=False),
        pa.field("base_session_id", pa.string(), nullable=False),
        pa.field("campaign_id", pa.string(), nullable=True),
        pa.field("prediction_timestamp_ns", pa.int64(), nullable=False),
        pa.field("feature", pa.string(), nullable=False),
        pa.field("contribution", pa.float64(), nullable=False),
        pa.field("direction", pa.string(), nullable=False),
        pa.field("absolute_rank", pa.int16(), nullable=False),
    ],
    metadata={b"schema_version": CONTRIBUTIONS_SCHEMA_VERSION.encode("ascii")},
)


@dataclass(frozen=True)
class CalibrationResult:
    output_dir: Path
    manifest_path: Path
    validation_predictions_path: Path
    validation_metrics_path: Path
    feature_importance_path: Path
    feature_schema_path: Path
    reliability_bins_path: Path
    reliability_diagram_path: Path
    manifest: CalibrationManifest
    manifest_artifact: ArtifactDigest
    validation_predictions_artifact: ArtifactDigest
    validation_metrics_artifact: ArtifactDigest
    feature_importance_artifact: ArtifactDigest
    feature_schema_artifact: ArtifactDigest
    reliability_bins_artifact: ArtifactDigest
    reliability_diagram_artifact: ArtifactDigest


@dataclass(frozen=True)
class PredictionResult:
    output_dir: Path
    manifest_path: Path
    predictions_path: Path
    contributions_path: Path
    manifest: DetectorPredictionsManifest
    manifest_artifact: ArtifactDigest
    predictions_artifact: ArtifactDigest
    contributions_artifact: ArtifactDigest


@dataclass(frozen=True)
class _ScoredBatch:
    shard_base_session_id: str
    shard_campaign_id: str | None
    batch: pa.RecordBatch
    raw_probabilities: np.ndarray
    contributions: np.ndarray


def calibrate_validation_predictions(
    dataset: GovernedFeatureDataset,
    *,
    training: LightGbmTrainingRun,
    artifact_root: Path,
    output_dir: Path,
    created_at: datetime,
    method: Literal["raw", "platt", "isotonic"] = "platt",
    precision_floor: float = 0.90,
    recall_floor: float = 0.90,
    ece_bins: int = 10,
    batch_size: int = 65_536,
) -> CalibrationResult:
    """Fit calibration and operating modes using validation rows only."""

    output_dir = output_dir.resolve()
    artifact_root = artifact_root.resolve()
    _validate_scoring_request(
        dataset,
        training=training,
        expected_access_mode="development",
        expected_fold="validation",
        artifact_root=artifact_root,
        output_dir=output_dir,
        created_at=created_at,
        batch_size=batch_size,
    )
    if method not in {"raw", "platt", "isotonic"}:
        raise ValueError("unsupported calibration method")
    if not 0.0 <= precision_floor <= 1.0 or not 0.0 <= recall_floor <= 1.0:
        raise ValueError("operating-point floors must be probabilities")
    if ece_bins < 2:
        raise ValueError("ECE requires at least two bins")

    booster, preprocessor = _load_model_and_preprocessor(training, artifact_root)
    fold = dataset.fold("validation")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        raw_path = staging / VALIDATION_PREDICTIONS_FILE
        writer = pq.ParquetWriter(raw_path, PREDICTION_ARROW_SCHEMA, compression="zstd")
        probability_chunks: list[np.ndarray] = []
        label_chunks: list[np.ndarray] = []
        family_mask_chunks: dict[str, list[np.ndarray]] = {
            family: [] for family in CHALLENGE_FAMILIES
        }
        contribution_totals = np.zeros(len(dataset.ordered_feature_columns), dtype=np.float64)
        observed_rows = 0
        try:
            for scored in _iter_scored_batches(
                fold,
                booster=booster,
                preprocessor=preprocessor,
                ordered_feature_columns=dataset.ordered_feature_columns,
                best_iteration=training.early_stopping.best_iteration,
                batch_size=batch_size,
            ):
                labels = _column_numpy(scored.batch, "label", dtype=np.int8)
                probability_chunks.append(scored.raw_probabilities)
                label_chunks.append(labels)
                family_column = scored.batch.column(
                    scored.batch.schema.get_field_index("attack_family")
                )
                for family in CHALLENGE_FAMILIES:
                    matches = pc.fill_null(pc.equal(family_column, family), False)
                    family_mask_chunks[family].append(
                        (labels == 1)
                        & np.asarray(
                            matches.to_numpy(zero_copy_only=False),
                            dtype=np.bool_,
                        )
                    )
                contribution_totals += np.abs(scored.contributions[:, :-1]).sum(axis=0)
                observed_rows += scored.batch.num_rows
                writer.write_table(
                    _prediction_table(
                        scored,
                        fold="validation",
                        calibrated=None,
                        threshold=None,
                    )
                )
        finally:
            writer.close()
        if observed_rows != fold.row_count:
            raise ValueError("validation prediction rows do not match the governed fold")
        validate_prediction_parquet(
            raw_path,
            expected_rows=fold.row_count,
            expected_fold="validation",
            require_decisions=False,
        )

        raw_probabilities = np.concatenate(probability_chunks)
        labels = np.concatenate(label_chunks)
        challenge_family_masks = {
            family: np.concatenate(chunks)
            for family, chunks in family_mask_chunks.items()
        }
        parameters = fit_calibration_parameters(method, raw_probabilities, labels)
        calibrated = apply_calibration(parameters, raw_probabilities)
        raw_metrics, raw_bins = calibration_metrics(labels, raw_probabilities, bins=ece_bins)
        calibrated_metrics, calibrated_bins = calibration_metrics(labels, calibrated, bins=ece_bins)
        operating_points = select_operating_points(
            labels,
            calibrated,
            precision_floor=precision_floor,
            recall_floor=recall_floor,
        )

        validation_predictions_artifact = artifact_digest_for_destination(
            raw_path,
            destination=output_dir / VALIDATION_PREDICTIONS_FILE,
            artifact_root=artifact_root,
            logical_name="validation_predictions",
            schema_version=PREDICTION_ROWS_SCHEMA_VERSION,
        )
        calibration_id = _calibration_id(
            training.binding,
            created_at=created_at,
            input_predictions=validation_predictions_artifact,
            parameters=parameters,
            operating_points=operating_points,
        )
        manifest = CalibrationManifest(
            calibration_id=calibration_id,
            binding=training.binding,
            created_at=created_at,
            input_predictions=validation_predictions_artifact,
            session_count=fold.session_count,
            row_count=fold.row_count,
            parameters=parameters,
            raw_metrics=raw_metrics,
            calibrated_metrics=calibrated_metrics,
            operating_points=operating_points,
        )

        metrics_payload = {
            "schema_version": VALIDATION_METRICS_SCHEMA_VERSION,
            "calibration_id": calibration_id,
            "binding": training.binding.model_dump(mode="json"),
            "row_count": fold.row_count,
            "negative_count": int(np.count_nonzero(labels == 0)),
            "positive_count": int(np.count_nonzero(labels == 1)),
            "raw_metrics": raw_metrics.model_dump(mode="json"),
            "calibrated_metrics": calibrated_metrics.model_dump(mode="json"),
            "operating_points": [point.model_dump(mode="json") for point in operating_points],
            "challenge_cases": _challenge_case_metrics(
                calibrated,
                challenge_family_masks,
                operating_points,
            ),
        }
        importance_payload = {
            "schema_version": FEATURE_IMPORTANCE_SCHEMA_VERSION,
            "binding": training.binding.model_dump(mode="json"),
            "validation_row_count": fold.row_count,
            "features": [
                {
                    "name": name,
                    "gain": float(gain),
                    "split_count": int(split),
                    "mean_absolute_contribution": float(contribution_totals[index] / fold.row_count),
                }
                for index, (name, gain, split) in enumerate(
                    zip(
                        dataset.ordered_feature_columns,
                        booster.feature_importance(importance_type="gain"),
                        booster.feature_importance(importance_type="split"),
                        strict=True,
                    )
                )
            ],
        }
        schema_payload = {
            "schema_version": FEATURE_SCHEMA_ARTIFACT_VERSION,
            "feature_schema_version": dataset.feature_schema_version,
            "feature_config_hash": dataset.feature_config_hash,
            "target": "attack_active",
            "numeric_storage_dtype": "float32",
            "ordered_features": [
                {"name": name, "dtype": "float32", "nullable": True}
                for name in dataset.ordered_feature_columns
            ],
        }
        bins_payload = {
            "schema_version": RELIABILITY_BINS_SCHEMA_VERSION,
            "calibration_id": calibration_id,
            "raw": raw_bins,
            "calibrated": calibrated_bins,
        }
        write_canonical_json(staging / VALIDATION_METRICS_FILE, metrics_payload)
        write_canonical_json(staging / FEATURE_IMPORTANCE_FILE, importance_payload)
        write_canonical_json(staging / FEATURE_SCHEMA_FILE, schema_payload)
        write_canonical_json(staging / RELIABILITY_BINS_FILE, bins_payload)
        (staging / RELIABILITY_DIAGRAM_FILE).write_text(
            _reliability_svg(raw_bins, calibrated_bins),
            encoding="utf-8",
        )
        write_canonical_json(staging / CALIBRATION_MANIFEST_FILE, manifest)

        artifacts = {
            "manifest_artifact": _staged_artifact(
                staging,
                output_dir,
                artifact_root,
                CALIBRATION_MANIFEST_FILE,
                "calibration_manifest",
                manifest.schema_version,
            ),
            "validation_metrics_artifact": _staged_artifact(
                staging,
                output_dir,
                artifact_root,
                VALIDATION_METRICS_FILE,
                "validation_metrics",
                VALIDATION_METRICS_SCHEMA_VERSION,
            ),
            "feature_importance_artifact": _staged_artifact(
                staging,
                output_dir,
                artifact_root,
                FEATURE_IMPORTANCE_FILE,
                "feature_importance",
                FEATURE_IMPORTANCE_SCHEMA_VERSION,
            ),
            "feature_schema_artifact": _staged_artifact(
                staging,
                output_dir,
                artifact_root,
                FEATURE_SCHEMA_FILE,
                "feature_schema",
                dataset.feature_schema_version,
            ),
            "reliability_bins_artifact": _staged_artifact(
                staging,
                output_dir,
                artifact_root,
                RELIABILITY_BINS_FILE,
                "reliability_bins",
                RELIABILITY_BINS_SCHEMA_VERSION,
            ),
            "reliability_diagram_artifact": _staged_artifact(
                staging,
                output_dir,
                artifact_root,
                RELIABILITY_DIAGRAM_FILE,
                "reliability_diagram",
                RELIABILITY_DIAGRAM_SCHEMA_VERSION,
            ),
        }
        if output_dir.exists():
            raise ValueError("calibration output directory was created concurrently")
        os.replace(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    return CalibrationResult(
        output_dir=output_dir,
        manifest_path=output_dir / CALIBRATION_MANIFEST_FILE,
        validation_predictions_path=output_dir / VALIDATION_PREDICTIONS_FILE,
        validation_metrics_path=output_dir / VALIDATION_METRICS_FILE,
        feature_importance_path=output_dir / FEATURE_IMPORTANCE_FILE,
        feature_schema_path=output_dir / FEATURE_SCHEMA_FILE,
        reliability_bins_path=output_dir / RELIABILITY_BINS_FILE,
        reliability_diagram_path=output_dir / RELIABILITY_DIAGRAM_FILE,
        manifest=manifest,
        validation_predictions_artifact=validation_predictions_artifact,
        **artifacts,
    )


def predict_governed_fold(
    dataset: GovernedFeatureDataset,
    *,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    artifact_root: Path,
    output_dir: Path,
    created_at: datetime,
    operating_mode: OperatingMode = "balanced",
    top_contributions: int = 5,
    batch_size: int = 65_536,
) -> PredictionResult:
    """Score the isolated frozen test fold with validation-frozen policy."""

    output_dir = output_dir.resolve()
    artifact_root = artifact_root.resolve()
    _validate_scoring_request(
        dataset,
        training=training,
        expected_access_mode="final_test",
        expected_fold="test",
        artifact_root=artifact_root,
        output_dir=output_dir,
        created_at=created_at,
        batch_size=batch_size,
    )
    if calibration.binding.identity_tuple() != training.binding.identity_tuple():
        raise ValueError("calibration binding does not match the training run")
    if not 1 <= top_contributions <= len(dataset.ordered_feature_columns):
        raise ValueError("top contribution count is outside the governed feature inventory")
    points = {point.mode: point for point in calibration.operating_points}
    point = points[operating_mode]
    booster, preprocessor = _load_model_and_preprocessor(training, artifact_root)
    fold = dataset.fold("test")
    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        predictions_path = staging / PREDICTIONS_FILE
        contributions_path = staging / CONTRIBUTIONS_FILE
        observed_rows = 0
        alert_count = 0
        with ExitStack() as writers:
            prediction_writer = writers.enter_context(
                pq.ParquetWriter(
                    predictions_path,
                    PREDICTION_ARROW_SCHEMA,
                    compression="zstd",
                )
            )
            contribution_writer = writers.enter_context(
                pq.ParquetWriter(
                    contributions_path,
                    CONTRIBUTION_ARROW_SCHEMA,
                    compression="zstd",
                )
            )
            for scored in _iter_scored_batches(
                fold,
                booster=booster,
                preprocessor=preprocessor,
                ordered_feature_columns=dataset.ordered_feature_columns,
                best_iteration=training.early_stopping.best_iteration,
                batch_size=batch_size,
            ):
                calibrated = apply_calibration(calibration.parameters, scored.raw_probabilities)
                alerts = calibrated >= point.threshold
                alert_count += int(np.count_nonzero(alerts))
                observed_rows += scored.batch.num_rows
                table = _prediction_table(
                    scored,
                    fold="test",
                    calibrated=calibrated,
                    threshold=point.threshold,
                )
                prediction_writer.write_table(table)
                contribution_table = _contribution_table(
                    table,
                    scored.contributions,
                    alerts=alerts,
                    feature_names=dataset.ordered_feature_columns,
                    top_count=top_contributions,
                )
                if contribution_table.num_rows:
                    contribution_writer.write_table(contribution_table)
        if observed_rows != fold.row_count:
            raise ValueError("test prediction rows do not match the governed fold")

        predictions_artifact = _staged_artifact(
            staging,
            output_dir,
            artifact_root,
            PREDICTIONS_FILE,
            "predictions",
            PREDICTION_ROWS_SCHEMA_VERSION,
        )
        contributions_artifact = _staged_artifact(
            staging,
            output_dir,
            artifact_root,
            CONTRIBUTIONS_FILE,
            "feature_contributions",
            CONTRIBUTIONS_SCHEMA_VERSION,
        )
        prediction_run_id = _prediction_run_id(
            training.binding,
            calibration_id=calibration.calibration_id,
            fold="test",
            operating_mode=operating_mode,
            threshold=point.threshold,
            predictions=predictions_artifact,
            created_at=created_at,
        )
        manifest = DetectorPredictionsManifest(
            prediction_run_id=prediction_run_id,
            binding=training.binding,
            calibration_id=calibration.calibration_id,
            created_at=created_at,
            fold="test",
            operating_mode=operating_mode,
            threshold=point.threshold,
            input_features=governed_fold_inputs(dataset, "test"),
            predictions=predictions_artifact,
            row_count=fold.row_count,
            alert_count=alert_count,
        )
        validate_prediction_parquet(
            predictions_path,
            manifest=manifest,
        )
        write_canonical_json(staging / PREDICTION_MANIFEST_FILE, manifest)
        manifest_artifact = _staged_artifact(
            staging,
            output_dir,
            artifact_root,
            PREDICTION_MANIFEST_FILE,
            "prediction_manifest",
            manifest.schema_version,
        )
        if output_dir.exists():
            raise ValueError("prediction output directory was created concurrently")
        os.replace(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return PredictionResult(
        output_dir=output_dir,
        manifest_path=output_dir / PREDICTION_MANIFEST_FILE,
        predictions_path=output_dir / PREDICTIONS_FILE,
        contributions_path=output_dir / CONTRIBUTIONS_FILE,
        manifest=manifest,
        manifest_artifact=manifest_artifact,
        predictions_artifact=predictions_artifact,
        contributions_artifact=contributions_artifact,
    )


def fit_calibration_parameters(
    method: Literal["raw", "platt", "isotonic"],
    raw_probabilities: np.ndarray,
    labels: np.ndarray,
) -> CalibrationParameters:
    probabilities, targets = _validate_probability_labels(raw_probabilities, labels)
    if method == "raw":
        return CalibrationParameters(method="raw")
    if method == "platt":
        from sklearn.linear_model import LogisticRegression

        logits = _logit(probabilities).reshape(-1, 1)
        model = LogisticRegression(
            C=1_000_000.0,
            solver="lbfgs",
            max_iter=1_000,
            random_state=0,
        )
        model.fit(logits, targets)
        return CalibrationParameters(
            method="platt",
            platt_slope=float(model.coef_[0, 0]),
            platt_intercept=float(model.intercept_[0]),
        )
    if method == "isotonic":
        from sklearn.isotonic import IsotonicRegression

        model = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
        model.fit(probabilities, targets)
        x = tuple(float(value) for value in model.X_thresholds_)
        y = tuple(float(value) for value in model.y_thresholds_)
        return CalibrationParameters(method="isotonic", isotonic_x=x, isotonic_y=y)
    raise ValueError("unsupported calibration method")


def apply_calibration(parameters: CalibrationParameters, raw_probabilities: np.ndarray) -> np.ndarray:
    probabilities = np.asarray(raw_probabilities, dtype=np.float64)
    if probabilities.ndim != 1 or not np.isfinite(probabilities).all() or np.any(
        (probabilities < 0.0) | (probabilities > 1.0)
    ):
        raise ValueError("raw probabilities must be a finite probability vector")
    if parameters.method == "raw":
        calibrated = probabilities.copy()
    elif parameters.method == "platt":
        assert parameters.platt_slope is not None
        assert parameters.platt_intercept is not None
        scores = parameters.platt_slope * _logit(probabilities) + parameters.platt_intercept
        calibrated = _sigmoid(scores)
    else:
        calibrated = np.interp(
            probabilities,
            np.asarray(parameters.isotonic_x, dtype=np.float64),
            np.asarray(parameters.isotonic_y, dtype=np.float64),
        )
    if not np.isfinite(calibrated).all():
        raise RuntimeError("calibration produced non-finite probabilities")
    return np.clip(calibrated, 0.0, 1.0)


def calibration_metrics(
    labels: np.ndarray,
    probabilities: np.ndarray,
    *,
    bins: int,
) -> tuple[CalibrationMetrics, list[dict[str, float | int]]]:
    probabilities, targets = _validate_probability_labels(probabilities, labels)
    brier = float(np.mean(np.square(probabilities - targets)))
    rows: list[dict[str, float | int]] = []
    ece = 0.0
    edges = np.linspace(0.0, 1.0, bins + 1)
    assignments = np.minimum(np.searchsorted(edges, probabilities, side="right") - 1, bins - 1)
    assignments = np.maximum(assignments, 0)
    for index in range(bins):
        mask = assignments == index
        count = int(np.count_nonzero(mask))
        mean_probability = float(np.mean(probabilities[mask])) if count else 0.0
        positive_rate = float(np.mean(targets[mask])) if count else 0.0
        ece += (count / targets.size) * abs(mean_probability - positive_rate)
        rows.append(
            {
                "index": index,
                "lower": float(edges[index]),
                "upper": float(edges[index + 1]),
                "count": count,
                "mean_probability": mean_probability,
                "positive_rate": positive_rate,
            }
        )
    return CalibrationMetrics(brier_score=brier, expected_calibration_error=float(ece)), rows


def select_operating_points(
    labels: np.ndarray,
    probabilities: np.ndarray,
    *,
    precision_floor: float,
    recall_floor: float,
) -> tuple[OperatingPoint, ...]:
    probabilities, targets = _validate_probability_labels(probabilities, labels)
    order = np.argsort(-probabilities, kind="stable")
    sorted_probabilities = probabilities[order]
    sorted_targets = targets[order]
    distinct_ends = np.flatnonzero(
        sorted_probabilities[:-1] != sorted_probabilities[1:]
    )
    cuts = np.append(distinct_ends, sorted_probabilities.size - 1)
    cumulative_true_positives = np.cumsum(
        sorted_targets == 1,
        dtype=np.int64,
    )[cuts]
    predicted_positives = cuts + 1
    total_positives = int(np.count_nonzero(targets == 1))
    candidates: list[tuple[float, OperatingPointMetrics]] = []
    for index, cut in enumerate(cuts):
        true_positive = int(cumulative_true_positives[index])
        false_positive = int(predicted_positives[index]) - true_positive
        false_negative = total_positives - true_positive
        precision = (
            true_positive / (true_positive + false_positive)
            if true_positive + false_positive
            else 0.0
        )
        recall = (
            true_positive / (true_positive + false_negative)
            if true_positive + false_negative
            else 0.0
        )
        f1 = (
            2 * precision * recall / (precision + recall)
            if precision + recall
            else 0.0
        )
        candidates.append(
            (
                float(sorted_probabilities[cut]),
                OperatingPointMetrics(
                    precision=precision,
                    recall=recall,
                    f1=f1,
                ),
            )
        )
    high_precision = [item for item in candidates if item[1].precision >= precision_floor]
    high_recall = [item for item in candidates if item[1].recall >= recall_floor]
    if not high_precision:
        raise ValueError("configured high-precision floor is unattainable on validation")
    if not high_recall:
        raise ValueError("configured high-recall floor is unattainable on validation")
    hp_threshold, hp_metrics = max(
        high_precision,
        key=lambda item: (item[1].recall, item[1].precision, item[1].f1, item[0]),
    )
    balanced_threshold, balanced_metrics = max(
        candidates,
        key=lambda item: (item[1].f1, item[1].precision, item[1].recall, item[0]),
    )
    hr_threshold, hr_metrics = max(
        high_recall,
        key=lambda item: (item[1].precision, item[1].recall, item[1].f1, item[0]),
    )
    return (
        OperatingPoint(
            mode="high_precision",
            threshold=hp_threshold,
            selection_policy="maximize_recall_at_precision_floor",
            validation_metrics=hp_metrics,
            metric_constraints=OperatingPointConstraints(precision_floor=precision_floor),
        ),
        OperatingPoint(
            mode="balanced",
            threshold=balanced_threshold,
            selection_policy="maximize_f1",
            validation_metrics=balanced_metrics,
        ),
        OperatingPoint(
            mode="high_recall",
            threshold=hr_threshold,
            selection_policy="maximize_precision_at_recall_floor",
            validation_metrics=hr_metrics,
            metric_constraints=OperatingPointConstraints(recall_floor=recall_floor),
        ),
    )


def governed_fold_inputs(dataset: GovernedFeatureDataset, fold_name: str) -> tuple[FoldFeatureInput, ...]:
    fold = dataset.fold(fold_name)  # type: ignore[arg-type]
    inputs: list[FoldFeatureInput] = []
    for shard in fold.shards:
        suffix = hashlib.sha256(shard.feature_uri.encode("utf-8")).hexdigest()[:24]
        inputs.append(
            FoldFeatureInput(
                fold=fold.fold,
                artifact=ArtifactDigest(
                    logical_name=f"features-{suffix}",
                    uri=shard.feature_uri,
                    sha256=shard.feature_sha256,
                    size_bytes=shard.feature_size_bytes,
                    schema_version=dataset.feature_schema_version,
                ),
                fold_membership_hash=fold.fold_membership_hash,
                session_count=1,
                row_count=shard.supervised_row_count,
            )
        )
    return tuple(inputs)


def validate_prediction_parquet(
    path: Path,
    *,
    expected_rows: int | None = None,
    expected_fold: str | None = None,
    require_decisions: bool | None = None,
    manifest: DetectorPredictionsManifest | None = None,
) -> None:
    """Validate governed prediction-row structure and frozen decision semantics."""

    parquet = pq.ParquetFile(path)
    if not parquet.schema_arrow.equals(PREDICTION_ARROW_SCHEMA, check_metadata=True):
        raise ValueError("detector prediction Parquet schema is incompatible")
    if manifest is not None:
        if expected_rows is not None and expected_rows != manifest.row_count:
            raise ValueError("prediction validation row-count expectations conflict")
        if expected_fold is not None and expected_fold != manifest.fold:
            raise ValueError("prediction validation fold expectations conflict")
        if require_decisions is False:
            raise ValueError("a prediction manifest requires frozen decision rows")
        expected_rows = manifest.row_count
        expected_fold = manifest.fold
        require_decisions = True
    if expected_rows is not None and parquet.metadata.num_rows != expected_rows:
        raise ValueError("detector prediction Parquet row count is incompatible")
    observed_rows, observed_alerts = _validate_prediction_rows(
        parquet,
        expected_fold=expected_fold,
        require_decisions=require_decisions,
        manifest=manifest,
    )
    if expected_rows is not None and observed_rows != expected_rows:
        raise ValueError("detector prediction Parquet row count is incompatible")
    if manifest is not None and observed_alerts != manifest.alert_count:
        raise ValueError("detector prediction alert count does not match its manifest")


def _validate_prediction_rows(
    parquet: pq.ParquetFile,
    *,
    expected_fold: str | None,
    require_decisions: bool | None,
    manifest: DetectorPredictionsManifest | None,
) -> tuple[int, int]:
    observed_rows = 0
    observed_alerts = 0
    with tempfile.TemporaryDirectory(prefix="lob-arena-prediction-validation-") as directory:
        database = sqlite3.connect(Path(directory) / "prediction-ids.sqlite3")
        try:
            database.execute("PRAGMA journal_mode=OFF")
            database.execute("PRAGMA synchronous=OFF")
            database.execute("PRAGMA temp_store=FILE")
            database.execute("CREATE TABLE prediction_ids (id TEXT PRIMARY KEY) WITHOUT ROWID")
            for batch in parquet.iter_batches(
                batch_size=65_536,
                columns=[
                    "prediction_row_id",
                    "fold",
                    "label",
                    "raw_probability",
                    "calibrated_probability",
                    "threshold",
                    "alert",
                ],
            ):
                observed_rows += batch.num_rows
                ids = [str(value) for value in _column_pylist(batch, "prediction_row_id")]
                if any(not value for value in ids):
                    raise ValueError("detector prediction row IDs must be non-empty and unique")
                try:
                    database.executemany(
                        "INSERT INTO prediction_ids VALUES (?)",
                        ((value,) for value in ids),
                    )
                except sqlite3.IntegrityError as exception:
                    raise ValueError(
                        "detector prediction row IDs must be non-empty and unique"
                    ) from exception
                folds = _column_pylist(batch, "fold")
                if expected_fold is not None and any(value != expected_fold for value in folds):
                    raise ValueError("detector prediction rows do not match the governed fold")
                labels = _column_numpy(batch, "label", dtype=np.int8)
                raw = _column_numpy(batch, "raw_probability", dtype=np.float64)
                if not np.isin(labels, (0, 1)).all() or not _is_probability_vector(raw):
                    raise ValueError("detector prediction labels or raw probabilities are invalid")

                calibrated_values = _column_pylist(batch, "calibrated_probability")
                threshold_values = _column_pylist(batch, "threshold")
                alert_values = _column_pylist(batch, "alert")
                decisions_present = all(
                    value is not None
                    for values in (calibrated_values, threshold_values, alert_values)
                    for value in values
                )
                decisions_absent = all(
                    value is None
                    for values in (calibrated_values, threshold_values, alert_values)
                    for value in values
                )
                if require_decisions is True and not decisions_present:
                    raise ValueError("detector prediction rows require frozen decisions")
                if require_decisions is False and not decisions_absent:
                    raise ValueError("raw validation predictions must not contain frozen decisions")
                if not decisions_present:
                    if not decisions_absent:
                        raise ValueError(
                            "detector prediction decision columns are partially populated"
                        )
                    continue

                calibrated = np.asarray(calibrated_values, dtype=np.float64)
                thresholds = np.asarray(threshold_values, dtype=np.float64)
                alerts = np.asarray(alert_values, dtype=np.bool_)
                if not _is_probability_vector(calibrated) or not _is_probability_vector(
                    thresholds
                ):
                    raise ValueError(
                        "detector calibrated probabilities or thresholds are invalid"
                    )
                if manifest is not None and not np.all(thresholds == manifest.threshold):
                    raise ValueError(
                        "detector prediction rows do not use the frozen manifest threshold"
                    )
                if not np.array_equal(alerts, calibrated >= thresholds):
                    raise ValueError(
                        "detector alert decisions do not match calibrated probabilities"
                    )
                observed_alerts += int(np.count_nonzero(alerts))
        finally:
            database.close()
    return observed_rows, observed_alerts


def _is_probability_vector(values: np.ndarray) -> bool:
    return bool(
        values.ndim == 1
        and np.isfinite(values).all()
        and not np.any((values < 0.0) | (values > 1.0))
    )


def _validate_scoring_request(
    dataset: GovernedFeatureDataset,
    *,
    training: LightGbmTrainingRun,
    expected_access_mode: str,
    expected_fold: str,
    artifact_root: Path,
    output_dir: Path,
    created_at: datetime,
    batch_size: int,
) -> None:
    expected_folds = (
        {expected_fold}
        if expected_access_mode == "final_test"
        else {"train", "validation"}
    )
    if (
        dataset.access_mode != expected_access_mode
        or {fold.fold for fold in dataset.folds} != expected_folds
    ):
        raise ValueError(f"scoring requires isolated {expected_fold} governed access")
    _require_dataset_binding(dataset, training.binding)
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("scoring created_at must be timezone-aware")
    if batch_size < 1:
        raise ValueError("scoring batch size must be positive")
    if output_dir.exists():
        raise ValueError("scoring output directory already exists")
    require_output_within_artifact_root(output_dir, artifact_root)
    for fold in dataset.folds:
        for shard in fold.shards:
            if (artifact_root / shard.feature_uri).resolve() != shard.feature_path.resolve():
                raise ValueError("governed features and scoring output must share one artifact root")


def _require_dataset_binding(dataset: GovernedFeatureDataset, binding: GovernedModelBinding) -> None:
    observed = (
        binding.protocol_id,
        binding.protocol_hash,
        binding.corpus_id,
        binding.corpus_hash,
        binding.split_id,
        binding.assignment_hash,
        binding.feature_schema_version,
        binding.feature_config_hash,
    )
    expected = (
        dataset.protocol_id,
        dataset.protocol_hash,
        dataset.corpus_id,
        dataset.corpus_hash,
        dataset.split_id,
        dataset.assignment_hash,
        dataset.feature_schema_version,
        dataset.feature_config_hash,
    )
    if observed != expected or dataset.ordered_feature_columns != tuple(FEATURE_COLUMNS):
        raise ValueError("governed feature dataset does not match the trained model binding")


def _load_model_and_preprocessor(
    training: LightGbmTrainingRun,
    artifact_root: Path,
) -> tuple[Any, Any | None]:
    import lightgbm as lgb

    model_path = resolve_verified_artifact(training.model_artifact, artifact_root=artifact_root)
    booster = lgb.Booster(model_file=str(model_path))
    if tuple(booster.feature_name()) != training.ordered_feature_columns:
        raise ValueError("LightGBM model feature identity does not match its training manifest")
    preprocessor = None
    if training.preprocessing.transformer is not None:
        import joblib

        path = resolve_verified_artifact(training.preprocessing.transformer, artifact_root=artifact_root)
        preprocessor = joblib.load(path)
        observed_names = tuple(
            str(value)
            for value in preprocessor.get_feature_names_out(
                np.asarray(training.ordered_feature_columns, dtype=object)
            )
        )
        if observed_names != training.ordered_feature_columns:
            raise ValueError("persisted preprocessor feature identity is incompatible")
    return booster, preprocessor


def _iter_scored_batches(
    fold: GovernedFeatureFold,
    *,
    booster: Any,
    preprocessor: Any | None,
    ordered_feature_columns: tuple[str, ...],
    best_iteration: int,
    batch_size: int,
) -> Iterator[_ScoredBatch]:
    for shard in fold.shards:
        if shard.feature_columns != ordered_feature_columns:
            raise ValueError("feature shard order changed after governed loading")
        for batch in shard.iter_supervised_batches(batch_size=batch_size):
            features = np.empty((batch.num_rows, len(ordered_feature_columns)), dtype=np.float32)
            for index, name in enumerate(ordered_feature_columns):
                values = pc.cast(batch.column(batch.schema.get_field_index(name)), pa.float32())
                features[:, index] = values.to_numpy(zero_copy_only=False)
            transformed = features if preprocessor is None else np.asarray(preprocessor.transform(features), dtype=np.float32)
            raw = np.asarray(booster.predict(transformed, num_iteration=best_iteration), dtype=np.float64)
            contributions = np.asarray(
                booster.predict(transformed, num_iteration=best_iteration, pred_contrib=True),
                dtype=np.float64,
            )
            if (
                raw.shape != (batch.num_rows,)
                or contributions.shape != (batch.num_rows, len(ordered_feature_columns) + 1)
                or not np.isfinite(raw).all()
                or not np.isfinite(contributions).all()
            ):
                raise RuntimeError("LightGBM scoring produced invalid output")
            yield _ScoredBatch(
                shard_base_session_id=shard.base_session_id,
                shard_campaign_id=shard.campaign_id,
                batch=batch,
                raw_probabilities=raw,
                contributions=contributions,
            )


def _prediction_table(
    scored: _ScoredBatch,
    *,
    fold: str,
    calibrated: np.ndarray | None,
    threshold: float | None,
) -> pa.Table:
    run_ids = _column_pylist(scored.batch, "run_id")
    timestamps = _column_numpy(scored.batch, "prediction_timestamp_ns", dtype=np.int64)
    sequences = _column_numpy(scored.batch, "sequence", dtype=np.int64)
    row_ids = [
        hashlib.sha256(f"{run_id}|{timestamp}|{sequence}".encode("utf-8")).hexdigest()
        for run_id, timestamp, sequence in zip(run_ids, timestamps, sequences, strict=True)
    ]
    alerts = calibrated >= threshold if calibrated is not None and threshold is not None else None
    count = scored.batch.num_rows
    return pa.Table.from_pydict(
        {
            "prediction_row_id": row_ids,
            "fold": [fold] * count,
            "run_id": run_ids,
            "base_session_id": [scored.shard_base_session_id] * count,
            "campaign_id": [scored.shard_campaign_id] * count,
            "instrument": _column_pylist(scored.batch, "instrument"),
            "session_id": _column_pylist(scored.batch, "session_id"),
            "source_type": _column_pylist(scored.batch, "source_type"),
            "prediction_timestamp_ns": timestamps,
            "sequence": sequences,
            "label": _column_numpy(scored.batch, "label", dtype=np.int8),
            "attack_family": _column_pylist(scored.batch, "attack_family"),
            "attack_phase": _column_pylist(scored.batch, "attack_phase"),
            "raw_probability": scored.raw_probabilities,
            "calibrated_probability": calibrated if calibrated is not None else [None] * count,
            "threshold": [threshold] * count if threshold is not None else [None] * count,
            "alert": alerts if alerts is not None else [None] * count,
        },
        schema=PREDICTION_ARROW_SCHEMA,
    )


def _contribution_table(
    predictions: pa.Table,
    contributions: np.ndarray,
    *,
    alerts: np.ndarray,
    feature_names: tuple[str, ...],
    top_count: int,
) -> pa.Table:
    rows: list[dict[str, object]] = []
    for index in np.flatnonzero(alerts):
        values = contributions[index, :-1]
        ordered = sorted(range(len(feature_names)), key=lambda position: (-abs(values[position]), position))[:top_count]
        for rank, feature_index in enumerate(ordered, 1):
            value = float(values[feature_index])
            rows.append(
                {
                    "prediction_row_id": predictions["prediction_row_id"][index].as_py(),
                    "base_session_id": predictions["base_session_id"][index].as_py(),
                    "campaign_id": predictions["campaign_id"][index].as_py(),
                    "prediction_timestamp_ns": predictions["prediction_timestamp_ns"][index].as_py(),
                    "feature": feature_names[feature_index],
                    "contribution": value,
                    "direction": "positive" if value >= 0.0 else "negative",
                    "absolute_rank": rank,
                }
            )
    return pa.Table.from_pylist(rows, schema=CONTRIBUTION_ARROW_SCHEMA)


def _challenge_case_metrics(
    probabilities: np.ndarray,
    family_masks: dict[str, np.ndarray],
    points: tuple[OperatingPoint, ...],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for family in CHALLENGE_FAMILIES:
        mask = family_masks[family]
        result[family] = {
            "positive_rows": int(np.count_nonzero(mask)),
            "recall_by_operating_mode": {
                point.mode: (
                    float(np.mean(probabilities[mask] >= point.threshold))
                    if np.any(mask)
                    else None
                )
                for point in points
            },
        }
    return result


def _validate_probability_labels(
    probabilities: np.ndarray,
    labels: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(probabilities, dtype=np.float64)
    targets = np.asarray(labels, dtype=np.int8)
    if (
        values.ndim != 1
        or targets.ndim != 1
        or values.shape != targets.shape
        or values.size == 0
        or not np.isfinite(values).all()
        or np.any((values < 0.0) | (values > 1.0))
        or not np.isin(targets, (0, 1)).all()
        or len(np.unique(targets)) != 2
    ):
        raise ValueError("calibration requires aligned finite probabilities and both binary classes")
    return values, targets


def _logit(values: np.ndarray) -> np.ndarray:
    clipped = np.clip(values, 1e-12, 1.0 - 1e-12)
    return np.log(clipped / (1.0 - clipped))


def _sigmoid(values: np.ndarray) -> np.ndarray:
    positive = values >= 0
    result = np.empty(values.shape, dtype=np.float64)
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponent = np.exp(values[~positive])
    result[~positive] = exponent / (1.0 + exponent)
    return result


def _calibration_id(
    binding: GovernedModelBinding,
    *,
    created_at: datetime,
    input_predictions: ArtifactDigest,
    parameters: CalibrationParameters,
    operating_points: tuple[OperatingPoint, ...],
) -> str:
    payload = {
        "binding": binding.model_dump(mode="json"),
        "created_at": created_at.isoformat(),
        "input_predictions": input_predictions.model_dump(mode="json"),
        "parameters": parameters.model_dump(mode="json"),
        "operating_points": [point.model_dump(mode="json") for point in operating_points],
    }
    digest = hashlib.sha256(
        json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"calibration-{digest[:24]}"


def _prediction_run_id(
    binding: GovernedModelBinding,
    *,
    calibration_id: str,
    fold: str,
    operating_mode: str,
    threshold: float,
    predictions: ArtifactDigest,
    created_at: datetime,
) -> str:
    payload = {
        "binding": binding.model_dump(mode="json"),
        "calibration_id": calibration_id,
        "fold": fold,
        "operating_mode": operating_mode,
        "threshold": threshold,
        "predictions": predictions.model_dump(mode="json"),
        "created_at": created_at.isoformat(),
    }
    digest = hashlib.sha256(
        json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"lightgbm-predict-{digest[:24]}"


def _staged_artifact(
    staging: Path,
    output_dir: Path,
    artifact_root: Path,
    filename: str,
    logical_name: str,
    schema_version: str,
) -> ArtifactDigest:
    return artifact_digest_for_destination(
        staging / filename,
        destination=output_dir / filename,
        artifact_root=artifact_root,
        logical_name=logical_name,
        schema_version=schema_version,
    )


def _column_numpy(batch: pa.RecordBatch, name: str, *, dtype: Any) -> np.ndarray:
    return np.asarray(
        batch.column(batch.schema.get_field_index(name)).to_numpy(zero_copy_only=False),
        dtype=dtype,
    )


def _column_pylist(batch: pa.RecordBatch, name: str) -> list[Any]:
    return batch.column(batch.schema.get_field_index(name)).to_pylist()


def _reliability_svg(
    raw_bins: list[dict[str, float | int]],
    calibrated_bins: list[dict[str, float | int]],
) -> str:
    def points(rows: list[dict[str, float | int]]) -> str:
        return " ".join(
            f"{40 + float(row['mean_probability']) * 320:.2f},{360 - float(row['positive_rate']) * 320:.2f}"
            for row in rows
            if int(row["count"]) > 0
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="400" viewBox="0 0 400 400">'
        '<rect width="400" height="400" fill="white"/>'
        '<line x1="40" y1="360" x2="360" y2="40" stroke="#999" stroke-dasharray="4 4"/>'
        f'<polyline points="{points(raw_bins)}" fill="none" stroke="#d95f02" stroke-width="2"/>'
        f'<polyline points="{points(calibrated_bins)}" fill="none" stroke="#1b9e77" stroke-width="2"/>'
        '<text x="40" y="25" font-family="sans-serif" font-size="14">Reliability: raw (orange), calibrated (green)</text>'
        '<text x="150" y="392" font-family="sans-serif" font-size="12">Predicted probability</text>'
        '<text x="12" y="235" transform="rotate(-90 12 235)" font-family="sans-serif" font-size="12">Observed rate</text>'
        "</svg>\n"
    )
