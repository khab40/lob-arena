from __future__ import annotations

import hashlib
import json
import math
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.corpus.governance import (
    CampaignManifest,
    CleanWindowAdjudication,
    CorpusValidationReport,
    GovernedCorpusManifest,
    GovernedSession,
    load_adjudications,
    merge_verified_clean_feature_labels,
    validate_adjudications,
    validate_corpus,
)
from app.corpus.models import GovernedBenchmarkProtocol
from app.corpus.splits import (
    FoldName,
    GovernedSplitManifest,
    SessionSplitAssignment,
    validate_split_manifest,
)
from app.features.io import feature_arrow_schema
from app.features.io import load_labels
from app.features.models import (
    FeaturePipelineConfig,
    FeatureRunMetadata,
    LabelSpec,
    assign_label,
)
from app.features.pipeline import (
    FEATURE_COLUMNS,
    METADATA_COLUMNS,
    SUPPORTED_FEATURE_SCHEMA_VERSIONS,
    feature_split_group,
)
from app.evaluation.canonical_bundle import (
    CanonicalJavaReplayManifest,
    bind_replay_manifest_to_corpus_session,
)
from app.ml.lightgbm.feature_release import (
    GovernedFeatureReleaseManifest,
    GovernedFeatureReleaseShard,
    load_governed_feature_release,
    resolve_verified_artifact,
)


SHA256_PATTERN = r"^[0-9a-f]{64}$"
AccessMode = Literal["development", "final_test"]
SUPERVISED_LABEL_SOURCES = {
    0: "independently_verified_clean",
    1: "synthetic_scenario",
}


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _FeatureRunOutput(_StrictModel):
    feature_file: Literal["features.parquet"]
    feature_file_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_file_size_bytes: int = Field(ge=1)
    logical_feature_rows_sha256: str | None = Field(
        default=None,
        pattern=SHA256_PATTERN,
    )
    quality_file: Literal["feature-quality.json"]
    quality_file_sha256: str = Field(pattern=SHA256_PATTERN)
    row_count: int = Field(ge=1)
    valid_row_count: int = Field(ge=0)
    invalid_row_count: int = Field(ge=0)


class _FeatureColumnInventory(_StrictModel):
    metadata: tuple[str, ...]
    features: tuple[str, ...]
    label: tuple[str, ...]


class _FeatureSplitPolicy(_StrictModel):
    group_column: Literal["split_group"]
    rule: Literal["group by instrument/session; never randomly split adjacent rows"]
    purging: str = Field(min_length=1)


class _StrictFeatureRunMetadata(FeatureRunMetadata):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _FeatureRunManifest(_StrictModel):
    schema_version: str
    feature_schema_version: str
    feature_config_hash: str = Field(pattern=SHA256_PATTERN)
    generated_at: AwareDatetime
    run: _StrictFeatureRunMetadata
    config: dict[str, Any]
    input: dict[str, Any]
    output: _FeatureRunOutput
    columns: _FeatureColumnInventory
    split_policy: _FeatureSplitPolicy
    streaming: dict[str, Any] | None = None


@dataclass(frozen=True)
class GovernedFeatureShard:
    fold: FoldName
    base_session_id: str
    campaign_id: str | None
    run_id: str
    source_type: str
    feature_path: Path
    feature_uri: str
    feature_sha256: str
    feature_size_bytes: int
    run_metadata_path: Path
    run_metadata_sha256: str
    total_row_count: int
    supervised_row_count: int
    positive_row_count: int
    negative_row_count: int
    unlabeled_row_count: int
    feature_columns: tuple[str, ...]

    def iter_supervised_batches(
        self,
        *,
        batch_size: int = 65_536,
    ) -> Iterator[pa.RecordBatch]:
        if batch_size < 1:
            raise ValueError("feature batch size must be positive")
        _verify_file(
            self.feature_path,
            expected_sha256=self.feature_sha256,
            expected_size=self.feature_size_bytes,
            description=f"feature shard {self.run_id}",
        )
        parquet = pq.ParquetFile(self.feature_path)
        for batch in parquet.iter_batches(
            batch_size=batch_size,
            columns=[*METADATA_COLUMNS, *self.feature_columns],
        ):
            label = batch.column(batch.schema.get_field_index("label"))
            supervised = batch.filter(pc.is_valid(label))
            if supervised.num_rows:
                yield supervised


