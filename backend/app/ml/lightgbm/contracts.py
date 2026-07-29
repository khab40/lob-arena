from __future__ import annotations

import hashlib
import json
import math
from pathlib import PurePosixPath
from typing import Literal, Sequence

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


SHA256_PATTERN = r"^[0-9a-f]{64}$"
GIT_COMMIT_PATTERN = r"^[0-9a-f]{40}$"
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
PREDICTION_ROWS_SCHEMA_VERSION = "detector_predictions_rows_v1"
CHECKSUM_INVENTORY_SCHEMA_VERSION = "sha256_inventory_v1"
FoldName = Literal["train", "validation", "test"]
OperatingMode = Literal["high_precision", "balanced", "high_recall"]
OPERATING_MODES = frozenset({"high_precision", "balanced", "high_recall"})
REQUIRED_MODEL_BUNDLE_ARTIFACTS = frozenset(
    {
        "model",
        "training_manifest",
        "calibration_manifest",
        "prediction_manifest",
        "predictions",
        "feature_schema",
        "validation_metrics",
        "feature_importance",
        "checksums",
    }
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _CanonicalManifest(_StrictModel):
    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def canonical_bytes(self) -> bytes:
        return self.canonical_json().encode("utf-8")

    def manifest_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class ArtifactDigest(_StrictModel):
    logical_name: str = Field(pattern=IDENTIFIER_PATTERN)
    uri: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)
    schema_version: str = Field(pattern=IDENTIFIER_PATTERN)

    @model_validator(mode="after")
    def validate_relative_uri(self) -> "ArtifactDigest":
        path = PurePosixPath(self.uri)
        if (
            path.is_absolute()
            or "\\" in self.uri
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.as_posix() != self.uri
        ):
            raise ValueError("artifact URI must be a normalized relative POSIX path")
        return self


class GovernedModelBinding(_StrictModel):
    model_id: str = Field(pattern=IDENTIFIER_PATTERN)
    training_run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    protocol_id: str = Field(pattern=IDENTIFIER_PATTERN)
    protocol_hash: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(pattern=IDENTIFIER_PATTERN)
    corpus_hash: str = Field(pattern=SHA256_PATTERN)
    split_id: str = Field(pattern=IDENTIFIER_PATTERN)
    assignment_hash: str = Field(pattern=SHA256_PATTERN)
    feature_schema_version: str = Field(pattern=IDENTIFIER_PATTERN)
    feature_config_hash: str = Field(pattern=SHA256_PATTERN)

    def identity_tuple(self) -> tuple[str, ...]:
        return (
            self.model_id,
            self.training_run_id,
            self.protocol_id,
            self.protocol_hash,
            self.corpus_id,
            self.corpus_hash,
            self.split_id,
            self.assignment_hash,
            self.feature_schema_version,
            self.feature_config_hash,
        )


class TrainingDataPolicy(_StrictModel):
    target: Literal["attack_active"] = "attack_active"
    training_fold: Literal["train"] = "train"
    early_stopping_fold: Literal["validation"] = "validation"
    negative_label_source: Literal["independently_verified_clean"] = "independently_verified_clean"
    positive_label_source: Literal["synthetic_scenario"] = "synthetic_scenario"
    invalid_row_policy: Literal["reject"] = "reject"
    missing_value_policy: Literal["lightgbm_native"] = "lightgbm_native"
    numeric_storage_dtype: Literal["float32"] = "float32"
    class_weights_fit_on: Literal["training_fold_only"] = "training_fold_only"
    preprocessing_fit_on: Literal["training_fold_only"] = "training_fold_only"
    base_session_weighting: Literal["normalize_within_class"] = "normalize_within_class"
    test_fold_accessed: Literal[False] = False


class FoldFeatureInput(_StrictModel):
    fold: FoldName
    artifact: ArtifactDigest
    fold_membership_hash: str = Field(pattern=SHA256_PATTERN)
    session_count: int = Field(ge=1)
    row_count: int = Field(ge=1)


