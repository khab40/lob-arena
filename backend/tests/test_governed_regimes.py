from pydantic import ValidationError
import pytest

from app.evaluation.governed_metrics import SessionMetricComponents
from app.evaluation.regimes import (
    GovernedRegimeEvidence,
    RegimeFitRow,
    assign_regimes,
    fit_regime_thresholds,
    regime_metric_matrix,
    worst_decile_results,
)


CONFIG_HASH = "a" * 64


def _fit_row(index: int) -> RegimeFitRow:
    return RegimeFitRow(
        base_session_id=f"session-{index}",
        split="train",
        control_or_pre_attack=True,
        feature_schema_version="lob_features_v1",
        feature_config_hash=CONFIG_HASH,
        liquidity_score=float(index),
        realized_volatility_long=float(index),
        spread_bps=float(index),
        message_rate_long=float(index),
    )


def _session(index: int, *, regime: str) -> SessionMetricComponents:
    detected = 0 if index == 0 else 1
    false_alert = 2 if index == 9 else 0
    return SessionMetricComponents(
        base_session_id=f"session-{index:02d}",
        instrument="SPY",
        regimes={
            "liquidity": regime,
            "volatility": "high" if index % 2 else "low",
        },
        true_positive=detected,
        false_positive=bool(false_alert),
        false_negative=1 - detected,
        true_negative=1 - bool(false_alert),
        evaluable_event_count=1_000,
        raw_false_alert_count=false_alert,
        false_alert_cluster_count=bool(false_alert),
        raw_evaluable_alert_count=detected + false_alert,
        evaluable_alert_cluster_count=detected + bool(false_alert),
        benefit_eligible_attack_count=1,
        detected_before_benefit_count=detected,
        detection_latencies_ns=(index,) if detected else (),
    )


def test_regime_thresholds_fit_only_training_control_rows_and_are_deterministic() -> None:
    rows = [_fit_row(index) for index in range(9)]

    first = fit_regime_thresholds(rows)
    second = fit_regime_thresholds(list(reversed(rows)))

    assert first == second
    assert first.fit_split == "train"
    assert first.fit_source == "control_or_pre_attack"
    assert first.boundaries["liquidity_score"].lower < first.boundaries["liquidity_score"].upper

    with pytest.raises(ValidationError):
        RegimeFitRow(
            base_session_id="invalid",
            split="validation",
            control_or_pre_attack=True,
            feature_schema_version="lob_features_v1",
            feature_config_hash=CONFIG_HASH,
            liquidity_score=1,
            realized_volatility_long=1,
            spread_bps=1,
            message_rate_long=1,
        )


def test_regime_assignment_uses_frozen_training_boundaries() -> None:
    thresholds = fit_regime_thresholds([_fit_row(index) for index in range(9)])

    assigned = assign_regimes(
        {
            "liquidity_score": 0.0,
            "realized_volatility_long": 8.0,
            "spread_bps": 4.0,
            "message_rate_long": 8.0,
        },
        thresholds,
    )

    assert assigned == {
        "liquidity": "thin",
        "volatility": "high",
        "spread": "normal",
        "message_intensity": "busy",
    }


def test_governed_regime_evidence_recomputes_training_thresholds() -> None:
    rows = [_fit_row(index) for index in range(3)]
    thresholds = fit_regime_thresholds(rows)
    evidence = GovernedRegimeEvidence(
        protocol_hash="b" * 64,
        corpus_hash="c" * 64,
        assignment_hash="d" * 64,
        fit_session_ids=[row.base_session_id for row in rows],
        fit_rows=rows,
        thresholds=thresholds,
        target_features={
            "test": {
                "liquidity_score": 1.0,
                "realized_volatility_long": 1.0,
                "spread_bps": 1.0,
                "message_rate_long": 1.0,
            }
        },
    )

    assert evidence.thresholds == thresholds
    with pytest.raises(ValidationError, match="thresholds do not match"):
        GovernedRegimeEvidence(
            **evidence.model_dump(exclude={"thresholds"}),
            thresholds=fit_regime_thresholds([_fit_row(index + 3) for index in range(3)]),
        )


def test_regime_matrix_suppresses_underpowered_cells() -> None:
    sessions = [_session(index, regime="thin" if index < 7 else "deep") for index in range(10)]

    matrix = regime_metric_matrix(sessions, minimum_cell_count=5)

    assert matrix["dimensions"]["liquidity"]["thin"]["sufficient"] is True
    assert matrix["dimensions"]["liquidity"]["deep"]["sufficient"] is False
    assert matrix["dimensions"]["liquidity"]["deep"]["metrics"] is None
    assert "liquidity_x_volatility" in matrix["dimensions"]


def test_worst_decile_uses_predeclared_metric_direction() -> None:
    sessions = [_session(index, regime="normal") for index in range(10)]

    result = worst_decile_results(
        sessions,
        metric_directions={
            "attack_level_recall": "lower",
            "false_alerts_per_million_events": "higher",
        },
        fraction=0.1,
    )

    assert result["metrics"]["attack_level_recall"]["session_ids"] == ["session-00"]
    assert result["metrics"]["false_alerts_per_million_events"]["session_ids"] == ["session-09"]
    assert result["metrics"]["attack_level_recall"]["selected_session_count"] == 1
