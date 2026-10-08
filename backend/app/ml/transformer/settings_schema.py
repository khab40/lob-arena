"""Research settings metadata; deliberately imports no model or cloud client."""
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictBool, StrictInt, model_validator

from app.features.pipeline import FEATURE_COLUMNS
from .contracts import Digest, Record
from .research_policy import Trial


class SettingsRecord(Record):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class Artifact(BaseModel):
    model_config = SettingsRecord.model_config
    uri: str
    version_id: Annotated[str, Field(min_length=1, max_length=128)]
    size_bytes: Annotated[StrictInt, Field(gt=0, le=64 * 1024 * 1024)]
    sha256: Digest

    @model_validator(mode="after")
    def location(self):
        if self.uri == "evidence:sha256:" + self.sha256:
            if self.version_id != "content-addressed":
                raise ValueError("evidence must be content addressed")
            return self
        parts = urlsplit(self.uri)
        if (parts.scheme != "s3" or not parts.netloc or not parts.path.strip("/")
                or parts.query or parts.fragment or parts.username or parts.password
                or any(p in ("", ".", "..") for p in parts.path[1:].split("/"))
                or "%" in self.uri or "\\" in self.uri or any(c.isspace() for c in self.uri)):
            raise ValueError("plain exact S3 object URI required")
        return self


class Artifacts(SettingsRecord):
    checkpoint: Artifact
    contract: Artifact
    normalization: Artifact
    verification: Artifact
    selection_verification: Artifact
    comparison_summary: Artifact
    decision: Artifact


class TrainingSettings(SettingsRecord):
    width: StrictInt
    learning_rate: FiniteFloat
    seed: StrictInt
    max_epochs: StrictInt = 30
    batch_size: StrictInt = 64
    patience: StrictInt = 5
    optimizer: Literal["AdamW"] = "AdamW"
    weight_decay: Literal[0.01] = 0.01
    betas: tuple[Literal[0.9], Literal[0.999]] = (0.9, 0.999)
    epsilon: Literal[1e-8] = 1e-8
    schedule: Literal["warmup_5pct_cosine_to_0.1"] = "warmup_5pct_cosine_to_0.1"
    gradient_clip: Literal[1.0] = 1.0
    weighting: Literal["equal_class_then_base_session"] = "equal_class_then_base_session"
    selection: Literal["S_log_loss_min_delta_1e-6"] = "S_log_loss_min_delta_1e-6"

    @model_validator(mode="after")
    def fixed_grid(self):
        Trial(**{k: getattr(self, k) for k in Trial.__dataclass_fields__})
        return self


class Architecture(SettingsRecord):
    name: Literal["SequenceClassifier_v1"] = "SequenceClassifier_v1"
    input_dimension: Literal[120] = 120
    blocks: Literal[2] = 2
    heads: Literal[4] = 4
    ffn_ratio: Literal[4] = 4
    dropout: Literal[0.1] = 0.1
    activation: Literal["GELU"] = "GELU"
    position: Literal["sinusoidal_64_base_10000"] = "sinusoidal_64_base_10000"
    pooling: Literal["last_valid_token"] = "last_valid_token"
    precision: Literal["float32"] = "float32"
    normalization: Literal["pre_norm_and_final_layer_norm"] = "pre_norm_and_final_layer_norm"
    output: Literal["one_binary_logit"] = "one_binary_logit"


class Preprocessing(SettingsRecord):
    ordered_features: tuple[str, ...]
    sequence_length: Literal[64] = 64
    stride: Literal[1] = 1
    cutoff: Literal["prediction_timestamp_ns_then_sequence"] = "prediction_timestamp_ns_then_sequence"
    history_reset: Literal["per_replay_shard"] = "per_replay_shard"
    padding: Literal["left_zero_invalid"] = "left_zero_invalid"
    valid_true: Literal["observed_step"] = "observed_step"
    missing_true: Literal["unknown_feature_on_observed_step"] = "unknown_feature_on_observed_step"
    missing_values: Literal["zero_after_normalization_plus_indicator"] = "zero_after_normalization_plus_indicator"
    normalization: Literal["unique_train_rows_welford_population_v1"] = "unique_train_rows_welford_population_v1"

    @model_validator(mode="after")
    def order(self):
        if self.ordered_features != FEATURE_COLUMNS:
            raise ValueError("ordered feature schema changed")
        return self


class OperatingPoint(SettingsRecord):
    mode: Literal["high_precision", "balanced", "high_recall"]
    threshold: Annotated[FiniteFloat, Field(ge=0, le=1)]


class Lineage(SettingsRecord):
    feature_release_id: str
    feature_release_sha256: Digest
    feature_config_sha256: Digest
    root_sha256: Digest
    training_binding_sha256: Digest
    trial_sha256: Digest
    selected_epoch: Annotated[StrictInt, Field(ge=1, le=30)]
    numerical_source_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    training_image_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    selection_request_sha256: Digest
    selection_job_id: str
    selection_run_id: str
    comparison_request_sha256: Digest
    comparison_job_id: str
    comparison_run_id: str
    comparison_source_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    comparison_image_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    role_manifest_sha256: Digest
    train_targets_sha256: Digest
    selection_targets_sha256: Digest
    calibration_targets_sha256: Digest
    operating_point_targets_sha256: Digest
    mlflow: Literal["pending_reconciliation"] = "pending_reconciliation"


class SettingsRelease(SettingsRecord):
    schema_version: Literal["transformer_selected_settings_v1"] = "transformer_selected_settings_v1"
    scope: Literal["research_only"] = "research_only"
    artifacts: Artifacts
    training: TrainingSettings
    architecture: Architecture = Architecture()
    preprocessing: Preprocessing
    lineage: Lineage
    temperature: Annotated[FiniteFloat, Field(ge=0.05, le=20)] | None
    operating_points: tuple[OperatingPoint, ...]
    selected_mode: Literal["balanced"] = "balanced"
    decision: Literal["continue_research", "stop_transformer", "inconclusive"]
    gates_passed: StrictBool
    limitations: tuple[str, ...]

    @property
    def release_id(self):
        return "transformer-research-" + self.sha256()

    def require_research_inference(self):
        if (self.decision != "continue_research" or not self.gates_passed or self.temperature is None
                or tuple(p.mode for p in self.operating_points) != ("high_precision", "balanced", "high_recall")):
            raise ValueError("research inference blocked: decision, calibration or operating-point gate")

    def require_serving(self):
        self.require_research_inference()
        raise ValueError("production serving requires separate qualification and authorization")
