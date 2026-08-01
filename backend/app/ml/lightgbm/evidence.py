from __future__ import annotations

import json
import math
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

import pyarrow.parquet as pq

from app.ml.lightgbm.contracts import (
    CalibrationManifest,
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
)
from app.ml.lightgbm.scoring import (
    CONTRIBUTION_ARROW_SCHEMA,
    FEATURE_IMPORTANCE_SCHEMA_VERSION,
    FEATURE_SCHEMA_ARTIFACT_VERSION,
    VALIDATION_METRICS_SCHEMA_VERSION,
)


def validate_release_evidence(
    *,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    predictions: DetectorPredictionsManifest,
    feature_schema_path: Path,
    validation_metrics_path: Path,
    feature_importance_path: Path,
    contributions_path: Path,
    predictions_path: Path,
) -> None:
    """Validate the semantics and cross-artifact bindings of release evidence."""

    _validate_feature_schema(feature_schema_path, training)
    _validate_validation_metrics(validation_metrics_path, training, calibration)
    _validate_feature_importance(feature_importance_path, training, calibration)
    _validate_contributions(
        contributions_path,
        predictions_path=predictions_path,
        predictions=predictions,
        ordered_features=training.ordered_feature_columns,
    )


def _validate_feature_schema(path: Path, training: LightGbmTrainingRun) -> None:
    payload = _json_object(path, "feature schema")
    expected_features = [
        {"name": name, "dtype": "float32", "nullable": True}
        for name in training.ordered_feature_columns
    ]
    expected = {
        "schema_version": FEATURE_SCHEMA_ARTIFACT_VERSION,
        "feature_schema_version": training.binding.feature_schema_version,
        "feature_config_hash": training.binding.feature_config_hash,
        "target": "attack_active",
        "numeric_storage_dtype": "float32",
        "ordered_features": expected_features,
    }
    if payload != expected:
        raise ValueError("LightGBM feature schema evidence is incompatible with the training run")


def _validate_validation_metrics(
    path: Path,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
) -> None:
    payload = _json_object(path, "validation metrics")
    if (
        payload.get("schema_version") != VALIDATION_METRICS_SCHEMA_VERSION
        or payload.get("calibration_id") != calibration.calibration_id
        or payload.get("binding") != training.binding.model_dump(mode="json")
        or payload.get("row_count") != calibration.row_count
        or payload.get("raw_metrics") != calibration.raw_metrics.model_dump(mode="json")
        or payload.get("calibrated_metrics")
        != calibration.calibrated_metrics.model_dump(mode="json")
        or payload.get("operating_points")
        != [point.model_dump(mode="json") for point in calibration.operating_points]
    ):
        raise ValueError("LightGBM validation metrics evidence is incompatible with calibration")
    negative_count = payload.get("negative_count")
    positive_count = payload.get("positive_count")
    if (
        not isinstance(negative_count, int)
        or isinstance(negative_count, bool)
        or not isinstance(positive_count, int)
        or isinstance(positive_count, bool)
        or negative_count < 1
        or positive_count < 1
        or negative_count + positive_count != calibration.row_count
    ):
        raise ValueError("LightGBM validation metrics class counts are invalid")
    challenge_cases = payload.get("challenge_cases")
    if not isinstance(challenge_cases, dict) or set(challenge_cases) != {
        "liquidity_evaporation",
        "layering_like",
    }:
        raise ValueError("LightGBM validation metrics lack the required challenge cases")


def _validate_feature_importance(
    path: Path,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
) -> None:
    payload = _json_object(path, "feature importance")
    features = payload.get("features")
    if (
        payload.get("schema_version") != FEATURE_IMPORTANCE_SCHEMA_VERSION
        or payload.get("binding") != training.binding.model_dump(mode="json")
        or payload.get("validation_row_count") != calibration.row_count
        or not isinstance(features, list)
        or [item.get("name") for item in features if isinstance(item, dict)]
        != list(training.ordered_feature_columns)
        or len(features) != len(training.ordered_feature_columns)
    ):
        raise ValueError("LightGBM feature-importance evidence is incompatible")
    for item in features:
        if not isinstance(item, dict):
            raise ValueError("LightGBM feature-importance row is invalid")
        gain = item.get("gain")
        split_count = item.get("split_count")
        mean_contribution = item.get("mean_absolute_contribution")
        if (
            not _finite_nonnegative_number(gain)
            or not isinstance(split_count, int)
            or isinstance(split_count, bool)
            or split_count < 0
            or not _finite_nonnegative_number(mean_contribution)
        ):
            raise ValueError("LightGBM feature-importance values are invalid")


