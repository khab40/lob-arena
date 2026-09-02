from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from app.corpus.governance import ArtifactReference
from app.data_ingestion.models import DatasetManifest
from app.evaluation.canonical_bundle import CanonicalJavaReplayManifest
from app.market_data.preparation import (
    NasdaqPreparationRequest,
    PreparationPublicationLimits,
    _run_replay_campaign,
)
from app.market_data.preparation_checkpoints import (
    CheckpointRepository,
    ComparisonCheckpoint,
    NormalizedCheckpoint,
    PreparationCheckpointBinding,
    inventory_evidence,
)
from app.nebius import object_storage
from app.nebius.object_storage import (
    TransferLimits,
    publish_local_result,
    read_verified_s3_release_member,
    sha256_file,
)


SHA = "a" * 64


def test_one_of_27_local_canary_publishes_then_resumes_without_recompute(
    tmp_path: Path,
) -> None:
    """The approved 1/27 check is local and proves the expensive unit is resumable."""

    repository = CheckpointRepository(
        (tmp_path / "checkpoints").as_uri(),
        work_root=tmp_path,
        endpoint_url=None,
        limits=TransferLimits(max_files=100, max_bytes=1024 * 1024),
    )
    binding = _binding()
    request = NasdaqPreparationRequest.model_construct(
        publication_limits=PreparationPublicationLimits()
    )
    manifests = {"AAPL": _dataset()}
    export_calls = 0

    def exporter(**kwargs: object) -> tuple[Path, Path, dict[str, object]]:
        nonlocal export_calls
        export_calls += 1
        output_root = Path(kwargs["output_root"])
        control = _write_replay_manifest(output_root / "control", mode="historical_control")
        hybrid = _write_replay_manifest(output_root / "hybrid", mode="hybrid")
        return control, hybrid, {"determinism": {"stream_match": True}}

    def features(_: Path, output: Path) -> None:
        output.mkdir(parents=True)
        (output / "features.parquet").write_bytes(b"fixture-feature")

    first = _run_replay_campaign(
        java_base_url="http://unused",
        staging=_new_directory(tmp_path / "first-attempt"),
        manifests=manifests,
        replay_exporter=exporter,
        feature_generator=features,
        repository=repository,
        binding=binding,
        request=request,
        max_new_comparisons=1,
    )
    assert export_calls == 1
    assert len(first[2]) == 1
    assert (tmp_path / "checkpoints" / "comparisons" / "001-aapl-spoofing-like-wall-s41" / "SUCCESS").is_file()

    second = _run_replay_campaign(
        java_base_url="http://unused",
        staging=_new_directory(tmp_path / "retry"),
        manifests=manifests,
        replay_exporter=lambda **_: pytest.fail("completed shard was recomputed"),
        feature_generator=lambda *_: pytest.fail("completed features were recomputed"),
        repository=repository,
        binding=binding,
        request=request,
        comparison_plan=((1, "AAPL", "spoofing_like_wall", 41),),
    )

    assert export_calls == 1
    assert second == first


def test_resume_rejects_a_checkpoint_from_a_different_request(tmp_path: Path) -> None:
    repository = CheckpointRepository(
        (tmp_path / "checkpoints").as_uri(),
        work_root=tmp_path,
        endpoint_url=None,
        limits=TransferLimits(max_files=100, max_bytes=1024 * 1024),
    )
    request = NasdaqPreparationRequest.model_construct(
        publication_limits=PreparationPublicationLimits()
    )
    plan = ((1, "AAPL", "spoofing_like_wall", 41),)

    _run_replay_campaign(
        java_base_url="http://unused",
        staging=_new_directory(tmp_path / "first"),
        manifests={"AAPL": _dataset()},
        replay_exporter=lambda **kwargs: _fixture_export(Path(kwargs["output_root"])),
        feature_generator=_fixture_features,
        repository=repository,
        binding=_binding(),
        request=request,
        comparison_plan=plan,
    )

    changed = _binding().model_copy(update={"request_sha256": "b" * 64})
    with pytest.raises(ValueError, match="exact preparation request"):
        _run_replay_campaign(
            java_base_url="http://unused",
            staging=_new_directory(tmp_path / "changed-request"),
            manifests={"AAPL": _dataset()},
            replay_exporter=lambda **_: pytest.fail("mismatched checkpoint was recomputed"),
            feature_generator=_fixture_features,
            repository=repository,
            binding=changed,
            request=request,
            comparison_plan=plan,
        )


