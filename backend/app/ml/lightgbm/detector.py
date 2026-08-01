from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import numpy as np

from app.ml.lightgbm.artifacts import resolve_verified_artifact
from app.ml.lightgbm.contracts import (
    CalibrationManifest,
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
    ModelBundleManifest,
    OperatingMode,
)
from app.ml.lightgbm.release import verify_complete_lightgbm_v1_release
from app.ml.lightgbm.scoring import apply_calibration, validate_prediction_parquet


@dataclass(frozen=True)
class FeatureContribution:
    feature: str
    value: float | None
    contribution: float
    direction: str
    absolute_rank: int


@dataclass(frozen=True)
class LightGbmDetectorScore:
    detector_id: str
    model_bundle_id: str
    training_run_id: str
    calibration_id: str
    operating_mode: OperatingMode
    raw_probability: float
    attack_probability: float
    threshold: float
    alert: bool
    top_contributions: tuple[FeatureContribution, ...]


class LightGbmV1Detector:
    """Fail-closed online adapter for a verified governed model bundle."""

    def __init__(
        self,
        *,
        artifact_root: Path,
        training: LightGbmTrainingRun,
        calibration: CalibrationManifest,
        bundle: ModelBundleManifest,
        release_predictions: DetectorPredictionsManifest,
        operating_mode: OperatingMode = "balanced",
        top_contributions: int = 5,
    ) -> None:
        verify_complete_lightgbm_v1_release(
            artifact_root,
            training=training,
            calibration=calibration,
            bundle=bundle,
            predictions=release_predictions,
        )
        validate_prediction_parquet(
            resolve_verified_artifact(
                release_predictions.predictions,
                artifact_root=artifact_root,
            ),
            manifest=release_predictions,
        )
        if not 1 <= top_contributions <= len(training.ordered_feature_columns):
            raise ValueError("detector contribution count is outside the feature inventory")
        if operating_mode != release_predictions.operating_mode:
            raise ValueError(
                "detector operating mode was not evaluated by the verified release"
            )
        points = {point.mode: point for point in calibration.operating_points}
        point = points[operating_mode]

        import lightgbm as lgb

        model_path = resolve_verified_artifact(training.model_artifact, artifact_root=artifact_root)
        booster = lgb.Booster(model_file=str(model_path))
        if tuple(booster.feature_name()) != training.ordered_feature_columns:
            raise ValueError("detector model feature identity does not match its manifest")
        preprocessor = None
        if training.preprocessing.transformer is not None:
            import joblib

            path = resolve_verified_artifact(
                training.preprocessing.transformer,
                artifact_root=artifact_root,
            )
            preprocessor = joblib.load(path)
            names = tuple(
                str(value)
                for value in preprocessor.get_feature_names_out(
                    np.asarray(training.ordered_feature_columns, dtype=object)
                )
            )
            if names != training.ordered_feature_columns:
                raise ValueError("detector preprocessor changed governed feature identity")
        self._training = training
        self._calibration = calibration
        self._bundle = bundle
        self._booster = booster
        self._preprocessor = preprocessor
        self._operating_mode = operating_mode
        self._threshold = point.threshold
        self._top_contributions = top_contributions

    @property
    def ordered_feature_columns(self) -> tuple[str, ...]:
        return self._training.ordered_feature_columns

    def score(self, features: Mapping[str, float | int | None]) -> LightGbmDetectorScore:
        expected = set(self.ordered_feature_columns)
        observed = set(features)
        if observed != expected:
            missing = sorted(expected - observed)
            unexpected = sorted(observed - expected)
            raise ValueError(
                f"detector feature identity mismatch: missing={missing}, unexpected={unexpected}"
            )
        values: list[float] = []
        original_values: list[float | None] = []
        for name in self.ordered_feature_columns:
            value = features[name]
            if value is None:
                values.append(float("nan"))
                original_values.append(None)
                continue
            numeric = float(value)
            if math.isinf(numeric):
                raise ValueError(f"detector feature is infinite: {name}")
            values.append(numeric)
            original_values.append(None if math.isnan(numeric) else numeric)
        matrix = np.asarray([values], dtype=np.float32)
        transformed = (
            matrix
            if self._preprocessor is None
            else np.asarray(self._preprocessor.transform(matrix), dtype=np.float32)
        )
        raw = float(
            self._booster.predict(
                transformed,
                num_iteration=self._training.early_stopping.best_iteration,
            )[0]
        )
        calibrated = float(
            apply_calibration(
                self._calibration.parameters,
                np.asarray([raw], dtype=np.float64),
            )[0]
        )
        contribution_values = np.asarray(
            self._booster.predict(
                transformed,
                num_iteration=self._training.early_stopping.best_iteration,
                pred_contrib=True,
            )[0][:-1],
            dtype=np.float64,
        )
        positions = sorted(
            range(len(self.ordered_feature_columns)),
            key=lambda index: (-abs(contribution_values[index]), index),
        )[: self._top_contributions]
        contributions = tuple(
            FeatureContribution(
                feature=self.ordered_feature_columns[index],
                value=original_values[index],
                contribution=float(contribution_values[index]),
                direction="positive" if contribution_values[index] >= 0.0 else "negative",
                absolute_rank=rank,
            )
            for rank, index in enumerate(positions, 1)
        )
        return LightGbmDetectorScore(
            detector_id=self._training.binding.model_id,
            model_bundle_id=self._bundle.manifest_hash(),
            training_run_id=self._training.binding.training_run_id,
            calibration_id=self._calibration.calibration_id,
            operating_mode=self._operating_mode,
            raw_probability=raw,
            attack_probability=calibrated,
            threshold=self._threshold,
            alert=calibrated >= self._threshold,
            top_contributions=contributions,
        )
