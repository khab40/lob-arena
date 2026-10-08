"""CUDA-only fixed inference; imported only inside the authorized Nebius Job."""
import time

import numpy as np
import torch

from .batches import iter_batches
from .research_inputs import ResearchSplit
from .research_policy import Trial
from .research_run import selected_model
from .research_training import configure, predict
from .verification_spec import canonical, digest


class FixedGpuConsumer:
    def __init__(self, release, checkpoint_path, original_bindings, *, expires):
        release.require_research_inference()
        configure(release.training.seed)
        trial = Trial(**{name: getattr(release.training, name) for name in Trial.__dataclass_fields__})
        self.model = selected_model(checkpoint_path, release.artifacts.checkpoint.sha256, trial, original_bindings)
        self.expires = expires
        self.measurements = {}

    def infer(self, dataset, normalizer, *, targets=None):
        wanted = None if targets is None else set(targets)
        ids, labels, logits = [], [], []
        torch.cuda.synchronize()
        started = time.monotonic()
        for batch in iter_batches(dataset, normalizer, batch_size=64,
                                  fold="validation" if targets is not None else "test"):
            indices = np.asarray([i for i, target in enumerate(batch.target_ids)
                                  if wanted is None or target in wanted], dtype=np.int64)
            if not len(indices):
                continue
            split = ResearchSplit("holdout", batch.values[indices], batch.valid_steps[indices],
                batch.missing_features[indices], batch.labels[indices],
                tuple(batch.target_ids[i] for i in indices), tuple(batch.run_ids[i] for i in indices))
            values = predict(self.model, split, expires=self.expires - 600)
            ids.extend(split.target_ids)
            labels.extend(map(int, split.labels))
            logits.extend(map(float, values))
            if wanted is not None and len(ids) == len(wanted):
                break
        if targets is not None and tuple(ids) != tuple(targets):
            raise ValueError("GPU reference target order differs")
        torch.cuda.synchronize()
        self.measurements = {"elapsed_seconds": time.monotonic() - started, "batch_size": 64,
            "rows": len(ids), "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_gpu_reserved_bytes": torch.cuda.max_memory_reserved(),
            "includes_host_to_device": True, "lightgbm_latency": "not_measured_saved_predictions_reused",
            "ordered_targets_sha256": digest(canonical(ids))}
        return tuple(ids), tuple(labels), np.asarray(logits, dtype=np.float64)
