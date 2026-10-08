"""Saved-logit arithmetic fixtures; no fitting or weight execution."""
from types import SimpleNamespace
import json
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
from app.ml.transformer import research_comparison_readback as readback  # noqa: E402
from app.ml.transformer.research_evaluation import compare, metrics  # noqa: E402


def fixture(monkeypatch):
    y, z = np.array([0, 1] * 20), np.zeros(40)
    ids, probs = tuple(str(i) for i in range(40)), np.full(40, .5)
    thresholds = {"high_precision": 1., "balanced": .5, "high_recall": 0.}
    split = SimpleNamespace(role="operating_point", labels=y, target_ids=ids)
    baseline = {"operating_point": {"target_ids": ids, "labels": y, "raw_probabilities": probs,
        "frozen_calibration": {"isotonic_x": [0., 1.], "isotonic_y": [0., 1.]},
        "families": ["control", "fixture"] * 20}}
    winner = {"trial_sha256": "a" * 64, "trial": {"width": 64, "learning_rate": .0003}}
    stability = {"passed": True}
    monkeypatch.setattr(readback, "load", lambda *args: (baseline, thresholds, {}))
    monkeypatch.setattr(readback, "select_grid", lambda *args: winner)
    monkeypatch.setattr(readback, "seed_stability", lambda *args: stability)
    comparison = compare(split, z, 1., ids, y, probs, thresholds)
    result = {"winner_trial_sha256": "a" * 64, "stability": stability,
        "calibration": {"temperature": 1., "objective_log_loss": float(np.log(2)),
            "fitting_role": "calibration", "solver": "golden_section_v1", "converged": True,
            "evaluations": 40}, "comparison": comparison,
        "per_family": {"fixture": {"population": "family_positives_plus_shared_controls",
            "threshold": .5, "rows": 40, "positives": 20, "negatives": 20,
            "transformer": metrics(y, probs), "lightgbm": metrics(y, probs)}},
        "freeze_blocked": comparison["freeze_blocked"], "inference": {"elapsed_seconds": 1., "rows": 40}}
    artifacts = {k: b"fixture" for k in ("baseline-predictions.parquet", "baseline-calibration.json",
        "calibration-predictions.json", "operating_point-predictions.json", "target-ledger.jsonl")}
    prior = {"seed-7": {"result": {}}, "seed-2027": {"result": {}}}
    return result, artifacts, {}, prior, lambda *args: (y, z)


def test_independent_comparison_accepts_saved_arithmetic(monkeypatch):
    assert readback.verify(*fixture(monkeypatch))["comparison_verified"]


@pytest.mark.parametrize("change", [None, "origin", "bindings", "event", "missing", "duplicate"])
def test_comparison_binds_original_checkpoint_to_observed_inputs(monkeypatch, change):
    from app.ml.transformer.research_execution_spec import comparison_template
    from app.ml.transformer.research_confirmation_contract import CONTEXT_PUBLIC_KEY
    previous = json.loads((Path(__file__).parent / "fixtures/transformer_selected_origin.json").read_bytes())
    request = comparison_template("a" * 40, "sha256:" + "b" * 64, CONTEXT_PUBLIC_KEY, "c" * 32)
    args = fixture(monkeypatch)
    result, artifacts, _, prior, _ = args
    prior["search-128-0003"] = previous
    bindings = {**previous["result"]["bindings"], "source_commit": request["source_commit"],
                "image_digest": request["image_digest"]}
    result.update(execution_bindings=bindings, checkpoint_origin=readback.checkpoint_origin(request, prior, bindings))
    event = {"kind": "inputs_verified", "payload": {"bindings": bindings}}
    artifacts["event-0001.json"] = json.dumps(event).encode()
    if change == "origin":
        result["checkpoint_origin"]["checkpoint"]["epoch"] = 5
    elif change == "bindings":
        result["execution_bindings"]["normalization_sha256"] = "f" * 64
    elif change == "event":
        event["payload"]["bindings"] = {}
        artifacts["event-0001.json"] = json.dumps(event).encode()
    elif change == "missing":
        del artifacts["event-0001.json"]
    elif change == "duplicate":
        artifacts["event-0002.json"] = artifacts["event-0001.json"]
    if change is None:
        assert readback.verify(*args, request=request)["comparison_verified"]
    else:
        with pytest.raises(ValueError):
            readback.verify(*args, request=request)


@pytest.mark.parametrize("field", ["family", "positive_only", "nan", "objective", "winner", "duration", "freeze"])
def test_report_tampering_is_rejected(monkeypatch, field):
    args = fixture(monkeypatch)
    result = args[0]
    if field == "family":
        result["per_family"]["fixture"]["rows"] = 41
    elif field == "positive_only":
        result["per_family"]["fixture"].update(rows=20, positives=20, negatives=0)
        result["per_family"]["fixture"]["transformer"].update(precision=1., f1=1., false_positive=0)
    elif field == "nan":
        result["calibration"]["objective_log_loss"] = float("nan")
    elif field == "objective":
        result["calibration"]["objective_log_loss"] += .1
    elif field == "winner":
        result["winner_trial_sha256"] = "b" * 64
    elif field == "duration":
        result["inference"]["elapsed_seconds"] = -1.
    else:
        result["freeze_blocked"] = not result["freeze_blocked"]
    with pytest.raises(ValueError):
        readback.verify(*args)
