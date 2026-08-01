"""Governed LightGBM detector boundary."""

from importlib import import_module
from typing import TYPE_CHECKING, Any

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
    validate_phase_zero_compatibility,
)
from app.ml.lightgbm.data import (
    GovernedFeatureDataset,
    GovernedFeatureFold,
    GovernedFeatureShard,
    load_governed_feature_dataset,
)
from app.ml.lightgbm.feature_release import (
    GovernedFeatureReleaseManifest,
    GovernedFeatureReleaseShard,
    artifact_digest,
    load_governed_feature_release,
    write_governed_feature_release,
)
from app.ml.lightgbm.release import (
    ModelBundleResult,
    build_model_bundle,
    verify_complete_lightgbm_v1_release,
    verify_phase_zero_release,
)
if TYPE_CHECKING:
    from app.ml.lightgbm.detector import FeatureContribution, LightGbmDetectorScore, LightGbmV1Detector
    from app.ml.lightgbm.scoring import CalibrationResult, PredictionResult
    from app.ml.lightgbm.training import DeterministicTrainingResult

_OPTIONAL_EXPORT_MODULES = {
    "CalibrationResult": "app.ml.lightgbm.scoring",
    "DeterministicTrainingResult": "app.ml.lightgbm.training",
    "FeatureContribution": "app.ml.lightgbm.detector",
    "LightGbmDetectorScore": "app.ml.lightgbm.detector",
    "LightGbmV1Detector": "app.ml.lightgbm.detector",
    "PredictionResult": "app.ml.lightgbm.scoring",
    "apply_calibration": "app.ml.lightgbm.scoring",
    "calculate_base_session_sample_weights": "app.ml.lightgbm.training",
    "calculate_training_class_weights": "app.ml.lightgbm.training",
    "calibrate_validation_predictions": "app.ml.lightgbm.scoring",
    "calibration_metrics": "app.ml.lightgbm.scoring",
    "predict_governed_fold": "app.ml.lightgbm.scoring",
    "select_operating_points": "app.ml.lightgbm.scoring",
    "train_binary_attack_model": "app.ml.lightgbm.training",
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
    """Load runtime ML symbols only when the optional ``ml`` extra is installed."""

    module_name = _OPTIONAL_EXPORT_MODULES.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(import_module(module_name), name)
    globals()[name] = value
    return value
