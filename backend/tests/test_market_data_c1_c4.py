from __future__ import annotations

import hashlib
import json
import struct
from argparse import Namespace
from datetime import UTC, date, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.data_ingestion import itch
from app.market_data.acquisition import (
    AcquisitionCampaignState,
    NasdaqAcquisitionRequest,
    QuarantineLifecycleEvidence,
)
from app.market_data.preparation import NasdaqPreparationRequest
from app.market_data.public_sample import EXPECTED_SOURCES, load_source_config
from app.market_data.projections import (
    EXPECTED_SOURCE_DATES,
    FrozenPublicSampleRoot,
    FrozenSourceBinding,
    EXPECTED_SOURCE_FILES,
    TabularProjectionManifest,
    TabularProjectionShard,
    SequenceProjectionManifest,
    materialize_sequence_shard,
    materialize_tabular_shard,
    supervised_row_id,
    verify_sequence_projection,
    verify_tabular_projection,
    write_manifest,
)
from app.ml.lightgbm.contracts import ArtifactDigest
from app.features.io import feature_arrow_schema
from scripts.market_data_wave1 import prepare_acquisition
from scripts.submit_market_data_stage_job import (
    _job_command,
    _verify_submission_gate,
    _validate_arguments,
    main as submit_stage_job,
)


def test_acquisition_campaign_is_strictly_sequential_and_stops_on_failure() -> None:
    ordered = tuple(EXPECTED_SOURCES)
    state = AcquisitionCampaignState(ordered_filenames=ordered)

    assert state.next_filename() == ordered[0]
    state = state.record(ordered[0], succeeded=True)
    assert state.next_filename() == ordered[1]
    with pytest.raises(ValueError, match="out of sequence"):
        state.record(ordered[2], succeeded=True)

    state = state.record(ordered[1], succeeded=False)
    assert state.stopped is True
    assert state.jobs_consumed == 2
    with pytest.raises(ValueError, match="no authorized next source"):
        state.next_filename()


def test_acquisition_request_staging_binds_lifecycle_and_first_source(
    tmp_path: Path,
) -> None:
    lifecycle = QuarantineLifecycleEvidence(
        bucket_id="storagebucket-e001935725601413893009",
        bucket_resource_version="19",
        prefix="data/public-sample-v1/quarantine/nasdaq/",
        observed_at=datetime.now(UTC),
        policy_sha256="a" * 64,
    )
    lifecycle_path = tmp_path / "lifecycle.json"
    lifecycle_path.write_text(lifecycle.model_dump_json(), encoding="utf-8")
    package = tmp_path / "package"
    evidence = tmp_path / "package-evidence.json"

    prepare_acquisition(
        run_id="nasdaq-acquire-pilot",
        image=f"cr.eu-north1.nebius.cloud/example/market-data@sha256:{'b' * 64}",
        filename="01302019.NASDAQ_ITCH50.gz",
        sequence_number=1,
        lifecycle_evidence=lifecycle_path,
        source_config=Path(__file__).resolve().parents[2]
        / "configs/data/nasdaq-public-sample-v1.json",
        package=package,
        evidence_output=evidence,
    )

    request = NasdaqAcquisitionRequest.model_validate_json(
        (package / "request.json").read_text(encoding="utf-8")
    )
    assert request.sequence_number == 1
    assert request.source.filename == "01302019.NASDAQ_ITCH50.gz"
    assert request.lifecycle == lifecycle
    assert request.max_download_bytes == 4_764_426_091


def test_stage_submission_does_not_require_spend_reconciliation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "NEBIUS_VOLUME",
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID",
        "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    args = Namespace(
        subnet_id="subnet-test",
        name="nasdaq-c2-test",
        data_prep_spend_usd=None,
        data_prep_jobs_consumed=2,
    )

    _validate_arguments(args)

    args.data_prep_spend_usd = -1
    with pytest.raises(SystemExit, match="finite and non-negative"):
        _validate_arguments(args)


def test_stage_dry_run_stdout_does_not_include_secret_selectors(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    for name in (
        "NEBIUS_VOLUME",
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID",
        "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    lifecycle = QuarantineLifecycleEvidence(
        bucket_id="storagebucket-e001935725601413893009",
        bucket_resource_version="19",
        prefix="data/public-sample-v1/quarantine/nasdaq/",
        observed_at=datetime.now(UTC),
        policy_sha256="a" * 64,
    )
    lifecycle_path = tmp_path / "lifecycle.json"
    lifecycle_path.write_text(lifecycle.model_dump_json(), encoding="utf-8")
    package_evidence = tmp_path / "package-evidence.json"
    image = f"cr.eu-north1.nebius.cloud/example/market-data@sha256:{'b' * 64}"
    prepare_acquisition(
        run_id="nasdaq-stage-dry-run",
        image=image,
        filename="01302019.NASDAQ_ITCH50.gz",
        sequence_number=1,
        lifecycle_evidence=lifecycle_path,
        source_config=Path(__file__).resolve().parents[2]
        / "configs/data/nasdaq-public-sample-v1.json",
        package=tmp_path / "package",
        evidence_output=package_evidence,
    )
    package = json.loads(package_evidence.read_text(encoding="utf-8"))
    dry_run = tmp_path / "dry-run.json"

    assert (
        submit_stage_job(
            [
                "--image",
                image,
                "--name",
                "nasdaq-stage-dry-run",
                "--subnet-id",
                "subnet-test",
                "--input-uri",
                package["destination"],
                "--request-evidence",
                str(package_evidence),
                "--access-key-secret-id",
                "access-selector-must-not-leak",
                "--secret-key-secret-id",
                "secret-selector-must-not-leak",
                "--data-prep-jobs-consumed",
                "0",
                "--evidence-output",
                str(dry_run),
                "--dry-run",
            ]
        )
        == 0
    )
    output = capsys.readouterr().out
    payload = json.loads(dry_run.read_text(encoding="utf-8"))

    assert output == (
        "Market-data stage dry-run evidence written; review the evidence file before submission.\n"
    )
    assert "access-selector-must-not-leak" not in output
    assert "secret-selector-must-not-leak" not in output
    assert "AWS_ACCESS_KEY_ID=[MYSTERYBOX_SELECTOR]" in payload["command"]
    assert "AWS_SECRET_ACCESS_KEY=[MYSTERYBOX_SELECTOR]" in payload["command"]


def test_resume_submission_keeps_publication_and_job_approvals_distinct(
    tmp_path: Path,
) -> None:
    class RequestStub:
        @staticmethod
        def canonical_hash() -> str:
            return "a" * 64

    package = {"package_inventory_sha256": "b" * 64}
    publication = tmp_path / "publication.json"
    publication.write_text(
        json.dumps(
            {
                "schema_version": "market_data_wave1_request_publication_v1",
                "approval_reference": "canary-publication-approval",
                "destination": "s3://example/request",
                "request_sha256": "a" * 64,
                "package_inventory_sha256": "b" * 64,
            }
        ),
        encoding="utf-8",
    )
    common = {"operation": "preparation", "registry_verification": None}
    reviewed = tmp_path / "reviewed.json"
    reviewed.write_text(
        json.dumps(
            {
                "schema_version": "market_data_wave1_stage_dry_run_v1",
                **common,
            }
        ),
        encoding="utf-8",
    )
    reviewed_sha = hashlib.sha256(reviewed.read_bytes()).hexdigest()
    args = Namespace(
        approval_reference="full-resume-approval",
        publication_evidence=publication,
        reviewed_dry_run=reviewed,
        reviewed_dry_run_sha256=reviewed_sha,
        input_uri="s3://example/request",
    )

    assert _verify_submission_gate(args, RequestStub(), package, common) == (
        reviewed_sha,
        "canary-publication-approval",
    )

    payload = json.loads(publication.read_text(encoding="utf-8"))
    payload["approval_reference"] = "bad"
    publication.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SystemExit, match="lacks a valid approval reference"):
        _verify_submission_gate(args, RequestStub(), package, common)


