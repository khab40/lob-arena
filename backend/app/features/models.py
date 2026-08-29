from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

SourceType = Literal["lobster", "nasdaq_itch", "synthetic", "hybrid"]
LABEL_SCHEMA_VERSION = "feature_labels_v2"


class FeaturePipelineConfig(BaseModel):
    """Versioned causal-window and threshold configuration."""

    schema_version: Literal["lob_features_v1", "lob_features_v2"] = "lob_features_v2"
    short_window_ns: int = Field(default=2_000_000_000, gt=0)
    long_window_ns: int = Field(default=10_000_000_000, gt=0)
    depth_levels: int = Field(default=5, ge=1, le=100)
    zscore_min_periods: int = Field(default=5, ge=2)
    rapid_cancel_ns: int = Field(default=100_000_000, ge=0)
    replenishment_ns: int = Field(default=500_000_000, ge=0)
    burst_gap_ns: int = Field(default=10_000_000, ge=0)
    large_order_quantity: float = Field(default=1_000.0, gt=0, allow_inf_nan=False)
    wall_size_multiple: float = Field(default=3.0, gt=1.0, allow_inf_nan=False)
    layering_min_levels: int = Field(default=3, ge=2)
    fail_on_invalid_rows: bool = True

    @model_validator(mode="after")
    def validate_windows(self) -> "FeaturePipelineConfig":
        if self.short_window_ns >= self.long_window_ns:
            raise ValueError("short_window_ns must be smaller than long_window_ns")
        for field_name in ("rapid_cancel_ns", "replenishment_ns", "burst_gap_ns"):
            if getattr(self, field_name) > self.long_window_ns:
                raise ValueError(f"{field_name} must not exceed long_window_ns")
        return self

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def config_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class FeatureRunMetadata(BaseModel):
    """Run-level fields copied to every typed feature row."""

    run_id: str = Field(min_length=1)
    dataset_id: str | None = None
    source_type: SourceType
    historical_source_type: Literal["lobster", "nasdaq_itch"] | None = None
    instrument: str = Field(min_length=1)
    venue: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    session_date: date
    seed: int | None = Field(default=None, ge=0)
    price_tick_size: float = Field(gt=0, allow_inf_nan=False)
    quantity_lot_size: float = Field(gt=0, allow_inf_nan=False)
    tick_interval_ns: int = Field(default=500_000_000, gt=0)

    @model_validator(mode="after")
    def validate_source_provenance(self) -> "FeatureRunMetadata":
        if self.source_type in {"lobster", "nasdaq_itch"}:
            expected = self.source_type
            if self.historical_source_type not in {None, expected}:
                raise ValueError("historical feature source provenance is inconsistent")
            if self.historical_source_type is None:
                self.historical_source_type = expected
        if self.source_type == "synthetic" and self.historical_source_type is not None:
            raise ValueError("synthetic feature rows cannot claim a historical source")
        return self


