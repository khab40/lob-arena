"""Read verified local artifacts for presentation; never load a model."""
import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(directory: Path):
    receipt_raw = (directory / "verification.json").read_bytes()
    receipt = json.loads(receipt_raw)
    request_raw = (directory / "request.json").read_bytes()
    request = json.loads(request_raw)
    provider = json.loads((directory / "provider-terminal.json").read_bytes())
    result = receipt["result"]
    if receipt["status"] != "verified" or result.get("status") != "verified" or result["kind"] != "trial":
        raise ValueError("report requires an independently verified training trial")
    if (provider["status"]["state"] != "COMPLETED"
            or provider["metadata"]["id"] != result["job_id"]
            or receipt["context"]["job_id"] != result["job_id"]
            or result["request_sha256"] != sha(request_raw)):
        raise ValueError("report execution identities differ")
    for key in ("source_commit", "image_digest"):
        if request[key] != result["bindings"][key]:
            raise ValueError("report source binding differs")
    for value in (request["slot"], request["run_id"], result["job_id"], request["output_bucket"]):
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", value):
            raise ValueError("unsafe report identity")
    for value in (request["output_prefix"], result["selected_checkpoint"]["object_name"]):
        if not re.fullmatch(r"[a-zA-Z0-9_./-]+", value) or ".." in value:
            raise ValueError("unsafe artifact identity")

    def artifact(name):
        raw = (directory / "artifacts" / name).read_bytes()
        expected = receipt["inventory"][name]
        if len(raw) != expected["size_bytes"] or sha(raw) != expected["sha256"]:
            raise ValueError(f"report artifact checksum differs: {name}")
        return json.loads(raw)

    saved = artifact("result.json")
    if {k: v for k, v in saved.items() if k != "status"} != {k: v for k, v in result.items() if k != "status"}:
        raise ValueError("report result differs from verified artifact")
    if artifact("configuration.json") != request:
        raise ValueError("report request differs from verified artifact")
    history = result["progress"]["history"]
    if not history or [h["epoch"] for h in history] != list(range(1, len(history) + 1)):
        raise ValueError("invalid report epoch sequence")
    for row in history:
        for key in ("weighted_train_loss", "selection_log_loss", "selection_f1_at_half"):
            if not math.isfinite(row[key]) or row[key] < 0 or key.endswith("half") and row[key] > 1:
                raise ValueError("invalid report metric")
    selected = result["selected_epoch"]
    if not 1 <= selected <= len(history):
        raise ValueError("selected epoch outside recorded history")
    rows = artifact("selection-predictions.json")
    counts = dict.fromkeys(("tn", "fp", "fn", "tp"), 0)
    if not rows or len({r["target_id"] for r in rows}) != len(rows):
        raise ValueError("empty or duplicate selection rows")
    losses = []
    for row in rows:
        label, logit = row["label"], row["logit"]
        if label not in (0, 1) or not math.isfinite(logit):
            raise ValueError("invalid saved selection prediction")
        counts[("tn", "fp", "fn", "tp")[2 * label + int(logit >= 0)]] += 1
        losses.append(max(logit, 0) + math.log1p(math.exp(-abs(logit))) - label * logit)
    tp, fp, fn = (counts[k] for k in ("tp", "fp", "fn"))
    metrics = {"precision": tp / max(1, tp + fp), "recall": tp / max(1, tp + fn),
               "f1": 2 * tp / max(1, 2 * tp + fp + fn), "log_loss": sum(losses) / len(rows)}
    for key, source in (("f1", "selection_f1_at_half"), ("log_loss", "selection_log_loss")):
        if abs(metrics[key] - result[source]) > 1e-9 or abs(result[source] - history[selected - 1][source]) > 1e-9:
            raise ValueError("report metrics differ from verified predictions")
    normalization = artifact("normalization.json")
    return {"request": request, "result": result, "provider": provider, "counts": counts,
            "training_rows": normalization["fitting_rows"],
            "metrics": metrics, "receipt_sha256": sha(receipt_raw), "receipt": receipt}