def test_stage_submitter_selects_split_entrypoint_by_request_type() -> None:
    source = load_source_config(
        Path(__file__).resolve().parents[2] / "configs/data/nasdaq-public-sample-v1.json"
    ).sources[0]
    image = f"cr.eu-north1.nebius.cloud/example/mda@sha256:{'b' * 64}"
    run_id = "nasdaq-split-entrypoint"
    common = {
        "run_id": run_id,
        "sequence_number": 1,
        "image": image,
        "git_commit": "a" * 40,
        "created_at": datetime.now(UTC),
        "source": source,
    }
    acquisition = NasdaqAcquisitionRequest(
        **common,
        lifecycle=QuarantineLifecycleEvidence(
            bucket_id="storagebucket-e001935725601413893009",
            bucket_resource_version="20",
            prefix="data/public-sample-v1/quarantine/nasdaq/",
            observed_at=datetime.now(UTC),
            policy_sha256="c" * 64,
        ),
        quarantine_uri=(
            "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
            f"quarantine/nasdaq/{source.date.isoformat()}/{run_id}"
        ),
        max_download_bytes=source.expected_content_length,
    )
    preparation = NasdaqPreparationRequest(
        **common,
        source_release_uri=(
            "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
            f"quarantine/nasdaq/{source.date.isoformat()}/nasdaq-source-release"
        ),
        source_release_manifest_sha256="d" * 64,
        result_uri=(
            "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
            f"prepared/{source.date.isoformat()}/{run_id}"
        ),
        checkpoint_uri=(
            "s3://aimada-wave1-dev-e00g6zvxpr00/data/public-sample-v1/"
            f"preparation-checkpoints/{source.date.isoformat()}/{run_id}"
        ),
        feature_config_sha256="e" * 64,
    )
    args = Namespace(
        image=image,
        input_uri="s3://example/input",
        name="nasdaq-split-entrypoint",
        subnet_id="vpcsubnet-example",
        access_key_secret_id="mbsec-access",
        secret_key_secret_id="mbsec-secret",
        max_new_comparisons=1,
    )

    acquisition_command = _job_command(args, acquisition, "registry/mda:short")
    preparation_command = _job_command(args, preparation, "registry/mdp:short")
    acquisition_args = acquisition_command[acquisition_command.index("--args") + 1]
    preparation_args = preparation_command[preparation_command.index("--args") + 1]

    assert "/job/serverless/jobs/run_market_data_acquisition.py acquire-s3" in acquisition_args
    assert "/job/serverless/jobs/run_market_data_preparation.py prepare-s3" in preparation_args
    assert "--max-new-comparisons 1" in preparation_args
    assert "--max-new-comparisons" not in acquisition_args
    assert "run_market_data_wave1.py" not in acquisition_args
    assert "run_market_data_wave1.py" not in preparation_args
    assert acquisition_command[acquisition_command.index("--preset") + 1] == "4vcpu-16gb"
    assert acquisition_command[acquisition_command.index("--disk-size") + 1] == "100Gi"
    assert acquisition_command[acquisition_command.index("--timeout") + 1] == "4h"
    assert preparation_command[preparation_command.index("--preset") + 1] == "8vcpu-32gb"
    assert preparation_command[preparation_command.index("--disk-size") + 1] == "250Gi"
    assert preparation_command[preparation_command.index("--timeout") + 1] == "16h"