@dataclass(frozen=True)
class GovernedFeatureFold:
    fold: FoldName
    shards: tuple[GovernedFeatureShard, ...]
    fold_membership_hash: str
    session_count: int
    row_count: int
    positive_row_count: int
    negative_row_count: int

    def iter_supervised_batches(
        self,
        *,
        batch_size: int = 65_536,
    ) -> Iterator[pa.RecordBatch]:
        for shard in self.shards:
            yield from shard.iter_supervised_batches(batch_size=batch_size)


@dataclass(frozen=True)
class GovernedFeatureDataset:
    access_mode: AccessMode
    protocol_id: str
    protocol_hash: str
    corpus_id: str
    corpus_hash: str
    split_id: str
    assignment_hash: str
    feature_schema_version: str
    feature_config_hash: str
    feature_release_id: str
    feature_release_sha256: str
    ordered_feature_columns: tuple[str, ...]
    folds: tuple[GovernedFeatureFold, ...]

    def fold(self, name: FoldName) -> GovernedFeatureFold:
        matches = [fold for fold in self.folds if fold.fold == name]
        if len(matches) != 1:
            raise KeyError(f"governed feature fold is not loaded: {name}")
        return matches[0]


def load_governed_feature_dataset(
    *,
    protocol_path: Path,
    corpus_manifest_path: Path,
    corpus_validation_path: Path,
    split_manifest_path: Path,
    feature_config_path: Path,
    feature_release_manifest_path: Path,
    expected_feature_release_sha256: str,
    feature_artifact_root: Path,
    corpus_artifact_root: Path,
    access_mode: AccessMode = "development",
) -> GovernedFeatureDataset:
    """Load only locally verified, hash-compatible, fold-governed feature rows.

    Development access loads train and validation together. Final-test access is
    deliberately a separate invocation that can load only the frozen test fold.
    Unlabeled rows remain in their immutable source Parquet files but are never
    yielded by this loader.
    """

    if access_mode not in {"development", "final_test"}:
        raise ValueError(f"unsupported governed feature access mode: {access_mode}")
    protocol = GovernedBenchmarkProtocol.model_validate(
        _load_json_object(protocol_path)
    )
    corpus = GovernedCorpusManifest.model_validate(
        _load_json_object(corpus_manifest_path)
    )
    supplied_validation = CorpusValidationReport.model_validate(
        _load_json_object(corpus_validation_path)
    )
    split = GovernedSplitManifest.model_validate(
        _load_json_object(split_manifest_path)
    )
    feature_config_payload = _load_json_object(feature_config_path)
    feature_config = FeaturePipelineConfig.model_validate(feature_config_payload)
    release = load_governed_feature_release(
        feature_release_manifest_path,
        expected_sha256=expected_feature_release_sha256,
    )
    _validate_governed_inputs(
        protocol=protocol,
        corpus=corpus,
        supplied_validation=supplied_validation,
        split=split,
        feature_config=feature_config,
        feature_config_payload=feature_config_payload,
        artifact_root=corpus_artifact_root,
    )
    _validate_feature_release(
        release,
        protocol=protocol,
        corpus=corpus,
        split=split,
        feature_config=feature_config,
    )
    adjudications_path = resolve_verified_artifact(
        release.adjudications,
        root=feature_artifact_root,
    )
    adjudications = load_adjudications(adjudications_path)
    validate_adjudications(
        adjudications,
        manifest=corpus,
        protocol=protocol,
        artifact_root=corpus_artifact_root,
    )

    requested_folds: tuple[FoldName, ...] = (
        ("train", "validation") if access_mode == "development" else ("test",)
    )

    sessions_by_identity = {
        _session_identity(session): session
        for session in corpus.sessions
    }
    assignments_by_session = {
        item.base_session_id: item
        for item in split.assignments
        if item.fold in requested_folds
    }
    shards: list[GovernedFeatureShard] = []
    run_ids: set[str] = set()
    inventory: set[tuple[str, str | None]] = set()
    selected_release_shards = [
        shard for shard in release.shards if shard.fold in requested_folds
    ]
    for release_shard in sorted(
        selected_release_shards,
        key=lambda item: (
            item.base_session_id,
            item.campaign_id or "",
            item.run_id,
        ),
    ):
        shard = _load_feature_shard(
            release_shard,
            protocol=protocol,
            corpus=corpus,
            feature_config=feature_config,
            sessions_by_identity=sessions_by_identity,
            assignments_by_session=assignments_by_session,
            adjudications=adjudications,
            adjudications_sha256=release.adjudications.sha256,
            feature_artifact_root=feature_artifact_root,
            corpus_artifact_root=corpus_artifact_root,
        )
        if shard.run_id in run_ids:
            raise ValueError(f"duplicate governed feature run ID: {shard.run_id}")
        run_ids.add(shard.run_id)
        inventory_key = (shard.base_session_id, shard.campaign_id)
        if inventory_key in inventory:
            domain = shard.campaign_id or "historical-control"
            raise ValueError(
                f"duplicate governed feature replay domain: "
                f"{shard.base_session_id}/{domain}"
            )
        inventory.add(inventory_key)
        shards.append(shard)

    expected_inventory = {
        (assignment.base_session_id, None)
        for assignment in assignments_by_session.values()
    }
    sessions_by_id = {session.base_session_id: session for session in corpus.sessions}
    expected_inventory.update(
        (assignment.base_session_id, campaign.campaign_id)
        for assignment in assignments_by_session.values()
        for campaign in sessions_by_id[assignment.base_session_id].campaigns
    )
    if inventory != expected_inventory:
        missing = sorted(expected_inventory - inventory)
        unexpected = sorted(inventory - expected_inventory)
        raise ValueError(
            "governed feature inventory does not exactly cover the selected folds: "
            f"missing={missing}, unexpected={unexpected}"
        )

    loaded_folds = tuple(
        _build_fold(
            fold,
            [shard for shard in shards if shard.fold == fold],
            split=split,
        )
        for fold in requested_folds
    )
    return GovernedFeatureDataset(
        access_mode=access_mode,
        protocol_id=protocol.protocol_id,
        protocol_hash=protocol.protocol_hash(),
        corpus_id=corpus.corpus_id,
        corpus_hash=corpus.corpus_hash(),
        split_id=split.split_id,
        assignment_hash=split.assignment_hash,
        feature_schema_version=feature_config.schema_version,
        feature_config_hash=feature_config.config_hash(),
        feature_release_id=release.release_id,
        feature_release_sha256=expected_feature_release_sha256,
        ordered_feature_columns=tuple(FEATURE_COLUMNS),
        folds=loaded_folds,
    )


