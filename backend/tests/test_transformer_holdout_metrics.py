from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from app.ml.transformer.holdout_metrics import (  # noqa: E402
    BASELINE_THRESHOLDS, MODES, defined_metrics, fixed_comparison, paired_bootstrap,
)


def release():
    return SimpleNamespace(require_research_inference=lambda: None, temperature=1.,
        operating_points=tuple(SimpleNamespace(threshold=.7) for _ in MODES))


def population():
    ledger = [{"label": label, "base_session_id": session, "campaign_id": session if label else None}
              for session in ("a", "b", "c") for label in (0, 1)]
    return ledger, np.asarray([-3., 3., -2., 2., -1., 1.]), np.asarray([.1, .9, .2, .8, .3, .7])


def test_fixed_thresholds_temperature_and_research_gates():
    rows, logits, baseline = population()
    before = release()
    result, probability = fixed_comparison(rows, logits, baseline,
        ("control", "wall") * 3, ("AAPL", "MSFT", "NVDA") * 2, before)
    assert list(result["modes"]) == list(MODES)
    assert result["modes"]["balanced"]["transformer"]["tp"] == 3
    assert result["campaign_coverage"]["transformer"]["observed"] == 3
    assert result["decision"] == "operator_review_required"
    assert result["production_qualified"] is False
    assert probability[-1] == pytest.approx(1 / (1 + np.exp(-1)))
    assert result["modes"]["high_precision"]["lightgbm"]["precision"] is None
    assert BASELINE_THRESHOLDS == (1., .5769230769230769, .01296456352636128)
    assert before.temperature == 1.


def test_undefined_metrics_keep_reasons():
    result = defined_metrics(np.asarray([0, 0]), np.asarray([.1, .2]), .5)
    assert result["precision"] is None
    assert result["recall"] is None
    assert result["average_precision"] is None
    assert set(result["undefined_reasons"]) == {"precision", "recall", "f1", "average_precision"}


def test_paired_bootstrap_reproducible_and_preserves_whole_sessions(monkeypatch):
    rows, logits, baseline = population()
    observed = []
    from app.ml.transformer import holdout_metrics
    original = holdout_metrics.defined_metrics
    def inspect(labels, probabilities, threshold):
        # Every sampled session contains both declared observations; no row sampling.
        assert labels.tolist() == [0, 1] * 3
        observed.append(len(labels))
        return original(labels, probabilities, threshold)
    monkeypatch.setattr(holdout_metrics, "defined_metrics", inspect)
    one = paired_bootstrap(rows, logits, baseline, release())
    two = paired_bootstrap(rows, logits, baseline, release())
    assert one == two
    assert one["draws"] == 2000 and one["seed"] == 20260828
    assert one["unit"] == "whole_base_session"
    assert one["intervals"]["log_loss"]["undefined_draws"] == 0
    assert len(observed) == 108  # 27 ordered session draws × two models × two runs.


@pytest.mark.parametrize("defect", ["shape", "nan", "probability", "clusters"])
def test_metric_failures_are_inconclusive(defect):
    rows, logits, baseline = population()
    if defect == "clusters":
        rows = rows[:4]
        with pytest.raises(ValueError, match="three source"):
            paired_bootstrap(rows, logits[:4], baseline[:4], release())
        return
    if defect == "shape":
        logits = logits[:-1]
    elif defect == "nan":
        logits[-1] = np.nan
    else:
        baseline[-1] = 1.1
    with pytest.raises(ValueError):
        fixed_comparison(rows, logits, baseline, ("wall",) * 6, ("AAPL",) * 6, release())
