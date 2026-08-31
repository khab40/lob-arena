from __future__ import annotations

import hashlib
import json
import tomllib
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import app.ml.lightgbm as lightgbm_boundary
from app.corpus.governance import (
    ArtifactReference,
    CampaignManifest,
    CleanWindowAdjudication,
    GovernedSession,
    ReviewDecision,
    build_corpus_manifest,
    validate_corpus,
)
from app.corpus.models import GovernedBenchmarkProtocol
from app.corpus.splits import generate_split_manifest
from app.evaluation.canonical_bundle import CanonicalJavaReplayManifest
from app.features.io import write_feature_run
from app.features.models import FeaturePipelineConfig, FeatureRunMetadata
from app.features.pipeline import (
    FEATURE_COLUMNS,
    FEATURE_SCHEMA_V2,
    FeatureRunResult,
    feature_quality_report,
    feature_split_group,
)
from app.ml.lightgbm.data import load_governed_feature_dataset
from app.ml.lightgbm.feature_release import (
    GovernedFeatureReleaseManifest,
    GovernedFeatureReleaseShard,
    artifact_digest,
    write_governed_feature_release,
)


ROOT = Path(__file__).resolve().parents[2]
HASH_A = "a" * 64
GENERATED_AT = datetime(2026, 7, 29, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class GovernedFixture:
    protocol: Path
    corpus: Path
    corpus_validation: Path
    split: Path
    feature_config: Path
    artifact_root: Path
    feature_artifact_root: Path
    feature_release: Path
    feature_release_sha256: str
    feature_dirs: dict[str, tuple[Path, ...]]
    replay_manifests: dict[tuple[str, str | None], Path]


def _json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )


def _artifact(root: Path, relative: str, payload: bytes, schema: str) -> ArtifactReference:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return ArtifactReference(
        name=path.name,
        uri=relative,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        schema_version=schema,
    )


def _validation(
    root: Path,
    *,
    relative: str,
    base_session_id: str,
    dataset_id: str,
    campaign_id: str | None,
    stream_hash: str,
) -> ArtifactReference:
    payload = {
        "verdict": "pass",
        "base_session_id": base_session_id,
        "dataset_id": dataset_id,
        "campaign_id": campaign_id,
        "session_start_timestamp_ns": 100,
        "session_end_timestamp_ns": 1_000,
        "complete_session": True,
        "canonical_event_stream_hash": stream_hash,
    }
    encoded = (json.dumps(payload, sort_keys=True) + "\n").encode()
    return _artifact(root, relative, encoded, "hybrid_dataset_validation_v1")


def _session(root: Path, index: int) -> GovernedSession:
    base_id = f"base-{index}"
    dataset_id = f"dataset-{index}"
    stream_hash = hashlib.sha256(f"control-{index}".encode()).hexdigest()
    campaign_hash = hashlib.sha256(f"campaign-{index}".encode()).hexdigest()
    campaign = CampaignManifest(
        campaign_id=f"campaign-{index}",
        attack_family="layering_like",
        master_seed=100,
        derived_seed=1_000 + index,
        injection_timestamp_ns=500,
        canonical_events=_artifact(
            root,
            f"{base_id}/campaign-events.jsonl",
            f"campaign-events-{index}".encode(),
            "canonical_events_v1",
        ),
        ground_truth=_artifact(
            root,
            f"{base_id}/campaign-ground-truth.json",
            (
                json.dumps(
                    {
                        "ground_truth": {
                            "scenario_family": "layering_like",
                            "start_tick": 1,
                            "end_tick": 1,
                            "source": "synthetic_scenario",
                            "phase_windows": {
                                "pressure_build": {
                                    "start_tick": 1,
                                    "end_tick": 1,
                                }
                            },
                        }
                    },
                    sort_keys=True,
                )
                + "\n"
            ).encode(),
            "scenario_ground_truth_v1",
        ),
        validation=_validation(
            root,
            relative=f"{base_id}/campaign-validation.json",
            base_session_id=base_id,
            dataset_id=dataset_id,
            campaign_id=f"campaign-{index}",
            stream_hash=campaign_hash,
        ),
    )
    return GovernedSession(
        base_session_id=base_id,
        dataset_id=dataset_id,
        instrument="SPY",
        venue="LOBSTER",
        session_id=f"session-{index}",
        session_date=date(2026, 1, 1) + timedelta(days=index),
        timezone="America/New_York",
        start_timestamp_ns=100,
        end_timestamp_ns=1_000,
        complete_session=True,
        source_manifest=_artifact(
            root,
            f"{base_id}/source-manifest.json",
            f"source-{index}".encode(),
            "lobster_source_manifest_v1",
        ),
        canonical_control_events=_artifact(
            root,
            f"{base_id}/control-events.jsonl",
            f"control-events-{index}".encode(),
            "canonical_events_v1",
        ),
        control_validation=_validation(
            root,
            relative=f"{base_id}/control-validation.json",
            base_session_id=base_id,
            dataset_id=dataset_id,
            campaign_id=None,
            stream_hash=stream_hash,
        ),
        campaigns=[campaign],
    )