def _validate_governed_inputs(
    *,
    protocol: GovernedBenchmarkProtocol,
    corpus: GovernedCorpusManifest,
    supplied_validation: CorpusValidationReport,
    split: GovernedSplitManifest,
    feature_config: FeaturePipelineConfig,
    feature_config_payload: dict[str, Any],
    artifact_root: Path,
) -> None:
    if feature_config_payload != feature_config.model_dump(mode="json"):
        raise ValueError("feature configuration contains unknown or non-canonical fields")
    if (
        protocol.feature_schema_version != feature_config.schema_version
        or feature_config.schema_version not in SUPPORTED_FEATURE_SCHEMA_VERSIONS
    ):
        raise ValueError("feature schema is incompatible with the governed protocol")
    recomputed = validate_corpus(
        corpus,
        protocol,
        artifact_root=artifact_root,
    )
    if (
        supplied_validation != recomputed
        or supplied_validation.verdict != "pass"
        or supplied_validation.artifact_verification_mode != "local"
    ):
        raise ValueError(
            "corpus validation is not the exact passing local validation "
            "for the governed corpus"
        )
    validate_split_manifest(split, corpus=corpus, protocol=protocol)


def _validate_feature_release(
    release: GovernedFeatureReleaseManifest,
    *,
    protocol: GovernedBenchmarkProtocol,
    corpus: GovernedCorpusManifest,
    split: GovernedSplitManifest,
    feature_config: FeaturePipelineConfig,
) -> None:
    required = {
        "protocol_id": protocol.protocol_id,
        "protocol_hash": protocol.protocol_hash(),
        "corpus_id": corpus.corpus_id,
        "corpus_hash": corpus.corpus_hash(),
        "split_id": split.split_id,
        "assignment_hash": split.assignment_hash,
        "feature_schema_version": feature_config.schema_version,
        "feature_config_hash": feature_config.config_hash(),
    }
    if any(getattr(release, name) != value for name, value in required.items()):
        raise ValueError("feature release is incompatible with governed inputs")

    assignments = {
        assignment.base_session_id: assignment.fold
        for assignment in split.assignments
    }
    sessions = {session.base_session_id: session for session in corpus.sessions}
    expected = {
        (base_session_id, None, fold)
        for base_session_id, fold in assignments.items()
    }
    expected.update(
        (base_session_id, campaign.campaign_id, assignments[base_session_id])
        for base_session_id, session in sessions.items()
        if base_session_id in assignments
        for campaign in session.campaigns
    )
    observed = {
        (shard.base_session_id, shard.campaign_id, shard.fold)
        for shard in release.shards
    }
    if observed != expected:
        raise ValueError(
            "feature release does not exactly inventory the frozen split domains"
        )


