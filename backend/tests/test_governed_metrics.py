from dataclasses import replace

import pytest

from app.evaluation.governed_metrics import (
    AlertObservation,
    AttackWindow,
    CleanWindow,
    GovernedSessionUnit,
    SessionMetricComponents,
    aggregate_governed_metrics,
    evaluate_governed_session,
)
from app.evaluation.statistics import (
    paired_session_comparison,
    session_cluster_bootstrap,
)


def _unit(session_id: str = "session-1") -> GovernedSessionUnit:
    return GovernedSessionUnit(
        base_session_id=session_id,
        instrument="SPY",
        canonical_event_count=1_000,
        evaluable_event_count=100,
        attacks=(
            AttackWindow("attack-a", "spoofing", 100, 199, 150),
            AttackWindow("attack-b", "layering", 300, 399, 350),
        ),
        clean_windows=(
            CleanWindow("clean-a", 500, 600),
            CleanWindow("clean-b", 700, 800),
        ),
        alerts=(
            AlertObservation("a1", "detector", 120),
            AlertObservation("a2", "detector", 125),
            AlertObservation("fp1", "detector", 520),
            AlertObservation("fp2", "detector", 525),
            AlertObservation("ignored-unlabeled", "detector", 900),
        ),
        regimes={"liquidity": "thin", "volatility": "high"},
    )


def _components(
    session_id: str,
    *,
    tp: int,
    fp: int,
    fn: int,
    tn: int,
) -> SessionMetricComponents:
    return SessionMetricComponents(
        base_session_id=session_id,
        instrument="SPY",
        regimes={"liquidity": "normal"},
        true_positive=tp,
        false_positive=fp,
        false_negative=fn,
        true_negative=tn,
        evaluable_event_count=1_000,
        raw_false_alert_count=fp,
        false_alert_cluster_count=fp,
        raw_evaluable_alert_count=tp + fp,
        evaluable_alert_cluster_count=tp + fp,
        benefit_eligible_attack_count=tp + fn,
        detected_before_benefit_count=tp,
        detection_latencies_ns=(10,) * tp,
    )


def test_operational_metrics_use_attack_and_verified_clean_units() -> None:
    components = evaluate_governed_session(
        _unit(),
        alert_deduplication_window_ns=10,
        alert_matching_horizon_ns=0,
    )
    metrics = aggregate_governed_metrics([components])

    assert metrics["true_positive"] == 1
    assert metrics["false_positive"] == 1
    assert metrics["false_negative"] == 1
    assert metrics["true_negative"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5
    assert metrics["attack_level_recall"] == 0.5
    assert metrics["false_alerts_per_million_events"] == 10_000
    assert metrics["raw_false_alerts_per_million_events"] == 20_000
    assert metrics["detection_before_benefit_rate"] == 0.5
    assert metrics["duplicate_alert_load"] == 2.0
    assert metrics["duplicate_alert_fraction"] == 0.5
    assert metrics["detection_latency_ns"]["p50"] == 20


def test_unreviewed_regions_do_not_create_false_alerts_or_true_negatives() -> None:
    components = evaluate_governed_session(
        _unit(),
        alert_deduplication_window_ns=10,
        alert_matching_horizon_ns=0,
    )

    assert components.raw_evaluable_alert_count == 4
    assert components.true_negative == 1
    assert components.false_positive == 1


def test_session_cluster_bootstrap_is_deterministic_and_not_row_resampled() -> None:
    sessions = [
        _components(f"session-{index}", tp=1, fp=index % 2, fn=0, tn=1)
        for index in range(8)
    ]

    first = session_cluster_bootstrap(
        sessions,
        metric="f1",
        resamples=500,
        confidence_level=0.95,
        seed=42,
    )
    second = session_cluster_bootstrap(
        sessions,
        metric="f1",
        resamples=500,
        confidence_level=0.95,
        seed=42,
    )

    assert first == second
    assert first.cluster_unit == "base_session"
    assert first.lower <= first.point_estimate <= first.upper


def test_paired_comparison_uses_identical_session_draws() -> None:
    baseline = [
        _components(f"session-{index}", tp=1, fp=1, fn=1, tn=1)
        for index in range(6)
    ]
    candidate = [
        _components(f"session-{index}", tp=2, fp=0, fn=0, tn=2)
        for index in range(6)
    ]

    result = paired_session_comparison(
        baseline,
        candidate,
        metric="f1",
        higher_is_better=True,
        resamples=500,
        seed=11,
    )

    assert result["difference"] > 0
    assert result["wins"] == 6
    assert result["losses"] == 0
    assert result["difference_confidence_interval"]["lower"] > 0
    assert result["statistically_resolved"] is True


def test_paired_comparison_rejects_unpaired_sessions() -> None:
    baseline = [_components("one", tp=1, fp=0, fn=0, tn=1)]
    candidate = [_components("two", tp=1, fp=0, fn=0, tn=1)]

    with pytest.raises(ValueError, match="identical base sessions"):
        paired_session_comparison(
            baseline,
            candidate,
            metric="f1",
            higher_is_better=True,
            resamples=100,
        )


def test_governed_windows_must_not_overlap() -> None:
    with pytest.raises(ValueError, match="overlap"):
        replace(
            _unit(),
            clean_windows=(CleanWindow("leaky-clean", 150, 250),),
        )
