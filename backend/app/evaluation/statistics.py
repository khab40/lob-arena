from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any

from app.evaluation.governed_metrics import (
    SessionMetricComponents,
    aggregate_governed_metrics,
)


@dataclass(frozen=True)
class ConfidenceInterval:
    point_estimate: float | None
    lower: float | None
    upper: float | None
    confidence_level: float
    resamples: int
    cluster_unit: str = "base_session"


def session_cluster_bootstrap(
    sessions: list[SessionMetricComponents],
    *,
    metric: str,
    resamples: int = 2_000,
    confidence_level: float = 0.95,
    seed: int = 0,
) -> ConfidenceInterval:
    if not sessions:
        raise ValueError("session bootstrap requires at least one session")
    if resamples < 100:
        raise ValueError("session bootstrap requires at least 100 resamples")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence level must be between zero and one")
    point = _numeric_metric(aggregate_governed_metrics(sessions), metric)
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(resamples):
        sample = [sessions[rng.randrange(len(sessions))] for _ in sessions]
        value = _numeric_metric(aggregate_governed_metrics(sample), metric)
        if value is not None:
            estimates.append(value)
    if point is None or not estimates:
        return ConfidenceInterval(
            point_estimate=point,
            lower=None,
            upper=None,
            confidence_level=confidence_level,
            resamples=resamples,
        )
    estimates.sort()
    alpha = (1 - confidence_level) / 2
    return ConfidenceInterval(
        point_estimate=point,
        lower=_percentile(estimates, alpha),
        upper=_percentile(estimates, 1 - alpha),
        confidence_level=confidence_level,
        resamples=resamples,
    )


def paired_session_comparison(
    baseline: list[SessionMetricComponents],
    candidate: list[SessionMetricComponents],
    *,
    metric: str,
    higher_is_better: bool,
    resamples: int = 2_000,
    confidence_level: float = 0.95,
    seed: int = 0,
) -> dict[str, Any]:
    if resamples < 100:
        raise ValueError("paired comparison requires at least 100 resamples")
    if not 0 < confidence_level < 1:
        raise ValueError("confidence level must be between zero and one")
    baseline_by_id = {item.base_session_id: item for item in baseline}
    candidate_by_id = {item.base_session_id: item for item in candidate}
    if len(baseline_by_id) != len(baseline) or len(candidate_by_id) != len(candidate):
        raise ValueError("paired comparison session IDs must be unique")
    if set(baseline_by_id) != set(candidate_by_id):
        raise ValueError("paired comparison requires identical base sessions")
    session_ids = sorted(baseline_by_id)
    baseline_point = _numeric_metric(aggregate_governed_metrics(baseline), metric)
    candidate_point = _numeric_metric(aggregate_governed_metrics(candidate), metric)
    point_difference = _difference(candidate_point, baseline_point)
    rng = random.Random(seed)
    differences: list[float] = []
    for _ in range(resamples):
        sampled_ids = [session_ids[rng.randrange(len(session_ids))] for _ in session_ids]
        baseline_sample = [baseline_by_id[session_id] for session_id in sampled_ids]
        candidate_sample = [candidate_by_id[session_id] for session_id in sampled_ids]
        left = _numeric_metric(aggregate_governed_metrics(baseline_sample), metric)
        right = _numeric_metric(aggregate_governed_metrics(candidate_sample), metric)
        difference = _difference(right, left)
        if difference is not None:
            differences.append(difference)
    differences.sort()
    alpha = (1 - confidence_level) / 2
    wins = ties = losses = 0
    for session_id in session_ids:
        left = _numeric_metric(aggregate_governed_metrics([baseline_by_id[session_id]]), metric)
        right = _numeric_metric(aggregate_governed_metrics([candidate_by_id[session_id]]), metric)
        difference = _difference(right, left)
        if difference is None or math.isclose(difference, 0.0, abs_tol=1e-12):
            ties += 1
        elif (difference > 0) == higher_is_better:
            wins += 1
        else:
            losses += 1
    return {
        "schema_version": "paired_session_comparison_v1",
        "metric": metric,
        "higher_is_better": higher_is_better,
        "session_count": len(session_ids),
        "baseline": baseline_point,
        "candidate": candidate_point,
        "difference": point_difference,
        "difference_confidence_interval": {
            "lower": _percentile(differences, alpha) if differences else None,
            "upper": _percentile(differences, 1 - alpha) if differences else None,
            "confidence_level": confidence_level,
            "resamples": resamples,
            "cluster_unit": "base_session",
        },
        "wins": wins,
        "ties": ties,
        "losses": losses,
        "statistically_resolved": (
            bool(differences)
            and (_percentile(differences, alpha) > 0 or _percentile(differences, 1 - alpha) < 0)
        ),
    }


def bootstrap_metric_matrix(
    sessions: list[SessionMetricComponents],
    *,
    metrics: list[str],
    resamples: int,
    confidence_level: float,
    seed: int,
) -> dict[str, dict[str, float | int | str | None]]:
    return {
        metric: session_cluster_bootstrap(
            sessions,
            metric=metric,
            resamples=resamples,
            confidence_level=confidence_level,
            seed=seed,
        ).__dict__
        for metric in metrics
    }


def _numeric_metric(payload: dict[str, Any], metric: str) -> float | None:
    value = payload.get(metric)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"metric is not a numeric aggregate: {metric}")
    return float(value)


def _difference(right: float | None, left: float | None) -> float | None:
    return right - left if right is not None and left is not None else None


def _percentile(values: list[float], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight
