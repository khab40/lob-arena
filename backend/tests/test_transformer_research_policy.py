"""Inert policy checks: no model imports, fitting, scoring or cloud calls."""
import math

import pytest

from app.ml.transformer.research_policy import (
    Trial, class_session_weights, improved, learning_rate_factor, select_grid,
)


def test_weights_equalize_classes_then_sessions_without_changing_mean():
    labels, sessions = [0, 0, 0, 1, 1, 1, 1], ["a", "a", "b", "a", "b", "b", "b"]
    weights = class_session_weights(labels, sessions)
    assert sum(weights) == pytest.approx(7)
    for label in (0, 1):
        assert sum(w for w, y in zip(weights, labels) if y == label) == pytest.approx(3.5)
        for session in ("a", "b"):
            assert sum(w for w, y, s in zip(weights, labels, sessions)
                       if y == label and s == session) == pytest.approx(1.75)


@pytest.mark.parametrize("labels,sessions", [([], []), ([0], ["a"]), ([0, 1], ["a"]),
    ([False, 1], ["a", "b"]), ([0, 2], ["a", "b"]), ([0, 1], ["a", ""])])
def test_invalid_weight_inputs_fail(labels, sessions):
    with pytest.raises(ValueError):
        class_session_weights(labels, sessions)


def test_schedule_warms_up_and_finishes_at_one_tenth():
    factors = [learning_rate_factor(step, 100) for step in range(100)]
    assert factors[:5] == pytest.approx([0.2, 0.4, 0.6, 0.8, 1])
    assert all(left > right for left, right in zip(factors[4:], factors[5:]))
    assert factors[-1] == pytest.approx(0.1)


def test_epoch_tie_keeps_the_earlier_checkpoint():
    assert improved(0.5, math.inf)
    assert not improved(0.5 - 0.5e-6, 0.5)
    assert improved(0.5 - 2e-6, 0.5)
    with pytest.raises(ValueError):
        improved(float("nan"), 0.5)


def grid():
    return [{"trial_sha256": Trial(w, rate).sha256(), "status": "verified",
             "selection_log_loss": 0.5, "parameter_count": w * 10}
            for w in (64, 128) for rate in (0.0003, 0.001)]


def test_grid_tie_prefers_size_then_hash():
    rows = grid()
    assert select_grid(rows) == min(rows[:2], key=lambda r: r["trial_sha256"])


@pytest.mark.parametrize("failure", ["missing", "duplicate", "failed", "nonfinite"])
def test_incomplete_grid_cannot_select_a_winner(failure):
    rows = grid()
    if failure == "missing":
        rows.pop()
    if failure == "duplicate":
        rows[-1] = rows[0]
    if failure == "failed":
        rows[-1]["status"] = "failed"
    if failure == "nonfinite":
        rows[-1]["selection_log_loss"] = float("nan")
    with pytest.raises(ValueError):
        select_grid(rows)
