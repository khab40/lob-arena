"""Bounded scalar-only JSONL progress; no tensor, model or credential handling."""
from dataclasses import asdict
import json
import math
import time


FIELDS = {
    "phase_started": {"phase", "slot"},
    "inputs_ready": {"slot", "train_rows", "selection_rows", "calibration_rows", "operating_point_rows"},
    "trial_started": {"width", "learning_rate", "seed", "max_epochs", "batch_size", "patience",
        "train_rows", "selection_rows", "batches_per_epoch", "resumed_from_epoch", "optimizer", "schedule"},
    "epoch_started": {"epoch", "max_epochs", "global_step"},
    "epoch_completed": {"epoch", "weighted_train_loss", "selection_log_loss", "selection_f1_at_half",
        "epoch_seconds", "learning_rate_first_step", "learning_rate_last_step", "global_step", "improved",
        "best_epoch", "best_selection_log_loss", "stale_epochs", "patience", "checkpoint", "checkpoint_sha256"},
    "training_completed": {"selected_epoch", "selection_log_loss", "selection_f1_at_half", "stopped_epoch",
        "stop_reason", "global_step", "parameter_count", "training_seconds", "peak_allocated_gpu_bytes",
        "peak_reserved_gpu_bytes", "selection_rule", "checkpoint", "checkpoint_sha256"},
    "grid_candidate": {"trial_sha256", "width", "learning_rate", "seed", "selected_epoch",
        "selection_log_loss", "selection_f1_at_half", "parameter_count"},
    "grid_selected": {"trial_sha256", "width", "learning_rate", "seed", "selected_epoch",
        "selection_log_loss", "selection_f1_at_half", "parameter_count", "selection_rule"},
}


def emit(event, **fields):
    if event not in FIELDS or set(fields) - FIELDS[event]:
        raise ValueError("unrecognized progress fields")
    for value in fields.values():
        if (type(value) not in (str, int, float, bool)
                or isinstance(value, str) and len(value) > 256
                or isinstance(value, float) and not math.isfinite(value)):
            raise ValueError("progress values must be bounded finite scalars")
    line = json.dumps({"event": event, "evidence_status": "progress_not_independent_verification", **fields},
                      sort_keys=True, separators=(",", ":"), allow_nan=False)
    try:
        print(line, flush=True)
    except BrokenPipeError:
        pass  # A broken log stream must not change optimization/publication.


class TrialProgress:
    def __init__(self, trial, train_rows, selection_rows, batches, *, persist=None):
        self.trial, self.persist = trial, persist
        self.counts = {"train_rows": train_rows, "selection_rows": selection_rows, "batches_per_epoch": batches}
        self.started = 0.0

    def start(self, progress):
        emit("trial_started", **asdict(self.trial), **self.counts, resumed_from_epoch=progress["epoch"],
             optimizer="AdamW", schedule="5_percent_warmup_then_cosine_to_10_percent")

    def epoch_started(self, epoch, global_step):
        self.started = time.monotonic()
        emit("epoch_started", epoch=epoch, max_epochs=self.trial.max_epochs, global_step=global_step)

    def record(self, event, fields):
        emit(event, **fields)
        if self.persist is not None:
            self.persist(event, fields)

    def epoch_completed(self, progress, checkpoint, first_lr, last_lr):
        self.record("epoch_completed", {**progress["history"][-1],
            "epoch_seconds": time.monotonic() - self.started,
            "learning_rate_first_step": first_lr, "learning_rate_last_step": last_lr,
            "global_step": progress["global_step"], "improved": progress["best_epoch"] == progress["epoch"],
            "best_epoch": progress["best_epoch"], "best_selection_log_loss": progress["best_loss"],
            "stale_epochs": progress["stale_epochs"], "patience": self.trial.patience,
            "checkpoint": checkpoint["name"], "checkpoint_sha256": checkpoint["sha256"]})

    def finish(self, result):
        progress = result["progress"]
        checkpoint = next((c for c in result["published_checkpoints"] if c["epoch"] == result["selected_epoch"]), None)
        self.record("training_completed", {
            **{k: result[k] for k in ("selected_epoch", "selection_log_loss", "selection_f1_at_half",
                "parameter_count", "peak_allocated_gpu_bytes", "peak_reserved_gpu_bytes")},
            "stopped_epoch": progress["epoch"], "stop_reason": "patience" if progress["stale_epochs"] >= self.trial.patience
                else "max_epochs", "global_step": progress["global_step"], "training_seconds": result["duration_seconds"],
            "selection_rule": "raw_selection_log_loss_improvement_gt_1e-6; F1_diagnostic_only",
            "checkpoint": checkpoint["name"] if checkpoint else "retained_resume_checkpoint",
            "checkpoint_sha256": checkpoint["sha256"] if checkpoint else "see_resume_receipt"})


def grid_selected(results, winner, *, persist=None):
    selected = None
    for result in results:
        fields = {k: result[k] for k in ("trial_sha256", "selected_epoch", "selection_log_loss",
                                         "selection_f1_at_half", "parameter_count")}
        fields.update({k: result["trial"][k] for k in ("width", "learning_rate", "seed")})
        emit("grid_candidate", **fields)
        if result["trial_sha256"] == winner["trial_sha256"]:
            selected = fields
    if selected is None:
        raise ValueError("selected grid trial absent from candidate results")
    selected = {**selected, "selection_rule": "lowest_selection_log_loss_then_parameter_count_then_trial_sha256"}
    emit("grid_selected", **selected)
    if persist is not None:
        persist("grid_selected", selected)
