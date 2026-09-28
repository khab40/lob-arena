from __future__ import annotations

from dataclasses import dataclass
from itertools import islice

import numpy as np

from .contracts import LENGTH, Normalization


@dataclass(frozen=True)
class InputBatch:
    values: np.ndarray
    valid_steps: np.ndarray
    missing_features: np.ndarray
    causal_allowed: np.ndarray
    timestamps_ns: np.ndarray
    target_ids: tuple[str, ...]
    history_row_ids: tuple[tuple[str, ...], ...]
    labels: np.ndarray
    folds: tuple[str, ...]
    run_ids: tuple[str, ...]
    contract_sha256: str
    normalization_sha256: str


def iter_batches(dataset, normalization: Normalization, *, batch_size=64, fold=None):
    if type(batch_size) is not int or not 1 <= batch_size <= 1024:
        raise ValueError("batch size must be an integer between 1 and 1024")
    if normalization.training_binding_sha256 != dataset.contract.training_binding():
        raise ValueError("normalization training lineage changed")
    means, scales = np.array(normalization.means), np.array(normalization.scales)
    contract_sha, normalization_sha = dataset.contract.sha256(), normalization.sha256()
    windows = iter(dataset.windows(fold))
    while chunk := tuple(islice(windows, batch_size)):
        raw = np.stack([w.values for w in chunk])
        valid = np.stack([w.valid_steps for w in chunk])
        missing = valid[:, :, None] & np.isnan(raw)
        observed = valid[:, :, None] & ~np.isnan(raw)
        normalized = np.zeros_like(raw)
        with np.errstate(over="raise", invalid="raise", divide="raise"):
            np.subtract(raw, means, out=normalized, where=observed)
            np.divide(normalized, scales, out=normalized, where=observed)
            values = normalized.astype(np.float32)
        if not np.isfinite(values).all():
            raise ValueError("nonfinite normalized inputs")
        allowed = (np.tri(LENGTH, dtype=np.bool_)[None, :, :]
                   & valid[:, :, None] & valid[:, None, :])
        times = np.stack([w.timestamps_ns for w in chunk])
        labels = np.array([w.label for w in chunk], dtype=np.int64)
        for array in (values, valid, missing, allowed, times, labels):
            array.setflags(write=False)
        yield InputBatch(values, valid, missing, allowed, times,
                         tuple(w.target_id for w in chunk), tuple(w.row_ids for w in chunk), labels,
                         tuple(w.fold for w in chunk), tuple(w.run_id for w in chunk),
                         contract_sha, normalization_sha)
