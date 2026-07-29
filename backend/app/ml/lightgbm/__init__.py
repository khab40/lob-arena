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
from app.ml.lightgbm.release import verify_phase_zero_release

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
    "LightGbmTrainingRun",
    "LightGbmV1Hyperparameters",
    "ModelBundleManifest",
    "OperatingPoint",
    "OperatingPointConstraints",
    "OperatingPointMetrics",
    "PreprocessingEvidence",
    "artifact_digest",
    "calculate_base_session_sample_weights",
    "calculate_training_class_weights",
    "load_governed_feature_release",
    "load_governed_feature_dataset",
    "train_binary_attack_model",
    "validate_phase_zero_compatibility",
    "verify_phase_zero_release",
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
