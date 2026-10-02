"""Artifact arithmetic only: no model construction, scoring or fitting."""
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from app.ml.transformer.research_evaluation import compare, metrics  # noqa: E402


def fixture():
    split = SimpleNamespace(role="operating_point", labels=np.array([0, 1, 0, 1]),
                            target_ids=("a", "b", "c", "d"))
    return dict(split=split, logits=np.array([-2., 2., -1., 1.]), temperature=1.,
                baseline_ids=split.target_ids, baseline_labels=split.labels.copy(),
                baseline_probabilities=np.array([.2, .8, .3, .7]),
                baseline_thresholds=dict(high_precision=.75, balanced=.5, high_recall=.6))


def test_known_metrics_and_tied_average_precision():
    result = metrics([0, 1, 0, 1], [.1, .9, .2, .8])
    assert result["f1"] == result["pr_auc_average_precision"] == 1
    assert result["brier_score"] == pytest.approx(.025)
    assert result["log_loss"] == pytest.approx((-np.log(.9) - np.log(.8)) / 2)
    assert metrics([0, 1, 0, 1], [.5] * 4)["pr_auc_average_precision"] == .5


@pytest.mark.parametrize("change", [
    {"baseline_ids": ("b", "a", "c", "d")},
    {"baseline_ids": ("a", "a", "c", "d")},
    {"baseline_labels": [1, 0, 0, 1]},
    {"baseline_probabilities": [.1, .9]},
    {"baseline_probabilities": [.1, .9, float("nan"), .8]},
    {"baseline_thresholds": {"balanced": .5}},
    {"temperature": float("nan")},
])
def test_rejects_unaligned_or_incomplete_baseline(change):
    arguments = fixture()
    arguments.update(change)
    with pytest.raises(ValueError):
        compare(**arguments)


def test_preserves_frozen_baseline_thresholds_and_research_limitations():
    result = compare(**fixture())
    assert not result["freeze_blocked"]
    assert result["delta_log_loss"] < 0
    frozen = result["lightgbm_frozen_operating_points"]
    assert frozen["high_precision"]["threshold"] == .75
    assert frozen["high_precision"]["metrics"]["recall"] == .5
    assert "operating_points_selected_on_reported_role" in result["limitations"]
    assert result["scope"] == "development_comparison_not_final_evaluation"


def test_unattainable_precision_is_retained_as_negative_result():
    arguments = fixture()
    arguments["logits"] = np.zeros(4)
    result = compare(**arguments)
    assert result["unattainable_floor"] and result["freeze_blocked"]
    assert result["transformer_selected_operating_points"] == []
    assert result["calibrated_transformer"]["pr_auc_average_precision"] == .5


def test_calibration_regression_blocks_freeze():
    arguments = fixture()
    arguments["temperature"] = 20.
    result = compare(**arguments)
    assert result["calibration_worsened_brier_and_ece"] and result["freeze_blocked"]