def _load_feature_shard(
    release_shard: GovernedFeatureReleaseShard,
    *,
    protocol: GovernedBenchmarkProtocol,
    corpus: GovernedCorpusManifest,
    feature_config: FeaturePipelineConfig,
    sessions_by_identity: dict[tuple[str, str, date, str], GovernedSession],
    assignments_by_session: dict[str, SessionSplitAssignment],
    adjudications: list[CleanWindowAdjudication],
    adjudications_sha256: str,
    feature_artifact_root: Path,
    corpus_artifact_root: Path,
) -> GovernedFeatureShard:
    metadata_path = resolve_verified_artifact(
        release_shard.run_metadata,
        root=feature_artifact_root,
    )
    manifest = _FeatureRunManifest.model_validate(_load_json_object(metadata_path))
    if manifest.schema_version != release_shard.run_metadata.schema_version:
        raise ValueError("feature run metadata schema is unsupported")
    if (
        manifest.feature_schema_version != feature_config.schema_version
        or manifest.feature_schema_version != protocol.feature_schema_version
        or manifest.feature_config_hash != feature_config.config_hash()
        or manifest.config != feature_config.model_dump(mode="json")
    ):
        raise ValueError("feature run schema or configuration binding is incompatible")
    expected_columns = _FeatureColumnInventory(
        metadata=tuple(METADATA_COLUMNS),
        features=tuple(FEATURE_COLUMNS),
        label=("attack_family", "attack_phase", "label", "label_source"),
    )
    if manifest.columns != expected_columns:
        raise ValueError("feature run column inventory is incompatible")
    session = sessions_by_identity.get(_run_identity(manifest.run))
    if (
        session is None
        or manifest.run.dataset_id != session.dataset_id
        or release_shard.base_session_id != session.base_session_id
    ):
        raise ValueError("feature run is not bound to a governed corpus session")
    assignment = assignments_by_session.get(session.base_session_id)
    if assignment is None or release_shard.fold != assignment.fold:
        raise ValueError(
            "feature run belongs to a fold that is unavailable in this access mode"
        )

    replay_path = resolve_verified_artifact(
        release_shard.replay_manifest,
        root=feature_artifact_root,
    )
    replay = CanonicalJavaReplayManifest.model_validate(
        _load_json_object(replay_path)
    )
    bind_replay_manifest_to_corpus_session(replay, session)
    expected_run_metadata = _feature_metadata_from_replay(replay)
    if (
        manifest.run.model_dump(mode="json")
        != expected_run_metadata.model_dump(mode="json")
        or manifest.run.run_id != release_shard.run_id
    ):
        raise ValueError(
            "feature run identity or market units do not match its canonical replay"
        )
    campaign = _resolve_campaign(session, replay.seed)
    if (
        release_shard.campaign_id != replay.campaign_id
        or (
            campaign is not None
            and campaign.campaign_id != release_shard.campaign_id
        )
    ):
        raise ValueError("feature release campaign identity is incompatible")
    expected_labels = _expected_labels(
        replay,
        session=session,
        campaign=campaign,
        adjudications=adjudications,
        corpus_artifact_root=corpus_artifact_root,
    )
    clean_window_ids = sorted(
        window.provenance_id
        for window in expected_labels.labels
        if window.label == 0 and window.provenance_id is not None
    )
    _validate_provenance(
        manifest,
        protocol=protocol,
        corpus=corpus,
        replay_manifest_sha256=release_shard.replay_manifest.sha256,
        adjudications_sha256=adjudications_sha256,
        clean_window_ids=clean_window_ids,
    )

    expected_split_group = feature_split_group(manifest.run)
    validation_reference = (
        session.control_validation if campaign is None else campaign.validation
    )
    validation_payload = _load_json_object(
        _resolve_artifact(corpus_artifact_root, validation_reference.uri)
    )
    if (
        validation_payload.get("canonical_event_stream_hash")
        != replay.canonical_event_stream_hash
        or manifest.input.get("java_canonical_event_stream_hash")
        != replay.canonical_event_stream_hash
    ):
        raise ValueError(
            "feature run canonical event hash does not match its governed replay"
        )

    feature_path = resolve_verified_artifact(
        release_shard.features,
        root=feature_artifact_root,
    )
    quality_path = resolve_verified_artifact(
        release_shard.quality,
        root=feature_artifact_root,
    )
    if (
        manifest.output.feature_file_sha256 != release_shard.features.sha256
        or manifest.output.feature_file_size_bytes
        != release_shard.features.size_bytes
        or manifest.output.quality_file_sha256 != release_shard.quality.sha256
    ):
        raise ValueError("feature run outputs do not match the frozen feature release")
    parquet = pq.ParquetFile(feature_path)
    if not parquet.schema_arrow.equals(
        feature_arrow_schema(
            feature_config.config_hash(),
            feature_config.schema_version,
        ),
        check_metadata=True,
    ):
        raise ValueError("feature Parquet schema or metadata is incompatible")
    if parquet.metadata.num_rows != manifest.output.row_count:
        raise ValueError("feature Parquet row count does not match run metadata")

    counts = _validate_feature_rows(
        parquet,
        manifest=manifest,
        session=session,
        campaign_id=campaign.campaign_id if campaign is not None else None,
        expected_labels=expected_labels,
        expected_split_group=expected_split_group,
    )
    quality = _load_json_object(quality_path)
    _validate_quality(quality, manifest=manifest, counts=counts)
    return GovernedFeatureShard(
        fold=assignment.fold,
        base_session_id=session.base_session_id,
        campaign_id=campaign.campaign_id if campaign is not None else None,
        run_id=manifest.run.run_id,
        source_type=manifest.run.source_type,
        feature_path=feature_path.resolve(),
        feature_uri=release_shard.features.uri,
        feature_sha256=manifest.output.feature_file_sha256,
        feature_size_bytes=manifest.output.feature_file_size_bytes,
        run_metadata_path=metadata_path.resolve(),
        run_metadata_sha256=release_shard.run_metadata.sha256,
        total_row_count=counts["total"],
        supervised_row_count=counts["positive"] + counts["negative"],
        positive_row_count=counts["positive"],
        negative_row_count=counts["negative"],
        unlabeled_row_count=counts["unlabeled"],
        feature_columns=tuple(FEATURE_COLUMNS),
    )


