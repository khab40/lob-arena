from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date
from pathlib import Path
from typing import Literal

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ml.lightgbm.contracts import ArtifactDigest, IDENTIFIER_PATTERN, SHA256_PATTERN
from app.ml.lightgbm.data import (
    GovernedFeatureDataset,
    GovernedFeatureFold,
    GovernedFeatureShard,
)
from app.features.pipeline import FEATURE_COLUMNS, METADATA_COLUMNS


FoldName = Literal["train", "validation", "test"]
AccessScope = Literal["development", "final_test"]
EXPECTED_SOURCE_DATES = (
    date(2019, 1, 30),
    date(2019, 3, 27),
    date(2019, 10, 30),
    date(2019, 12, 30),
)
EXPECTED_SOURCE_FOLDS: tuple[FoldName, ...] = (
    "train",
    "train",
    "validation",
    "test",
)
EXPECTED_SOURCE_FILES = (
    "01302019.NASDAQ_ITCH50.gz",
    "03272019.NASDAQ_ITCH50.gz",
    "10302019.NASDAQ_ITCH50.gz",
    "12302019.NASDAQ_ITCH50.gz",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class FrozenSourceBinding(_StrictModel):
    trade_date: date
    fold: FoldName
    filename: str = Field(min_length=1)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    source_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    preparation_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    parser_config_sha256: str = Field(pattern=SHA256_PATTERN)


class FrozenPublicSampleRoot(_StrictModel):
    schema_version: Literal["nasdaq_public_sample_frozen_root_v1"] = (
        "nasdaq_public_sample_frozen_root_v1"
    )
    release_id: str = Field(pattern=IDENTIFIER_PATTERN)
    protocol_id: Literal["nasdaq-public-sample-v1"] = "nasdaq-public-sample-v1"
    protocol_sha256: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(pattern=IDENTIFIER_PATTERN)
    corpus_sha256: str = Field(pattern=SHA256_PATTERN)
    split_id: str = Field(pattern=IDENTIFIER_PATTERN)
    assignment_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_release_id: str = Field(pattern=IDENTIFIER_PATTERN)
    feature_release_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_schema_version: Literal["lob_features_v2"] = "lob_features_v2"
    feature_config_sha256: str = Field(pattern=SHA256_PATTERN)
    source_config_sha256: str = Field(pattern=SHA256_PATTERN)
    negative_label_source: Literal["research_control_assumption"] = (
        "research_control_assumption"
    )
    sources: tuple[FrozenSourceBinding, ...]

    @model_validator(mode="after")
    def validate_complete_root(self) -> "FrozenPublicSampleRoot":
        if len(self.sources) != 4:
            raise ValueError("frozen public-sample root requires exactly four sources")
        if tuple(item.trade_date for item in self.sources) != EXPECTED_SOURCE_DATES:
            raise ValueError("frozen public-sample sources changed date or chronological order")
        if tuple(item.filename for item in self.sources) != EXPECTED_SOURCE_FILES:
            raise ValueError("frozen public-sample source filename inventory changed")
        if tuple(item.fold for item in self.sources) != EXPECTED_SOURCE_FOLDS:
            raise ValueError("frozen public-sample root changed the exact 2/1/1 folds")
        return self


class TabularProjectionShard(_StrictModel):
    fold: FoldName
    base_session_id: str = Field(pattern=IDENTIFIER_PATTERN)
    campaign_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    replay_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    rows: ArtifactDigest
    supervised_row_count: int = Field(ge=1)
    row_identity_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_rows(self) -> "TabularProjectionShard":
        if self.rows.schema_version != "tabular_projection_rows_v1":
            raise ValueError("tabular shard has an incompatible row schema")
        return self


class TabularProjectionManifest(_StrictModel):
    schema_version: Literal["tabular_projection_v1"] = "tabular_projection_v1"
    projection_id: str = Field(pattern=IDENTIFIER_PATTERN)
    access_scope: AccessScope
    root_release_id: str = Field(pattern=IDENTIFIER_PATTERN)
    root_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol_sha256: str = Field(pattern=SHA256_PATTERN)
    corpus_sha256: str = Field(pattern=SHA256_PATTERN)
    assignment_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_release_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_schema_version: Literal["lob_features_v2"] = "lob_features_v2"
    negative_label_source: Literal["research_control_assumption"] = (
        "research_control_assumption"
    )
    folds: tuple[FoldName, ...]
    shards: tuple[TabularProjectionShard, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fold_isolation(self) -> "TabularProjectionManifest":
        _validate_scope(self.access_scope, self.folds)
        if {item.fold for item in self.shards} != set(self.folds):
            raise ValueError("tabular shard folds do not exactly match projection folds")
        identities = [(item.base_session_id, item.campaign_id) for item in self.shards]
        if len(identities) != len(set(identities)):
            raise ValueError("tabular projection replay domains must be unique")
        uris = [item.rows.uri for item in self.shards]
        if len(uris) != len(set(uris)):
            raise ValueError("tabular projection artifact paths must be unique")
        return self


class SequenceProjectionShard(_StrictModel):
    fold: FoldName
    base_session_id: str = Field(pattern=IDENTIFIER_PATTERN)
    campaign_id: str | None = Field(default=None, pattern=IDENTIFIER_PATTERN)
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    replay_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    sequences: ArtifactDigest
    sequence_count: int = Field(ge=1)
    sequence_length: int = Field(ge=2, le=4096)
    sequence_identity_sha256: str = Field(pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_sequences(self) -> "SequenceProjectionShard":
        if self.sequences.schema_version != "causal_feature_sequences_v1":
            raise ValueError("sequence shard has an incompatible sequence schema")
        return self


class SequenceProjectionManifest(_StrictModel):
    schema_version: Literal["sequence_projection_v1"] = "sequence_projection_v1"
    projection_id: str = Field(pattern=IDENTIFIER_PATTERN)
    access_scope: AccessScope
    root_release_id: str = Field(pattern=IDENTIFIER_PATTERN)
    root_sha256: str = Field(pattern=SHA256_PATTERN)
    protocol_sha256: str = Field(pattern=SHA256_PATTERN)
    corpus_sha256: str = Field(pattern=SHA256_PATTERN)
    assignment_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_release_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_schema_version: Literal["lob_features_v2"] = "lob_features_v2"
    causal: Literal[True] = True
    order_columns: tuple[Literal["prediction_timestamp_ns", "sequence"], ...] = (
        "prediction_timestamp_ns",
        "sequence",
    )
    cutoff_column: Literal["cutoff_timestamp_ns"] = "cutoff_timestamp_ns"
    mask_column: Literal["attention_mask"] = "attention_mask"
    target_row_id_column: Literal["target_supervised_row_id"] = (
        "target_supervised_row_id"
    )
    folds: tuple[FoldName, ...]
    shards: tuple[SequenceProjectionShard, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_fold_isolation(self) -> "SequenceProjectionManifest":
        _validate_scope(self.access_scope, self.folds)
        if {item.fold for item in self.shards} != set(self.folds):
            raise ValueError("sequence shard folds do not exactly match projection folds")
        identities = [(item.base_session_id, item.campaign_id) for item in self.shards]
        if len(identities) != len(set(identities)):
            raise ValueError("sequence projection replay domains must be unique")
        return self


class FinalAccessDenialEvidence(_StrictModel):
    schema_version: Literal["final_projection_access_denial_v1"] = (
        "final_projection_access_denial_v1"
    )
    development_identity_id: str = Field(min_length=1)
    tabular_final_uri: str = Field(min_length=1)
    sequence_final_uri: str = Field(min_length=1)
    tabular_read_denied: Literal[True] = True
    sequence_read_denied: Literal[True] = True
    observed_error_code: Literal["AccessDenied"] = "AccessDenied"
    test_objects_read: Literal[0] = 0


def verify_tabular_projection(
    manifest_path: Path,
    *,
    expected_sha256: str,
    root: FrozenPublicSampleRoot,
    artifact_root: Path,
) -> TabularProjectionManifest:
    manifest = _load_bound_manifest(
        manifest_path,
        expected_sha256=expected_sha256,
        model=TabularProjectionManifest,
        root=root,
    )
    for shard in manifest.shards:
        path = _resolve(shard.rows, artifact_root)
        parquet = pq.ParquetFile(path)
        required = {
            "supervised_row_id",
            "label",
            "label_source",
            "prediction_timestamp_ns",
            "sequence",
        }
        if not required <= set(parquet.schema_arrow.names):
            raise ValueError("tabular projection is missing governed row identity columns")
        identity = hashlib.sha256()
        count = 0
        for batch in parquet.iter_batches(columns=sorted(required)):
            for row in batch.to_pylist():
                if row["label"] not in {0, 1}:
                    raise ValueError("tabular projection contains an unsupervised row")
                expected_source = (
                    "research_control_assumption"
                    if row["label"] == 0
                    else "synthetic_scenario"
                )
                if row["label_source"] != expected_source:
                    raise ValueError("tabular projection label provenance is invalid")
                row_id = supervised_row_id(
                    root_sha256=manifest.root_sha256,
                    assignment_sha256=manifest.assignment_sha256,
                    replay_sha256=shard.replay_manifest_sha256,
                    run_id=shard.run_id,
                    sequence=row["sequence"],
                    timestamp_ns=row["prediction_timestamp_ns"],
                )
                if row["supervised_row_id"] != row_id:
                    raise ValueError("tabular projection row identity is invalid")
                identity.update((row_id + "\n").encode())
                count += 1
        if count != shard.supervised_row_count or identity.hexdigest() != shard.row_identity_sha256:
            raise ValueError("tabular projection row inventory changed after freeze")
    return manifest


def verify_sequence_projection(
    manifest_path: Path,
    *,
    expected_sha256: str,
    root: FrozenPublicSampleRoot,
    artifact_root: Path,
) -> SequenceProjectionManifest:
    manifest = _load_bound_manifest(
        manifest_path,
        expected_sha256=expected_sha256,
        model=SequenceProjectionManifest,
        root=root,
    )
    for shard in manifest.shards:
        path = _resolve(shard.sequences, artifact_root)
        identity = hashlib.sha256()
        count = 0
        previous_cutoff = -1
        for batch in pq.ParquetFile(path).iter_batches():
            for row in batch.to_pylist():
                row_ids = row.get("sequence_row_ids")
                timestamps = row.get("sequence_timestamps_ns")
                mask = row.get("attention_mask")
                cutoff = row.get("cutoff_timestamp_ns")
                target = row.get("target_supervised_row_id")
                if not all(isinstance(value, list) for value in (row_ids, timestamps, mask)):
                    raise ValueError("sequence projection arrays are missing")
                if not (len(row_ids) == len(timestamps) == len(mask) == shard.sequence_length):
                    raise ValueError("sequence projection shape changed")
                if cutoff < previous_cutoff or any(
                    active and timestamp > cutoff
                    for timestamp, active in zip(timestamps, mask, strict=True)
                ):
                    raise ValueError("sequence projection violates causal cutoff ordering")
                active_ids = [value for value, active in zip(row_ids, mask, strict=True) if active]
                if not active_ids or active_ids[-1] != target:
                    raise ValueError("sequence target is not the final causal row")
                previous_cutoff = cutoff
                identity.update((target + "\n").encode())
                count += 1
        if count != shard.sequence_count or identity.hexdigest() != shard.sequence_identity_sha256:
            raise ValueError("sequence projection inventory changed after freeze")
    return manifest


def load_tabular_projection_dataset(
    manifest_path: Path,
    *,
    expected_sha256: str,
    root: FrozenPublicSampleRoot,
    artifact_root: Path,
    access_mode: AccessScope,
) -> GovernedFeatureDataset:
    manifest = verify_tabular_projection(
        manifest_path,
        expected_sha256=expected_sha256,
        root=root,
        artifact_root=artifact_root,
    )
    if manifest.access_scope != access_mode:
        raise ValueError("tabular projection access scope does not match the loader mode")
    loaded: list[GovernedFeatureShard] = []
    for projected in manifest.shards:
        path = _resolve(projected.rows, artifact_root)
        parquet = pq.ParquetFile(path)
        required_columns = {*METADATA_COLUMNS, *FEATURE_COLUMNS, "supervised_row_id"}
        if not required_columns <= set(parquet.schema_arrow.names):
            raise ValueError("tabular projection is not compatible with lob_features_v2")
        counts = {0: 0, 1: 0}
        source_types: set[str] = set()
        for batch in parquet.iter_batches(columns=["label", "source_type"]):
            for row in batch.to_pylist():
                counts[row["label"]] += 1
                source_types.add(row["source_type"])
        if len(source_types) != 1:
            raise ValueError("each tabular projection shard requires exactly one source")
        loaded.append(
            GovernedFeatureShard(
                fold=projected.fold,
                base_session_id=projected.base_session_id,
                campaign_id=projected.campaign_id,
                run_id=projected.run_id,
                source_type=next(iter(source_types)),
                feature_path=path,
                feature_uri=projected.rows.uri,
                feature_sha256=projected.rows.sha256,
                feature_size_bytes=projected.rows.size_bytes,
                run_metadata_path=manifest_path,
                run_metadata_sha256=expected_sha256,
                total_row_count=projected.supervised_row_count,
                supervised_row_count=projected.supervised_row_count,
                positive_row_count=counts[1],
                negative_row_count=counts[0],
                unlabeled_row_count=0,
                feature_columns=tuple(FEATURE_COLUMNS),
            )
        )
    folds = tuple(
        _projection_fold(
            fold,
            [item for item in loaded if item.fold == fold],
            split_id=root.split_id,
            assignment_sha256=root.assignment_sha256,
        )
        for fold in manifest.folds
    )
    return GovernedFeatureDataset(
        access_mode=access_mode,
        protocol_id=root.protocol_id,
        protocol_hash=root.protocol_sha256,
        corpus_id=root.corpus_id,
        corpus_hash=root.corpus_sha256,
        split_id=root.split_id,
        assignment_hash=root.assignment_sha256,
        feature_schema_version=root.feature_schema_version,
        feature_config_hash=root.feature_config_sha256,
        feature_release_id=root.feature_release_id,
        feature_release_sha256=root.feature_release_sha256,
        ordered_feature_columns=tuple(FEATURE_COLUMNS),
        folds=folds,
        negative_label_source="research_control_assumption",
    )


def materialize_tabular_shard(
    source_features: Path,
    output: Path,
    *,
    artifact_root: Path,
    root_sha256: str,
    assignment_sha256: str,
    replay_sha256: str,
    fold: FoldName,
    base_session_id: str,
    campaign_id: str | None,
    run_id: str,
) -> TabularProjectionShard:
    if output.exists():
        raise FileExistsError(f"tabular projection shard already exists: {output}")
    parquet = pq.ParquetFile(source_features)
    required = {*METADATA_COLUMNS, *FEATURE_COLUMNS}
    if not required <= set(parquet.schema_arrow.names):
        raise ValueError("source feature shard is incompatible with lob_features_v2")
    output.parent.mkdir(parents=True, exist_ok=True)
    writer: pq.ParquetWriter | None = None
    count = 0
    identity = hashlib.sha256()
    try:
        for batch in parquet.iter_batches():
            supervised = batch.filter(pc.is_valid(batch.column(batch.schema.get_field_index("label"))))
            if not supervised.num_rows:
                continue
            row_ids = []
            for row in supervised.select(
                ["sequence", "prediction_timestamp_ns", "label", "label_source"]
            ).to_pylist():
                expected_source = (
                    "research_control_assumption"
                    if row["label"] == 0
                    else "synthetic_scenario"
                )
                if row["label"] not in {0, 1} or row["label_source"] != expected_source:
                    raise ValueError("source feature shard has invalid research label provenance")
                row_id = supervised_row_id(
                    root_sha256=root_sha256,
                    assignment_sha256=assignment_sha256,
                    replay_sha256=replay_sha256,
                    run_id=run_id,
                    sequence=row["sequence"],
                    timestamp_ns=row["prediction_timestamp_ns"],
                )
                row_ids.append(row_id)
                identity.update((row_id + "\n").encode())
            projected = supervised.append_column(
                "supervised_row_id", pa.array(row_ids, type=pa.string())
            )
            if writer is None:
                writer = pq.ParquetWriter(output, projected.schema, compression="zstd")
            writer.write_batch(projected)
            count += projected.num_rows
    except Exception:
        if writer is not None:
            writer.close()
        output.unlink(missing_ok=True)
        raise
    else:
        if writer is not None:
            writer.close()
    if count == 0 or not output.is_file():
        output.unlink(missing_ok=True)
        raise ValueError("source feature shard contains no supervised rows")
    artifact = _artifact_digest(
        output,
        root=artifact_root,
        logical_name=f"{run_id}_tabular_rows",
        schema_version="tabular_projection_rows_v1",
    )
    return TabularProjectionShard(
        fold=fold,
        base_session_id=base_session_id,
        campaign_id=campaign_id,
        run_id=run_id,
        replay_manifest_sha256=replay_sha256,
        rows=artifact,
        supervised_row_count=count,
        row_identity_sha256=identity.hexdigest(),
    )


def materialize_sequence_shard(
    tabular: TabularProjectionShard,
    output: Path,
    *,
    artifact_root: Path,
    sequence_length: int = 64,
) -> SequenceProjectionShard:
    if not 2 <= sequence_length <= 4096:
        raise ValueError("sequence length must be between 2 and 4096")
    if output.exists():
        raise FileExistsError(f"sequence projection shard already exists: {output}")
    source = _resolve(tabular.rows, artifact_root)
    table = pq.read_table(
        source,
        columns=[
            "supervised_row_id",
            "prediction_timestamp_ns",
            "sequence",
            *FEATURE_COLUMNS,
        ],
    ).sort_by([("prediction_timestamp_ns", "ascending"), ("sequence", "ascending")])
    rows = table.to_pylist()
    output_rows = []
    identity = hashlib.sha256()
    for index, target in enumerate(rows):
        start = max(0, index - sequence_length + 1)
        active = rows[start : index + 1]
        padding = sequence_length - len(active)
        target_id = target["supervised_row_id"]
        identity.update((target_id + "\n").encode())
        output_rows.append(
            {
                "target_supervised_row_id": target_id,
                "cutoff_timestamp_ns": target["prediction_timestamp_ns"],
                "sequence_row_ids": [""] * padding
                + [item["supervised_row_id"] for item in active],
                "sequence_timestamps_ns": [0] * padding
                + [item["prediction_timestamp_ns"] for item in active],
                "attention_mask": [False] * padding + [True] * len(active),
                "feature_vectors": [[0.0] * len(FEATURE_COLUMNS)] * padding
                + [
                    [
                        float(item[name]) if item[name] is not None else float("nan")
                        for name in FEATURE_COLUMNS
                    ]
                    for item in active
                ],
            }
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(output_rows), output, compression="zstd")
    artifact = _artifact_digest(
        output,
        root=artifact_root,
        logical_name=f"{tabular.run_id}_causal_sequences",
        schema_version="causal_feature_sequences_v1",
    )
    return SequenceProjectionShard(
        fold=tabular.fold,
        base_session_id=tabular.base_session_id,
        campaign_id=tabular.campaign_id,
        run_id=tabular.run_id,
        replay_manifest_sha256=tabular.replay_manifest_sha256,
        sequences=artifact,
        sequence_count=len(output_rows),
        sequence_length=sequence_length,
        sequence_identity_sha256=identity.hexdigest(),
    )


def write_manifest(path: Path, manifest: _StrictModel) -> str:
    if path.exists():
        raise FileExistsError(f"immutable manifest already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return _sha256(path)


def _load_bound_manifest(
    path: Path,
    *,
    expected_sha256: str,
    model: type[TabularProjectionManifest] | type[SequenceProjectionManifest],
    root: FrozenPublicSampleRoot,
) -> TabularProjectionManifest | SequenceProjectionManifest:
    if _sha256(path) != expected_sha256:
        raise ValueError("projection manifest failed external SHA-256 verification")
    manifest = model.model_validate_json(path.read_text(encoding="utf-8"))
    expected = {
        "root_release_id": root.release_id,
        "root_sha256": root.canonical_hash(),
        "protocol_sha256": root.protocol_sha256,
        "corpus_sha256": root.corpus_sha256,
        "assignment_sha256": root.assignment_sha256,
        "feature_release_sha256": root.feature_release_sha256,
        "feature_schema_version": root.feature_schema_version,
    }
    if any(getattr(manifest, name) != value for name, value in expected.items()):
        raise ValueError("projection is not bound to the frozen public-sample root")
    return manifest


def _validate_scope(scope: AccessScope, folds: tuple[FoldName, ...]) -> None:
    expected = ("train", "validation") if scope == "development" else ("test",)
    if folds != expected:
        raise ValueError(f"{scope} projection must contain exactly {expected}")


def _resolve(artifact: ArtifactDigest, root: Path) -> Path:
    resolved_root = root.resolve()
    path = (resolved_root / artifact.uri).resolve()
    if (
        resolved_root not in path.parents
        or not path.is_file()
        or path.stat().st_size != artifact.size_bytes
        or _sha256(path) != artifact.sha256
    ):
        raise ValueError(f"projection artifact failed verification: {artifact.logical_name}")
    return path


def _artifact_digest(
    path: Path, *, root: Path, logical_name: str, schema_version: str
) -> ArtifactDigest:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if resolved_root not in resolved.parents or not resolved.is_file():
        raise ValueError("projection artifact is missing or outside its root")
    return ArtifactDigest(
        logical_name=logical_name,
        uri=resolved.relative_to(resolved_root).as_posix(),
        sha256=_sha256(resolved),
        size_bytes=resolved.stat().st_size,
        schema_version=schema_version,
    )


def supervised_row_id(
    *,
    root_sha256: str,
    assignment_sha256: str,
    replay_sha256: str,
    run_id: str,
    sequence: int,
    timestamp_ns: int,
) -> str:
    payload = [root_sha256, assignment_sha256, replay_sha256, run_id, sequence, timestamp_ns]
    return hashlib.sha256(
        json.dumps(payload, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def _projection_fold(
    fold: FoldName,
    shards: list[GovernedFeatureShard],
    *,
    split_id: str,
    assignment_sha256: str,
) -> GovernedFeatureFold:
    if not shards:
        raise ValueError(f"tabular projection fold has no shards: {fold}")
    ordered = tuple(
        sorted(shards, key=lambda item: (item.base_session_id, item.campaign_id or "", item.run_id))
    )
    positive = sum(item.positive_row_count for item in ordered)
    negative = sum(item.negative_row_count for item in ordered)
    if not positive or not negative:
        raise ValueError(f"tabular projection fold requires both classes: {fold}")
    identity = {
        "split_id": split_id,
        "assignment_hash": assignment_sha256,
        "fold": fold,
        "shards": [
            {
                "base_session_id": item.base_session_id,
                "campaign_id": item.campaign_id,
                "run_id": item.run_id,
                "feature_sha256": item.feature_sha256,
                "projection_manifest_sha256": item.run_metadata_sha256,
                "supervised_row_count": item.supervised_row_count,
            }
            for item in ordered
        ],
    }
    return GovernedFeatureFold(
        fold=fold,
        shards=ordered,
        fold_membership_hash=hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        session_count=len({item.base_session_id for item in ordered}),
        row_count=positive + negative,
        positive_row_count=positive,
        negative_row_count=negative,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
