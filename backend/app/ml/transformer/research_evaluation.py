"""Saved-prediction calibration and comparison for the authorized research Job."""
import math

import numpy as np

from app.ml.lightgbm.scoring import calibration_metrics, select_operating_points


def checked(labels, values):
    labels, values = np.asarray(labels), np.asarray(values, dtype=np.float64)
    if (labels.ndim != 1 or values.shape != labels.shape or not len(labels)
            or not np.isin(labels, (0, 1)).all() or not np.isfinite(values).all()):
        raise ValueError("finite aligned binary predictions required")
    return labels.astype(np.int64), values


def sigmoid(logits):
    return np.exp(-np.logaddexp(0, -logits))


def fit_temperature(split, logits):
    """Fixed golden-section minimization, at most200 evaluations, C only."""
    if split.role != "calibration":
        raise ValueError("temperature fitting requires the calibration role")
    labels, logits = checked(split.labels, logits)
    if min(np.count_nonzero(labels == label) for label in (0, 1)) < 20:
        raise ValueError("insufficient calibration support")
    calls = []
    def objective(temperature):
        if len(calls) >= 200:
            raise ValueError("temperature evaluation bound exhausted")
        scaled = logits / temperature
        value = float(np.mean(np.logaddexp(0, scaled) - labels * scaled))
        if not math.isfinite(value):
            raise ValueError("nonfinite calibration objective")
        calls.append((temperature, value))
        return value
    left, right, ratio = 0.05, 20.0, (math.sqrt(5) - 1) / 2
    objective(left)
    objective(right)
    a, b = right - ratio * (right - left), left + ratio * (right - left)
    fa, fb = objective(a), objective(b)
    while right - left > 1e-6:
        if fa <= fb:
            right, b, fb = b, a, fa
            a = right - ratio * (right - left)
            fa = objective(a)
        else:
            left, a, fa = a, b, fb
            b = left + ratio * (right - left)
            fb = objective(b)
    temperature, loss = min(calls, key=lambda item: (item[1], item[0]))
    return {"temperature": temperature, "objective_log_loss": loss, "evaluations": len(calls),
            "converged": True, "boundary_hit": temperature in (0.05, 20.0),
            "solver": "golden_section_v1", "tolerance": 1e-6, "fitting_role": "calibration"}


def metrics(labels, probabilities, threshold=0.5):
    labels, probabilities = checked(labels, probabilities)
    if np.any((probabilities < 0) | (probabilities > 1)) or not 0 <= threshold <= 1:
        raise ValueError("probabilities and threshold must be in [0,1]")
    predicted = probabilities >= threshold
    tp, fp, fn = (int(np.count_nonzero(mask)) for mask in
                  (predicted & (labels == 1), predicted & (labels == 0), ~predicted & (labels == 1)))
    clipped = np.clip(probabilities, 1e-15, 1 - 1e-15)
    reliability, bins = calibration_metrics(labels, probabilities, bins=10)
    order = np.argsort(-probabilities, kind="stable")
    ends = np.r_[np.flatnonzero(np.diff(probabilities[order]) != 0), len(labels) - 1]
    cumulative = np.cumsum(labels[order])[ends]
    recall = cumulative / max(1, int(labels.sum()))
    ap = float(np.sum(np.diff(np.r_[0, recall]) * cumulative / (ends + 1)))
    return {"log_loss": float(-np.mean(labels * np.log(clipped) + (1 - labels) * np.log1p(-clipped))),
            "pr_auc_average_precision": ap, "precision": tp / max(1, tp + fp),
            "recall": tp / max(1, tp + fn), "f1": 2 * tp / max(1, 2 * tp + fp + fn),
            "true_positive": tp, "false_positive": fp, "false_negative": fn,
            **reliability.model_dump(), "reliability_bins": bins}


def family_comparison(labels, families, transformer_probabilities, baseline_probabilities):
    """Each family's positives versus shared controls, at threshold 0.5.

    Controls are reused across families; these overlapping populations must not
    be summed into campaign totals. Other families' positives are excluded.
    """
    labels, transformer = checked(labels, transformer_probabilities)
    _, baseline = checked(labels, baseline_probabilities)
    families = np.asarray(families)
    if (families.shape != labels.shape or any(not isinstance(f, str) or not f for f in families)
            or set(labels.tolist()) != {0, 1} or np.any((families == "control") & (labels == 1))):
        raise ValueError("aligned named attack positives and negative controls required")
    for probabilities in (transformer, baseline):
        if np.any((probabilities < 0) | (probabilities > 1)):
            raise ValueError("family probabilities must be in [0,1]")
    controls = labels == 0
    results = {}
    for family in sorted(set(families[labels == 1])):
        mask = controls | ((families == family) & (labels == 1))
        results[family] = {"population": "family_positives_plus_shared_controls", "threshold": 0.5,
            "rows": int(mask.sum()), "positives": int(labels[mask].sum()), "negatives": int(controls.sum()),
            "transformer": metrics(labels[mask], transformer[mask]),
            "lightgbm": metrics(labels[mask], baseline[mask])}
    return results


def compare(split, logits, temperature, baseline_ids, baseline_labels, baseline_probabilities, baseline_thresholds):
    if split.role != "operating_point" or not 0.05 <= temperature <= 20:
        raise ValueError("bounded temperature and operating-point role required")
    if (tuple(baseline_ids) != split.target_ids or len(set(baseline_ids)) != len(baseline_ids)
            or not np.array_equal(baseline_labels, split.labels)):
        raise ValueError("baseline and Transformer targets/labels do not match exactly")
    _, logits = checked(split.labels, logits)
    raw, calibrated = sigmoid(logits), sigmoid(logits / temperature)
    before, after = metrics(split.labels, raw), metrics(split.labels, calibrated)
    baseline = metrics(split.labels, baseline_probabilities)
    calibration_failed = (after["brier_score"] > before["brier_score"] + 1e-6
                          and after["expected_calibration_error"] > before["expected_calibration_error"] + 1e-6)
    thresholds, floor_failed = [], False
    try:
        thresholds = [point.model_dump(mode="json") for point in select_operating_points(
            split.labels, calibrated, precision_floor=0.9, recall_floor=0.9)]
    except ValueError:
        floor_failed = True
    if set(baseline_thresholds) != {"high_precision", "balanced", "high_recall"}:
        raise ValueError("all frozen baseline operating points required")
    return {"scope": "development_comparison_not_final_evaluation", "raw_transformer": before,
            "calibrated_transformer": after, "frozen_lightgbm": baseline,
            "delta_log_loss": after["log_loss"] - baseline["log_loss"],
            "delta_average_precision": after["pr_auc_average_precision"] - baseline["pr_auc_average_precision"],
            "transformer_selected_operating_points": thresholds,
            "lightgbm_frozen_operating_points": {name: {"threshold": threshold,
                "metrics": metrics(split.labels, baseline_probabilities, threshold)}
                for name, threshold in baseline_thresholds.items()},
            "freeze_blocked": calibration_failed or floor_failed,
            "calibration_worsened_brier_and_ece": calibration_failed, "unattainable_floor": floor_failed,
            "limitations": ["operating_points_selected_on_reported_role", "prior_development_exposure",
                            "one_date_and_one_instrument_per_role", "research_control_negative_labels"]}