def _feature_row(
    metadata: FeatureRunMetadata,
    config: FeaturePipelineConfig,
    *,
    sequence: int,
    label: int | None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "feature_schema_version": config.schema_version,
        "feature_config_hash": config.config_hash(),
        "run_id": metadata.run_id,
        "dataset_id": metadata.dataset_id,
        "source_type": metadata.source_type,
        "historical_source_type": metadata.historical_source_type,
        "instrument": metadata.instrument,
        "venue": metadata.venue,
        "session_id": metadata.session_id,
        "session_date": metadata.session_date,
        "seed": metadata.seed,
        "prediction_timestamp_ns": 100 + sequence,
        "tick": sequence,
        "sequence": sequence,
        "split_group": feature_split_group(metadata),
        "attack_family": "layering_like" if label == 1 else None,
        "attack_phase": "pressure_build" if label == 1 else "none" if label == 0 else None,
        "label": label,
        "label_source": (
            "synthetic_scenario"
            if label == 1
            else "independently_verified_clean"
            if label == 0
            else None
        ),
        "row_valid": True,
        "invalid_reason": None,
    }
    row.update({name: float(sequence) for name in FEATURE_COLUMNS})
    return row


def _write_feature_bundle(
    output: Path,
    *,
    session: GovernedSession,
    protocol: GovernedBenchmarkProtocol,
    corpus_hash: str,
    config: FeaturePipelineConfig,
    campaign: bool,
    artifact_root: Path,
    adjudications_sha256: str,
    replay_manifest_sha256: str,
) -> None:
    campaign_manifest = session.campaigns[0] if campaign else None
    metadata = FeatureRunMetadata(
        run_id=f"{session.base_session_id}-{'campaign' if campaign else 'control'}",
        dataset_id=session.dataset_id,
        source_type="hybrid" if campaign else "lobster",
        instrument=session.instrument,
        venue=session.venue,
        session_id=session.session_id,
        session_date=session.session_date,
        seed=campaign_manifest.derived_seed if campaign_manifest else None,
        price_tick_size=0.01,
        quantity_lot_size=1.0,
        tick_interval_ns=100,
    )
    validation = campaign_manifest.validation if campaign_manifest else session.control_validation
    validation_payload = json.loads((artifact_root / validation.uri).read_text(encoding="utf-8"))
    rows = [
        _feature_row(metadata, config, sequence=1, label=1 if campaign else 0),
        _feature_row(metadata, config, sequence=2, label=None),
    ]
    result = FeatureRunResult(
        rows=rows,
        quality_report=feature_quality_report(rows, FEATURE_COLUMNS),
        input_sha256=HASH_A,
        input_provenance={
            "feature_checkpoint_count": len(rows),
            "governed_corpus_id": "governed-fixture",
            "governed_corpus_sha256": corpus_hash,
            "governed_protocol_id": protocol.protocol_id,
            "governed_protocol_sha256": protocol.protocol_hash(),
            "clean_adjudications_sha256": adjudications_sha256,
            "clean_negative_window_ids": (
                [] if campaign else [f"clean-{session.base_session_id}"]
            ),
            "clean_negative_window_count": 0 if campaign else 1,
            "clean_label_artifact_verification_mode": "local",
            "canonical_java_replay_bundle": "canonical_java_replay_bundle_v1",
            "java_canonical_event_stream_hash": validation_payload["canonical_event_stream_hash"],
            "replay_manifest_sha256": replay_manifest_sha256,
        },
    )
    write_feature_run(
        output,
        result=result,
        config=config,
        metadata=metadata,
    )