def markdown(data):
    req, r, c, m = (data[k] for k in ("request", "result", "counts", "metrics"))
    trial, checkpoint = r["trial"], r["selected_checkpoint"]
    status = data["provider"]["status"]
    elapsed = (datetime.fromisoformat(status["finished_at"]) - datetime.fromisoformat(status["started_at"])).total_seconds()
    lines = [f'# Experiment: {req["slot"]}', "", "Status: independently verified training result.", "",
        ("[Story #24](https://github.com/khab40/lob-arena/issues/24) · "
         "[Project #3](https://github.com/users/khab40/projects/3)"), "",
        "## Basic results", "", "| Measure | Value |", "|---|---:|",
        f'| Width / learning rate / seed | {trial["width"]} / {trial["learning_rate"]} / {trial["seed"]} |',
        f'| Batch / max epochs / patience | {trial["batch_size"]} / {trial["max_epochs"]} / {trial["patience"]} |',
        f'| Selected / stopped epoch | {r["selected_epoch"]} / {r["progress"]["epoch"]} |',
        f'| Training rows (normalizer fit) | {data["training_rows"]} |',
        f'| Selection rows / positives / negatives | {sum(c.values())} / {c["tp"] + c["fn"]} / {c["tn"] + c["fp"]} |',
        f'| Raw selection log loss | {m["log_loss"]:.10f} |',
        f'| Precision / recall / F1 at 0.5 | {m["precision"]:.6f} / {m["recall"]:.6f} / {m["f1"]:.6f} |',
        f'| Parameters | {r["parameter_count"]:,} |', "",
        "Selection data was used for tuning. Probabilities are uncalibrated; these",
        "metrics do not establish generalization or superiority to LightGBM.", "",
        "## Learning curves", "", "![Losses and selection F1 by epoch](learning-curves.png)", "",
        "The dashed line marks the selected epoch. Training loss is class/session",
        "weighted; selection log loss is unweighted. Their magnitudes are not directly comparable.", "",
        "| Epoch | Weighted training loss | Selection log loss | Selection F1 at 0.5 |", "|---:|---:|---:|---:|"]
    for row in r["progress"]["history"]:
        lines.append(f'| {row["epoch"]} | {row["weighted_train_loss"]:.8f} | '
                     f'{row["selection_log_loss"]:.8f} | {row["selection_f1_at_half"]:.6f} |')
    lines += ["", "## Selected-checkpoint errors", "", "![Selection confusion matrix at 0.5](confusion-matrix.png)",
        "", "| Actual / predicted | Negative | Positive |", "|---|---:|---:|",
        f'| Negative | {c["tn"]} | {c["fp"]} |', f'| Positive | {c["fn"]} | {c["tp"]} |', "",
        "## Runtime and preservation", "", "| Measure | Value |", "|---|---:|",
        f'| Provider runtime / training loop (s) | {elapsed:.2f} / {r["duration_seconds"]:.2f} |',
        f'| Worker elapsed / CPU time (s) | {r["measurements"]["elapsed_seconds"]:.2f} / {r["measurements"]["cpu_seconds"]:.2f} |',
        f'| Peak host RSS (GiB) | {r["measurements"]["peak_rss_kib"] / 1024**2:.3f} |',
        f'| GPU allocated / reserved (MiB) | {r["peak_allocated_gpu_bytes"] / 1024**2:.2f} / {r["peak_reserved_gpu_bytes"] / 1024**2:.2f} |',
        f'| Verified artifacts | {len(data["receipt"]["inventory"])} |', "",
        "Training-loop time includes selection evaluation and checkpoint publication.",
        "Actual cost, GPU utilization and inference latency remain unmeasured/unreconciled.",
        (f'Online MLflow status: `{r.get("mlflow_reconciliation", "not_recorded")}`. '
         "Configuration, metrics and replayable events are retained."), "",
        "## Lineage", "", f'- Run: `{req["run_id"]}`', f'- Job: `{r["job_id"]}`',
        f'- Source: `{req["source_commit"]}`', f'- Image: `{req["image_digest"]}`',
        f'- Request SHA-256: `{r["request_sha256"]}`', f'- Verification SHA-256: `{data["receipt_sha256"]}`',
        f'- S3 prefix: `s3://{req["output_bucket"]}/{req["output_prefix"]}`',
        f'- Checkpoint: `{checkpoint["object_name"]}` (version `{checkpoint["version_id"]}`)',
        f'- Checkpoint SHA-256: `{checkpoint["sha256"]}`', "",
        "Calibration, precision-recall comparison and latency plots await those later measurements.", ""]
    return "\n".join(lines)