class LabelWindow(BaseModel):
    label: Literal[0, 1] = 1
    attack_family: str | None = None
    label_source: str = Field(default="synthetic_scenario", min_length=1)
    provenance_id: str | None = Field(default=None, min_length=1)
    start_tick: int | None = Field(default=None, ge=0)
    end_tick: int | None = Field(default=None, ge=0)
    start_timestamp_ns: int | None = Field(default=None, ge=0)
    end_timestamp_ns: int | None = Field(default=None, ge=0)
    end_inclusive: bool = True
    phases: dict[str, tuple[int, int]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_bounds(self) -> "LabelWindow":
        tick_pair = self.start_tick is not None and self.end_tick is not None
        time_pair = self.start_timestamp_ns is not None and self.end_timestamp_ns is not None
        tick_present = self.start_tick is not None or self.end_tick is not None
        time_present = self.start_timestamp_ns is not None or self.end_timestamp_ns is not None
        if tick_present != tick_pair or time_present != time_pair:
            raise ValueError("label ranges require both start and end")
        if tick_pair == time_pair:
            raise ValueError("label window requires exactly one complete tick or timestamp range")
        if tick_pair and self.start_tick > self.end_tick:
            raise ValueError("label tick start must not exceed end")
        if time_pair and self.start_timestamp_ns > self.end_timestamp_ns:
            raise ValueError("label timestamp start must not exceed end")
        if not self.end_inclusive and (
            (tick_pair and self.start_tick == self.end_tick)
            or (time_pair and self.start_timestamp_ns == self.end_timestamp_ns)
        ):
            raise ValueError("half-open label windows must have positive width")
        if self.label == 1 and not self.attack_family:
            raise ValueError("positive label windows require an attack family")
        if self.label == 0 and self.attack_family is not None:
            raise ValueError("negative label windows cannot have an attack family")
        if self.label == 0 and self.phases:
            raise ValueError("negative label windows cannot have attack phases")
        if self.phases and not tick_pair:
            raise ValueError("label phases require tick bounds")
        ordered_phases: list[tuple[int, int, str]] = []
        for phase, bounds in self.phases.items():
            if not phase or bounds[0] > bounds[1]:
                raise ValueError("phase names must be non-empty and bounds ordered")
            if bounds[0] < self.start_tick or bounds[1] > self.end_tick:
                raise ValueError("label phases must stay within the label tick range")
            ordered_phases.append((bounds[0], bounds[1], phase))
        ordered_phases.sort()
        for previous, current in zip(ordered_phases, ordered_phases[1:], strict=False):
            if current[0] <= previous[1]:
                raise ValueError("label phases must not overlap")
        return self


class LabelSpec(BaseModel):
    """Separate ground truth; default_label is never inferred from market data."""

    schema_version: Literal["feature_labels_v1", "feature_labels_v2"] = LABEL_SCHEMA_VERSION
    labels: list[LabelWindow] = Field(default_factory=list)
    default_label: Literal[0, 1] | None = None
    default_attack_family: str | None = None
    default_label_source: str | None = None

    @model_validator(mode="after")
    def validate_default(self) -> "LabelSpec":
        if self.default_label is not None and not self.default_label_source:
            raise ValueError("an explicit default label requires default_label_source")
        if self.default_label == 1 and not self.default_attack_family:
            raise ValueError("a positive default label requires default_attack_family")
        if self.default_label == 0 and self.default_attack_family is not None:
            raise ValueError("a negative default label cannot have an attack family")
        for coordinate_system in ("tick", "timestamp"):
            ordered = sorted(
                (
                    (
                        window.start_tick if coordinate_system == "tick" else window.start_timestamp_ns,
                        window.end_tick if coordinate_system == "tick" else window.end_timestamp_ns,
                        window.end_inclusive,
                        window.provenance_id or "",
                    )
                    for window in self.labels
                    if (window.start_tick is not None) == (coordinate_system == "tick")
                )
            )
            for previous, current in zip(ordered, ordered[1:], strict=False):
                if current[0] < previous[1] or (
                    current[0] == previous[1] and previous[2]
                ):
                    raise ValueError("label windows must not overlap")
        return self

    def canonical_json(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))

    def spec_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


class AssignedLabel(BaseModel):
    label: Literal[0, 1] | None
    attack_family: str | None
    attack_phase: str | None
    label_source: str | None


def assign_label(
    spec: LabelSpec,
    *,
    tick: int,
    prediction_timestamp_ns: int,
) -> AssignedLabel:
    matches: list[LabelWindow] = []
    for window in spec.labels:
        tick_match = (
            window.start_tick is not None
            and window.end_tick is not None
            and window.start_tick <= tick
            and (tick <= window.end_tick if window.end_inclusive else tick < window.end_tick)
        )
        time_match = (
            window.start_timestamp_ns is not None
            and window.end_timestamp_ns is not None
            and window.start_timestamp_ns <= prediction_timestamp_ns
            and (
                prediction_timestamp_ns <= window.end_timestamp_ns
                if window.end_inclusive
                else prediction_timestamp_ns < window.end_timestamp_ns
            )
        )
        if tick_match or time_match:
            matches.append(window)
    if len(matches) > 1:
        provenance = sorted(window.provenance_id or "<unidentified>" for window in matches)
        raise ValueError(
            f"feature row matches multiple ground-truth windows: {', '.join(provenance)}"
        )
    if matches:
        window = matches[0]
        phase = next(
            (name for name, bounds in sorted(window.phases.items()) if bounds[0] <= tick <= bounds[1]),
            "attack" if window.label == 1 else "none",
        )
        return AssignedLabel(
            label=window.label,
            attack_family=window.attack_family if window.label == 1 else None,
            attack_phase=phase,
            label_source=window.label_source,
        )
    return AssignedLabel(
        label=spec.default_label,
        attack_family=spec.default_attack_family if spec.default_label == 1 else None,
        attack_phase="attack" if spec.default_label == 1 else "none" if spec.default_label == 0 else None,
        label_source=spec.default_label_source,
    )
