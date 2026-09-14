"""C4-specific, frozen-threshold evaluation on paired supervised observations.

This contract is deliberately distinct from the seven-date governed benchmark.
It never fits a model, recalibrates probabilities, selects a threshold, or calls
observation counts canonical-event counts. Rules decisions must be supplied by
the verified canonical-replay adapter, not reconstructed from model features.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from collections import defaultdict
from collections.abc import Iterable
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

C4_METRIC_NAMES = (
    frozenset(
        f"{detector}.{metric}"
        for detector in ("lightgbm", "rules")
        for metric in (
            "row_precision",
            "row_recall",
            "row_f1",
            "false_alerts_per_million_observations",
            "negative_row_false_positive_rate",
            "observed_campaign_recall",
        )
    )
    | frozenset(
        f"delta.lightgbm_minus_rules.{metric}"
        for metric in (
            "row_precision",
            "row_recall",
            "row_f1",
            "false_alerts_per_million_observations",
            "observed_campaign_recall",
        )
    )
    | frozenset(f"lightgbm.{score}_{metric}" for score in ("raw", "calibrated") for metric in ("brier", "ece"))
)


class C4EvaluationInputs(BaseModel):
    """Evidence locations, not assertions that evaluation has been verified."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    profile: Path
    frozen_root: Path
    projection: Path
    comparison: Path
    candidate: Path
    source_result: Path | None = None

    @classmethod
    def from_file(cls, path: Path) -> "C4EvaluationInputs":
        inputs = cls.model_validate_json(path.read_bytes())
        return cls(
            **{
                name: (path.parent / value).resolve() if value is not None else None
                for name, value in inputs.model_dump().items()
            }
        )


class C4EvaluationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["g8_c4_evaluation_profile_v1"] = "g8_c4_evaluation_profile_v1"
    candidate_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    frozen_root_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    projection_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    comparison_evidence_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    observation_unit: Literal["supervised_projection_row"] = "supervised_projection_row"
    negative_label_source: Literal["research_control_assumption"] = "research_control_assumption"
    rules_policy: Literal["canonical_java_rules_union_at_same_tick"] = "canonical_java_rules_union_at_same_tick"
    calibration_bins: Literal[10] = 10
    bootstrap_resamples: Literal[2000] = 2000
    bootstrap_seed: Literal[20260828] = 20260828
    confidence_level: Literal[0.95] = 0.95
    cluster_unit: Literal["base_session_id"] = "base_session_id"
    seven_date_benchmark_compliance: Literal[False] = False

    def canonical_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        ).hexdigest()


def _new_stats() -> np.ndarray:
    # Rows, TP/FP/FN/TN for each detector, raw/calibrated squared error,
    # followed by count/probability/positive sums in ten bins for each score.
    return np.zeros(71, dtype=np.float64)


def _ratio(numerator: float, denominator: float) -> float | None:
    return float(numerator / denominator) if denominator else None


def _metrics(stats: np.ndarray) -> dict[str, float | None]:
    metrics = {}
    for name, offset in (("lightgbm", 1), ("rules", 5)):
        tp, fp, fn, tn = stats[offset : offset + 4]
        metrics.update(
            {
                f"{name}.row_precision": _ratio(tp, tp + fp),
                f"{name}.row_recall": _ratio(tp, tp + fn),
                f"{name}.row_f1": _ratio(2 * tp, 2 * tp + fp + fn),
                f"{name}.false_alerts_per_million_observations": _ratio(fp * 1_000_000, stats[0]),
                f"{name}.negative_row_false_positive_rate": _ratio(fp, fp + tn),
            }
        )
    for name, error_offset, bin_offset in (("raw", 9, 11), ("calibrated", 10, 41)):
        bins = stats[bin_offset : bin_offset + 30].reshape(10, 3)
        metrics[f"lightgbm.{name}_brier"] = _ratio(stats[error_offset], stats[0])
        metrics[f"lightgbm.{name}_ece"] = _ratio(np.abs(bins[:, 1] - bins[:, 2]).sum(), stats[0])
    for metric in ("row_precision", "row_recall", "row_f1", "false_alerts_per_million_observations"):
        left, right = metrics[f"lightgbm.{metric}"], metrics[f"rules.{metric}"]
        metrics[f"delta.lightgbm_minus_rules.{metric}"] = None if left is None or right is None else left - right
    return metrics