class LightGbmV1Hyperparameters(_StrictModel):
    objective: Literal["binary"] = "binary"
    metric: Literal["binary_logloss"] = "binary_logloss"
    boosting_type: Literal["gbdt"] = "gbdt"
    deterministic: Literal[True] = True
    num_boost_round: int = Field(default=500, ge=1)
    learning_rate: float = Field(default=0.03, gt=0, le=1, allow_inf_nan=False)
    num_leaves: int = Field(default=31, ge=2)
    max_depth: int = -1
    min_data_in_leaf: int = Field(default=20, ge=1)
    feature_fraction: float = Field(default=1.0, gt=0, le=1, allow_inf_nan=False)
    bagging_fraction: float = Field(default=1.0, gt=0, le=1, allow_inf_nan=False)
    bagging_freq: int = Field(default=0, ge=0)
    lambda_l1: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    lambda_l2: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    num_threads: int = Field(default=1, ge=1)

    @model_validator(mode="after")
    def validate_tree_shape(self) -> "LightGbmV1Hyperparameters":
        if self.max_depth == 0 or self.max_depth < -1:
            raise ValueError("max_depth must be -1 or a positive integer")
        return self


class ClassWeightEvidence(_StrictModel):
    strategy: Literal["balanced_training_fold"] = "balanced_training_fold"
    fit_fold: Literal["train"] = "train"
    negative_count: int = Field(ge=1)
    positive_count: int = Field(ge=1)
    negative_weight: float = Field(gt=0, allow_inf_nan=False)
    positive_weight: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_balanced_weights(self) -> "ClassWeightEvidence":
        total = self.negative_count + self.positive_count
        expected_negative = total / (2 * self.negative_count)
        expected_positive = total / (2 * self.positive_count)
        if not (
            math.isclose(self.negative_weight, expected_negative, rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(self.positive_weight, expected_positive, rel_tol=1e-12, abs_tol=1e-12)
        ):
            raise ValueError("class weights must be derived from training-fold class counts")
        return self


class PreprocessingEvidence(_StrictModel):
    mode: Literal["none", "training_fitted"]
    fit_fold: Literal["train"] = "train"
    transformer: ArtifactDigest | None = None

    @model_validator(mode="after")
    def validate_transformer(self) -> "PreprocessingEvidence":
        if self.mode == "none" and self.transformer is not None:
            raise ValueError("preprocessing mode none must not reference a transformer")
        if self.mode == "training_fitted" and self.transformer is None:
            raise ValueError("training-fitted preprocessing requires a transformer artifact")
        return self


class EarlyStoppingEvidence(_StrictModel):
    selection_fold: Literal["validation"] = "validation"
    metric: Literal["binary_logloss"] = "binary_logloss"
    stopping_rounds: int = Field(ge=1)
    min_delta: float = Field(default=0.0, ge=0, allow_inf_nan=False)
    best_iteration: int = Field(ge=1)
    best_score: float = Field(ge=0, allow_inf_nan=False)


class LightGbmTrainingRun(_CanonicalManifest):
    schema_version: Literal["lightgbm_training_run_v1"] = "lightgbm_training_run_v1"
    binding: GovernedModelBinding
    feature_release_id: str = Field(min_length=1)
    feature_release_sha256: str = Field(pattern=SHA256_PATTERN)
    model_artifact: ArtifactDigest
    git_commit: str = Field(pattern=GIT_COMMIT_PATTERN)
    created_at: AwareDatetime
    training_seed: int = Field(ge=0)
    data_policy: TrainingDataPolicy = Field(default_factory=TrainingDataPolicy)
    ordered_feature_columns: tuple[str, ...] = Field(min_length=1)
    input_features: tuple[FoldFeatureInput, ...] = Field(min_length=2)
    hyperparameters: LightGbmV1Hyperparameters
    class_weights: ClassWeightEvidence
    preprocessing: PreprocessingEvidence
    early_stopping: EarlyStoppingEvidence

    @model_validator(mode="after")
    def validate_training_inputs(self) -> "LightGbmTrainingRun":
        if self.model_artifact.logical_name != "model" or self.model_artifact.schema_version != "lightgbm_text_v1":
            raise ValueError("training model artifact must use the governed LightGBM text format")
        if any(not column for column in self.ordered_feature_columns):
            raise ValueError("ordered feature columns must be non-empty")
        if len(self.ordered_feature_columns) != len(set(self.ordered_feature_columns)):
            raise ValueError("ordered feature columns must be unique")
        folds = {item.fold for item in self.input_features}
        if folds != {"train", "validation"}:
            raise ValueError("training inputs require train and validation folds only")
        if any(item.artifact.schema_version != self.binding.feature_schema_version for item in self.input_features):
            raise ValueError("training feature inputs do not match the bound feature schema")
        training_rows = sum(item.row_count for item in self.input_features if item.fold == "train")
        if self.class_weights.negative_count + self.class_weights.positive_count != training_rows:
            raise ValueError("training-fold class counts must equal the training feature rows")
        _require_unique_artifacts(tuple(item.artifact for item in self.input_features))
        if self.early_stopping.best_iteration > self.hyperparameters.num_boost_round:
            raise ValueError("best iteration cannot exceed num_boost_round")
        return self


class CalibrationParameters(_StrictModel):
    method: Literal["raw", "platt", "isotonic"]
    platt_slope: float | None = Field(default=None, allow_inf_nan=False)
    platt_intercept: float | None = Field(default=None, allow_inf_nan=False)
    isotonic_x: tuple[float, ...] = ()
    isotonic_y: tuple[float, ...] = ()

    @model_validator(mode="after")
    def validate_method_parameters(self) -> "CalibrationParameters":
        if self.method == "raw":
            if self.platt_slope is not None or self.platt_intercept is not None or self.isotonic_x or self.isotonic_y:
                raise ValueError("raw calibration must not contain fitted parameters")
        elif self.method == "platt":
            if self.platt_slope is None or self.platt_intercept is None:
                raise ValueError("Platt calibration requires slope and intercept")
            if self.isotonic_x or self.isotonic_y:
                raise ValueError("Platt calibration must not contain isotonic knots")
        else:
            if self.platt_slope is not None or self.platt_intercept is not None:
                raise ValueError("isotonic calibration must not contain Platt parameters")
            if len(self.isotonic_x) < 2 or len(self.isotonic_x) != len(self.isotonic_y):
                raise ValueError("isotonic calibration requires matching x/y knots")
            if any(left >= right for left, right in zip(self.isotonic_x, self.isotonic_x[1:], strict=False)):
                raise ValueError("isotonic x knots must be strictly increasing")
            if any(left > right for left, right in zip(self.isotonic_y, self.isotonic_y[1:], strict=False)):
                raise ValueError("isotonic y knots must be non-decreasing")
            if any(not 0.0 <= value <= 1.0 for value in (*self.isotonic_x, *self.isotonic_y)):
                raise ValueError("isotonic knots must be probabilities")
        return self


class CalibrationMetrics(_StrictModel):
    brier_score: float = Field(ge=0, le=1, allow_inf_nan=False)
    expected_calibration_error: float = Field(ge=0, le=1, allow_inf_nan=False)


class OperatingPointMetrics(_StrictModel):
    precision: float = Field(ge=0, le=1, allow_inf_nan=False)
    recall: float = Field(ge=0, le=1, allow_inf_nan=False)
    f1: float = Field(ge=0, le=1, allow_inf_nan=False)
    attack_level_recall: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    detection_before_benefit_rate: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    false_alerts_per_million_events: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    duplicate_alert_load: float | None = Field(default=None, ge=0, allow_inf_nan=False)


class OperatingPointConstraints(_StrictModel):
    precision_floor: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)
    recall_floor: float | None = Field(default=None, ge=0, le=1, allow_inf_nan=False)


