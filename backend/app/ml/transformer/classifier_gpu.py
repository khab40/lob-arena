"""Dedicated CUDA research inference; import only in an authorized Nebius Job."""
from io import BytesIO
import math
from numbers import Real
import time
from types import SimpleNamespace

from .classifier_package import (
    _target_digest, checked_checkpoint_bytes, reauthenticate_classifier, validate_development_inputs,
    verify_checkpoint_header,
)


def _numerical_runtime():
    import numpy as np
    import torch
    from .batches import iter_batches
    from .research_inputs import ResearchSplit
    from .research_model import SequenceClassifier
    from .research_training import configure, predict
    return SimpleNamespace(np=np, torch=torch, iter_batches=iter_batches, split=ResearchSplit,
                           model=SequenceClassifier, configure=configure, predict=predict)


class DedicatedGpuClassifier:
    def __init__(self, package, *, expires):
        package = reauthenticate_classifier(package)  # Before any numerical import.
        if (isinstance(expires, bool) or not isinstance(expires, Real)
                or not math.isfinite(expires) or time.monotonic() >= expires):
            raise ValueError("classifier requires a finite future deadline")
        runtime = _numerical_runtime()
        torch = runtime.torch
        runtime.configure(package.release.training.seed)  # CUDA required; no CPU fallback.
        raw = checked_checkpoint_bytes(package)  # Exact immutable snapshot immediately before load.
        state = torch.load(BytesIO(raw), map_location="cpu", weights_only=True)
        verify_checkpoint_header(package, state)
        if any(not isinstance(value, torch.Tensor) or value.dtype != torch.float32
               or not torch.isfinite(value).all() for value in state["model"].values()):
            raise ValueError("classifier selected state requires finite float32 tensors")
        if time.monotonic() >= expires:
            raise TimeoutError("classifier selected-state validation deadline")
        self.model = runtime.model(package.release.training.width).to("cuda")
        self.model.load_state_dict(state["model"], strict=True)
        self.model.eval()
        self._package, self._runtime = package, runtime
        self.expires, self.measurements = expires, {}

    def infer(self, dataset, normalizer, *, fold, tabular_path, sequence_path):
        package = reauthenticate_classifier(self._package)
        if fold not in ("train", "validation"):
            raise ValueError("dedicated classifier rejects final folds")
        validate_development_inputs(package, dataset, tabular_path=tabular_path, sequence_path=sequence_path)
        if type(normalizer) is not type(package.normalization) or normalizer != package.normalization:
            raise ValueError("dedicated classifier normalizer differs")
        runtime, torch, np = self._runtime, self._runtime.torch, self._runtime.np
        ids, labels, logits = [], [], []
        torch.cuda.synchronize()
        started = time.monotonic()
        for batch in runtime.iter_batches(dataset, normalizer, batch_size=64, fold=fold):
            split = runtime.split(fold, batch.values, batch.valid_steps, batch.missing_features,
                batch.labels, batch.target_ids, batch.run_ids)
            values = runtime.predict(self.model, split, expires=self.expires)
            if values.shape != (len(batch.target_ids),) or not np.isfinite(values).all():
                raise ValueError("dedicated classifier batch output differs")
            ids.extend(batch.target_ids)
            labels.extend(map(int, batch.labels))
            logits.extend(map(float, values))
        torch.cuda.synchronize()
        self.measurements = {"elapsed_seconds": time.monotonic() - started, "batch_size": 64,
            "rows": len(ids), "peak_gpu_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_gpu_reserved_bytes": torch.cuda.max_memory_reserved(), "includes_host_to_device": True,
            "ordered_targets_sha256": _target_digest(ids), "scope": "development_research_inference"}
        return tuple(ids), tuple(labels), np.asarray(logits, dtype=np.float64)
