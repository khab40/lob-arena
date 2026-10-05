"""Distinct gated final adapter; the development adapter remains unchanged."""
from dataclasses import dataclass
from pathlib import Path

from app.market_data.projections import (
    SequenceProjectionManifest, TabularProjectionManifest, _load_bound_manifest, _resolve,
)
from .contracts import LENGTH
from .data import baseline_order, domain, rows
from .windows import verified_windows


@dataclass(frozen=True)
class HoldoutInputs:
    root: object
    tabular: TabularProjectionManifest
    sequences: SequenceProjectionManifest
    artifact_root: Path
    contract: object  # Original development contract: never relabel checkpoint bindings.
    request: object
    gate: object

    @classmethod
    def open(cls, *, request, gate, contract, artifact_root):
        gate.require(request)  # Before either manifest or shard file is opened.
        artifact_root = Path(artifact_root).resolve()
        tab = request.input(request.tabular_path)
        seq = request.input(request.sequence_path)
        tabular = _load_bound_manifest(artifact_root / tab.path, expected_sha256=tab.reference.sha256,
            model=TabularProjectionManifest, root=contract.root)
        sequences = _load_bound_manifest(artifact_root / seq.path, expected_sha256=seq.reference.sha256,
            model=SequenceProjectionManifest, root=contract.root)
        if (tabular.access_scope != "final_test" or sequences.access_scope != "final_test"
                or sequences.order_columns != ("prediction_timestamp_ns", "sequence")):
            raise ValueError("holdout requires exact final-test scope and causal ordering")
        by_domain = {domain(s): s for s in sequences.shards}
        if (len(by_domain) != len(sequences.shards)
                or set(by_domain) != {domain(s) for s in tabular.shards}
                or len({s.run_id for s in tabular.shards}) != len(tabular.shards)
                or len({s.sequences.uri for s in sequences.shards}) != len(sequences.shards)):
            raise ValueError("holdout replay domains differ or duplicate")
        approved = {item.path: item for item in request.inputs if item.scope == "final_test"}
        consumed = {tab.path, seq.path, *request.baseline_paths}
        for shard in tabular.shards:
            history = by_domain[domain(shard)]
            if (history.sequence_length != LENGTH or history.sequence_count != shard.supervised_row_count
                    or history.sequence_identity_sha256 != shard.row_identity_sha256
                    or shard.base_session_id in {s.base_session_id for s in contract.training_shards}):
                raise ValueError("holdout shape, identities or train exclusion differs")
            for ref in (shard.rows, history.sequences):
                item = approved.get(ref.uri)
                if (item is None or item.reference.sha256 != ref.sha256
                        or item.reference.size_bytes != ref.size_bytes):
                    raise ValueError("projection shard leaves exact approved inventory")
                consumed.add(ref.uri)
        if consumed != set(approved):
            raise ValueError("unaccounted final inputs in approved inventory")
        result = cls(contract.root, tabular, sequences, artifact_root, contract, request, gate)
        for _ in result.windows():
            pass  # Complete verification before the first inference batch.
        return result

    def windows(self, fold=None):
        self.gate.require(self.request)
        if fold not in (None, "test"):
            raise ValueError("holdout exposes the test fold only")
        sequences = {domain(s): s for s in self.sequences.shards}
        for shard in sorted(self.tabular.shards, key=baseline_order):
            source = _resolve(shard.rows, self.artifact_root)
            history = _resolve(sequences[domain(shard)].sequences, self.artifact_root)
            yield from verified_windows(rows(source), rows(history), root=self.root, shard=shard)

    def ledger(self):
        shards = {s.run_id: s for s in self.tabular.shards}
        for window in self.windows():
            shard = shards[window.run_id]
            yield {"target_id": window.target_id, "label": window.label, "run_id": window.run_id,
                   "base_session_id": shard.base_session_id, "campaign_id": shard.campaign_id,
                   "prediction_timestamp_ns": int(window.timestamps_ns[-1])}
