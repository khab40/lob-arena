"""One fixed-grid GPU trial; model execution is reserved for Nebius Jobs."""
from dataclasses import asdict
import math
import os
from pathlib import Path
import random
import time

import numpy as np
import torch
from torch.nn import functional as F

from .research_checkpoint import load_checkpoint, write_checkpoint
from .research_model import SequenceClassifier
from .research_policy import class_session_weights, improved, learning_rate_factor


def configure(seed):
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":4096:8"
    if not torch.cuda.is_available():
        raise RuntimeError("authorized CUDA Job required; no CPU training fallback")
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.use_deterministic_algorithms(True)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True
    torch.backends.cuda.enable_flash_sdp(False)
    torch.backends.cuda.enable_mem_efficient_sdp(False)
    torch.backends.cuda.enable_math_sdp(True)
    torch.cuda.reset_peak_memory_stats()


def tensors(split, indices):
    return tuple(torch.from_numpy(np.array(value[indices], copy=True)).to("cuda")
                 for value in (split.values, split.valid, split.missing))


def predict(model, split, batch_size=64, *, expires=math.inf):
    model.eval()
    logits = []
    with torch.inference_mode():
        for offset in range(0, len(split), batch_size):
            if time.monotonic() >= expires:
                raise TimeoutError("prediction deadline")
            indices = np.arange(offset, min(offset + batch_size, len(split)))
            logits.extend(model(*tensors(split, indices)).cpu().tolist())
    return np.asarray(logits, dtype=np.float64)


def selection_metrics(logits, labels):
    # Stable raw-logit loss; no calibration or operating-point data enters training.
    loss = float(np.mean(np.logaddexp(0, logits) - labels * logits))
    positive = logits >= 0
    tp = int(np.sum(positive & (labels == 1)))
    fp = int(np.sum(positive & (labels == 0)))
    fn = int(np.sum(~positive & (labels == 1)))
    return loss, 2 * tp / max(1, 2 * tp + fp + fn)


def train_trial(train, selection, trial, *, output: Path, bindings, publish, expires, resume=None):
    """publish(path, sha) must return a verified version-id/checksum receipt.

    The Job wrapper owns input authentication, exact execution authorization,
    publication timeouts and independent result verification. This is not a
    cloud submission API. Calibration/operating-point rows are never arguments.
    """
    if train.role != "train" or selection.role != "selection":
        raise ValueError("training and checkpoint selection roles are fixed")
    if not callable(publish) or not math.isfinite(expires) or expires <= time.monotonic() + 600:
        raise ValueError("durable publication callback and execution reserve required")
    if not bindings.get("source_commit") or not bindings.get("image_digest"):
        raise ValueError("code and runtime image bindings required")
    if set(train.target_ids) & set(selection.target_ids):
        raise ValueError("training/selection targets overlap")
    weights = np.asarray(class_session_weights(train.labels.tolist(), list(train.sessions)), dtype=np.float32)
    configure(trial.seed)
    output.mkdir(parents=True, exist_ok=False)
    model = SequenceClassifier(trial.width).to("cuda")
    optimizer = torch.optim.AdamW(model.parameters(), lr=trial.learning_rate, weight_decay=0.01,
                                 betas=(0.9, 0.999), eps=1e-8)
    batches = math.ceil(len(train) / trial.batch_size)
    total_steps = batches * trial.max_epochs
    progress = {"epoch": 0, "global_step": 0, "best_loss": math.inf, "best_epoch": 0,
                "stale_epochs": 0, "history": []}
    if resume is not None:
        progress = load_checkpoint(resume["path"], resume["sha256"], model=model,
            optimizer=optimizer, trial=trial, bindings=bindings)
        if (not 0 < progress["epoch"] <= trial.max_epochs
                or progress["global_step"] != progress["epoch"] * batches):
            raise ValueError("checkpoint epoch/optimizer position differs")
    started = time.monotonic()
    records = []
    for epoch in range(progress["epoch"], trial.max_epochs):
        if progress["stale_epochs"] >= trial.patience:
            break
        model.train()
        order = torch.randperm(len(train), generator=torch.Generator().manual_seed(trial.seed + epoch)).numpy()
        weighted_sum = 0.0
        for offset in range(0, len(order), trial.batch_size):
            if time.monotonic() >= expires - 600:
                raise TimeoutError("training publication reserve reached; resume last acknowledged epoch")
            indices = order[offset:offset + trial.batch_size]
            labels = torch.from_numpy(train.labels[indices].astype(np.float32)).to("cuda")
            weight = torch.from_numpy(weights[indices]).to("cuda")
            factor = learning_rate_factor(progress["global_step"], total_steps)
            for group in optimizer.param_groups:
                group["lr"] = trial.learning_rate * factor
            optimizer.zero_grad(set_to_none=True)
            logits = model(*tensors(train, indices))
            loss = (F.binary_cross_entropy_with_logits(logits, labels, reduction="none") * weight).mean()
            if not torch.isfinite(loss):
                raise ValueError("nonfinite weighted training loss")
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0, error_if_nonfinite=True)
            optimizer.step()
            weighted_sum += float(loss.detach()) * len(indices)
            progress["global_step"] += 1
        predicted = predict(model, selection, expires=expires - 600)
        selection_loss, f1 = selection_metrics(predicted, selection.labels)
        if improved(selection_loss, progress["best_loss"]):
            progress.update(best_loss=selection_loss, best_epoch=epoch + 1, stale_epochs=0)
        else:
            progress["stale_epochs"] += 1
        progress["epoch"] = epoch + 1
        progress["history"].append({"epoch": epoch + 1, "weighted_train_loss": weighted_sum / len(train),
            "selection_log_loss": selection_loss, "selection_f1_at_half": f1})
        records.append(write_checkpoint(output, model=model, optimizer=optimizer, trial=trial,
            bindings=bindings, progress=progress, publish=publish))
    torch.cuda.synchronize()
    return {"status": "completed_pending_independent_verification", "trial": asdict(trial),
            "trial_sha256": trial.sha256(), "bindings": bindings, "progress": progress,
            "published_checkpoints": records, "selected_epoch": progress["best_epoch"],
            "selection_log_loss": progress["best_loss"],
            "parameter_count": sum(p.numel() for p in model.parameters()),
            "duration_seconds": time.monotonic() - started,
            "peak_allocated_gpu_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_gpu_bytes": torch.cuda.max_memory_reserved(),
            "runtime": {"torch": str(torch.__version__), "cuda": torch.version.cuda,
                        "cudnn": torch.backends.cudnn.version(), "gpu": torch.cuda.get_device_name()}}
