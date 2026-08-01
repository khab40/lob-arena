"""Governed LightGBM detector boundary."""

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
from app.ml.lightgbm.scoring import (
    CalibrationResult,
    PredictionResult,
    apply_calibration,
    calibrate_validation_predictions,
    calibration_metrics,
    predict_governed_fold,
    select_operating_points,
)
from app.ml.lightgbm.detector import (
    FeatureContribution,
    LightGbmDetectorScore,
    LightGbmV1Detector,
)

if TYPE_CHECKING:
    from app.ml.lightgbm.training import DeterministicTrainingResult

_TRAINING_EXPORTS = frozenset(
    {
        "DeterministicTrainingResult",
        "calculate_base_session_sample_weights",
        "calculate_training_class_weights",
        "train_binary_attack_model",
    }
)

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
    """Load trainer symbols only when the optional ``ml`` extra is installed."""

    if name not in _TRAINING_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    from app.ml.lightgbm import training

    value = getattr(training, name)
    globals()[name] = value
    return value