class OperatingPoint(_StrictModel):
    mode: OperatingMode
    threshold: float = Field(ge=0, le=1, allow_inf_nan=False)
    selection_policy: Literal[
        "maximize_recall_at_precision_floor",
        "maximize_f1",
        "maximize_precision_at_recall_floor",
    ]
    validation_metrics: OperatingPointMetrics
    metric_constraints: OperatingPointConstraints = Field(default_factory=OperatingPointConstraints)

    @model_validator(mode="after")
    def validate_mode_semantics(self) -> "OperatingPoint":
        constraints = self.metric_constraints
        if self.mode == "high_precision":
            if (
                self.selection_policy != "maximize_recall_at_precision_floor"
                or constraints.precision_floor is None
                or constraints.recall_floor is not None
            ):
                raise ValueError("high-precision mode requires only a precision floor")
            if self.validation_metrics.precision < constraints.precision_floor:
                raise ValueError("high-precision operating point violates its precision floor")
        elif self.mode == "balanced":
            if self.selection_policy != "maximize_f1" or constraints != OperatingPointConstraints():
                raise ValueError("balanced mode must maximize F1 without metric floors")
        else:
            if (
                self.selection_policy != "maximize_precision_at_recall_floor"
                or constraints.recall_floor is None
                or constraints.precision_floor is not None
            ):
                raise ValueError("high-recall mode requires only a recall floor")
            if self.validation_metrics.recall < constraints.recall_floor:
                raise ValueError("high-recall operating point violates its recall floor")
        return self