def _write_adjudications(
    path: Path,
    *,
    artifact_root: Path,
    sessions: list[GovernedSession],
) -> list[CleanWindowAdjudication]:
    adjudications: list[CleanWindowAdjudication] = []
    for session in sessions:
        reviews = [
            ReviewDecision(
                reviewer_id=f"reviewer-{reviewer}",
                decision="clean",
                reviewed_at=GENERATED_AT,
                method="blind_manual_review",
                model_outputs_hidden=True,
                evidence=[
                    _artifact(
                        artifact_root,
                        (
                            f"{session.base_session_id}/"
                            f"clean-review-{reviewer}.json"
                        ),
                        f"review-{session.base_session_id}-{reviewer}".encode(),
                        "clean_window_review_evidence_v1",
                    )
                ],
            )
            for reviewer in (1, 2)
        ]
        adjudications.append(
            CleanWindowAdjudication(
                window_id=f"clean-{session.base_session_id}",
                base_session_id=session.base_session_id,
                start_timestamp_ns=100,
                end_timestamp_ns=102,
                status="verified_clean",
                reviewer_decisions=reviews,
                label_source="independently_verified_clean",
            )
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(
            json.dumps(item.model_dump(mode="json"), sort_keys=True) + "\n"
            for item in adjudications
        ),
        encoding="utf-8",
    )
    return adjudications


def _write_replay_manifest(
    path: Path,
    *,
    artifact_root: Path,
    session: GovernedSession,
    campaign: bool,
) -> CanonicalJavaReplayManifest:
    campaign_manifest = session.campaigns[0] if campaign else None
    domain = "campaign" if campaign else "control"
    validation = (
        campaign_manifest.validation
        if campaign_manifest is not None
        else session.control_validation
    )
    validation_payload = json.loads(
        (artifact_root / validation.uri).read_text(encoding="utf-8")
    )
    snapshots = _artifact(
        artifact_root,
        f"{session.base_session_id}/{domain}-snapshots.parquet",
        f"{domain}-snapshots-{session.base_session_id}".encode(),
        "canonical_snapshots_v1",
    )
    alerts = _artifact(
        artifact_root,
        f"{session.base_session_id}/{domain}-alerts.jsonl",
        f"{domain}-alerts-{session.base_session_id}".encode(),
        "detector_alerts_v1",
    )
    manifest = CanonicalJavaReplayManifest(
        run_id=f"{session.base_session_id}-{domain}",
        base_session_id=session.base_session_id,
        dataset_id=session.dataset_id,
        mode="hybrid" if campaign else "historical_control",
        campaign_id=(
            campaign_manifest.campaign_id
            if campaign_manifest is not None
            else None
        ),
        attack_family=(
            campaign_manifest.attack_family
            if campaign_manifest is not None
            else None
        ),
        instrument=session.instrument,
        venue=session.venue,
        session_id=session.session_id,
        session_date=session.session_date,
        seed=(
            campaign_manifest.derived_seed
            if campaign_manifest is not None
            else None
        ),
        price_tick_size=0.01,
        quantity_lot_size=1.0,
        tick_interval_ns=100,
        java_engine_version="fixture-java",
        canonical_event_stream_hash=validation_payload[
            "canonical_event_stream_hash"
        ],
        event_count=2,
        snapshot_count=1,
        alert_count=0,
        label_count=1 if campaign else 0,
        last_sequence=2,
        first_timestamp_ns=101,
        last_timestamp_ns=102,
        events=(
            campaign_manifest.canonical_events
            if campaign_manifest is not None
            else session.canonical_control_events
        ),
        snapshots=snapshots,
        alerts=alerts,
        ground_truth=(
            campaign_manifest.ground_truth
            if campaign_manifest is not None
            else None
        ),
        validation=validation,
    )
    _json(path, manifest.model_dump(mode="json"))
    return manifest