def test_one_pass_normalizer_extracts_three_symbols_with_one_stream_scan(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    source = tmp_path / "01302019.NASDAQ_ITCH50"
    _write_three_symbol_itch(source)
    calls = 0
    original = itch.iter_records

    def counted(path: Path):
        nonlocal calls
        calls += 1
        yield from original(path)

    monkeypatch.setattr(itch, "iter_records", counted)
    manifests = itch.convert_itch_symbols(
        source,
        tmp_path / "registry",
        symbols=("AAPL", "MSFT", "NVDA"),
        trade_date="2019-01-30",
        start_time_ms=36_000_000,
        end_time_ms=37_800_000,
        min_free_bytes=0,
        max_working_bytes=1024 * 1024 * 1024,
    )

    assert calls == 1
    assert tuple(manifests) == ("AAPL", "MSFT", "NVDA")
    assert len({item.parser_config_sha256 for item in manifests.values()}) == 1
    for symbol, manifest in manifests.items():
        dataset = tmp_path / "registry" / manifest.dataset_id
        assert manifest.source_type == "nasdaq_itch"
        assert manifest.filters["symbols_normalized_in_one_pass"] == ["AAPL", "MSFT", "NVDA"]
        assert manifest.row_count == 2
        assert pq.read_table(dataset / "events.parquet").column("symbol").to_pylist() == [
            symbol,
            symbol,
        ]


def test_one_pass_normalizer_is_byte_deterministic(tmp_path: Path) -> None:
    source = tmp_path / "01302019.NASDAQ_ITCH50"
    _write_three_symbol_itch(source)
    runs = []
    for name in ("first", "second"):
        runs.append(
            itch.convert_itch_symbols(
                source,
                tmp_path / name,
                symbols=("AAPL", "MSFT", "NVDA"),
                trade_date="2019-01-30",
                start_time_ms=36_000_000,
                end_time_ms=37_800_000,
                min_free_bytes=0,
                max_working_bytes=1024 * 1024 * 1024,
            )
        )
    for symbol in ("AAPL", "MSFT", "NVDA"):
        assert runs[0][symbol].dataset_id == runs[1][symbol].dataset_id
        for filename in ("events.parquet", "book_snapshots.parquet", "manifest.json"):
            first = tmp_path / "first" / runs[0][symbol].dataset_id / filename
            second = tmp_path / "second" / runs[1][symbol].dataset_id / filename
            assert first.read_bytes() == second.read_bytes()


def test_feature_metadata_preserves_nasdaq_and_hybrid_base_source() -> None:
    from app.features.models import FeatureRunMetadata

    common = {
        "run_id": "run",
        "dataset_id": "dataset",
        "instrument": "AAPL",
        "venue": "XNAS",
        "session_id": "session",
        "session_date": "2019-01-30",
        "price_tick_size": 0.0001,
        "quantity_lot_size": 1.0,
    }
    control = FeatureRunMetadata(source_type="nasdaq_itch", **common)
    hybrid = FeatureRunMetadata(
        source_type="hybrid", historical_source_type="nasdaq_itch", **common
    )

    assert control.historical_source_type == "nasdaq_itch"
    assert hybrid.historical_source_type == "nasdaq_itch"
    with pytest.raises(ValueError, match="cannot claim"):
        FeatureRunMetadata(
            source_type="synthetic", historical_source_type="nasdaq_itch", **common
        )


def test_development_projection_verifies_without_any_test_artifact(tmp_path: Path) -> None:
    root = _frozen_root()
    artifact_root = tmp_path / "development"
    artifact_root.mkdir()
    rows_path = artifact_root / "train.parquet"
    rows = []
    identity = hashlib.sha256()
    for sequence, label in ((1, 0), (2, 1)):
        row_id = supervised_row_id(
            root_sha256=root.canonical_hash(),
            assignment_sha256=root.assignment_sha256,
            replay_sha256="8" * 64,
            run_id="train-run",
            sequence=sequence,
            timestamp_ns=sequence * 100,
        )
        identity.update((row_id + "\n").encode())
        rows.append(
            {
                "supervised_row_id": row_id,
                "label": label,
                "label_source": (
                    "research_control_assumption" if label == 0 else "synthetic_scenario"
                ),
                "prediction_timestamp_ns": sequence * 100,
                "sequence": sequence,
            }
        )
    pq.write_table(pa.Table.from_pylist(rows), rows_path)
    artifact = ArtifactDigest(
        logical_name="train_rows",
        uri="train.parquet",
        sha256=hashlib.sha256(rows_path.read_bytes()).hexdigest(),
        size_bytes=rows_path.stat().st_size,
        schema_version="tabular_projection_rows_v1",
    )
    train = TabularProjectionShard(
        fold="train",
        base_session_id="train-session",
        run_id="train-run",
        replay_manifest_sha256="8" * 64,
        rows=artifact,
        supervised_row_count=2,
        row_identity_sha256=identity.hexdigest(),
    )
    validation = train.model_copy(
        update={
            "fold": "validation",
            "base_session_id": "validation-session",
            "run_id": "validation-run",
        }
    )
    # Give validation its own file and row binding; no test object is present.
    validation_path = artifact_root / "validation.parquet"
    validation_rows = []
    validation_identity = hashlib.sha256()
    for sequence, label in ((1, 0), (2, 1)):
        row_id = supervised_row_id(
            root_sha256=root.canonical_hash(),
            assignment_sha256=root.assignment_sha256,
            replay_sha256="8" * 64,
            run_id="validation-run",
            sequence=sequence,
            timestamp_ns=sequence * 100,
        )
        validation_identity.update((row_id + "\n").encode())
        validation_rows.append({**rows[sequence - 1], "supervised_row_id": row_id})
    pq.write_table(pa.Table.from_pylist(validation_rows), validation_path)
    validation_artifact = ArtifactDigest(
        logical_name="validation_rows",
        uri="validation.parquet",
        sha256=hashlib.sha256(validation_path.read_bytes()).hexdigest(),
        size_bytes=validation_path.stat().st_size,
        schema_version="tabular_projection_rows_v1",
    )
    validation = validation.model_copy(
        update={
            "rows": validation_artifact,
            "row_identity_sha256": validation_identity.hexdigest(),
        }
    )
    manifest = TabularProjectionManifest(
        projection_id="nasdaq-development-v1",
        access_scope="development",
        root_release_id=root.release_id,
        root_sha256=root.canonical_hash(),
        protocol_sha256=root.protocol_sha256,
        corpus_sha256=root.corpus_sha256,
        assignment_sha256=root.assignment_sha256,
        feature_release_sha256=root.feature_release_sha256,
        folds=("train", "validation"),
        shards=(train, validation),
    )
    manifest_path = tmp_path / "projection.json"
    digest = write_manifest(manifest_path, manifest)

    loaded = verify_tabular_projection(
        manifest_path,
        expected_sha256=digest,
        root=root,
        artifact_root=artifact_root,
    )

    assert loaded.folds == ("train", "validation")
    assert not (artifact_root / "test.parquet").exists()


def test_projection_scope_rejects_test_in_development() -> None:
    artifact = ArtifactDigest(
        logical_name="rows",
        uri="rows.parquet",
        sha256="6" * 64,
        size_bytes=1,
        schema_version="tabular_projection_rows_v1",
    )
    shard = TabularProjectionShard(
        fold="train",
        base_session_id="session",
        run_id="run",
        replay_manifest_sha256="7" * 64,
        rows=artifact,
        supervised_row_count=1,
        row_identity_sha256="8" * 64,
    )
    with pytest.raises(ValueError, match="development projection"):
        TabularProjectionManifest(
            projection_id="bad",
            access_scope="development",
            root_release_id="root",
            root_sha256="1" * 64,
            protocol_sha256="2" * 64,
            corpus_sha256="3" * 64,
            assignment_sha256="4" * 64,
            feature_release_sha256="5" * 64,
            folds=("train", "validation", "test"),
            shards=(shard,),
        )


def test_c4_materializers_emit_bound_tabular_and_causal_sequence_rows(
    tmp_path: Path,
) -> None:
    root = _frozen_root()
    schema = feature_arrow_schema("b" * 64)
    source = tmp_path / "features.parquet"
    rows = []
    for sequence, label in ((1, 0), (2, 1), (3, 0)):
        row = _feature_row(schema, sequence=sequence, label=label)
        rows.append(row)
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), source)
    artifact_root = tmp_path / "projection"
    tabular = materialize_tabular_shard(
        source,
        artifact_root / "tabular/train.parquet",
        artifact_root=artifact_root,
        root_sha256=root.canonical_hash(),
        assignment_sha256=root.assignment_sha256,
        replay_sha256="c" * 64,
        fold="train",
        base_session_id="train-session",
        campaign_id="train-campaign",
        run_id="train-run",
    )
    sequence = materialize_sequence_shard(
        tabular,
        artifact_root / "sequence/train.parquet",
        artifact_root=artifact_root,
        sequence_length=2,
    )
    sequence_manifest = SequenceProjectionManifest(
        projection_id="nasdaq-sequence-final-v1",
        access_scope="final_test",
        root_release_id=root.release_id,
        root_sha256=root.canonical_hash(),
        protocol_sha256=root.protocol_sha256,
        corpus_sha256=root.corpus_sha256,
        assignment_sha256=root.assignment_sha256,
        feature_release_sha256=root.feature_release_sha256,
        folds=("test",),
        shards=(sequence.model_copy(update={"fold": "test"}),),
    )
    manifest_path = tmp_path / "sequence-manifest.json"
    manifest_sha = write_manifest(manifest_path, sequence_manifest)

    verified = verify_sequence_projection(
        manifest_path,
        expected_sha256=manifest_sha,
        root=root,
        artifact_root=artifact_root,
    )

    assert tabular.supervised_row_count == 3
    assert verified.shards[0].sequence_count == 3
    sequence_rows = pq.read_table(artifact_root / "sequence/train.parquet").to_pylist()
    assert sequence_rows[0]["attention_mask"] == [False, True]
    assert sequence_rows[-1]["sequence_timestamps_ns"][-1] == 300


