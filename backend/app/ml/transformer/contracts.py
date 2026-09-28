from __future__ import annotations

import hashlib
import json
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StrictInt, model_validator

from app.features.pipeline import FEATURE_COLUMNS
from app.market_data.projections import FrozenPublicSampleRoot, TabularProjectionShard

Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Count = Annotated[StrictInt, Field(ge=0)]
LENGTH = 64


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode()

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class InputContract(Record):
    schema_version: Literal["transformer_input_v1"] = "transformer_input_v1"
    root: FrozenPublicSampleRoot
    tabular_manifest_sha256: Digest
    sequence_manifest_sha256: Digest
    ordered_features: tuple[str, ...] = FEATURE_COLUMNS
    sequence_length: Literal[64] = LENGTH
    stride: Literal[1] = 1
    access_scope: Literal["development"] = "development"
    target_semantics: Literal["unchanged_governed_tabular_label"] = "unchanged_governed_tabular_label"
    training_shards: tuple[TabularProjectionShard, ...]
    valid_step_true_means: Literal["observed_step"] = "observed_step"
    missing_true_means: Literal["unknown_feature_on_observed_step"] = "unknown_feature_on_observed_step"

    @model_validator(mode="after")
    def check(self):
        if self.ordered_features != FEATURE_COLUMNS:
            raise ValueError("ordered feature schema changed")
        if not self.training_shards or any(s.fold != "train" for s in self.training_shards):
            raise ValueError("normalization binding requires training shards only")
        return self

    def training_binding(self) -> str:
        # Full projection hashes include validation; fitting identity must not.
        value = {"root": self.root.canonical_hash(), "features": self.ordered_features,
                 "shards": [s.model_dump(mode="json") for s in self.training_shards]}
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Normalization(Record):
    schema_version: Literal["transformer_normalization_v1"] = "transformer_normalization_v1"
    algorithm: Literal["unique_train_rows_welford_population_v1"] = "unique_train_rows_welford_population_v1"
    training_binding_sha256: Digest
    fitting_row_sha256: Digest
    fitting_rows: Annotated[StrictInt, Field(gt=0)]
    observed_counts: tuple[Count, ...]
    means: tuple[FiniteFloat, ...]
    scales: tuple[FiniteFloat, ...]

    @model_validator(mode="after")
    def check(self):
        if any(len(v) != len(FEATURE_COLUMNS) for v in (self.means, self.scales, self.observed_counts)):
            raise ValueError("normalization feature dimension changed")
        for count, mean, scale in zip(self.observed_counts, self.means, self.scales, strict=True):
            if count > self.fitting_rows or scale <= 0:
                raise ValueError("invalid normalization statistics")
            if count == 0 and (mean != 0 or scale != 1):
                raise ValueError("wholly missing training features require mean 0 and scale 1")
        return self
