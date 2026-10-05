"""Fixed operating points and paired source-session summaries; never optimize."""
import numpy as np

from .research_evaluation import metrics, sigmoid

MODES = ("high_precision", "balanced", "high_recall")
BASELINE_THRESHOLDS = (1.0, 0.5769230769230769, 0.01296456352636128)


def defined_metrics(labels, probabilities, threshold):
    if not len(labels):
        return {"undefined_reason": "no retained observations"}
    result = metrics(labels, probabilities, threshold)
    tp, fp, fn = result["tp"], result["fp"], result["fn"]
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


def fixed_comparison(ledger, logits, baseline, families, symbols, release):
    release.require_research_inference()
    labels = np.asarray([row["label"] for row in ledger], dtype=np.int64)
    logits, baseline = np.asarray(logits, dtype=np.float64), np.asarray(baseline, dtype=np.float64)
    if (not len(labels) or logits.shape != labels.shape or baseline.shape != labels.shape
            or len(families) != len(labels) or len(symbols) != len(labels)
            or not np.isfinite(logits).all() or not np.isfinite(baseline).all()
            or np.any((baseline < 0) | (baseline > 1))):
        raise ValueError("holdout metric population differs or is nonfinite")
    probability = sigmoid(logits / release.temperature)
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


def paired_bootstrap(ledger, logits, baseline, release):
    """Keep every variant of each base session together in every paired draw."""
    sessions = np.asarray([row["base_session_id"] for row in ledger])
    groups = [np.flatnonzero(sessions == value) for value in sorted(set(sessions))]
    if len(groups) != 3:
        raise ValueError("December protocol requires three source clusters")
    labels = np.asarray([row["label"] for row in ledger])
    probabilities = sigmoid(np.asarray(logits) / release.temperature)
    baseline = np.asarray(baseline)
    rng = np.random.default_rng(20260828)
    draws = {"average_precision": [], "log_loss": []}
    for _ in range(2000):
        indices = np.concatenate([groups[i] for i in rng.integers(0, len(groups), size=len(groups))])
        t = defined_metrics(labels[indices], probabilities[indices], release.operating_points[1].threshold)
        b = defined_metrics(labels[indices], baseline[indices], BASELINE_THRESHOLDS[1])
        for name in draws:
            draws[name].append(None if t[name] is None or b[name] is None else t[name] - b[name])
    return {"draws": 2000, "seed": 20260828, "unit": "whole_base_session", "paired": True,
        "interpretation": "weak_conditional_summary_three_clusters_one_date",
        "intervals": {name: {"lower": float(np.quantile(valid, .025)) if valid else None,
                            "upper": float(np.quantile(valid, .975)) if valid else None,
                            "undefined_draws": len(values) - len(valid)}
                      for name, values in draws.items() for valid in [[v for v in values if v is not None]]}}