def _frozen_root() -> FrozenPublicSampleRoot:
    folds = ("train", "train", "train", "train", "validation", "test", "test")
    return FrozenPublicSampleRoot(
        release_id="nasdaq-public-sample-root-v1",
        protocol_sha256="1" * 64,
        corpus_id="nasdaq-corpus-v1",
        corpus_sha256="2" * 64,
        split_id="nasdaq-split-v1",
        assignment_sha256="3" * 64,
        feature_release_id="nasdaq-features-v1",
        feature_release_sha256="4" * 64,
        feature_config_sha256="5" * 64,
        source_config_sha256="6" * 64,
        sources=tuple(
            FrozenSourceBinding(
                trade_date=trade_date,
                fold=fold,
                filename=EXPECTED_SOURCE_FILES[index - 1],
                source_sha256="7" * 64,
                source_manifest_sha256="8" * 64,
                preparation_manifest_sha256="9" * 64,
                parser_config_sha256="a" * 64,
            )
            for index, (trade_date, fold) in enumerate(
                zip(EXPECTED_SOURCE_DATES, folds, strict=True), 1
            )
        ),
    )


def _feature_row(schema: pa.Schema, *, sequence: int, label: int) -> dict[str, object]:
    row: dict[str, object] = {}
    for field in schema:
        if pa.types.is_string(field.type):
            row[field.name] = "value"
        elif pa.types.is_date32(field.type):
            row[field.name] = date(2019, 1, 30)
        elif pa.types.is_boolean(field.type):
            row[field.name] = True
        elif pa.types.is_integer(field.type):
            row[field.name] = sequence
        elif pa.types.is_floating(field.type):
            row[field.name] = 1.0
        else:
            raise AssertionError(f"unhandled feature field type: {field}")
    row.update(
        {
            "feature_schema_version": "lob_features_v2",
            "feature_config_hash": "b" * 64,
            "run_id": "train-run",
            "dataset_id": "dataset",
            "source_type": "hybrid",
            "historical_source_type": "nasdaq_itch",
            "instrument": "AAPL",
            "venue": "XNAS",
            "session_id": "session",
            "session_date": date(2019, 1, 30),
            "prediction_timestamp_ns": sequence * 100,
            "sequence": sequence,
            "tick": sequence,
            "split_group": "XNAS/AAPL/2019-01-30/session",
            "row_valid": True,
            "invalid_reason": None,
            "attack_family": None if label == 0 else "spoofing_like_wall",
            "attack_phase": None,
            "label": label,
            "label_source": (
                "research_control_assumption" if label == 0 else "synthetic_scenario"
            ),
        }
    )
    return row


