"""Artifact arithmetic only: no model construction, scoring or fitting."""
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from app.ml.transformer.research_evaluation import compare, family_comparison, metrics  # noqa: E402


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


def test_family_comparison_includes_shared_false_alerts_but_not_other_attacks():
    labels = [0, 1, 0, 1, 1]
    families = ["control", "layering", "control", "wall", "wall"]
    # Transformer alerts on everything; baseline correctly separates all rows.
    report = family_comparison(labels, families, [.9] * 5, [.1, .9, .1, .9, .9])
    assert set(report) == {"layering", "wall"}
    for family, positives in (("layering", 1), ("wall", 2)):
        item = report[family]
        assert item["population"] == "family_positives_plus_shared_controls"
        assert item["threshold"] == .5
        assert item["rows"] == positives + 2
        assert item["positives"] == positives and item["negatives"] == 2
        assert item["transformer"]["false_positive"] == 2
        assert item["transformer"]["precision"] == pytest.approx(positives / (positives + 2))
        assert item["transformer"]["f1"] == pytest.approx(2 * positives / (2 * positives + 2))
        assert item["lightgbm"]["f1"] == 1
    # Changing another family's positive cannot change layering metrics.
    changed = family_comparison(labels, families, [.9, .9, .9, .1, .1], [.1, .9, .1, .9, .9])
    assert changed["layering"] == report["layering"]
    assert changed["wall"]["transformer"]["recall"] == 0


@pytest.mark.parametrize("labels,families,probabilities", [
    ([1, 1], ["wall", "wall"], [.9, .9]),
    ([0, 0], ["control", "control"], [.1, .1]),
    ([0, 1], ["control", "control"], [.1, .9]),
    ([0, 1], ["control"], [.1, .9]),
    ([0, 1], ["control", ""], [.1, .9]),
    ([0, 1], ["control", "wall"], [.1, float("nan")]),
    ([0, 1], ["control", "wall"], [.1, 1.1]),
])
def test_family_comparison_rejects_invalid_populations(labels, families, probabilities):
    with pytest.raises(ValueError):
        family_comparison(labels, families, probabilities, probabilities)
