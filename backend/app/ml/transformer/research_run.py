"""GPU slot execution; cloud publication and verification remain separate."""
from dataclasses import replace
import time

import numpy as np
import torch

from .research_evaluation import compare, family_comparison, fit_temperature, sigmoid
from .research_model import SequenceClassifier
from .research_policy import Trial, class_session_weights, seed_stability, select_grid
from .research_smoke import run_smoke
from .research_training import configure, predict, tensors, train_trial
from .verification_spec import canonical, digest


def logits_artifact(store, role, split, logits):
    rows = [{"target_id": target, "label": int(label), "logit": float(value)}
            for target, label, value in zip(split.target_ids, split.labels, logits, strict=True)]
    return store.put(role + "-predictions.json", canonical(rows))


def selected_model(path, checksum, trial, bindings):
    raw = path.read_bytes()
    if digest(raw) != checksum:
        raise ValueError("selected checkpoint checksum differs")
    state = torch.load(path, map_location="cpu", weights_only=True)
    if state["bindings"] != bindings or state["trial"] != trial.__dict__:
        raise ValueError("selected checkpoint lineage differs")
    model = SequenceClassifier(trial.width).to("cuda")
    model.load_state_dict(state["model"], strict=True)
    return model.eval()


def real_smoke(split, expires):
    indices = np.linspace(0, len(split) - 1, 1024, dtype=np.int64)
    small = replace(split, values=split.values[indices], valid=split.valid[indices],
        missing=split.missing[indices], labels=split.labels[indices],
        target_ids=tuple(split.target_ids[i] for i in indices), sessions=tuple(split.sessions[i] for i in indices))
    weights = class_session_weights(small.labels.tolist(), list(small.sessions))
    model = SequenceClassifier(64).to("cuda").train()
    optimizer = torch.optim.AdamW(model.parameters(), lr=.0003, weight_decay=.01)
    for _ in range(2):
        for offset in range(0, 1024, 64):
            if time.monotonic() >= expires:
                raise TimeoutError("real-data smoke deadline")
            take = np.arange(offset, offset + 64)
            target = torch.tensor(small.labels[take], dtype=torch.float32, device="cuda")
            weight = torch.tensor(np.asarray(weights)[take], dtype=torch.float32, device="cuda")
            optimizer.zero_grad(set_to_none=True)
            loss = (torch.nn.functional.binary_cross_entropy_with_logits(
                model(*tensors(small, take)), target, reduction="none") * weight).mean()
            if not torch.isfinite(loss):
                raise ValueError("nonfinite real-data smoke loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1., error_if_nonfinite=True)
            optimizer.step()
    return {"rows": 1024, "epochs": 2, "optimizer_steps": 32,
        "ordered_target_sha256": digest(canonical(small.target_ids)), "loss": float(loss.detach())}


def run(slot, splits, bindings, baseline, thresholds, prior, store, work, expires):
    configure(42)
    if slot == "smoke":
        return {"kind": "smoke", "checks": run_smoke(work / "synthetic", bindings=bindings, publish=store.checkpoint),
                "real_data": real_smoke(splits["train"], expires - 600)}
    grid = [prior[name]["result"] for name in prior if name.startswith("search-")]
    if slot.startswith("search-"):
        _, width, rate = slot.split("-")
        trial = Trial(int(width), .0003 if rate == "0003" else .001)
    else:
        winner = select_grid(grid)
        trial = Trial(**winner["trial"])
        if slot.startswith("seed-"):
            trial = replace(trial, seed=int(slot.split("-")[1]))
    if slot != "inference":
        result = train_trial(splits["train"], splits["selection"], trial, output=work / slot,
            bindings=bindings, publish=store.checkpoint, expires=expires)
        checkpoint = next(item for item in result["published_checkpoints"] if item["epoch"] == result["selected_epoch"])
        model = selected_model(work / slot / checkpoint["name"], checkpoint["sha256"], trial, bindings)
        logits = predict(model, splits["selection"], expires=expires - 120)
        logits_artifact(store, "selection", splits["selection"], logits)
        return {**result, "kind": "trial", "selected_checkpoint": checkpoint}
    stability = seed_stability([winner, prior["seed-7"]["result"], prior["seed-2027"]["result"]], trial)
    winner_slot = next(name for name in prior if prior[name]["result"].get("trial_sha256") == winner["trial_sha256"])
    item = winner["selected_checkpoint"]
    raw, _ = store.read(winner_slot, item["object_name"], {k: item[k] for k in ("sha256", "size_bytes", "version_id")})
    checkpoint = work / "selected.pt"
    checkpoint.write_bytes(raw)
    model = selected_model(checkpoint, item["sha256"], trial, bindings)
    logits = {role: predict(model, splits[role], expires=expires - 600) for role in ("calibration", "operating_point")}
    for role, values in logits.items():
        logits_artifact(store, role, splits[role], values)
    calibration = fit_temperature(splits["calibration"], logits["calibration"])
    baseline_o = baseline["operating_point"]
    frozen = baseline_o["frozen_calibration"]
    probabilities = np.interp(baseline_o["raw_probabilities"], frozen["isotonic_x"], frozen["isotonic_y"])
    comparison = compare(splits["operating_point"], logits["operating_point"], calibration["temperature"],
        baseline_o["target_ids"], baseline_o["labels"], probabilities, thresholds)
    calibrated = sigmoid(logits["operating_point"] / calibration["temperature"])
    families = family_comparison(splits["operating_point"].labels, baseline_o["families"],
                                 calibrated, probabilities)
    torch.cuda.synchronize()
    started = time.monotonic()
    predict(model, splits["operating_point"], expires=expires - 120)
    torch.cuda.synchronize()
    return {"kind": "inference", "winner_trial_sha256": winner["trial_sha256"], "stability": stability,
        "calibration": calibration, "comparison": comparison, "per_family": families,
        "inference": {"batch_size": 64, "rows": len(splits["operating_point"]),
            "elapsed_seconds": time.monotonic() - started, "includes_host_to_device": True,
            "lightgbm_latency": "not_measured_saved_predictions_reused"},
        "freeze_blocked": comparison["freeze_blocked"] or not stability["passed"],
        "decision": "operator_review_required", "final_test_access": False}