class CalibrationManifest(_CanonicalManifest):
    schema_version: Literal["model_calibration_v1"] = "model_calibration_v1"
    calibration_id: str = Field(pattern=IDENTIFIER_PATTERN)
    binding: GovernedModelBinding
    created_at: AwareDatetime
    fit_fold: Literal["validation"] = "validation"
    test_fold_accessed: Literal[False] = False
    input_predictions: ArtifactDigest
    session_count: int = Field(ge=1)
    row_count: int = Field(ge=1)
    parameters: CalibrationParameters
    raw_metrics: CalibrationMetrics
    calibrated_metrics: CalibrationMetrics
    operating_points: tuple[OperatingPoint, ...] = Field(min_length=3, max_length=3)

    @model_validator(mode="after")
    def validate_operating_modes(self) -> "CalibrationManifest":
        if self.input_predictions.schema_version != PREDICTION_ROWS_SCHEMA_VERSION:
            raise ValueError("calibration input does not use the governed prediction-row schema")
        modes = [point.mode for point in self.operating_points]
        if set(modes) != OPERATING_MODES or len(modes) != len(set(modes)):
            raise ValueError("calibration requires exactly one operating point for every supported mode")
        return self


class ModelBundleManifest(_CanonicalManifest):
    schema_version: Literal["lightgbm_model_bundle_v1"] = "lightgbm_model_bundle_v1"
    binding: GovernedModelBinding
    calibration_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: AwareDatetime
    model_format: Literal["lightgbm_text_v1"] = "lightgbm_text_v1"
    artifacts: tuple[ArtifactDigest, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_artifact_inventory(self) -> "ModelBundleManifest":
        names = _require_unique_artifacts(self.artifacts)
        uris = [artifact.uri for artifact in self.artifacts]
        if len(uris) != len(set(uris)):
            raise ValueError("model bundle artifact URIs must be unique")
        missing = sorted(REQUIRED_MODEL_BUNDLE_ARTIFACTS - names)
        if missing:
            raise ValueError(f"model bundle is missing required artifacts: {', '.join(missing)}")
        return self

    def artifact_map(self) -> dict[str, ArtifactDigest]:
        return {artifact.logical_name: artifact for artifact in self.artifacts}


class DetectorPredictionsManifest(_CanonicalManifest):
    schema_version: Literal["detector_predictions_v1"] = "detector_predictions_v1"
    prediction_run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    binding: GovernedModelBinding
    calibration_id: str = Field(pattern=IDENTIFIER_PATTERN)
    created_at: AwareDatetime
    fold: FoldName
    operating_mode: OperatingMode
    threshold: float = Field(ge=0, le=1, allow_inf_nan=False)
    input_features: tuple[FoldFeatureInput, ...] = Field(min_length=1)
    predictions: ArtifactDigest
    row_count: int = Field(ge=1)
    alert_count: int = Field(ge=0)
    contains_raw_probabilities: Literal[True] = True
    contains_calibrated_probabilities: Literal[True] = True

    @model_validator(mode="after")
    def validate_prediction_counts(self) -> "DetectorPredictionsManifest":
        if self.alert_count > self.row_count:
            raise ValueError("alert count cannot exceed prediction row count")
        if any(item.fold != self.fold for item in self.input_features):
            raise ValueError("prediction feature inputs must match the declared fold")
        if any(item.artifact.schema_version != self.binding.feature_schema_version for item in self.input_features):
            raise ValueError("prediction feature inputs do not match the bound feature schema")
        if sum(item.row_count for item in self.input_features) != self.row_count:
            raise ValueError("prediction row count must equal its feature input rows")
        _require_unique_artifacts(tuple(item.artifact for item in self.input_features))
        if self.predictions.logical_name != "predictions":
            raise ValueError("prediction artifact logical name must be predictions")
        return self


def validate_phase_zero_compatibility(
    *,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    bundle: ModelBundleManifest,
    predictions: DetectorPredictionsManifest,
) -> None:
    expected = training.binding.identity_tuple()
    for name, manifest_binding in (
        ("calibration", calibration.binding),
        ("model bundle", bundle.binding),
        ("predictions", predictions.binding),
    ):
        if manifest_binding.identity_tuple() != expected:
            raise ValueError(f"{name} binding does not match the training run")
    if calibration.calibration_id != bundle.calibration_id:
        raise ValueError("model bundle calibration ID does not match the calibration manifest")
    if calibration.calibration_id != predictions.calibration_id:
        raise ValueError("prediction calibration ID does not match the calibration manifest")
    operating_points = {point.mode: point for point in calibration.operating_points}
    expected_threshold = operating_points[predictions.operating_mode].threshold
    if predictions.threshold != expected_threshold:
        raise ValueError("prediction threshold does not match the frozen calibration operating point")
    artifacts = bundle.artifact_map()
    if artifacts["model"].schema_version != bundle.model_format:
        raise ValueError("model artifact schema version does not match the bundle model format")
    if artifacts["model"] != training.model_artifact:
        raise ValueError("model bundle artifact does not match the training run")
    if artifacts["feature_schema"].schema_version != bundle.binding.feature_schema_version:
        raise ValueError("feature schema artifact does not match the bound feature schema")
    if artifacts["checksums"].schema_version != CHECKSUM_INVENTORY_SCHEMA_VERSION:
        raise ValueError("checksum artifact does not use the governed inventory schema")
    _require_manifest_binding(artifacts["training_manifest"], training, "training")
    _require_manifest_binding(artifacts["calibration_manifest"], calibration, "calibration")
    _require_manifest_binding(artifacts["prediction_manifest"], predictions, "prediction")
    if artifacts["predictions"] != predictions.predictions:
        raise ValueError("model bundle predictions artifact does not match the prediction manifest")


def _require_manifest_binding(
    artifact: ArtifactDigest,
    manifest: _CanonicalManifest,
    name: str,
) -> None:
    if artifact.sha256 != manifest.manifest_hash() or artifact.size_bytes != len(manifest.canonical_bytes()):
        raise ValueError(f"model bundle {name} manifest digest does not match its canonical content")
    if artifact.schema_version != manifest.schema_version:
        raise ValueError(f"model bundle {name} manifest schema version is invalid")


def _require_unique_artifacts(artifacts: Sequence[ArtifactDigest]) -> set[str]:
    names = [artifact.logical_name for artifact in artifacts]
    if len(names) != len(set(names)):
        raise ValueError("artifact logical names must be unique")
    return set(names)