def _feature_metadata_from_replay(
    replay: CanonicalJavaReplayManifest,
) -> FeatureRunMetadata:
    source_type = {
        "historical_control": "lobster",
        "synthetic": "synthetic",
        "hybrid": "hybrid",
    }[replay.mode]
    return FeatureRunMetadata(
        run_id=replay.run_id,
        dataset_id=replay.dataset_id,
        source_type=source_type,
        instrument=replay.instrument,
        venue=replay.venue,
        session_id=replay.session_id,
        session_date=replay.session_date,
        seed=replay.seed,
        price_tick_size=replay.price_tick_size,
        quantity_lot_size=replay.quantity_lot_size,
        tick_interval_ns=replay.tick_interval_ns,
    )


def _expected_labels(
    replay: CanonicalJavaReplayManifest,
    *,
    session: GovernedSession,
    campaign: CampaignManifest | None,
    adjudications: list[CleanWindowAdjudication],
    corpus_artifact_root: Path,
) -> LabelSpec:
    base_labels = LabelSpec()
    if campaign is not None:
        base_labels = load_labels(
            _resolve_artifact(corpus_artifact_root, campaign.ground_truth.uri)
        )
        if (
            len(base_labels.labels) != replay.label_count
            or any(window.label != 1 for window in base_labels.labels)
            or any(
                window.attack_family != campaign.attack_family
                or window.label_source != "synthetic_scenario"
                for window in base_labels.labels
            )
        ):
            raise ValueError(
                "campaign ground truth does not define the governed synthetic labels"
            )
    return merge_verified_clean_feature_labels(
        base_labels,
        adjudications,
        base_session_id=session.base_session_id,
        replay_mode=replay.mode,
    )


