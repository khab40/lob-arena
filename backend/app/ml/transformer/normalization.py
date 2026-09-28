from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from app.features.pipeline import FEATURE_COLUMNS
from .contracts import Normalization


def fit_normalization(dataset) -> Normalization:
    counts = np.zeros(len(FEATURE_COLUMNS), dtype=np.int64)
    means = np.zeros(len(FEATURE_COLUMNS), dtype=np.float64)
    m2 = means.copy()
    identity = hashlib.sha256()
    total = 0
    with np.errstate(over="raise", invalid="raise"):
        for window in dataset.windows("train"):
            # Each target occurs once; history overlap and padding get no weight.
            values = window.values[-1]
            observed = ~np.isnan(values)
            counts[observed] += 1
            delta = values[observed] - means[observed]
            means[observed] += delta / counts[observed]
            m2[observed] += delta * (values[observed] - means[observed])
            identity.update((window.target_id + "\n").encode())
            total += 1
    variance = np.divide(m2, counts, out=np.zeros_like(m2), where=counts > 0)
    scales = np.sqrt(np.maximum(variance, 0))
    scales[scales == 0] = 1
    return Normalization(training_binding_sha256=dataset.contract.training_binding(),
                         fitting_row_sha256=identity.hexdigest(), fitting_rows=total,
                         observed_counts=tuple(map(int, counts)), means=tuple(map(float, means)),
                         scales=tuple(map(float, scales)))


def save_normalization(normalization: Normalization, path: Path) -> str:
    with path.open("xb") as stream:
        stream.write(normalization.canonical_bytes())
    return normalization.sha256()


def load_normalization(path: Path, *, expected_sha256: str, contract) -> Normalization:
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("normalization checksum changed")
    result = Normalization.model_validate_json(payload)
    if result.training_binding_sha256 != contract.training_binding():
        raise ValueError("normalization training lineage changed")
    return result
