"""Inert C4-shaped records; no model, market feed or frozen evaluation runtime."""
import hashlib

import pyarrow as pa
import pyarrow.parquet as pq

from app.features.pipeline import FEATURE_COLUMNS
from app.market_data.projections import (
    EXPECTED_SOURCE_DATES, EXPECTED_SOURCE_FILES, EXPECTED_SOURCE_FOLDS,
    FrozenPublicSampleRoot, FrozenSourceBinding, SequenceProjectionManifest,
    TabularProjectionManifest, TabularProjectionShard, _artifact_digest,
    materialize_sequence_shard, supervised_row_id, write_manifest,
)


def frozen_root():
    return FrozenPublicSampleRoot(
        release_id="fixture-root", corpus_id="fixture-corpus", split_id="fixture-split",
        feature_release_id="fixture-features", protocol_sha256="1" * 64, corpus_sha256="2" * 64,
        assignment_sha256="3" * 64, feature_release_sha256="4" * 64,
        feature_config_sha256="5" * 64, source_config_sha256="6" * 64,
        sources=tuple(FrozenSourceBinding(trade_date=day, fold=fold, filename=name,
                      source_sha256="7" * 64, source_manifest_sha256="8" * 64,
                      preparation_manifest_sha256="9" * 64, parser_config_sha256="a" * 64)
                      for day, fold, name in zip(EXPECTED_SOURCE_DATES, EXPECTED_SOURCE_FOLDS,
                                                EXPECTED_SOURCE_FILES, strict=True)))


def make_inputs(path, *, count=4, validation_shift=0, flip_labels=False,
                validation_flip_labels=False, mutate=None, source_mutate=None):
    root = frozen_root()
    path.mkdir(parents=True, exist_ok=True)
    tabular, sequences = [], []
    for fold in ("train", "validation"):
        records = []
        identity = hashlib.sha256()
        for index in range(count):
            ts, seq = (index // 2) * 100, index + 1  # Deliberately include timestamp ties.
            label = (index + int(flip_labels) + int(fold == "validation" and validation_flip_labels)) % 2
            target = supervised_row_id(root_sha256=root.canonical_hash(), assignment_sha256=root.assignment_sha256,
                                       replay_sha256="b" * 64, run_id=fold, sequence=seq, timestamp_ns=ts)
            values = {name: float(index + feature + 1) for feature, name in enumerate(FEATURE_COLUMNS)}
            values.update({FEATURE_COLUMNS[1]: None, FEATURE_COLUMNS[2]: 3.0, FEATURE_COLUMNS[3]: 0.0})
            if index == 0:
                values[FEATURE_COLUMNS[4]] = None
            if fold == "validation":
                values = {name: value + validation_shift if value is not None else None
                          for name, value in values.items()}
            row = {**values, "supervised_row_id": target, "run_id": fold, "sequence": seq,
                   "prediction_timestamp_ns": ts, "label": label,
                   "label_source": "synthetic_scenario" if label else "research_control_assumption"}
            if source_mutate:
                source_mutate(row, fold, index)
            records.append(row)
            identity.update((row["supervised_row_id"] + "\n").encode())
        source = path / f"{fold}.parquet"
        pq.write_table(pa.Table.from_pylist(records), source)
        shard = TabularProjectionShard(fold=fold, base_session_id=fold, run_id=fold,
                    replay_manifest_sha256="b" * 64, supervised_row_count=count,
                    row_identity_sha256=identity.hexdigest(), rows=_artifact_digest(
                        source, root=path, logical_name=fold, schema_version="tabular_projection_rows_v1"))
        sequence_path = path / f"{fold}-sequences.parquet"
        sequence = materialize_sequence_shard(shard, sequence_path, artifact_root=path)
        if mutate:
            rows = pq.read_table(sequence_path).to_pylist()
            mutate(rows, fold)
            pq.write_table(pa.Table.from_pylist(rows), sequence_path)
            sequence = sequence.model_copy(update={"sequences": _artifact_digest(
                sequence_path, root=path, logical_name=fold + "-sequences",
                schema_version="causal_feature_sequences_v1")})
        tabular.append(shard)
        sequences.append(sequence)
    common = dict(access_scope="development", root_release_id=root.release_id,
                  root_sha256=root.canonical_hash(), protocol_sha256=root.protocol_sha256,
                  corpus_sha256=root.corpus_sha256, assignment_sha256=root.assignment_sha256,
                  feature_release_sha256=root.feature_release_sha256, folds=("train", "validation"))
    tab = TabularProjectionManifest(projection_id="fixture-tabular", shards=tuple(tabular), **common)
    seq = SequenceProjectionManifest(projection_id="fixture-sequence", shards=tuple(sequences), **common)
    tab_path, seq_path = path / "tabular.json", path / "sequence.json"
    return dict(root=root, artifact_root=path, tabular_path=tab_path, sequence_path=seq_path,
                tabular_sha256=write_manifest(tab_path, tab), sequence_sha256=write_manifest(seq_path, seq))
