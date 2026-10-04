"""Recompute reported comparison arithmetic; never train, score weights or fit."""
import json
import math
from types import SimpleNamespace

import numpy as np

from .research_baseline import align, load
from .research_comparison_contract import checkpoint_origin, is_comparison
from .research_evaluation import compare, family_comparison, sigmoid
from .research_policy import Trial, seed_stability, select_grid
from .verification_spec import canonical


def verify(result, artifacts, metadata, prior, predictions, *, request=None):
    baseline, thresholds, _ = load(artifacts["baseline-predictions.parquet"],
                                    artifacts["baseline-calibration.json"], metadata)
    winner = select_grid([prior[name]["result"] for name in prior if name.startswith("search-")])
    if result["winner_trial_sha256"] != winner["trial_sha256"]:
        raise ValueError("comparison uses a different grid winner")
    stability = seed_stability([winner, prior["seed-7"]["result"], prior["seed-2027"]["result"]], Trial(**winner["trial"]))
    if canonical(stability) != canonical(result["stability"]):
        raise ValueError("confirmation stability differs")
    if request is not None and is_comparison(request):
        origin = checkpoint_origin(request, prior, result["execution_bindings"])
        inputs = [json.loads(raw)["payload"]["bindings"] for name, raw in artifacts.items()
                  if name.startswith("event-") and json.loads(raw)["kind"] == "inputs_verified"]
        if (not stability["passed"] or canonical(origin) != canonical(result["checkpoint_origin"])
                or len(inputs) != 1 or canonical(inputs[0]) != canonical(result["execution_bindings"])):
            raise ValueError("comparison checkpoint or execution provenance differs")
    calibration = result["calibration"]
    temperature = calibration["temperature"]
    if (not .05 <= temperature <= 20 or calibration["fitting_role"] != "calibration"
            or calibration["solver"] != "golden_section_v1" or not calibration["converged"]
            or not 4 <= calibration["evaluations"] <= 200):
        raise ValueError("calibration escaped its declared protocol")
    y, z = predictions(artifacts["calibration-predictions.json"], artifacts["target-ledger.jsonl"], "calibration", metadata)
    scaled = z / temperature
    objective = float(np.mean(np.logaddexp(0, scaled) - y * scaled))
    if (not math.isfinite(calibration["objective_log_loss"])
            or abs(objective - calibration["objective_log_loss"]) > 1e-10):
        raise ValueError("calibration objective differs from saved C logits")
    # Loss is convex in inverse temperature: check its bounded optimum without
    # fitting a second calibrator or using operating-point labels to select it.
    gradient = float(np.mean((sigmoid(scaled) - y) * z))
    if ((.05 < temperature < 20 and abs(gradient) > 1e-5)
            or temperature == .05 and gradient > 1e-5
            or temperature == 20 and gradient < -1e-5):
        raise ValueError("temperature fails independent bounded-optimum check")
    y, z = predictions(artifacts["operating_point-predictions.json"], artifacts["target-ledger.jsonl"], "operating_point", metadata)
    b = baseline["operating_point"]
    split = SimpleNamespace(role="operating_point", target_ids=b["target_ids"], labels=y)
    align(split, b)
    frozen = b["frozen_calibration"]
    probabilities = np.interp(b["raw_probabilities"], frozen["isotonic_x"], frozen["isotonic_y"])
    comparison = compare(split, z, temperature, b["target_ids"], b["labels"], probabilities, thresholds)
    if canonical(comparison) != canonical(result["comparison"]):
        raise ValueError("reported comparison differs from frozen predictions")
    families = family_comparison(y, b["families"], sigmoid(z / temperature), probabilities)
    if canonical(families) != canonical(result["per_family"]):
        raise ValueError("per-family metrics differ from saved predictions")
    if result["freeze_blocked"] != (comparison["freeze_blocked"] or not stability["passed"]):
        raise ValueError("research freeze disposition differs")
    duration = result["inference"]["elapsed_seconds"]
    if not math.isfinite(duration) or duration <= 0 or result["inference"]["rows"] != len(y):
        raise ValueError("invalid inference measurement")
    return {"comparison_verified": True, "calibration_optimum_checked_without_fitting": True}