def _validate_contributions(
    path: Path,
    *,
    predictions_path: Path,
    predictions: DetectorPredictionsManifest,
    ordered_features: tuple[str, ...],
) -> None:
    parquet = pq.ParquetFile(path)
    if not parquet.schema_arrow.equals(CONTRIBUTION_ARROW_SCHEMA, check_metadata=True):
        raise ValueError("LightGBM contribution Parquet schema is incompatible")
    with tempfile.TemporaryDirectory(prefix="lob-arena-contribution-validation-") as directory:
        database = sqlite3.connect(Path(directory) / "evidence.sqlite3")
        try:
            database.execute("PRAGMA journal_mode=OFF")
            database.execute("PRAGMA synchronous=OFF")
            database.execute("PRAGMA temp_store=FILE")
            database.executescript(
                """
                CREATE TABLE alerts (
                    prediction_row_id TEXT PRIMARY KEY,
                    base_session_id TEXT NOT NULL,
                    campaign_id TEXT,
                    prediction_timestamp_ns INTEGER NOT NULL
                ) WITHOUT ROWID;
                CREATE TABLE contributions (
                    prediction_row_id TEXT NOT NULL,
                    base_session_id TEXT NOT NULL,
                    campaign_id TEXT,
                    prediction_timestamp_ns INTEGER NOT NULL,
                    feature TEXT NOT NULL,
                    absolute_rank INTEGER NOT NULL,
                    PRIMARY KEY (prediction_row_id, absolute_rank),
                    UNIQUE (prediction_row_id, feature)
                ) WITHOUT ROWID;
                """
            )
            _load_alert_identity(database, predictions_path)
            _load_contribution_identity(database, parquet, set(ordered_features))
            alert_count = int(database.execute("SELECT COUNT(*) FROM alerts").fetchone()[0])
            if alert_count != predictions.alert_count:
                raise ValueError("LightGBM contribution evidence alert inventory is incompatible")
            extra = database.execute(
                """
                SELECT 1
                FROM contributions AS c
                LEFT JOIN alerts AS a USING (prediction_row_id)
                WHERE a.prediction_row_id IS NULL
                   OR c.base_session_id != a.base_session_id
                   OR c.campaign_id IS NOT a.campaign_id
                   OR c.prediction_timestamp_ns != a.prediction_timestamp_ns
                LIMIT 1
                """
            ).fetchone()
            if extra is not None:
                raise ValueError("LightGBM contributions do not bind to their alert rows")
            grouped = database.execute(
                """
                SELECT prediction_row_id, COUNT(*), MIN(absolute_rank), MAX(absolute_rank)
                FROM contributions GROUP BY prediction_row_id
                """
            ).fetchall()
            if len(grouped) != alert_count:
                raise ValueError("LightGBM contributions must cover every alert exactly once")
            contribution_counts = {int(row[1]) for row in grouped}
            if (
                alert_count > 0
                and (
                    len(contribution_counts) != 1
                    or 0 in contribution_counts
                    or any(int(row[2]) != 1 or int(row[3]) != int(row[1]) for row in grouped)
                )
            ):
                raise ValueError("LightGBM contribution ranks are incomplete or inconsistent")
        finally:
            database.close()


def _load_alert_identity(database: sqlite3.Connection, path: Path) -> None:
    parquet = pq.ParquetFile(path)
    for batch in parquet.iter_batches(
        batch_size=65_536,
        columns=[
            "prediction_row_id",
            "base_session_id",
            "campaign_id",
            "prediction_timestamp_ns",
            "alert",
        ],
    ):
        rows = zip(*(batch.column(index).to_pylist() for index in range(batch.num_columns)), strict=True)
        database.executemany(
            "INSERT INTO alerts VALUES (?, ?, ?, ?)",
            (
                (str(row_id), str(base_session_id), campaign_id, int(timestamp))
                for row_id, base_session_id, campaign_id, timestamp, alert in rows
                if alert is True
            ),
        )


def _load_contribution_identity(
    database: sqlite3.Connection,
    parquet: pq.ParquetFile,
    feature_names: set[str],
) -> None:
    for batch in parquet.iter_batches(batch_size=65_536):
        rows = batch.to_pylist()
        for row in rows:
            contribution = row["contribution"]
            direction = row["direction"]
            feature = row["feature"]
            rank = row["absolute_rank"]
            if (
                feature not in feature_names
                or not isinstance(rank, int)
                or isinstance(rank, bool)
                or rank < 1
                or not isinstance(contribution, (int, float))
                or isinstance(contribution, bool)
                or not math.isfinite(float(contribution))
                or direction != ("positive" if contribution >= 0 else "negative")
            ):
                raise ValueError("LightGBM contribution row is invalid")
        try:
            database.executemany(
                "INSERT INTO contributions VALUES (?, ?, ?, ?, ?, ?)",
                (
                    (
                        str(row["prediction_row_id"]),
                        str(row["base_session_id"]),
                        row["campaign_id"],
                        int(row["prediction_timestamp_ns"]),
                        str(row["feature"]),
                        int(row["absolute_rank"]),
                    )
                    for row in rows
                ),
            )
        except sqlite3.IntegrityError as exception:
            raise ValueError("LightGBM contribution rows contain duplicate identities") from exception


def _json_object(path: Path, description: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exception:
        raise ValueError(f"LightGBM {description} evidence is not valid JSON") from exception
    if not isinstance(payload, dict):
        raise ValueError(f"LightGBM {description} evidence must be a JSON object")
    return payload


def _finite_nonnegative_number(value: object) -> bool:
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and float(value) >= 0.0
    )
