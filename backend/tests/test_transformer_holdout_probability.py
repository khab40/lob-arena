"""Inert float64 arithmetic only; no detector, fitting or real artifact access."""
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from app.ml.transformer.holdout_metrics import fixed_comparison, paired_bootstrap, sigmoid  # noqa: E402
from app.ml.transformer.holdout_probability import verified_probabilities  # noqa: E402
from app.ml.transformer.research_comparison_readback import arithmetic_matches  # noqa: E402

THRESHOLDS = (.8, .7, .2)


def test_one_adjacent_float_allowed_and_two_rejected_in_both_directions():
    expected = np.asarray([.37, .73])
    for direction in (0., 1.):
        adjacent = np.nextafter(expected, direction)
        assert np.array_equal(verified_probabilities(expected, adjacent, THRESHOLDS), adjacent)
        with pytest.raises(ValueError, match="one float64 ULP"):
            verified_probabilities(expected, np.nextafter(adjacent, direction), THRESHOLDS)


@pytest.mark.parametrize("supplied", [[np.nan], [np.inf], [-np.inf], [-.1], [1.1],
                                      [.37, .4], [[.37]], ["0.37"], [True], [.37 + 0j]])
def test_invalid_published_probability_rejected(supplied):
    with pytest.raises(ValueError):
        verified_probabilities([.37], supplied, THRESHOLDS)


@pytest.mark.parametrize("supplied,expected", [([True, .37], [1., .37]),
    ([False, .37], [0., .37]), ([False, 0], [0., 0.]), ([True, 1], [1., 1.]),
    ([np.bool_(False), 0.], [0., 0.]), ([np.bool_(True), 1.], [1., 1.])])
def test_mixed_booleans_rejected_before_numeric_coercion(supplied, expected):
    with pytest.raises(ValueError, match="booleans"):
        verified_probabilities(expected, supplied, THRESHOLDS)


@pytest.mark.parametrize("expected", [[], [[.37]], [np.nan], [np.inf], [-.1], [1.1]])
def test_invalid_independent_probability_rejected(expected):
    with pytest.raises(ValueError):
        verified_probabilities(expected, [.37], THRESHOLDS)


@pytest.mark.parametrize("threshold", [*THRESHOLDS, .5])
def test_one_ulp_cannot_cross_any_frozen_or_diagnostic_threshold(threshold):
    with pytest.raises(ValueError, match="frozen decision"):
        verified_probabilities([threshold], [np.nextafter(threshold, 0.)], THRESHOLDS)


def test_one_ulp_cannot_reorder_rows():
    lower, upper = .37, np.nextafter(.37, 1.)
    with pytest.raises(ValueError, match="stable ranking"):
        verified_probabilities([lower, upper], [upper, lower], THRESHOLDS)


@pytest.mark.parametrize("merge", [False, True])
def test_one_ulp_cannot_split_or_merge_ties_even_when_order_is_exact(merge):
    lower, upper = .37, np.nextafter(.37, 1.)
    expected, supplied = ([upper, lower], [lower, lower]) if merge else ([lower, lower], [upper, lower])
    with pytest.raises(ValueError, match="ties"):
        verified_probabilities(expected, supplied, THRESHOLDS)


@pytest.mark.parametrize("edge", [.1, .3, .4, .6, .9])
def test_one_ulp_cannot_cross_reliability_bins(edge):
    boundary = np.linspace(0., 1., 11)[round(edge * 10)]
    with pytest.raises(ValueError, match="reliability bins"):
        verified_probabilities([boundary], [np.nextafter(boundary, 0.)], THRESHOLDS)


def test_zero_one_and_subnormal_endpoints_keep_absolute_float64_adjacency():
    expected = np.asarray([0., 1.])
    adjacent = np.asarray([np.nextafter(0., 1.), np.nextafter(1., 0.)])
    assert np.array_equal(verified_probabilities(expected, adjacent, THRESHOLDS), adjacent)
    with pytest.raises(ValueError):
        verified_probabilities(expected, [-np.nextafter(0., 1.), 1.], THRESHOLDS)


@pytest.mark.parametrize("thresholds", [(), (.7,), (.1, .2, .3, .4), (np.nan, .7, .2), (1.1, .7, .2)])
def test_missing_or_invalid_frozen_thresholds_rejected(thresholds):
    with pytest.raises(ValueError):
        verified_probabilities([.37], [.37], thresholds)


def inert_population():
    ledger = [{"label": 1, "base_session_id": session, "campaign_id": session}
              for session in ("a", "b", "c") for _ in range(12)]
    logits = np.full(36, np.log(.999 / (1 - .999)))
    baseline = np.full(36, .8)
    release = SimpleNamespace(require_research_inference=lambda: None, temperature=1.,
        operating_points=tuple(SimpleNamespace(threshold=t) for t in THRESHOLDS))
    return ledger, logits, baseline, release


def test_one_ulp_calibration_amplifies_reductions_but_verified_values_preserve_policy():
    ledger, logits, baseline, release = inert_population()
    args = (ledger, logits, baseline, ("wall",) * 36, ("AAPL",) * 36, release)
    default, expected = fixed_comparison(*args)
    published = np.nextafter(expected, 1.)
    verified, actual = fixed_comparison(*args, published_probabilities=published)
    assert np.array_equal(actual, published)
    assert not arithmetic_matches(default, verified)  # Relative amplification exceeds eight ULP.
    assert arithmetic_matches(verified, fixed_comparison(*args, published_probabilities=published)[0])
    assert default["modes"]["balanced"]["transformer"]["tp"] == verified["modes"]["balanced"]["transformer"]["tp"]
    for key in ("log_loss", "brier_score"):
        a = default["modes"]["balanced"]["transformer"][key]
        b = verified["modes"]["balanced"]["transformer"][key]
        assert abs(a - b) > 8 * np.spacing(a)
    assert np.array_equal(expected, sigmoid(logits / release.temperature))
    assert paired_bootstrap(ledger, logits, baseline, release) == paired_bootstrap(
        ledger, logits, baseline, release, published_probabilities=None)
    assert paired_bootstrap(ledger, logits, baseline, release, published_probabilities=published) == paired_bootstrap(
        ledger, logits, baseline, release, published_probabilities=published)


@pytest.mark.parametrize("reducer", ["comparison", "bootstrap"])
def test_reducers_cannot_bypass_independent_calibration_with_arbitrary_probabilities(reducer):
    ledger, logits, baseline, release = inert_population()
    supplied = np.full(36, .8)
    with pytest.raises(ValueError, match="one float64 ULP"):
        if reducer == "comparison":
            fixed_comparison(ledger, logits, baseline, ("wall",) * 36, ("AAPL",) * 36,
                             release, published_probabilities=supplied)
        else:
            paired_bootstrap(ledger, logits, baseline, release, published_probabilities=supplied)
