"""Fixed operating points and paired source-session summaries; never optimize."""
import numpy as np

from .holdout_probability import verified_probabilities

MODES = ("high_precision", "balanced", "high_recall")
BASELINE_THRESHOLDS = (1.0, 0.5769230769230769, 0.01296456352636128)


def sigmoid(logits):
    return np.exp(-np.logaddexp(0., -np.asarray(logits, dtype=np.float64)))


def calibrated_probabilities(logits, release, published):
    expected = sigmoid(logits / release.temperature)
    if published is None:
        return expected
    return verified_probabilities(expected, published, (point.threshold for point in release.operating_points))


def defined_metrics(labels, probabilities, threshold):
    labels, probabilities = np.asarray(labels), np.asarray(probabilities, dtype=np.float64)
    if (labels.ndim != 1 or labels.shape != probabilities.shape or not np.isin(labels, (0, 1)).all()
            or not np.isfinite(probabilities).all() or np.any((probabilities < 0) | (probabilities > 1))
            or not 0 <= threshold <= 1):
        raise ValueError("invalid fixed metric inputs")
    if not len(labels):
        return {"undefined_reason": "no retained observations"}
    predicted = probabilities >= threshold
    tp = int(np.sum(predicted & (labels == 1)))
    fp = int(np.sum(predicted & (labels == 0)))
    fn = int(np.sum(~predicted & (labels == 1)))
    clipped = np.clip(probabilities, 1e-15, 1 - 1e-15)
    order = np.argsort(-probabilities, kind="stable")
    ends = np.r_[np.flatnonzero(np.diff(probabilities[order]) != 0), len(labels) - 1]
    cumulative = np.cumsum(labels[order])[ends]
    recall = cumulative / max(1, int(labels.sum()))
    bins, ece = [], 0.
    assignments = np.clip(np.searchsorted(np.linspace(0., 1., 11), probabilities, side="right") - 1, 0, 9)
    for index in range(10):
        selected = assignments == index
        count = int(selected.sum())
        mean = float(probabilities[selected].mean()) if count else None
        rate = float(labels[selected].mean()) if count else None
        if count:
            ece += count / len(labels) * abs(mean - rate)
        bins.append({"index": index, "count": count, "mean_probability": mean, "positive_rate": rate})
    result = {"tp": tp, "fp": fp, "fn": fn, "tn": len(labels) - tp - fp - fn,
        "precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn),
        "f1": 2 * tp / max(1, 2 * tp + fp + fn),
        "average_precision": float(np.sum(np.diff(np.r_[0, recall]) * cumulative / (ends + 1))),
        "log_loss": float(-np.mean(labels * np.log(clipped) + (1 - labels) * np.log1p(-clipped))),
        "brier_score": float(np.mean((probabilities - labels) ** 2)),
        "expected_calibration_error": float(ece), "reliability_bins": bins}
    reasons = {}
    for name, denominator in (("precision", tp + fp), ("recall", tp + fn), ("f1", 2 * tp + fp + fn)):
        if denominator == 0:
            result[name] = None
            reasons[name] = "zero denominator"
    if not np.sum(labels == 1):
        result["average_precision"] = None
        reasons["average_precision"] = "no positive observations"
    negatives = int(np.sum(labels == 0))
    result["negative_row_false_positive_rate"] = fp / negatives if negatives else None
    if not negatives:
        reasons["negative_row_false_positive_rate"] = "no negative observations"
    result["undefined_reasons"] = reasons
    return result