def _validate_provenance(
    manifest: _FeatureRunManifest,
    *,
    protocol: GovernedBenchmarkProtocol,
    corpus: GovernedCorpusManifest,
    replay_manifest_sha256: str,
    adjudications_sha256: str,
    clean_window_ids: list[str],
) -> None:
    required = {
        "governed_corpus_id": corpus.corpus_id,
        "governed_corpus_sha256": corpus.corpus_hash(),
        "governed_protocol_id": protocol.protocol_id,
        "governed_protocol_sha256": protocol.protocol_hash(),
        "clean_label_artifact_verification_mode": "local",
        "canonical_java_replay_bundle": "canonical_java_replay_bundle_v1",
        "replay_manifest_sha256": replay_manifest_sha256,
        "clean_adjudications_sha256": adjudications_sha256,
        "clean_negative_window_ids": clean_window_ids,
        "clean_negative_window_count": len(clean_window_ids),
    }
    if any(manifest.input.get(name) != value for name, value in required.items()):
        raise ValueError("feature run governed provenance is incompatible")
    for name in (
        "canonical_event_stream_sha256",
        "java_canonical_event_stream_hash",
    ):
        _require_sha256(manifest.input.get(name), name)


def _validate_feature_rows(
    parquet: pq.ParquetFile,
    *,
    manifest: _FeatureRunManifest,
    session: GovernedSession,
    campaign_id: str | None,
    expected_labels: LabelSpec,
    expected_split_group: str,
) -> Counter[str]:
    counts: Counter[str] = Counter()
    previous_sequence = -1
    previous_timestamp = -1
    previous_tick = -1
    for batch in parquet.iter_batches(batch_size=65_536):
        for row in batch.to_pylist():
            counts["total"] += 1
            expected = {
                "feature_schema_version": manifest.feature_schema_version,
                "feature_config_hash": manifest.feature_config_hash,
                "run_id": manifest.run.run_id,
                "dataset_id": session.dataset_id,
                "source_type": manifest.run.source_type,
                "instrument": session.instrument,
                "venue": session.venue,
                "session_id": session.session_id,
                "session_date": session.session_date,
                "seed": manifest.run.seed,
                "split_group": expected_split_group,
            }
            if any(row.get(name) != value for name, value in expected.items()):
                raise ValueError("feature row identity or governed binding is incompatible")
            if row["row_valid"] is not True or row["invalid_reason"] is not None:
                raise ValueError("invalid feature rows cannot enter a governed dataset")
            sequence = row["sequence"]
            timestamp = row["prediction_timestamp_ns"]
            tick = row["tick"]
            if (
                sequence <= previous_sequence
                or timestamp < previous_timestamp
                or tick < previous_tick
            ):
                raise ValueError("feature rows are not in strict causal sequence order")
            previous_sequence = sequence
            previous_timestamp = timestamp
            previous_tick = tick
            for name in FEATURE_COLUMNS:
                value = row[name]
                if value is not None and (
                    not isinstance(value, (int, float))
                    or not math.isfinite(float(value))
                ):
                    raise ValueError(f"feature row contains a non-finite value: {name}")

            expected_label = assign_label(
                expected_labels,
                tick=tick,
                prediction_timestamp_ns=timestamp,
            )
            if any(
                row[name] != value
                for name, value in {
                    "label": expected_label.label,
                    "attack_family": expected_label.attack_family,
                    "attack_phase": expected_label.attack_phase,
                    "label_source": expected_label.label_source,
                }.items()
            ):
                raise ValueError(
                    "feature row label does not match governed ground truth "
                    "and clean-window adjudications"
                )
            label = expected_label.label
            if label is None:
                counts["unlabeled"] += 1
                continue
            if label not in (0, 1):
                raise ValueError("governed feature labels must be binary")
            expected_source = SUPERVISED_LABEL_SOURCES[label]
            if row["label_source"] != expected_source:
                raise ValueError("governed feature label provenance is invalid")
            if label == 0:
                if (
                    row["attack_family"] is not None
                    or row["attack_phase"] not in {None, "none"}
                    or (
                        campaign_id is None
                        and manifest.run.source_type != "lobster"
                    )
                ):
                    raise ValueError("verified-clean feature row semantics are invalid")
                counts["negative"] += 1
                continue
            if (
                campaign_id is None
                or not expected_label.attack_family
                or not expected_label.attack_phase
            ):
                raise ValueError("positive feature row is not bound to its governed campaign")
            counts["positive"] += 1

    if counts["total"] != manifest.output.row_count:
        raise ValueError("feature row scan does not match run metadata")
    if counts["positive"] + counts["negative"] == 0:
        raise ValueError("feature run contains no governed supervised rows")
    if campaign_id is None and counts["positive"]:
        raise ValueError("historical control feature runs cannot contain positive labels")
    if campaign_id is not None and counts["positive"] == 0:
        raise ValueError("campaign feature runs require governed positive rows")
    return counts


