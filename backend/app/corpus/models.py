from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PROTOCOL_SCHEMA_VERSION = "governed_benchmark_protocol_v1"


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CorpusMinimums(_StrictModel):
    complete_sessions: int = Field(default=30, ge=1)
    instruments: int = Field(default=3, ge=1)
    distinct_dates: int = Field(default=10, ge=1)
    seeds_per_attack_family: int = Field(default=3, ge=1)
    require_all_attack_families: bool = True
    required_attack_families: tuple[str, ...] = (
        "spoofing_like_wall",
        "layering_like",
        "quote_stuffing",
    )

    @model_validator(mode="after")
    def validate_attack_families(self) -> "CorpusMinimums":
        if not self.required_attack_families or any(not value for value in self.required_attack_families):
            raise ValueError("at least one non-empty required attack family is required")
        if len(set(self.required_attack_families)) != len(self.required_attack_families):
            raise ValueError("required attack families must be unique")
        return self


class CleanLabelPolicy(_StrictModel):
    independent_reviewers: int = Field(default=2, ge=2)
    blind_to_model_outputs: Literal[True] = True
    conflicts_require_adjudicator: Literal[True] = True
    historical_default_label: None = None
    transferable_to_hybrid_only_after_exact_equivalence: Literal[True] = True
    statuses: tuple[str, ...] = (
        "unreviewed",
        "candidate_clean",
        "verified_clean",
        "ambiguous",
        "excluded",
        "synthetic_attack",
    )

    @model_validator(mode="after")
    def validate_status_contract(self) -> "CleanLabelPolicy":
        required = {
            "unreviewed",
            "candidate_clean",
            "verified_clean",
            "ambiguous",
            "excluded",
            "synthetic_attack",
        }
        if set(self.statuses) != required or len(self.statuses) != len(required):
            raise ValueError("clean-label statuses must contain the complete unique governed status set")
        return self


class SplitPolicy(_StrictModel):
    strategy: Literal["chronological_session_grouped_purged"] = "chronological_session_grouped_purged"
    group_fields: tuple[str, ...] = ("venue", "instrument", "session_date", "session_id")
    keep_all_session_campaigns_together: Literal[True] = True
    purge_feature_window_ns: int = Field(default=10_000_000_000, ge=0)
    purge_alert_horizon_ns: int = Field(default=5_000_000_000, ge=0)
    purge_causal_tail_ns: int = Field(default=10_000_000_000, ge=0)
    purge_label_uncertainty_ns: int = Field(default=0, ge=0)
    embargo_sessions: int = Field(default=1, ge=0)
    train_fraction: float = Field(default=0.6, gt=0, lt=1, allow_inf_nan=False)
    validation_fraction: float = Field(default=0.2, gt=0, lt=1, allow_inf_nan=False)
    test_fraction: float = Field(default=0.2, gt=0, lt=1, allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_split_contract(self) -> "SplitPolicy":
        required_fields = {"venue", "instrument", "session_date", "session_id"}
        if not required_fields.issubset(self.group_fields):
            raise ValueError("split group must bind venue, instrument, session date, and session id")
        if len(set(self.group_fields)) != len(self.group_fields):
            raise ValueError("split group fields must be unique")
        total = self.train_fraction + self.validation_fraction + self.test_fraction
        if abs(total - 1.0) > 1e-12:
            raise ValueError("train, validation, and test fractions must sum to one")
        return self

    @property
    def purge_ns(self) -> int:
        return max(
            self.purge_feature_window_ns,
            self.purge_alert_horizon_ns,
            self.purge_causal_tail_ns,
            self.purge_label_uncertainty_ns,
        )


class BootstrapPolicy(_StrictModel):
    method: Literal["session_cluster_percentile"] = "session_cluster_percentile"
    resamples: int = Field(default=2_000, ge=100)
    confidence_level: float = Field(default=0.95, gt=0, lt=1, allow_inf_nan=False)
    seed: int = Field(default=20260726, ge=0)
    paired_comparisons: Literal[True] = True


class MetricPolicy(_StrictModel):
    alert_deduplication_window_ns: int = Field(default=1_000_000_000, ge=0)
    minimum_regime_cell_count: int = Field(default=10, ge=1)
    false_alert_denominator: Literal["evaluable_canonical_events"] = "evaluable_canonical_events"
    attack_recall_unit: Literal["campaign"] = "campaign"
    require_realized_benefit_event: Literal[True] = True
    report_raw_and_deduplicated_alerts: Literal[True] = True
    worst_decile_fraction: float = Field(default=0.1, gt=0, le=0.5, allow_inf_nan=False)


class StreamingPolicy(_StrictModel):
    event_chunk_size: int = Field(default=50_000, ge=1)
    parquet_row_group_size: int = Field(default=25_000, ge=1)
    quantile_sketch: Literal["deterministic_priority_sample_v1"] = "deterministic_priority_sample_v1"
    quantile_sample_size: int = Field(default=2_048, ge=128)
    max_memory_growth_fraction: float = Field(default=0.2, ge=0, allow_inf_nan=False)
    require_chunk_size_equivalence: Literal[True] = True


class GovernedBenchmarkProtocol(_StrictModel):
    schema_version: Literal["governed_benchmark_protocol_v1"] = PROTOCOL_SCHEMA_VERSION
    protocol_id: str = Field(min_length=1)
    corpus: CorpusMinimums = Field(default_factory=CorpusMinimums)
    clean_labels: CleanLabelPolicy = Field(default_factory=CleanLabelPolicy)
    splits: SplitPolicy = Field(default_factory=SplitPolicy)
    bootstrap: BootstrapPolicy = Field(default_factory=BootstrapPolicy)
    metrics: MetricPolicy = Field(default_factory=MetricPolicy)
    streaming: StreamingPolicy = Field(default_factory=StreamingPolicy)
    canonical_event_schema_version: int = Field(default=1, ge=1)
    feature_schema_version: str = Field(default="lob_features_v1", min_length=1)
    freeze_test_before_training: Literal[True] = True
    require_signed_release_manifest: Literal[True] = True

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def protocol_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def load_benchmark_protocol(path: Path) -> GovernedBenchmarkProtocol:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return GovernedBenchmarkProtocol.model_validate(payload)
