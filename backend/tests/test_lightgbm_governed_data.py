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
    GovernedSession,
    build_corpus_manifest,
    validate_corpus,
)
from app.corpus.models import GovernedBenchmarkProtocol
from app.corpus.splits import generate_split_manifest
from app.features.io import write_feature_run
from app.features.models import FeaturePipelineConfig, FeatureRunMetadata
from app.features.pipeline import (
    FEATURE_COLUMNS,
    FEATURE_SCHEMA_VERSION,
    FeatureRunResult,
    feature_quality_report,
    feature_split_group,
)
from app.ml.lightgbm.data import load_governed_feature_dataset


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
    feature_dirs: dict[str, tuple[Path, ...]]


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
            f"campaign-ground-truth-{index}".encode(),
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
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_config_hash": config.config_hash(),
        "run_id": metadata.run_id,
        "dataset_id": metadata.dataset_id,
        "source_type": metadata.source_type,
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
            "clean_adjudications_sha256": "b" * 64,
            "clean_label_artifact_verification_mode": "local",
            "canonical_java_replay_bundle": "canonical_java_replay_bundle_v1",
            "java_canonical_event_stream_hash": validation_payload["canonical_event_stream_hash"],
            "replay_manifest_sha256": "c" * 64,
        },
    )
    write_feature_run(
        output,
        result=result,
        config=config,
        metadata=metadata,
    )


@pytest.fixture
def governed_fixture(tmp_path: Path) -> GovernedFixture:
    artifact_root = tmp_path / "artifacts"
    protocol = GovernedBenchmarkProtocol(
        protocol_id="lightgbm-phase1-fixture",
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
    config = FeaturePipelineConfig()
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

    sessions_by_id = {session.base_session_id: session for session in sessions}
    feature_dirs: dict[str, list[Path]] = {
        "train": [],
        "validation": [],
        "test": [],
    }
    for assignment in split.assignments:
        session = sessions_by_id[assignment.base_session_id]
        for campaign in (False, True):
            output = (
                tmp_path
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
            )
            feature_dirs[assignment.fold].append(output)
    return GovernedFixture(
        protocol=protocol_path,
        corpus=corpus_path,
        corpus_validation=corpus_validation_path,
        split=split_path,
        feature_config=config_path,
        artifact_root=artifact_root,
        feature_dirs={name: tuple(paths) for name, paths in feature_dirs.items()},
    )


def _load(
    fixture: GovernedFixture,
    *,
    access_mode: str = "development",
    feature_dirs: tuple[Path, ...] | None = None,
):
    selected = (
        (*fixture.feature_dirs["train"], *fixture.feature_dirs["validation"])
        if access_mode == "development"
        else fixture.feature_dirs["test"]
    )
    return load_governed_feature_dataset(
        protocol_path=fixture.protocol,
        corpus_manifest_path=fixture.corpus,
        corpus_validation_path=fixture.corpus_validation,
        split_manifest_path=fixture.split,
        feature_config_path=fixture.feature_config,
        feature_run_dirs=feature_dirs or selected,
        artifact_root=fixture.artifact_root,
        access_mode=access_mode,
    )


def _rewrite_feature(
    directory: Path,
    transform,
) -> None:
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


def test_governed_loader_exposes_only_supervised_development_rows(
    governed_fixture: GovernedFixture,
) -> None:
    dataset = _load(governed_fixture)

    assert dataset.access_mode == "development"
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
    with pytest.raises(ValueError, match="unavailable in this access mode"):
        _load(
            governed_fixture,
            feature_dirs=governed_fixture.feature_dirs["test"],
        )

    dataset = _load(governed_fixture, access_mode="final_test")
    assert [fold.fold for fold in dataset.folds] == ["test"]
    assert dataset.fold("test").row_count == 2
    with pytest.raises(KeyError, match="not loaded"):
        dataset.fold("train")


def test_unknown_access_mode_fails_closed(
    governed_fixture: GovernedFixture,
) -> None:
    with pytest.raises(ValueError, match="unsupported governed feature access mode"):
        _load(governed_fixture, access_mode="all")


def test_governed_provenance_and_local_corpus_validation_are_exact(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0] / "run-metadata.json"
    metadata = json.loads(target.read_text(encoding="utf-8"))
    metadata["input"]["governed_protocol_sha256"] = "f" * 64
    _json(target, metadata)
    with pytest.raises(ValueError, match="governed provenance"):
        _load(governed_fixture)


def test_feature_artifact_hash_and_schema_tampering_fail_closed(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0]
    feature_path = target / "features.parquet"
    feature_path.write_bytes(feature_path.read_bytes() + b"tamper")
    with pytest.raises(ValueError, match="SHA-256 verification"):
        _load(governed_fixture)


def test_reordered_feature_columns_fail_closed(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0]
    _rewrite_feature(
        target,
        lambda table: table.select(list(reversed(table.column_names))),
    )
    with pytest.raises(ValueError, match="Parquet schema"):
        _load(governed_fixture)


def test_invalid_or_wrongly_provenanced_labels_fail_closed(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0]

    def invalidate(table: pa.Table) -> pa.Table:
        rows = table.to_pylist()
        rows[0]["row_valid"] = False
        rows[0]["invalid_reason"] = "tampered"
        return pa.Table.from_pylist(rows, schema=table.schema)

    _rewrite_feature(target, invalidate)
    with pytest.raises(ValueError, match="Invalid feature rows|invalid feature rows"):
        _load(governed_fixture)


def test_unlabeled_rows_cannot_smuggle_label_metadata(
    governed_fixture: GovernedFixture,
) -> None:
    target = governed_fixture.feature_dirs["train"][0]

    def add_hidden_family(table: pa.Table) -> pa.Table:
        rows = table.to_pylist()
        rows[1]["attack_family"] = "layering_like"
        return pa.Table.from_pylist(rows, schema=table.schema)

    _rewrite_feature(target, add_hidden_family)
    with pytest.raises(ValueError, match="unlabeled feature rows"):
        _load(governed_fixture)


def test_complete_fold_inventory_and_unique_runs_are_required(
    governed_fixture: GovernedFixture,
) -> None:
    selected = (
        *governed_fixture.feature_dirs["train"],
        *governed_fixture.feature_dirs["validation"],
    )
    with pytest.raises(ValueError, match="exactly cover"):
        _load(governed_fixture, feature_dirs=selected[:-1])
    with pytest.raises(ValueError, match="directories must be unique"):
        _load(governed_fixture, feature_dirs=(*selected, selected[0]))


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
