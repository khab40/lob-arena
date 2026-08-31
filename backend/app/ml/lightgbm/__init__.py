"""Governed LightGBM detector boundary."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.ml.lightgbm.contracts import (
        ArtifactDigest,
        CalibrationManifest,
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
    )
    from app.ml.lightgbm.data import (
        GovernedFeatureDataset,
        GovernedFeatureFold,
        GovernedFeatureShard,
    )
    from app.ml.lightgbm.detector import FeatureContribution, LightGbmDetectorScore, LightGbmV1Detector
    from app.ml.lightgbm.feature_release import (
        GovernedFeatureReleaseManifest,
        GovernedFeatureReleaseShard,
    )
    from app.ml.lightgbm.release import ModelBundleResult
    from app.ml.lightgbm.scoring import CalibrationResult, PredictionResult
    from app.ml.lightgbm.training import DeterministicTrainingResult

_EXPORT_MODULES = {
    "ArtifactDigest": "app.ml.lightgbm.contracts",
    "CalibrationManifest": "app.ml.lightgbm.contracts",
    "CalibrationResult": "app.ml.lightgbm.scoring",
    "ClassWeightEvidence": "app.ml.lightgbm.contracts",
    "DetectorPredictionsManifest": "app.ml.lightgbm.contracts",
    "DeterministicTrainingResult": "app.ml.lightgbm.training",
    "EarlyStoppingEvidence": "app.ml.lightgbm.contracts",
    "FeatureContribution": "app.ml.lightgbm.detector",
    "FoldFeatureInput": "app.ml.lightgbm.contracts",
    "GovernedFeatureDataset": "app.ml.lightgbm.data",
    "GovernedFeatureFold": "app.ml.lightgbm.data",
    "GovernedFeatureReleaseManifest": "app.ml.lightgbm.feature_release",
    "GovernedFeatureReleaseShard": "app.ml.lightgbm.feature_release",
    "GovernedFeatureShard": "app.ml.lightgbm.data",
    "GovernedModelBinding": "app.ml.lightgbm.contracts",
    "LightGbmDetectorScore": "app.ml.lightgbm.detector",
    "LightGbmTrainingRun": "app.ml.lightgbm.contracts",
    "LightGbmV1Hyperparameters": "app.ml.lightgbm.contracts",
    "LightGbmV1Detector": "app.ml.lightgbm.detector",
    "ModelBundleManifest": "app.ml.lightgbm.contracts",
    "ModelBundleResult": "app.ml.lightgbm.release",
    "OperatingPoint": "app.ml.lightgbm.contracts",
    "OperatingPointConstraints": "app.ml.lightgbm.contracts",
    "OperatingPointMetrics": "app.ml.lightgbm.contracts",
    "PreprocessingEvidence": "app.ml.lightgbm.contracts",
    "PredictionResult": "app.ml.lightgbm.scoring",
    "apply_calibration": "app.ml.lightgbm.scoring",
    "artifact_digest": "app.ml.lightgbm.feature_release",
    "build_model_bundle": "app.ml.lightgbm.release",
    "calculate_base_session_sample_weights": "app.ml.lightgbm.training",
    "calculate_training_class_weights": "app.ml.lightgbm.training",
    "calibrate_validation_predictions": "app.ml.lightgbm.scoring",
    "calibration_metrics": "app.ml.lightgbm.scoring",
    "load_governed_feature_dataset": "app.ml.lightgbm.data",
    "load_governed_feature_release": "app.ml.lightgbm.feature_release",
    "predict_governed_fold": "app.ml.lightgbm.scoring",
    "select_operating_points": "app.ml.lightgbm.scoring",
    "train_binary_attack_model": "app.ml.lightgbm.training",
    "validate_phase_zero_compatibility": "app.ml.lightgbm.contracts",
    "verify_complete_lightgbm_v1_release": "app.ml.lightgbm.release",
    "verify_phase_zero_release": "app.ml.lightgbm.release",
    "write_governed_feature_release": "app.ml.lightgbm.feature_release",
}

__all__ = [
    "ArtifactDigest",
    "CalibrationManifest",
    "CalibrationResult",
    "ClassWeightEvidence",
    "DetectorPredictionsManifest",
    "DeterministicTrainingResult",
    "EarlyStoppingEvidence",
    "FoldFeatureInput",
    "GovernedFeatureDataset",
    "GovernedFeatureFold",
    "GovernedFeatureReleaseManifest",
    "GovernedFeatureReleaseShard",
    "GovernedFeatureShard",
    "GovernedModelBinding",
    "FeatureContribution",
    "LightGbmDetectorScore",
    "LightGbmV1Detector",
    "LightGbmTrainingRun",
    "LightGbmV1Hyperparameters",
    "ModelBundleManifest",
    "ModelBundleResult",
    "OperatingPoint",
    "OperatingPointConstraints",
    "OperatingPointMetrics",
    "PreprocessingEvidence",
    "PredictionResult",
    "apply_calibration",
    "artifact_digest",
    "calculate_base_session_sample_weights",
    "calculate_training_class_weights",
    "calibrate_validation_predictions",
    "calibration_metrics",
    "load_governed_feature_release",
    "load_governed_feature_dataset",
    "predict_governed_fold",
    "select_operating_points",
    "train_binary_attack_model",
    "validate_phase_zero_compatibility",
    "verify_phase_zero_release",
    "verify_complete_lightgbm_v1_release",
    "build_model_bundle",
    "write_governed_feature_release",
]


def __getattr__(name: str) -> Any:
    """Load governed ML symbols only when a caller actually uses them."""

    module_name = _EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