def test_partial_checkpoint_fails_closed(tmp_path: Path) -> None:
    partial = tmp_path / "checkpoints" / "comparisons" / "001-aapl-spoofing-like-wall-s41"
    partial.mkdir(parents=True)
    (partial / "checkpoint.json").write_text("{}\n", encoding="utf-8")
    repository = CheckpointRepository(
        (tmp_path / "checkpoints").as_uri(),
        work_root=tmp_path,
        endpoint_url=None,
        limits=TransferLimits(max_files=100, max_bytes=1024 * 1024),
    )

    with pytest.raises(ValueError, match="SUCCESS is required"):
        repository.load(
            "comparisons/001-aapl-spoofing-like-wall-s41",
            ComparisonCheckpoint,
        )


def test_normalization_checkpoint_restores_exact_payload(tmp_path: Path) -> None:
    repository = CheckpointRepository(
        (tmp_path / "checkpoints").as_uri(),
        work_root=tmp_path,
        endpoint_url=None,
        limits=TransferLimits(max_files=100, max_bytes=1024 * 1024),
    )
    stage = _new_directory(tmp_path / "normalized-stage")
    dataset_root = stage / "normalized" / "xnas-2019-01-30-aapl"
    dataset_root.mkdir(parents=True)
    (dataset_root / "events.parquet").write_bytes(b"fixture-normalized")
    evidence = inventory_evidence(stage)
    record = NormalizedCheckpoint(
        binding_sha256=_binding().canonical_hash(),
        manifests={"AAPL": _dataset()},
        payload_inventory_sha256=evidence[0],
        payload_file_count=evidence[1],
        payload_size_bytes=evidence[2],
    )
    reference = repository.publish("normalized", stage, record)

    restored_root = tmp_path / "restored"
    restored = repository.restore_normalized(
        restored_root,
        expected_binding_sha256=_binding().canonical_hash(),
    )

    assert restored is not None
    assert restored[1] == reference
    assert (restored_root / "xnas-2019-01-30-aapl" / "events.parquet").read_bytes() == b"fixture-normalized"