def fixed_comparison(ledger, logits, baseline, families, symbols, release, *, published_probabilities=None):
    release.require_research_inference()
    labels = np.asarray([row["label"] for row in ledger], dtype=np.int64)
    logits, baseline = np.asarray(logits, dtype=np.float64), np.asarray(baseline, dtype=np.float64)
    if (not len(labels) or logits.shape != labels.shape or baseline.shape != labels.shape
            or len(families) != len(labels) or len(symbols) != len(labels)
            or not np.isfinite(logits).all() or not np.isfinite(baseline).all()
            or np.any((baseline < 0) | (baseline > 1))):
        raise ValueError("holdout metric population differs or is nonfinite")
    probability = calibrated_probabilities(logits, release, published_probabilities)
    transform = tuple(point.threshold for point in release.operating_points)
    modes = {mode: {"transformer": defined_metrics(labels, probability, t),
                    "lightgbm": defined_metrics(labels, baseline, b)}
             for mode, t, b in zip(MODES, transform, BASELINE_THRESHOLDS, strict=True)}
    groups = {}
    for kind, values in (("symbol", symbols), ("family", families)):
        groups[kind] = {}
        for value in sorted(set(values)):
            selected = np.asarray([item == value for item in values])
            groups[kind][value] = {"rows": int(selected.sum()), "positives": int(labels[selected].sum()),
                "transformer": defined_metrics(labels[selected], probability[selected], transform[1]),
                "lightgbm": defined_metrics(labels[selected], baseline[selected], BASELINE_THRESHOLDS[1])}
    campaigns = sorted({row["campaign_id"] for row in ledger if row["campaign_id"] is not None})
    coverage = {}
    for name, values, threshold in (("transformer", probability, transform[1]),
                                     ("lightgbm", baseline, BASELINE_THRESHOLDS[1])):
        detected = sum(any(row["campaign_id"] == campaign and row["label"] == 1 and p >= threshold
                           for row, p in zip(ledger, values, strict=True)) for campaign in campaigns)
        coverage[name] = {"detected": detected, "observed": len(campaigns),
                          "recall": detected / len(campaigns) if campaigns else None}
    balanced = modes["balanced"]
    delta = {name: balanced["transformer"][name] - balanced["lightgbm"][name]
             if balanced["transformer"][name] is not None and balanced["lightgbm"][name] is not None else None
             for name in ("average_precision", "log_loss")}
    return {"rows": len(labels), "positives": int(labels.sum()), "modes": modes,
        "diagnostic_0_5": {"transformer": defined_metrics(labels, probability, .5),
                          "lightgbm": defined_metrics(labels, baseline, .5)},
        "primary_delta_transformer_minus_lightgbm": delta, "groups": groups, "campaign_coverage": coverage,
        "research_gates": {"high_precision": modes["high_precision"]["transformer"]["precision"] is not None
            and modes["high_precision"]["transformer"]["precision"] >= .9,
            "high_recall": modes["high_recall"]["transformer"]["recall"] is not None
            and modes["high_recall"]["transformer"]["recall"] >= .9},
        "decision": "operator_review_required", "production_qualified": False}, probability


def paired_bootstrap(ledger, logits, baseline, release, *, published_probabilities=None):
    """Keep every variant of each base session together in every paired draw."""
    sessions = np.asarray([row["base_session_id"] for row in ledger])
    groups = [np.flatnonzero(sessions == value) for value in sorted(set(sessions))]
    if len(groups) != 3:
        raise ValueError("December protocol requires three source clusters")
    labels = np.asarray([row["label"] for row in ledger])
    probabilities = calibrated_probabilities(np.asarray(logits), release, published_probabilities)
    baseline = np.asarray(baseline)
    rng = np.random.default_rng(20260828)
    draws = {"average_precision": [], "log_loss": []}
    cache = {}
    for _ in range(2000):
        choice = tuple(map(int, rng.integers(0, len(groups), size=len(groups))))
        if choice not in cache:
            indices = np.concatenate([groups[i] for i in choice])
            cache[choice] = (
                defined_metrics(labels[indices], probabilities[indices], release.operating_points[1].threshold),
                defined_metrics(labels[indices], baseline[indices], BASELINE_THRESHOLDS[1]))
        t, b = cache[choice]
        for name in draws:
            draws[name].append(None if t[name] is None or b[name] is None else t[name] - b[name])
    return {"draws": 2000, "seed": 20260828, "unit": "whole_base_session", "paired": True,
        "interpretation": "weak_conditional_summary_three_clusters_one_date",
        "intervals": {name: {"lower": float(np.quantile(valid, .025)) if valid else None,
                            "upper": float(np.quantile(valid, .975)) if valid else None,
                            "undefined_draws": len(values) - len(valid)}
                      for name, values in draws.items() for valid in [[v for v in values if v is not None]]}}
