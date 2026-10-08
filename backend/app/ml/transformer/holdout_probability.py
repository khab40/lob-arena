"""Bound calibrated float64 portability while keeping discrete behavior exact."""
import numpy as np

PROBABILITY_POLICY = "calibrated_sigmoid_max_1_float64_ulp_exact_decisions_ranking_ties_bins"


def verified_probabilities(expected, published, thresholds):
    """Check adjacent float64 values, not a relative or aggregate tolerance."""
    original = np.asarray(published, dtype=object)
    if any(isinstance(value, (bool, np.bool_)) for value in original.flat):
        raise ValueError("published probabilities cannot contain booleans")
    expected, supplied = np.asarray(expected, dtype=np.float64), np.asarray(published)
    if supplied.dtype.kind not in "fiu":
        raise ValueError("published probabilities must be numeric")
    supplied = supplied.astype(np.float64)
    if (expected.ndim != 1 or not len(expected) or supplied.shape != expected.shape
            or not np.isfinite(expected).all() or not np.isfinite(supplied).all()
            or np.any((expected < 0) | (expected > 1) | (supplied < 0) | (supplied > 1))):
        raise ValueError("published probability shape, range or finiteness differs")
    if np.any((supplied < np.nextafter(expected, -np.inf))
              | (supplied > np.nextafter(expected, np.inf))):
        raise ValueError("published probabilities exceed one float64 ULP")
    thresholds = tuple(thresholds)
    if (len(thresholds) != 3 or not np.isfinite(thresholds).all()
            or any(not 0 <= value <= 1 for value in thresholds)):
        raise ValueError("three frozen probability thresholds required")
    for threshold in (*thresholds, .5):
        if not np.array_equal(expected >= threshold, supplied >= threshold):
            raise ValueError("published probabilities change a frozen decision")
    order = np.argsort(-expected, kind="stable")
    if not np.array_equal(order, np.argsort(-supplied, kind="stable")):
        raise ValueError("published probabilities change stable ranking")
    if not np.array_equal(np.diff(expected[order]) == 0, np.diff(supplied[order]) == 0):
        raise ValueError("published probabilities change ties")
    edges = np.linspace(0., 1., 11)
    def bins(values):
        return np.clip(np.searchsorted(edges, values, side="right") - 1, 0, 9)
    if not np.array_equal(bins(expected), bins(supplied)):
        raise ValueError("published probabilities change reliability bins")
    return supplied
