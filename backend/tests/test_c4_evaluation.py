import json

import pytest

pytest.importorskip("numpy")

from app.ml.lightgbm.c4_evaluation import C4EvaluationProfile, evaluate_c4_observations  # noqa: E402


def profile():
    return C4EvaluationProfile(
        candidate_sha256="a" * 64,
        frozen_root_sha256="b" * 64,
        projection_sha256="c" * 64,
        comparison_evidence_sha256="d" * 64,
    )


def observations():
    for session in ("a", "b", "c"):
        for i, (label, probability, rules) in enumerate(
            ((1, 0.9, True), (1, 0.4, True), (0, 0.8, False), (0, 0.1, False))
        ):
            yield dict(
                base_session_id=session,
                run_id=session + "-run",
                label=label,
                raw_probability=probability,
                calibrated_probability=probability,
                alert=probability >= 0.5,
                rules_alert=rules,
                threshold=0.5,
                fold="test",
                campaign_id=session + "-campaign" if label else None,
                attack_family="layering_like" if label else None,
                label_source="synthetic_scenario" if label else "research_control_assumption",
            )


def test_frozen_metrics_calibration_rules_and_paired_uncertainty():
    result = evaluate_c4_observations(observations(), profile=profile(), frozen_threshold=0.5)
    assert result["row_count"] == 12
    assert result["metrics"]["lightgbm.row_f1"] == 0.5
    assert result["metrics"]["rules.row_f1"] == 1
    assert result["metrics"]["delta.lightgbm_minus_rules.row_f1"] == -0.5
    assert result["metrics"]["lightgbm.calibrated_brier"] == pytest.approx(0.255)
    assert result["metrics"]["lightgbm.calibrated_ece"] == pytest.approx(0.4)
    assert result["metrics"]["lightgbm.false_alerts_per_million_observations"] == 250000
    assert result["metrics"]["lightgbm.observed_campaign_recall"] == 1
    assert result["confusion_counts"]["lightgbm"] == dict(
        true_positive=3, false_positive=3, false_negative=3, true_negative=3
    )
    interval = result["uncertainty"]["intervals"]["delta.lightgbm_minus_rules.row_f1"]
    assert interval == dict(lower=-0.5, upper=-0.5, valid_resamples=2000, undefined_resamples=0)
    assert result["uncertainty"]["support"] == "limited"
    assert not result["seven_date_benchmark_compliance"]
    json.dumps(result, allow_nan=False)


@pytest.mark.parametrize(
    "change",
    [
        {"threshold": 0.4},
        {"alert": False},
        {"fold": "validation"},
        {"label_source": "verified_clean"},
        {"calibrated_probability": float("nan")},
        {"rules_alert": 1},
        {"campaign_id": None},
    ],
)
def test_rejects_invalid_or_posthoc_decisions(change):
    row = next(observations()) | change
    with pytest.raises(ValueError):
        evaluate_c4_observations([row], profile=profile(), frozen_threshold=0.5)


def test_uncertainty_is_deterministic_and_handles_undefined_metrics():
    rows = [row | {"alert": False, "calibrated_probability": 0.1, "rules_alert": False} for row in observations()]
    first = evaluate_c4_observations(rows, profile=profile(), frozen_threshold=0.5)
    second = evaluate_c4_observations(rows, profile=profile(), frozen_threshold=0.5)
    assert first == second
    assert first["metrics"]["lightgbm.row_precision"] is None
    assert first["uncertainty"]["intervals"]["lightgbm.row_precision"]["undefined_resamples"] == 2000


def test_one_session_does_not_manufacture_confidence_intervals():
    result = evaluate_c4_observations(
        (row for row in observations() if row["base_session_id"] == "a"), profile=profile(), frozen_threshold=0.5
    )
    assert result["uncertainty"]["support"] == "insufficient"
    assert result["uncertainty"]["intervals"] == {}


def test_profile_has_no_test_tuning_knobs():
    with pytest.raises(ValueError):
        C4EvaluationProfile(**profile().model_dump() | {"bootstrap_seed": 123})
    with pytest.raises(ValueError):
        C4EvaluationProfile(**profile().model_dump() | {"threshold": 0.2})
