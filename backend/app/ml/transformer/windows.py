"""Streaming equality checks against the original governed supervised rows."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import hashlib
from itertools import zip_longest

import numpy as np

from app.features.pipeline import FEATURE_COLUMNS
from app.market_data.projections import supervised_row_id
from .contracts import LENGTH


@dataclass(frozen=True)
class Window:
    target_id: str
    fold: str
    run_id: str
    label: int
    values: np.ndarray
    valid_steps: np.ndarray
    timestamps_ns: np.ndarray
    row_ids: tuple[str, ...]


def source_vector(row):
    values = [row[name] for name in FEATURE_COLUMNS]
    if any(v is not None and type(v) not in (int, float) for v in values):
        raise ValueError("source features must be numeric or missing")
    vector = np.array(values, dtype=np.float64)
    if np.isinf(vector).any():
        raise ValueError("infinite source feature")
    return vector


def verified_windows(source_rows, sequence_rows, *, root, shard):
    history = deque(maxlen=LENGTH)
    identity = hashlib.sha256()
    previous = (-1, -1)
    count = 0
    for source, row in zip_longest(source_rows, sequence_rows):
        if source is None or row is None:
            raise ValueError("tabular/sequence row count mismatch")
        ts, seq = source["prediction_timestamp_ns"], source["sequence"]
        if type(ts) is not int or type(seq) is not int or ts < previous[0] or seq <= previous[1]:
            raise ValueError("source causal sequence order changed")
        if source["run_id"] != shard.run_id:
            raise ValueError("source replay domain changed")
        label = source["label"]
        if type(label) is not int or label not in (0, 1):
            raise ValueError("invalid target label")
        if source["label_source"] != ("synthetic_scenario" if label else "research_control_assumption"):
            raise ValueError("target label provenance changed")
        target = supervised_row_id(root_sha256=root.canonical_hash(),
                                   assignment_sha256=root.assignment_sha256,
                                   replay_sha256=shard.replay_manifest_sha256,
                                   run_id=shard.run_id, sequence=seq, timestamp_ns=ts)
        if source["supervised_row_id"] != target or row["target_supervised_row_id"] != target:
            raise ValueError("target row identity or exact alignment changed")
        if type(row["cutoff_timestamp_ns"]) is not int or row["cutoff_timestamp_ns"] != ts:
            raise ValueError("target cutoff changed")
        previous = (ts, seq)
        history.append((target, ts, source_vector(source)))
        padding = LENGTH - len(history)
        expected_ids = [""] * padding + [item[0] for item in history]
        expected_ts = [0] * padding + [item[1] for item in history]
        expected_mask = [False] * padding + [True] * len(history)
        mask, timestamps = row["attention_mask"], row["sequence_timestamps_ns"]
        if (not isinstance(mask, list) or any(type(v) is not bool for v in mask)
                or mask != expected_mask):
            raise ValueError("invalid boolean left-padding mask")
        if (not isinstance(timestamps, list) or any(type(v) is not int for v in timestamps)
                or timestamps != expected_ts or row["sequence_row_ids"] != expected_ids):
            raise ValueError("history is not the exact causal source window")
        expected = np.zeros((LENGTH, len(FEATURE_COLUMNS)), dtype=np.float64)
        expected[padding:] = np.stack([item[2] for item in history])
        values = np.asarray(row["feature_vectors"])
        if (values.dtype.kind not in "fiu" or values.shape != expected.shape
                or not np.array_equal(values, expected, equal_nan=True)):
            raise ValueError("sequence feature values, shape or padding changed")
        valid = np.array(mask, dtype=np.bool_)
        times = np.array(timestamps, dtype=np.int64)
        for array in (expected, valid, times):
            array.setflags(write=False)
        count += 1
        identity.update((target + "\n").encode())
        yield Window(target, shard.fold, shard.run_id, label, expected, valid, times, tuple(expected_ids))
    if count != shard.supervised_row_count or identity.hexdigest() != shard.row_identity_sha256:
        raise ValueError("source row inventory changed")