def _write_three_symbol_itch(path: Path) -> None:
    rows: list[bytes] = []
    timestamp = 36_000_000_000_000
    sequence = 0
    for locate, symbol in enumerate(("AAPL", "MSFT", "NVDA"), 1):
        sequence += 1
        rows.append(_itch_message("R", locate, sequence, timestamp + sequence, symbol.encode().ljust(8) + b" " * 20))
    for locate, symbol in enumerate(("AAPL", "MSFT", "NVDA"), 1):
        reference = locate * 100
        sequence += 1
        add = (
            struct.pack(">Q", reference)
            + b"B"
            + struct.pack(">I", 100)
            + symbol.encode().ljust(8)
            + struct.pack(">I", 1_000_000 + locate)
        )
        rows.append(_itch_message("A", locate, sequence, timestamp + sequence, add))
        sequence += 1
        rows.append(
            _itch_message("D", locate, sequence, timestamp + sequence, struct.pack(">Q", reference))
        )
    path.write_bytes(b"".join(struct.pack(">H", len(row)) + row for row in rows))


def _itch_message(
    message_type: str, locate: int, tracking: int, timestamp: int, body: bytes
) -> bytes:
    payload = (
        message_type.encode()
        + struct.pack(">HH", locate, tracking)
        + timestamp.to_bytes(6, "big")
        + body
    )
    assert len(payload) == itch.MESSAGE_LENGTHS[message_type]
    return payload
