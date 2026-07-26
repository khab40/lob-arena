from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.evaluation.governed_metrics import (
    SessionMetricComponents,
    aggregate_governed_metrics,
)


REGIME_FEATURES = (
    "liquidity_score",
    "realized_volatility_long",
    "spread_bps",
    "message_rate_long",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RegimeFitRow(_StrictModel):
    base_session_id: str = Field(min_length=1)
    split: Literal["train"]
    control_or_pre_attack: Literal[True]
    feature_schema_version: str = Field(min_length=1)
    feature_config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    liquidity_score: float = Field(allow_inf_nan=False)
    realized_volatility_long: float = Field(ge=0, allow_inf_nan=False)
    spread_bps: float = Field(ge=0, allow_inf_nan=False)
    message_rate_long: float = Field(ge=0, allow_inf_nan=False)


class RegimeBoundary(_StrictModel):
    lower: float = Field(allow_inf_nan=False)
    upper: float = Field(allow_inf_nan=False)

    @model_validator(mode="after")
    def validate_order(self) -> "RegimeBoundary":
        if self.lower > self.upper:
            raise ValueError("regime lower boundary must not exceed upper")
        return self


class RegimeThresholdManifest(_StrictModel):
    schema_version: Literal["regime_thresholds_v1"] = "regime_thresholds_v1"
    feature_schema_version: str = Field(min_length=1)
    feature_config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    fit_split: Literal["train"] = "train"
    fit_source: Literal["control_or_pre_attack"] = "control_or_pre_attack"
    fit_row_count: int = Field(ge=3)
    fit_input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    boundaries: dict[str, RegimeBoundary]

    @model_validator(mode="after")
    def validate_complete_features(self) -> "RegimeThresholdManifest":
        if set(self.boundaries) != set(REGIME_FEATURES):
            raise ValueError("regime threshold manifest must contain every governed regime feature")
        return self


class GovernedRegimeEvidence(_StrictModel):
    schema_version: Literal["governed_regime_evidence_v1"] = "governed_regime_evidence_v1"
    protocol_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    corpus_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    assignment_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    fit_session_ids: list[str] = Field(min_length=1)
    fit_rows: list[RegimeFitRow] = Field(min_length=3)
    thresholds: RegimeThresholdManifest
    target_features: dict[str, dict[str, float]] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_frozen_thresholds(self) -> "GovernedRegimeEvidence":
        if self.thresholds != fit_regime_thresholds(self.fit_rows):
            raise ValueError("regime thresholds do not match the supplied training-control rows")
        if (
            len(self.fit_session_ids) != len(set(self.fit_session_ids))
            or set(self.fit_session_ids) != {row.base_session_id for row in self.fit_rows}
        ):
            raise ValueError("regime fit session inventory does not match fit rows")
        if any(set(features) != set(REGIME_FEATURES) for features in self.target_features.values()):
            raise ValueError("target regime evidence must contain exactly the governed features")
        return self


def fit_regime_thresholds(rows: list[RegimeFitRow]) -> RegimeThresholdManifest:
    if len(rows) < 3:
        raise ValueError("regime fitting requires at least three training control rows")
    schema_versions = {row.feature_schema_version for row in rows}
    config_hashes = {row.feature_config_hash for row in rows}
    if len(schema_versions) != 1 or len(config_hashes) != 1:
        raise ValueError("regime fitting requires one feature schema and configuration")
    boundaries = {
        name: RegimeBoundary(
            lower=_percentile(sorted(getattr(row, name) for row in rows), 1 / 3),
            upper=_percentile(sorted(getattr(row, name) for row in rows), 2 / 3),
        )
        for name in REGIME_FEATURES
    }
    canonical_rows = [
        row.model_dump(mode="json")
        for row in sorted(
            rows,
            key=lambda item: tuple(getattr(item, name) for name in REGIME_FEATURES),
        )
    ]
    input_hash = hashlib.sha256(
        json.dumps(canonical_rows, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return RegimeThresholdManifest(
        feature_schema_version=next(iter(schema_versions)),
        feature_config_hash=next(iter(config_hashes)),
        fit_row_count=len(rows),
        fit_input_hash=input_hash,
        boundaries=boundaries,
    )


def assign_regimes(
    features: dict[str, float],
    thresholds: RegimeThresholdManifest,
) -> dict[str, str]:
    for name in REGIME_FEATURES:
        value = features.get(name)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
            raise ValueError(f"regime assignment requires finite feature: {name}")
    return {
        "liquidity": _bucket(
            features["liquidity_score"],
            thresholds.boundaries["liquidity_score"],
            ("thin", "normal", "deep"),
        ),
        "volatility": _bucket(
            features["realized_volatility_long"],
            thresholds.boundaries["realized_volatility_long"],
            ("low", "normal", "high"),
        ),
        "spread": _bucket(
            features["spread_bps"],
            thresholds.boundaries["spread_bps"],
            ("tight", "normal", "wide"),
        ),
        "message_intensity": _bucket(
            features["message_rate_long"],
            thresholds.boundaries["message_rate_long"],
            ("quiet", "normal", "busy"),
        ),
    }


def regime_metric_matrix(
    sessions: list[SessionMetricComponents],
    *,
    minimum_cell_count: int,
) -> dict[str, Any]:
    if minimum_cell_count < 1:
        raise ValueError("regime matrix minimum cell count must be positive")
    dimensions = sorted({name for session in sessions for name in session.regimes})
    matrix: dict[str, Any] = {}
    for dimension in dimensions:
        groups: dict[str, list[SessionMetricComponents]] = defaultdict(list)
        for session in sessions:
            value = session.regimes.get(dimension)
            if value is not None:
                groups[value].append(session)
        matrix[dimension] = {
            value: _regime_cell(items, minimum_cell_count)
            for value, items in sorted(groups.items())
        }
    if {"liquidity", "volatility"} <= set(dimensions):
        groups = defaultdict(list)
        for session in sessions:
            key = f"{session.regimes['liquidity']}|{session.regimes['volatility']}"
            groups[key].append(session)
        matrix["liquidity_x_volatility"] = {
            value: _regime_cell(items, minimum_cell_count)
            for value, items in sorted(groups.items())
        }
    return {
        "schema_version": "regime_metric_matrix_v1",
        "minimum_cell_count": minimum_cell_count,
        "dimensions": matrix,
    }


def worst_decile_results(
    sessions: list[SessionMetricComponents],
    *,
    metric_directions: dict[str, Literal["lower", "higher"]],
    fraction: float = 0.1,
) -> dict[str, Any]:
    if not sessions:
        raise ValueError("worst-decile analysis requires sessions")
    if not 0 < fraction <= 0.5:
        raise ValueError("worst-decile fraction must be between zero and one half")
    output: dict[str, Any] = {}
    for metric, direction in metric_directions.items():
        values: list[tuple[float, str, SessionMetricComponents]] = []
        for session in sessions:
            payload = aggregate_governed_metrics([session])
            value = payload.get(metric)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                values.append((float(value), session.base_session_id, session))
        reverse = direction == "higher"
        ordered = sorted(values, key=lambda item: (item[0], item[1]), reverse=reverse)
        count = max(1, math.ceil(len(ordered) * fraction)) if ordered else 0
        selected = ordered[:count]
        output[metric] = {
            "worse_direction": direction,
            "eligible_session_count": len(ordered),
            "selected_session_count": count,
            "session_ids": [item[1] for item in selected],
            "values": [item[0] for item in selected],
            "aggregate": (
                aggregate_governed_metrics([item[2] for item in selected])
                if selected
                else None
            ),
        }
    return {
        "schema_version": "worst_decile_results_v1",
        "fraction": fraction,
        "metrics": output,
    }


def _regime_cell(
    sessions: list[SessionMetricComponents],
    minimum_cell_count: int,
) -> dict[str, Any]:
    sufficient = len(sessions) >= minimum_cell_count
    return {
        "session_count": len(sessions),
        "sufficient": sufficient,
        "metrics": aggregate_governed_metrics(sessions) if sufficient else None,
    }


def _bucket(
    value: float,
    boundary: RegimeBoundary,
    names: tuple[str, str, str],
) -> str:
    if value < boundary.lower:
        return names[0]
    if value <= boundary.upper:
        return names[1]
    return names[2]


def _percentile(values: list[float], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight
