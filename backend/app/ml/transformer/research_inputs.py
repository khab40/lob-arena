"""Authenticate existing C4 roles and materialize inputs inside a research Job."""
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .batches import iter_batches
from .contracts import Normalization
from .data import DevelopmentInputs
from .role_audit import summarize_rows
from .role_manifest import load_metadata, metadata_plan
from .role_source import authenticate
from .verification_spec import SEQUENCE_SHA, TABULAR_SHA, canonical, digest


@dataclass(frozen=True)
class ResearchSplit:
    role: str
    values: np.ndarray
    valid: np.ndarray
    missing: np.ndarray
    labels: np.ndarray
    target_ids: tuple[str, ...]
    sessions: tuple[str, ...]

    def __len__(self):
        return len(self.labels)


def prepare(inputs: Path, bundle_raw: bytes, source_raw: bytes):
    metadata, contract, normalizer_raw, binding = authenticate(bundle_raw, source_raw)
    root, tabular, sequences = load_metadata(inputs)
    if canonical(metadata_plan(root, tabular, sequences)) != canonical(metadata):
        raise ValueError("research roles differ from authenticated source proof")
    data = DevelopmentInputs.open(root=root, tabular_path=inputs / "manifests/tabular-projection.json",
        tabular_sha256=TABULAR_SHA, sequence_path=inputs / "manifests/sequence-projection.json",
        sequence_sha256=SEQUENCE_SHA, artifact_root=inputs / "artifacts")
    if data.contract.canonical_bytes() != contract.canonical_bytes():
        raise ValueError("research input contract changed")
    normalizer = Normalization.model_validate_json(normalizer_raw)
    roles = {s["run_id"]: g["role"] for g in metadata["groups"] for s in g["shards"]}
    counts = {s["run_id"]: s["row_count"] for g in metadata["groups"] for s in g["shards"]}
    support = summarize_rows(data.windows("validation"), roles, counts)
    if not all(row["support_passed"] for row in support.values()):
        raise ValueError("insufficient research role class support; no fitting allowed")
    session_by_run = {s.run_id: s.base_session_id for s in tabular.shards}
    chunks = {role: [] for role in ("train", "selection", "calibration", "operating_point")}
    for batch in iter_batches(data, normalizer):
        assigned = ["train" if fold == "train" else roles[run]
                    for fold, run in zip(batch.folds, batch.run_ids, strict=True)]
        for role in chunks:
            indices = np.array([i for i, value in enumerate(assigned) if value == role], dtype=np.int64)
            if len(indices):
                chunks[role].append((batch, indices))
    prepared = {}
    for role, rows in chunks.items():
        if not rows:
            raise ValueError("empty research role")
        ids = tuple(batch.target_ids[i] for batch, indices in rows for i in indices)
        labels = np.concatenate([batch.labels[indices] for batch, indices in rows])
        if len(set(ids)) != len(ids) or set(labels.tolist()) != {0, 1}:
            raise ValueError("duplicate targets or missing class")
        if role != "train" and list(ids) != support[role]["target_ids"]:
            raise ValueError("materialized role order differs from audited order")
        prepared[role] = ResearchSplit(role,
            np.concatenate([batch.values[indices] for batch, indices in rows]),
            np.concatenate([batch.valid_steps[indices] for batch, indices in rows]),
            np.concatenate([batch.missing_features[indices] for batch, indices in rows]), labels, ids,
            tuple(session_by_run[batch.run_ids[i]] for batch, indices in rows for i in indices))
    bindings = {"contract_sha256": contract.sha256(), "normalization_sha256": digest(normalizer_raw),
                "role_manifest_sha256": digest(canonical(metadata)), "source_binding": binding,
                "ordered_targets_sha256": {role: digest("".join(t + "\n" for t in split.target_ids).encode())
                                            for role, split in prepared.items()}}
    return prepared, bindings
