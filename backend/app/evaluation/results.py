from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SHA256_PATTERN = r"^[0-9a-f]{64}$"
INTERVAL_METRICS = frozenset(
    {
        "precision",
        "attack_level_recall",
        "f1",
        "false_alerts_per_million_events",
        "detection_before_benefit_rate",
        "duplicate_alert_load",
    }
)
HEADLINE_METRICS = frozenset(
    {
        "true_positive",
        "false_positive",
        "false_negative",
        "true_negative",
        "precision",
        "recall",
        "f1",
        "false_alerts_per_million_events",
        "attack_level_recall",
        "detection_before_benefit_rate",
        "duplicate_alert_load",
    }
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BenchmarkInputArtifact(_StrictModel):
    kind: str = Field(min_length=1)
    manifest: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    base_session_id: str | None = None
    run_id: str | None = None
    mode: Literal["historical_control", "synthetic", "hybrid"] | None = None
    campaign_id: str | None = None
    java_canonical_event_stream_hash: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )


class GovernedBenchmarkResults(_StrictModel):
    schema_version: Literal["governed_benchmark_results_v2"] = (
        "governed_benchmark_results_v2"
    )
    model_id: str = Field(min_length=1)
    protocol_id: str = Field(min_length=1)
    protocol_hash: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=1)
    corpus_hash: str = Field(pattern=SHA256_PATTERN)
    split_id: str = Field(min_length=1)
    assignment_hash: str = Field(pattern=SHA256_PATTERN)
    fold: Literal["train", "validation", "test"]
    metrics: dict[str, Any]
    confidence_intervals: dict[str, dict[str, Any]]
    paired_comparisons: dict[str, dict[str, Any]]
    regime_matrix: dict[str, Any]
    worst_decile: dict[str, Any]
    input_artifacts: list[BenchmarkInputArtifact] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_complete_result(self) -> "GovernedBenchmarkResults":
        if not HEADLINE_METRICS <= set(self.metrics):
            raise ValueError("benchmark results are missing governed headline metrics")
        if (
            set(self.confidence_intervals) != INTERVAL_METRICS
            or set(self.paired_comparisons) != INTERVAL_METRICS
        ):
            raise ValueError(
                "benchmark results require confidence intervals and paired comparisons "
                "for every governed interval metric"
            )
        if self.regime_matrix.get("schema_version") != "regime_metric_matrix_v1":
            raise ValueError("benchmark results require a governed regime matrix")
        if self.worst_decile.get("schema_version") != "worst_decile_results_v1":
            raise ValueError("benchmark results require governed worst-decile results")
        return self