@pytest.fixture
def governed_fixture(tmp_path: Path) -> GovernedFixture:
    artifact_root = tmp_path / "artifacts"
    protocol = GovernedBenchmarkProtocol(
        protocol_id="lightgbm-phase1-fixture",
        feature_schema_version=FEATURE_SCHEMA_V2,
        corpus={
            "complete_sessions": 5,
            "instruments": 1,
            "distinct_dates": 5,
            "seeds_per_attack_family": 1,
            "require_all_attack_families": True,
            "required_attack_families": ["layering_like"],
        },
        splits={
            "embargo_sessions": 1,
            "train_fraction": 0.6,
            "validation_fraction": 0.2,
            "test_fraction": 0.2,
        },
    )
    sessions = [_session(artifact_root, index) for index in range(5)]
    corpus = build_corpus_manifest(
        corpus_id="governed-fixture",
        sessions=sessions,
        protocol=protocol,
        generated_at=GENERATED_AT,
    )
    corpus_validation = validate_corpus(
        corpus,
        protocol,
        artifact_root=artifact_root,
    )
    assert corpus_validation.verdict == "pass"
    split = generate_split_manifest(
        split_id="chronological-fixture",
        corpus=corpus,
        protocol=protocol,
        generated_at=GENERATED_AT,
    )
    config = FeaturePipelineConfig(schema_version=FEATURE_SCHEMA_V2)
    protocol_path = tmp_path / "protocol.json"
    corpus_path = tmp_path / "corpus.json"
    corpus_validation_path = tmp_path / "corpus-validation.json"
    split_path = tmp_path / "split.json"
    config_path = tmp_path / "feature-config.json"
    _json(protocol_path, protocol.model_dump(mode="json"))
    _json(corpus_path, corpus.model_dump(mode="json"))
    _json(corpus_validation_path, corpus_validation.model_dump(mode="json"))
    _json(split_path, split.model_dump(mode="json"))
    _json(config_path, config.model_dump(mode="json"))

    feature_artifact_root = tmp_path / "feature-release"
    adjudications_path = feature_artifact_root / "label-adjudications.jsonl"
    _write_adjudications(
        adjudications_path,
        artifact_root=artifact_root,
        sessions=sessions,
    )
    adjudications_sha256 = hashlib.sha256(
        adjudications_path.read_bytes()
    ).hexdigest()
    sessions_by_id = {session.base_session_id: session for session in sessions}
    feature_dirs: dict[str, list[Path]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    replay_manifests: dict[tuple[str, str | None], Path] = {}
    release_shards: list[GovernedFeatureReleaseShard] = []
    for assignment in split.assignments:
        session = sessions_by_id[assignment.base_session_id]
        for campaign in (False, True):
            campaign_id = session.campaigns[0].campaign_id if campaign else None
            replay_path = (
                feature_artifact_root
                / "replays"
                / session.base_session_id
                / f"{'campaign' if campaign else 'control'}.json"
            )
            _write_replay_manifest(
                replay_path,
                artifact_root=artifact_root,
                session=session,
                campaign=campaign,
            )
            replay_manifests[(session.base_session_id, campaign_id)] = replay_path
            replay_sha256 = hashlib.sha256(replay_path.read_bytes()).hexdigest()
            output = (
                feature_artifact_root
                / "features"
                / assignment.fold
                / session.base_session_id
                / ("campaign" if campaign else "control")
            )
            _write_feature_bundle(
                output,
                session=session,
                protocol=protocol,
                corpus_hash=corpus.corpus_hash(),
                config=config,
                campaign=campaign,
                artifact_root=artifact_root,
                adjudications_sha256=adjudications_sha256,
                replay_manifest_sha256=replay_sha256,
            )
            feature_dirs[assignment.fold].append(output)
            release_shards.append(
                GovernedFeatureReleaseShard(
                    fold=assignment.fold,
                    base_session_id=session.base_session_id,
                    campaign_id=campaign_id,
                    run_id=(
                        f"{session.base_session_id}-"
                        f"{'campaign' if campaign else 'control'}"
                    ),
                    replay_manifest=artifact_digest(
                        replay_path,
                        root=feature_artifact_root,
                        logical_name=(
                            f"{session.base_session_id}-"
                            f"{'campaign' if campaign else 'control'}-replay"
                        ),
                        schema_version="canonical_java_replay_bundle_v1",
                    ),
                    run_metadata=artifact_digest(
                        output / "run-metadata.json",
                        root=feature_artifact_root,
                        logical_name=(
                            f"{session.base_session_id}-"
                            f"{'campaign' if campaign else 'control'}-metadata"
                        ),
                        schema_version="feature_run_metadata_v1",
                    ),
                    features=artifact_digest(
                        output / "features.parquet",
                        root=feature_artifact_root,
                        logical_name=(
                            f"{session.base_session_id}-"
                            f"{'campaign' if campaign else 'control'}-features"
                        ),
                        schema_version=config.schema_version,
                    ),
                    quality=artifact_digest(
                        output / "feature-quality.json",
                        root=feature_artifact_root,
                        logical_name=(
                            f"{session.base_session_id}-"
                            f"{'campaign' if campaign else 'control'}-quality"
                        ),
                        schema_version="feature_quality_report_v1",
                    ),
                )
            )
    release = GovernedFeatureReleaseManifest(
        release_id="phase1-feature-release",
        created_at=GENERATED_AT,
        protocol_id=protocol.protocol_id,
        protocol_hash=protocol.protocol_hash(),
        corpus_id=corpus.corpus_id,
        corpus_hash=corpus.corpus_hash(),
        split_id=split.split_id,
        assignment_hash=split.assignment_hash,
        feature_schema_version=config.schema_version,
        feature_config_hash=config.config_hash(),
        adjudications=artifact_digest(
            adjudications_path,
            root=feature_artifact_root,
            logical_name="clean-window-adjudications",
            schema_version="clean_window_adjudications_jsonl_v1",
        ),
        shards=tuple(release_shards),
    )
    release_path = feature_artifact_root / "governed-feature-release.json"
    release_sha256 = write_governed_feature_release(release_path, release)
    return GovernedFixture(
        protocol=protocol_path,
        corpus=corpus_path,
        corpus_validation=corpus_validation_path,
        split=split_path,
        feature_config=config_path,
        artifact_root=artifact_root,
        feature_artifact_root=feature_artifact_root,
        feature_release=release_path,
        feature_release_sha256=release_sha256,
        feature_dirs={name: tuple(paths) for name, paths in feature_dirs.items()},
        replay_manifests=replay_manifests,
    )


def _load(
    fixture: GovernedFixture,
    *,
    access_mode: str = "development",
    feature_release_sha256: str | None = None,
):
    return load_governed_feature_dataset(
        protocol_path=fixture.protocol,
        corpus_manifest_path=fixture.corpus,
        corpus_validation_path=fixture.corpus_validation,
        split_manifest_path=fixture.split,
        feature_config_path=fixture.feature_config,
        feature_release_manifest_path=fixture.feature_release,
        expected_feature_release_sha256=(
            feature_release_sha256 or fixture.feature_release_sha256
        ),
        feature_artifact_root=fixture.feature_artifact_root,
        corpus_artifact_root=fixture.artifact_root,
        access_mode=access_mode,
    )


def _rewrite_feature(
    fixture: GovernedFixture,
    directory: Path,
    transform,
) -> str:
    feature_path = directory / "features.parquet"
    table = pq.read_table(feature_path)
    changed = transform(table)
    pq.write_table(changed, feature_path, compression="zstd")
    metadata_path = directory / "run-metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    payload = feature_path.read_bytes()
    metadata["output"]["feature_file_sha256"] = hashlib.sha256(payload).hexdigest()
    metadata["output"]["feature_file_size_bytes"] = len(payload)
    _json(metadata_path, metadata)
    release = json.loads(fixture.feature_release.read_text(encoding="utf-8"))
    feature_uri = feature_path.relative_to(fixture.feature_artifact_root).as_posix()
    metadata_uri = metadata_path.relative_to(
        fixture.feature_artifact_root
    ).as_posix()
    matches = [
        shard
        for shard in release["shards"]
        if shard["features"]["uri"] == feature_uri
    ]
    assert len(matches) == 1
    shard = matches[0]
    shard["features"]["sha256"] = hashlib.sha256(
        feature_path.read_bytes()
    ).hexdigest()
    shard["features"]["size_bytes"] = feature_path.stat().st_size
    shard["run_metadata"]["uri"] = metadata_uri
    shard["run_metadata"]["sha256"] = hashlib.sha256(
        metadata_path.read_bytes()
    ).hexdigest()
    shard["run_metadata"]["size_bytes"] = metadata_path.stat().st_size
    _json(fixture.feature_release, release)
    return hashlib.sha256(fixture.feature_release.read_bytes()).hexdigest()


def _rewrite_release(
    fixture: GovernedFixture,
    transform,
) -> str:
    release = json.loads(fixture.feature_release.read_text(encoding="utf-8"))
    transform(release)
    _json(fixture.feature_release, release)
    return hashlib.sha256(fixture.feature_release.read_bytes()).hexdigest()


def _refresh_release_artifact(
    fixture: GovernedFixture,
    path: Path,
) -> str:
    uri = path.relative_to(fixture.feature_artifact_root).as_posix()
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    size = path.stat().st_size

    def refresh(release: dict[str, object]) -> None:
        artifacts = [release["adjudications"]]
        artifacts.extend(
            artifact
            for shard in release["shards"]
            for artifact in (
                shard["replay_manifest"],
                shard["run_metadata"],
                shard["features"],
                shard["quality"],
            )
        )
        matches = [artifact for artifact in artifacts if artifact["uri"] == uri]
        assert len(matches) == 1
        matches[0]["sha256"] = digest
        matches[0]["size_bytes"] = size

    return _rewrite_release(fixture, refresh)


def test_governed_loader_exposes_only_supervised_development_rows(
    governed_fixture: GovernedFixture,
) -> None:
    dataset = _load(governed_fixture)

    assert dataset.access_mode == "development"
    assert dataset.feature_release_id == "phase1-feature-release"
    assert dataset.feature_release_sha256 == governed_fixture.feature_release_sha256
    assert [fold.fold for fold in dataset.folds] == ["train", "validation"]
    assert dataset.ordered_feature_columns == FEATURE_COLUMNS
    for fold in dataset.folds:
        assert fold.session_count == 1
        assert fold.row_count == 2
        assert fold.positive_row_count == 1
        assert fold.negative_row_count == 1
        labels = [
            label
            for batch in fold.iter_supervised_batches(batch_size=1)
            for label in batch.column(batch.schema.get_field_index("label")).to_pylist()
        ]
        assert sorted(labels) == [0, 1]
        assert sum(shard.unlabeled_row_count for shard in fold.shards) == 2


def test_test_fold_requires_explicit_final_test_access(
    governed_fixture: GovernedFixture,
) -> None:
    dataset = _load(governed_fixture, access_mode="final_test")
    assert [fold.fold for fold in dataset.folds] == ["test"]
    assert dataset.fold("test").row_count == 2
    with pytest.raises(KeyError, match="not loaded"):
        dataset.fold("train")

    test_feature = (
        governed_fixture.feature_dirs["test"][0] / "features.parquet"
    )
    test_feature.write_bytes(test_feature.read_bytes() + b"tamper")
    assert [fold.fold for fold in _load(governed_fixture).folds] == [
        "train",
        "validation",
    ]
    with pytest.raises(ValueError, match="feature release artifact"):
        _load(governed_fixture, access_mode="final_test")


def test_unknown_access_mode_fails_closed(
    governed_fixture: GovernedFixture,
) -> None:
    with pytest.raises(ValueError, match="unsupported governed feature access mode"):
        _load(governed_fixture, access_mode="all")


def test_float32_release_rejects_a_float64_protocol(
    governed_fixture: GovernedFixture,
) -> None:
    protocol = json.loads(governed_fixture.protocol.read_text(encoding="utf-8"))
    protocol["feature_schema_version"] = "lob_features_v1"
    _json(governed_fixture.protocol, protocol)

    with pytest.raises(ValueError, match="feature schema is incompatible"):
        _load(governed_fixture)


def test_governed_provenance_and_local_corpus_validation_are_exact(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0] / "run-metadata.json"
    metadata = json.loads(target.read_text(encoding="utf-8"))
    metadata["input"]["governed_protocol_sha256"] = "f" * 64
    _json(target, metadata)
    release_sha256 = _refresh_release_artifact(governed_fixture, target)
    with pytest.raises(ValueError, match="governed provenance"):
        _load(
            governed_fixture,
            feature_release_sha256=release_sha256,
        )


def test_feature_artifact_hash_and_schema_tampering_fail_closed(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0]
    feature_path = target / "features.parquet"
    feature_path.write_bytes(feature_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="feature release artifact"):
        _load(governed_fixture)


def test_reordered_feature_columns_fail_closed(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0]
    release_sha256 = _rewrite_feature(
        governed_fixture,
        target,
        lambda table: table.select(list(reversed(table.column_names))),
    )
    with pytest.raises(ValueError, match="Parquet schema"):
        _load(governed_fixture, feature_release_sha256=release_sha256)


def test_invalid_or_wrongly_provenanced_labels_fail_closed(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0]

    def invalidate(table: pa.Table) -> pa.Table:
        rows = table.to_pylist()
        rows[0]["row_valid"] = False
        rows[0]["invalid_reason"] = "tampered"
        return pa.Table.from_pylist(rows, schema=table.schema)

    release_sha256 = _rewrite_feature(
        governed_fixture,
        target,
        invalidate,
    )
    with pytest.raises(ValueError, match="Invalid feature rows|invalid feature rows"):
        _load(governed_fixture, feature_release_sha256=release_sha256)


def test_unlabeled_rows_cannot_smuggle_label_metadata(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0]

    def add_hidden_family(table: pa.Table) -> pa.Table:
        rows = table.to_pylist()
        rows[1]["attack_family"] = "layering_like"
        return pa.Table.from_pylist(rows, schema=table.schema)

    release_sha256 = _rewrite_feature(
        governed_fixture,
        target,
        add_hidden_family,
    )
    with pytest.raises(ValueError, match="does not match governed ground truth"):
        _load(governed_fixture, feature_release_sha256=release_sha256)


def test_campaign_labels_are_reconstructed_from_governed_ground_truth(
    governed_fixture: GovernedFixture,
) -> None:
    target = next(
        path
        for path in governed_fixture.feature_dirs["train"]
        if path.name == "campaign"
    )

    def forge_phase(table: pa.Table) -> pa.Table:
        rows = table.to_pylist()
        rows[0]["attack_phase"] = "forged_phase"
        return pa.Table.from_pylist(rows, schema=table.schema)

    release_sha256 = _rewrite_feature(
        governed_fixture,
        target,
        forge_phase,
    )
    with pytest.raises(ValueError, match="does not match governed ground truth"):
        _load(governed_fixture, feature_release_sha256=release_sha256)


def test_clean_labels_require_the_exact_revalidated_adjudications(
    governed_fixture: GovernedFixture,
) -> None:
    adjudications = (
        governed_fixture.feature_artifact_root / "label-adjudications.jsonl"
    )
    records = [
        json.loads(line)
        for line in adjudications.read_text(encoding="utf-8").splitlines()
    ]
    records[0]["reviewer_decisions"][0]["decision"] = "not_clean"
    adjudications.write_text(
        "".join(json.dumps(record, sort_keys=True) + "\n" for record in records),
        encoding="utf-8",
    )
    release_sha256 = _refresh_release_artifact(
        governed_fixture,
        adjudications,
    )
    with pytest.raises(ValueError, match="unresolved reviewer disagreement"):
        _load(governed_fixture, feature_release_sha256=release_sha256)


def test_feature_units_must_match_the_frozen_canonical_replay(
    governed_fixture: GovernedFixture,
) -> None:
    target = next(
        path
        for path in governed_fixture.feature_dirs["train"]
        if path.name == "control"
    )
    base_session_id = target.parent.name
    replay_path = governed_fixture.replay_manifests[
        (base_session_id, None)
    ]
    replay = json.loads(replay_path.read_text(encoding="utf-8"))
    replay["price_tick_size"] = 0.02
    _json(replay_path, replay)
    release_sha256 = _refresh_release_artifact(
        governed_fixture,
        replay_path,
    )
    with pytest.raises(ValueError, match="market units"):
        _load(governed_fixture, feature_release_sha256=release_sha256)


def test_feature_release_requires_an_external_frozen_hash(
    governed_fixture: GovernedFixture,
) -> None:
    release = json.loads(
        governed_fixture.feature_release.read_text(encoding="utf-8")
    )
    release["release_id"] = "untrusted-replacement"
    _json(governed_fixture.feature_release, release)
    with pytest.raises(ValueError, match="external SHA-256"):
        _load(governed_fixture)


def test_complete_fold_inventory_and_unique_runs_are_required(
    governed_fixture: GovernedFixture,
) -> None:
    release_sha256 = _rewrite_release(
        governed_fixture,
        lambda release: release["shards"].pop(),
    )
    with pytest.raises(ValueError, match="exactly inventory"):
        _load(governed_fixture, feature_release_sha256=release_sha256)


def test_ml_dependency_group_is_declared_for_training_jobs() -> None:
    project = tomllib.loads((ROOT / "backend" / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = project["project"]["optional-dependencies"]["ml"]
    lock = tomllib.loads((ROOT / "backend" / "uv.lock").read_text(encoding="utf-8"))
    locked = {package["name"]: package["version"] for package in lock["package"]}

    assert any(item.startswith("lightgbm>=4.6.0") for item in dependencies)
    assert "mlflow-skinny==3.13.0" in dependencies
    assert any(item.startswith("scikit-learn>=1.7.2") for item in dependencies)
    assert tuple(map(int, locked["lightgbm"].split("."))) >= (4, 6, 0)
    assert locked["mlflow-skinny"] == "3.13.0"
    assert tuple(map(int, locked["scikit-learn"].split("."))) >= (1, 7, 2)


def test_governed_loader_is_part_of_the_lightgbm_public_boundary() -> None:
    assert (
        lightgbm_boundary.load_governed_feature_dataset
        is load_governed_feature_dataset
    )
    assert "load_governed_feature_dataset" in lightgbm_boundary.__all__
    assert (
        lightgbm_boundary.GovernedFeatureReleaseManifest
        is GovernedFeatureReleaseManifest
    )
    assert "GovernedFeatureReleaseManifest" in lightgbm_boundary.__all__