def evaluate_c4_observations(
    rows: Iterable[dict],
    *,
    profile: C4EvaluationProfile,
    frozen_threshold: float,
) -> dict:
    """Consume a verified one-to-one join; bounded memory is per session/campaign.

    The caller must ensure unique row identities and checksum-bind the join to
    both the projection and the canonical replay evidence. This pure accumulator
    validates decisions and labels but is not itself a provenance verifier.
    """
    if not math.isfinite(frozen_threshold) or not 0 <= frozen_threshold <= 1:
        raise ValueError("frozen threshold must be a finite probability")
    sessions = defaultdict(_new_stats)
    families = defaultdict(lambda: {"positive_rows": 0, "lightgbm_hits": 0, "rules_hits": 0})
    campaigns = {}
    edges = np.linspace(0.0, 1.0, profile.calibration_bins + 1)
    for row in rows:
        session, run_id = row.get("base_session_id"), row.get("run_id")
        label, decision, rule = row.get("label"), row.get("alert"), row.get("rules_alert")
        raw, calibrated = row.get("raw_probability"), row.get("calibrated_probability")
        if not isinstance(session, str) or not session or not isinstance(run_id, str) or not run_id:
            raise ValueError("paired observations require session and replay identities")
        if type(label) is not int or label not in (0, 1) or type(decision) is not bool or type(rule) is not bool:
            raise ValueError("paired observations require binary labels and boolean decisions")
        if any(type(p) not in (float, int) or not math.isfinite(p) or not 0 <= p <= 1 for p in (raw, calibrated)):
            raise ValueError("paired observations require finite raw and calibrated probabilities")
        if row.get("threshold") != frozen_threshold or decision != (calibrated >= frozen_threshold):
            raise ValueError("prediction decision differs from the frozen operating threshold")
        if row.get("fold") != "test":
            raise ValueError("C4 evaluation accepts only held-out test observations")
        expected_label_source = "synthetic_scenario" if label else "research_control_assumption"
        if row.get("label_source") != expected_label_source:
            raise ValueError("C4 observation label provenance changed")
        stats = sessions[session]
        stats[0] += 1
        for alert, offset in ((decision, 1), (rule, 5)):
            index = (0 if alert else 2) if label else (1 if alert else 3)
            stats[offset + index] += 1
        for probability, error_offset, bin_offset in ((raw, 9, 11), (calibrated, 10, 41)):
            stats[error_offset] += (probability - label) ** 2
            index = min(int(np.searchsorted(edges, probability, side="right") - 1), profile.calibration_bins - 1)
            stats[bin_offset + index * 3 : bin_offset + index * 3 + 3] += (1, probability, label)
        if label:
            family, campaign = row.get("attack_family"), row.get("campaign_id")
            if not isinstance(family, str) or not family or not isinstance(campaign, str) or not campaign:
                raise ValueError("attack observations require family and campaign identity")
            family_stats = families[family]
            family_stats["positive_rows"] += 1
            family_stats["lightgbm_hits"] += decision
            family_stats["rules_hits"] += rule
            key = (session, campaign)
            state = campaigns.setdefault(key, {"run_id": run_id, "family": family, "lightgbm": False, "rules": False})
            if state["run_id"] != run_id or state["family"] != family:
                raise ValueError("campaign identity spans inconsistent replay/family domains")
            state["lightgbm"] |= decision
            state["rules"] |= rule
    if not sessions:
        raise ValueError("C4 evaluation has no paired observations")
    session_names = sorted(sessions)
    matrix = np.stack([sessions[name] for name in session_names])
    totals = matrix.sum(axis=0)
    metrics = _metrics(totals)
    # Campaign recall is explicitly limited to campaigns with retained positive
    # observations; zero-positive campaigns must be reported by the join adapter.
    campaign_matrix = np.array(
        [
            [
                sum(s == name for s, _ in campaigns),
                sum(state["lightgbm"] for (s, _), state in campaigns.items() if s == name),
                sum(state["rules"] for (s, _), state in campaigns.items() if s == name),
            ]
            for name in session_names
        ]
    )

    def campaign_metrics(counts):
        total, lightgbm, rules = counts
        return {
            "lightgbm.observed_campaign_recall": _ratio(lightgbm, total),
            "rules.observed_campaign_recall": _ratio(rules, total),
            "delta.lightgbm_minus_rules.observed_campaign_recall": _ratio(lightgbm - rules, total),
        }

    metrics.update(campaign_metrics(campaign_matrix.sum(axis=0)))
    intervals = {}
    if len(sessions) > 1:
        rng = np.random.default_rng(profile.bootstrap_seed)
        draws = defaultdict(list)
        for _ in range(profile.bootstrap_resamples):
            selected = rng.integers(0, len(sessions), size=len(sessions))
            values = _metrics(matrix[selected].sum(axis=0))
            values.update(campaign_metrics(campaign_matrix[selected].sum(axis=0)))
            for name, value in values.items():
                if value is not None:
                    draws[name].append(value)
        for name in metrics:
            values = draws[name]
            intervals[name] = {
                "lower": float(np.quantile(values, 0.025)) if values else None,
                "upper": float(np.quantile(values, 0.975)) if values else None,
                "valid_resamples": len(values),
                "undefined_resamples": profile.bootstrap_resamples - len(values),
            }
    reliability = {}
    for name, start in (("raw", 11), ("calibrated", 41)):
        reliability[name] = [
            {
                "lower": i / 10,
                "upper": (i + 1) / 10,
                "count": int(count),
                "mean_probability": _ratio(probability, count),
                "positive_rate": _ratio(positive, count),
            }
            for i, (count, probability, positive) in enumerate(totals[start : start + 30].reshape(10, 3))
        ]
    return {
        "schema_version": "g8_c4_observation_metrics_v1",
        "evaluation_profile_sha256": profile.canonical_hash(),
        "candidate_sha256": profile.candidate_sha256,
        "frozen_threshold": frozen_threshold,
        "observation_unit": profile.observation_unit,
        "negative_label_source": profile.negative_label_source,
        "row_count": int(totals[0]),
        "session_count": len(sessions),
        "observed_campaign_count": len(campaigns),
        "metrics": metrics,
        "reliability_bins": reliability,
        "confusion_counts": {
            name: dict(
                zip(
                    ("true_positive", "false_positive", "false_negative", "true_negative"),
                    map(int, totals[offset : offset + 4]),
                    strict=True,
                )
            )
            for name, offset in (("lightgbm", 1), ("rules", 5))
        },
        "family_recall": {
            name: {
                **counts,
                "lightgbm_recall": counts["lightgbm_hits"] / counts["positive_rows"],
                "rules_recall": counts["rules_hits"] / counts["positive_rows"],
            }
            for name, counts in sorted(families.items())
        },
        "uncertainty": {
            "method": "paired_session_cluster_percentile",
            "confidence_level": 0.95,
            "resamples": profile.bootstrap_resamples,
            "seed": profile.bootstrap_seed,
            "cluster_count": len(sessions),
            "support": "insufficient"
            if len(sessions) == 1
            else "limited"
            if len(sessions) < 10
            else "session_conditional",
            "scope": "conditional_on_observed_sessions_not_temporal_generalization",
            "intervals": intervals,
        },
        "not_computed": [
            "false_alerts_per_million_canonical_events",
            "detection_before_realized_benefit",
            "full_seven_date_benchmark_qualification",
        ],
        "seven_date_benchmark_compliance": False,
    }