def _validate_quality(
    quality: dict[str, Any],
    *,
    manifest: _FeatureRunManifest,
    counts: Counter[str],
) -> None:
    expected_balance = {
        "positive": counts["positive"],
        "negative": counts["negative"],
        "unlabeled": counts["unlabeled"],
    }
    balance = quality.get("class_balance")
    if (
        quality.get("schema_version") != "feature_quality_report_v1"
        or quality.get("row_count") != counts["total"]
        or quality.get("valid_row_count") != counts["total"]
        or quality.get("invalid_row_count") != 0
        or not isinstance(balance, dict)
        or any(balance.get(name) != value for name, value in expected_balance.items())
        or manifest.output.valid_row_count != counts["total"]
        or manifest.output.invalid_row_count != 0
    ):
        raise ValueError("feature quality report does not match verified feature rows")


def _build_fold(
    fold: FoldName,
    shards: list[GovernedFeatureShard],
    *,
    split: GovernedSplitManifest,
) -> GovernedFeatureFold:
    if not shards:
        raise ValueError(f"governed feature fold has no shards: {fold}")
    positive = sum(shard.positive_row_count for shard in shards)
    negative = sum(shard.negative_row_count for shard in shards)
    if positive == 0 or negative == 0:
        raise ValueError(f"governed feature fold requires both binary classes: {fold}")
    ordered = tuple(
        sorted(
            shards,
            key=lambda item: (
                item.base_session_id,
                item.campaign_id or "",
                item.run_id,
            ),
        )
    )
    payload = {
        "split_id": split.split_id,
        "assignment_hash": split.assignment_hash,
        "fold": fold,
        "shards": [
            {
                "base_session_id": shard.base_session_id,
                "campaign_id": shard.campaign_id,
                "run_id": shard.run_id,
                "feature_sha256": shard.feature_sha256,
                "run_metadata_sha256": shard.run_metadata_sha256,
                "supervised_row_count": shard.supervised_row_count,
            }
            for shard in ordered
        ],
    }
    membership_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return GovernedFeatureFold(
        fold=fold,
        shards=ordered,
        fold_membership_hash=membership_hash,
        session_count=len({shard.base_session_id for shard in ordered}),
        row_count=positive + negative,
        positive_row_count=positive,
        negative_row_count=negative,
    )


def _resolve_campaign(
    session: GovernedSession,
    seed: int | None,
) -> CampaignManifest | None:
    if seed is None:
        return None
    matches = [
        campaign
        for campaign in session.campaigns
        if campaign.derived_seed == seed
    ]
    if len(matches) != 1:
        raise ValueError(
            "feature run seed does not identify exactly one governed campaign"
        )
    return matches[0]


def _session_identity(session: GovernedSession) -> tuple[str, str, date, str]:
    return (
        session.venue,
        session.instrument,
        session.session_date,
        session.session_id,
    )


def _run_identity(metadata: FeatureRunMetadata) -> tuple[str, str, date, str]:
    return (
        metadata.venue,
        metadata.instrument,
        metadata.session_date,
        metadata.session_id,
    )


def _load_json_object(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (OSError, json.JSONDecodeError) as exception:
        raise ValueError(f"failed to load governed JSON object: {path}") from exception
    if not isinstance(payload, dict):
        raise ValueError(f"governed JSON input must be an object: {path}")
    return payload


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _resolve_artifact(root: Path, uri: str) -> Path:
    resolved_root = root.resolve()
    path = (resolved_root / uri).resolve()
    if path == resolved_root or resolved_root not in path.parents or not path.is_file():
        raise ValueError(f"governed artifact is missing or outside its root: {uri}")
    return path


def _verify_file(
    path: Path,
    *,
    expected_sha256: str,
    expected_size: int,
    description: str,
) -> None:
    if (
        not path.is_file()
        or path.stat().st_size != expected_size
        or _sha256(path) != expected_sha256
    ):
        raise ValueError(f"{description} failed size or SHA-256 verification")


def _require_sha256(value: object, name: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"feature run provenance has invalid {name}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
