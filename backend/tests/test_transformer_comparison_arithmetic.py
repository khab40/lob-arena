"""Cross-platform saved aggregates and strict decision boundaries; no model calls."""
from copy import deepcopy
import math

import pytest

pytest.importorskip("numpy")
from app.ml.transformer.research_comparison_readback import arithmetic_matches, verify  # noqa: E402
from test_transformer_research_comparison_readback import fixture  # noqa: E402


def shifted(value, steps):
    for _ in range(steps):
        value = math.nextafter(value, math.inf)
    return value


def test_retained_linux_macos_snapshot_differs_by_one_ulp():
    linux, macos = .0005067766777381927, .0005067766777381926
    assert linux != macos and abs(linux-macos) == math.ulp(macos)
    assert arithmetic_matches({"log_loss": linux}, {"log_loss": macos})


@pytest.mark.parametrize("field", ["log_loss", "brier_score", "expected_calibration_error",
                                  "mean_probability", "delta_log_loss"])
@pytest.mark.parametrize("steps,accepted", [(1, True), (8, True), (9, False)])
def test_named_aggregate_boundary(field, steps, accepted):
    assert arithmetic_matches({field: shifted(.125, steps)}, {field: .125}) is accepted


@pytest.mark.parametrize("changed", [
    {"threshold": shifted(.5, 1)}, {"threshold": 1}, {"threshold": True}, {},
    {"threshold": .5, "extra": 0}, {"threshold": float("nan")}, {"threshold": float("inf")},
])
def test_threshold_structure_types_and_nonfinite_values_remain_exact(changed):
    assert not arithmetic_matches(changed, {"threshold": .5})


@pytest.mark.parametrize("field", ["true_positive", "false_positive", "rows", "freeze_blocked",
                                  "precision", "recall", "f1", "pr_auc_average_precision"])
def test_counts_flags_and_nonreduction_metrics_remain_exact(field):
    assert not arithmetic_matches({field: shifted(.5, 1)}, {field: .5})


def test_zero_and_nonfinite_aggregates_cannot_hide_errors():
    assert not arithmetic_matches({"log_loss": 1e-300}, {"log_loss": 0.})
    assert not arithmetic_matches({"log_loss": float("inf")}, {"log_loss": float("inf")})
    assert not arithmetic_matches([{"log_loss": .5}], [])


def test_full_verifier_preserves_result_and_rejects_threshold_tampering(monkeypatch):
    args = fixture(monkeypatch)
    result = args[0]
    result["comparison"]["raw_transformer"]["log_loss"] = shifted(
        result["comparison"]["raw_transformer"]["log_loss"], 1)
    before = deepcopy(result)
    assert verify(*args)["aggregate_arithmetic_policy"] == "named_float64_reductions_max_8_ulp"
    assert result == before
    result["comparison"]["lightgbm_frozen_operating_points"]["balanced"]["threshold"] = shifted(.5, 1)
    with pytest.raises(ValueError):
        verify(*args)
