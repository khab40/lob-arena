"""Development-only adapter over frozen C4 projections; never rewrites source rows."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq

from app.market_data.projections import (
    FrozenPublicSampleRoot, SequenceProjectionManifest, TabularProjectionManifest,
    _load_bound_manifest, _resolve,
)
from .contracts import InputContract, LENGTH
from .windows import verified_windows


def domain(shard):
    return (shard.fold, shard.base_session_id, shard.campaign_id, shard.run_id,
            shard.replay_manifest_sha256)


def baseline_order(shard):
    return (0 if shard.fold == "train" else 1, shard.base_session_id,
            shard.campaign_id or "", shard.run_id)


def rows(path):
    # Expanded sequence rows are large: bound Arrow and Python batches separately
    # from the consumer's output batch size. Never read a whole shard into RAM.
    with path.open("rb") as stream:
        for batch in pq.ParquetFile(stream).iter_batches(batch_size=16):
            yield from batch.to_pylist()


@dataclass(frozen=True)
class DevelopmentInputs:
    root: FrozenPublicSampleRoot
    tabular: TabularProjectionManifest
    sequences: SequenceProjectionManifest
    artifact_root: Path
    contract: InputContract

    @classmethod
    def open(cls, *, root, tabular_path, tabular_sha256, sequence_path, sequence_sha256, artifact_root):
        """The caller supplies the trusted frozen root and externally expected hashes.

        Validate all rows before returning a usable adapter. Metadata access checks
        precede every shard read, including for accidentally supplied final manifests.
        """
        tabular = _load_bound_manifest(Path(tabular_path), expected_sha256=tabular_sha256,
                                       model=TabularProjectionManifest, root=root)
        sequences = _load_bound_manifest(Path(sequence_path), expected_sha256=sequence_sha256,
                                         model=SequenceProjectionManifest, root=root)
        if tabular.access_scope != "development" or sequences.access_scope != "development":
            raise ValueError("Transformer development rejects final-test manifests before shard access")
        if sequences.order_columns != ("prediction_timestamp_ns", "sequence"):
            raise ValueError("sequence ordering contract changed")
        by_domain = {domain(s): s for s in sequences.shards}
        if len(by_domain) != len(sequences.shards) or set(by_domain) != {domain(s) for s in tabular.shards}:
            raise ValueError("tabular and sequence replay domains differ")
        if len({s.sequences.uri for s in sequences.shards}) != len(sequences.shards):
            raise ValueError("sequence artifact paths must be unique")
        if len({s.run_id for s in tabular.shards}) != len(tabular.shards):
            raise ValueError("replay run IDs must be unique")
        session_folds = {}
        for shard in tabular.shards:
            if session_folds.setdefault(shard.base_session_id, shard.fold) != shard.fold:
                raise ValueError("base session crosses train/validation folds")
            sequence = by_domain[domain(shard)]
            if (sequence.sequence_length != LENGTH
                    or sequence.sequence_count != shard.supervised_row_count
                    or sequence.sequence_identity_sha256 != shard.row_identity_sha256):
                raise ValueError("sequence shape or row inventory differs from baseline")
        contract = InputContract(root=root, tabular_manifest_sha256=tabular_sha256,
                                 sequence_manifest_sha256=sequence_sha256,
                                 training_shards=tuple(sorted(
                                     (s for s in tabular.shards if s.fold == "train"), key=baseline_order)))
        dataset = cls(root, tabular, sequences, Path(artifact_root).resolve(), contract)
        for _ in dataset.windows():
            pass  # Complete preflight: even a corrupt final row rejects open().
        return dataset

    def windows(self, fold=None):
        if fold not in (None, "train", "validation"):
            raise ValueError("only train/validation inputs are available")
        by_domain = {domain(s): s for s in self.sequences.shards}
        # Match LightGBM's fold/shard order; never reorder rows within a shard.
        for shard in sorted(self.tabular.shards, key=baseline_order):
            if fold is not None and shard.fold != fold:
                continue
            sequence = by_domain[domain(shard)]
            source = _resolve(shard.rows, self.artifact_root)
            history = _resolve(sequence.sequences, self.artifact_root)
            yield from verified_windows(rows(source), rows(history), root=self.root, shard=shard)