def test_s3_resume_probe_verifies_release_metadata_without_payload_download(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stage = _new_directory(tmp_path / "remote-stage")
    (stage / "checkpoint.json").write_text('{"binding":"fixture"}\n', encoding="utf-8")
    (stage / "large-payload.bin").write_bytes(b"not-downloaded")
    release = publish_local_result(stage, (tmp_path / "remote-release").as_uri())
    downloaded: list[str] = []

    def fake_aws_json(_: str, *args: str, **__: object) -> dict[str, object]:
        operation = args[1]
        prefix = "checkpoints/shard/"
        if operation == "list-objects-v2":
            return {
                "Contents": [
                    {
                        "Key": prefix + path.relative_to(release).as_posix(),
                        "Size": path.stat().st_size,
                    }
                    for path in sorted(release.rglob("*"))
                    if path.is_file()
                ],
                "IsTruncated": False,
            }
        key = args[args.index("--key") + 1]
        relative = key.removeprefix(prefix)
        source = release / relative
        if operation == "get-object":
            downloaded.append(relative)
            Path(args[-1]).write_bytes(source.read_bytes())
            return {}
        if operation == "head-object":
            return {
                "ContentLength": source.stat().st_size,
                "Metadata": {"sha256": sha256_file(source)},
            }
        raise AssertionError(f"unexpected operation: {operation}")

    monkeypatch.setattr(object_storage, "_aws_json", fake_aws_json)
    payload = read_verified_s3_release_member(
        "s3://fixture/checkpoints/shard",
        "checkpoint.json",
        endpoint_url="https://storage.example",
        limits=TransferLimits(max_files=10, max_bytes=1024 * 1024),
    )

    assert payload == b'{"binding":"fixture"}\n'
    assert downloaded == ["SUCCESS", "checksums.sha256", "checkpoint.json"]


def _binding() -> PreparationCheckpointBinding:
    return PreparationCheckpointBinding(
        request_sha256="1" * 64,
        source_manifest_sha256="2" * 64,
        source_sha256="3" * 64,
        image=f"cr.eu-north1.nebius.cloud/example/mdp@sha256:{'4' * 64}",
        git_commit="5" * 40,
        feature_config_sha256="6" * 64,
    )


def _dataset() -> DatasetManifest:
    return DatasetManifest(
        dataset_id="xnas-2019-01-30-aapl",
        source_type="nasdaq_itch",
        format="nasdaq_itch_parquet_v1",
        venue="XNAS",
        parser_version="fixture",
        symbol="AAPL",
        trade_date="2019-01-30",
        start_time_ms=36_000_000,
        end_time_ms=37_800_000,
        depth=10,
        row_count=1,
        event_counts={"add": 1},
        imported_at=datetime(2026, 9, 1, tzinfo=UTC),
        source_files=[],
        output_files=[],
        source_stream_sha256="7" * 64,
        parser_config_sha256="8" * 64,
        message_counts={"S": 1},
    )


def _artifact(name: str) -> ArtifactReference:
    return ArtifactReference(
        name=name,
        uri=f"{name}.fixture",
        sha256=SHA,
        size_bytes=1,
        schema_version="fixture_v1",
    )


def _write_replay_manifest(output: Path, *, mode: str) -> Path:
    output.mkdir(parents=True)
    hybrid = mode == "hybrid"
    run_id = "xnas-2019-01-30-aapl-spoofing-like-wall-s41" if hybrid else "xnas-2019-01-30-aapl-control"
    manifest = CanonicalJavaReplayManifest(
        run_id=run_id,
        base_session_id="xnas-2019-01-30-aapl",
        dataset_id="xnas-2019-01-30-aapl",
        mode=mode,
        historical_source_type="nasdaq_itch",
        campaign_id=run_id if hybrid else None,
        attack_family="spoofing_like_wall" if hybrid else None,
        instrument="AAPL",
        venue="XNAS",
        session_id="xnas-2019-01-30-aapl",
        session_date=date(2019, 1, 30),
        seed=41 if hybrid else None,
        price_tick_size=0.0001,
        quantity_lot_size=1.0,
        tick_interval_ns=500_000_000,
        java_engine_version="fixture",
        canonical_event_stream_hash=("b" if hybrid else "a") * 64,
        event_count=1,
        snapshot_count=1,
        alert_count=0,
        label_count=1 if hybrid else 0,
        last_sequence=1,
        first_timestamp_ns=1,
        last_timestamp_ns=1,
        events=_artifact("events"),
        snapshots=_artifact("snapshots"),
        alerts=_artifact("alerts"),
        ground_truth=_artifact("ground-truth") if hybrid else None,
        validation=_artifact("validation"),
    )
    path = output / "manifest.json"
    path.write_text(json.dumps(manifest.model_dump(mode="json"), sort_keys=True), encoding="utf-8")
    return path


def _fixture_export(output: Path) -> tuple[Path, Path, dict[str, object]]:
    return (
        _write_replay_manifest(output / "control", mode="historical_control"),
        _write_replay_manifest(output / "hybrid", mode="hybrid"),
        {"determinism": {"stream_match": True}},
    )


def _fixture_features(_: Path, output: Path) -> None:
    output.mkdir(parents=True)
    (output / "features.parquet").write_bytes(b"fixture-feature")


def _new_directory(path: Path) -> Path:
    path.mkdir()
    return path
