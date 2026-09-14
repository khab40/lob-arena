"""Synthetic C4/C3 contract fixtures; never use these as production evidence."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from itertools import product
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from app.corpus.governance import ArtifactReference
from app.evaluation.canonical_bundle import CanonicalJavaReplayManifest, canonical_java_event_stream_hash
from app.exchange.schemas import exchange_event_from_dict
from app.features.io import feature_arrow_schema
from app.features.pipeline import FEATURE_SCHEMA_V2
from app.market_data.preparation import PreparationManifest
from app.market_data.preparation_checkpoints import CheckpointReference, ComparisonCheckpoint, inventory_evidence
from app.market_data.projections import (
    C4MlflowDatasetReleaseReceipt,
    FrozenPublicSampleRoot,
    TabularProjectionManifest,
    materialize_tabular_shard,
    write_manifest,
)
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.c4_replay_evidence import C4CheckpointLocation, C4ComparisonPackage
from app.ml.lightgbm.cloud_contracts import CloudArtifact
from app.ml.lightgbm.cloud_fixture import _row, fixture_hash
from app.nebius.object_storage import publish_local_result

SYMBOLS = ("AAPL", "MSFT", "NVDA")
FAMILIES = ("spoofing_like_wall", "layering_like", "quote_stuffing")
SEEDS = (41, 42, 43)
DAY = date(2019, 12, 30)


def _reference(path: Path) -> ArtifactReference:
    return ArtifactReference(
        name=path.name,
        uri=path.name,
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
        schema_version="synthetic_fixture_v1",
    )


def _json(path: Path, value) -> ArtifactReference:
    path.write_text(json.dumps(value, sort_keys=True) + "\n")
    return _reference(path)


def _replay(directory: Path, symbol: str, family: str | None, seed: int | None):
    directory.mkdir(parents=True)
    session = f"xnas-{DAY}-{symbol.lower()}"
    run_id = session + (f"-{family}-s{seed}" if family else "-control")
    campaign = run_id + "-campaign" if family else None
    rows = []
    events = []
    for index in range(6 if family else 12):
        row = _row(
            run_id=run_id, base_session_id=session, label=int(family is not None), index=index, day=5, family=family
        )
        row.update(
            instrument=symbol,
            venue="XNAS",
            session_id="regular",
            session_date=DAY,
            source_type="hybrid" if family else "nasdaq_itch",
            seed=seed,
            label_source="synthetic_scenario" if family else "research_control_assumption",
        )
        rows.append(row)
        events.append(
            dict(
                schema_version=1,
                event_type="snapshot",
                event_id=run_id + f"-{index}",
                sequence=row["sequence"],
                source="simulation",
                source_sequence=row["sequence"],
                symbol=symbol,
                venue="XNAS",
                tick=row["tick"],
                exchange_timestamp_ns=row["prediction_timestamp_ns"],
                received_timestamp_ns=row["prediction_timestamp_ns"],
                depth=1,
                book=dict(
                    bids=[dict(price=99.0, quantity=10.0)],
                    asks=[dict(price=101.0, quantity=10.0)],
                    best_bid=99.0,
                    best_ask=101.0,
                    mid=100.0,
                    spread=2.0,
                ),
            )
        )
    event_path = directory / "events.jsonl"
    event_path.write_text("".join(json.dumps(event, sort_keys=True) + "\n" for event in events))
    stream_hash = canonical_java_event_stream_hash(
        [exchange_event_from_dict(event) for event in events],
        price_tick_size=0.01,
        quantity_lot_size=1.0,
    )
    snapshots = directory / "snapshots.parquet"
    pq.write_table(pa.Table.from_pylist([dict(tick=row["tick"]) for row in rows]), snapshots)
    # Predetermined synthetic Java-format alerts, not regenerated from predictions.
    alerts = [
        dict(run_id=run_id, campaign_id=campaign, detector="fixture_rules", tick=tick)
        for tick in ((2, 4, 6) if family else (3,))
    ]
    alerts_path = directory / "alerts.jsonl"
    alerts_path.write_text("".join(json.dumps(alert) + "\n" for alert in alerts))
    labels = None
    if family:
        labels = _json(
            directory / "labels.jsonl",
            dict(
                run_id=run_id,
                campaign_id=campaign,
                ground_truth=dict(
                    scenario_family=family, start_tick=1, end_tick=len(rows), source="synthetic_scenario"
                ),
            ),
        )
    validation = _json(
        directory / "validation.json",
        dict(
            verdict="pass",
            run_id=run_id,
            base_session_id=session,
            canonical_event_stream_hash=stream_hash,
        ),
    )
    replay = CanonicalJavaReplayManifest(
        run_id=run_id,
        base_session_id=session,
        dataset_id=f"dataset-{session}",
        mode="hybrid" if family else "historical_control",
        historical_source_type="nasdaq_itch",
        campaign_id=campaign,
        attack_family=family,
        instrument=symbol,
        venue="XNAS",
        session_id="regular",
        session_date=DAY,
        seed=seed,
        price_tick_size=0.01,
        quantity_lot_size=1.0,
        tick_interval_ns=1,
        java_engine_version="synthetic-contract-fixture-not-a-java-performance-run",
        canonical_event_stream_hash=stream_hash,
        event_count=len(events),
        snapshot_count=len(rows),
        alert_count=len(alerts),
        label_count=int(family is not None),
        last_sequence=len(events),
        first_timestamp_ns=rows[0]["prediction_timestamp_ns"],
        last_timestamp_ns=rows[-1]["prediction_timestamp_ns"],
        events=_reference(event_path),
        snapshots=_reference(snapshots),
        alerts=_reference(alerts_path),
        ground_truth=labels,
        validation=validation,
    )
    write_manifest(directory / "manifest.json", replay)
    features = directory / "features.parquet"
    pq.write_table(
        pa.Table.from_pylist(
            rows, schema=feature_arrow_schema(fixture_hash("wave1-fixture-feature-config"), FEATURE_SCHEMA_V2)
        ),
        features,
    )
    return replay


def complete_c4_fixtures(output: Path, development: Path, final: Path) -> tuple[Path, Path, Path]:
    """Replace only synthetic packages, before the fixture candidate is trained."""
    evidence = output / "comparison-evidence"
    evidence.mkdir()
    references, locations, replay_sources = [], [], []
    controls = {}
    for number, (symbol, family, seed) in enumerate(product(SYMBOLS, FAMILIES, SEEDS), 1):
        stage = evidence / f"stage-{number}"
        relative = f"replays/xnas-{DAY}-{symbol.lower()}/comparisons/{family}-s{seed}"
        hybrid = _replay(stage / relative / "hybrid", symbol, family, seed)
        include_control = symbol not in controls
        if include_control:
            controls[symbol] = _replay(stage / relative / "control", symbol, None, None)
        control = controls[symbol]
        digest, count, size = inventory_evidence(stage)
        checkpoint = ComparisonCheckpoint(
            binding_sha256=fixture_hash("c4-comparison-binding"),
            comparison_number=number,
            symbol=symbol,
            attack_family=family,
            seed=seed,
            control_run_id=control.run_id,
            control_event_stream_sha256=control.canonical_event_stream_hash,
            hybrid_run_id=hybrid.run_id,
            hybrid_event_stream_sha256=hybrid.canonical_event_stream_hash,
            includes_control_artifacts=include_control,
            payload_inventory_sha256=digest,
            payload_file_count=count,
            payload_size_bytes=size,
        )
        write_manifest(stage / "checkpoint.json", checkpoint)
        target = evidence / f"checkpoint-{number}"
        publish_local_result(stage, target.as_uri())
        uri = f"s3://synthetic-c4-checkpoints/comparison-{number}"
        references.append(
            CheckpointReference(
                kind="comparison",
                uri=uri,
                checkpoint_sha256=sha256_file(target / "checkpoint.json"),
                payload_inventory_sha256=digest,
                payload_file_count=count,
                payload_size_bytes=size,
            )
        )
        locations.append(C4CheckpointLocation(source_uri=uri, relative_root=target.name))
        replay_sources.append((hybrid, target / relative / "hybrid/features.parquet"))
        if include_control:
            replay_sources.append((control, target / relative / "control/features.parquet"))
    preparation = PreparationManifest(
        run_id="synthetic-c4-preparation",
        source_filename="synthetic-only.gz",
        source_sha256=fixture_hash("source"),
        source_manifest_sha256=fixture_hash("source-manifest"),
        parser_version="synthetic",
        parser_config_sha256=fixture_hash("parser"),
        itch_message_counts={"S": 2},
        system_event_count=2,
        symbols=SYMBOLS,
        dataset_ids={s: controls[s].dataset_id for s in SYMBOLS},
        control_run_ids={s: controls[s].run_id for s in SYMBOLS},
        campaign_run_ids=tuple(replay.run_id for replay, _ in replay_sources if replay.campaign_id),
        checkpoint_binding_sha256=fixture_hash("c4-comparison-binding"),
        normalized_checkpoint=references[0].model_copy(update={"kind": "normalized"}),
        comparison_checkpoints=tuple(references),
        checkpoint_payload_bytes=sum(r.payload_size_bytes for r in references),
        created_at=datetime.now(UTC),
    )
    preparation_path = evidence / "preparation.json"
    write_manifest(preparation_path, preparation)
    comparison = C4ComparisonPackage(
        preparation=CloudArtifact(
            logical_name="preparation",
            uri="preparation.json",
            sha256=sha256_file(preparation_path),
            size_bytes=preparation_path.stat().st_size,
        ),
        checkpoints=tuple(locations),
    )
    comparison_path = evidence / "comparison.json"
    write_manifest(comparison_path, comparison)
    original_root = FrozenPublicSampleRoot.model_validate_json(
        (development / "manifests/frozen-root.json").read_bytes()
    )
    root = original_root.model_copy(
        update={
            "sources": tuple(
                source.model_copy(update={"preparation_manifest_sha256": sha256_file(preparation_path)})
                if source.fold == "test"
                else source
                for source in original_root.sources
            )
        }
    )
    packages = []
    for source_package, scope in ((development, "development"), (final, "final_test")):
        package = output / ("c4-" + scope)
        (package / "manifests").mkdir(parents=True)
        old = TabularProjectionManifest.model_validate_json(
            (source_package / "manifests/tabular-projection.json").read_bytes()
        )
        if scope == "development":
            specs = [
                (
                    shard.fold,
                    shard.run_id,
                    shard.base_session_id,
                    shard.campaign_id,
                    shard.replay_manifest_sha256,
                    source_package / "artifacts" / shard.rows.uri,
                )
                for shard in old.shards
            ]
            originals = []
            for fold, run_id, session, campaign, stream_hash, path in specs:
                source = package / "source-input" / fold / (run_id + ".parquet")
                source.parent.mkdir(parents=True, exist_ok=True)
                pq.write_table(pq.read_table(path).drop(["supervised_row_id"]), source)
                originals.append((fold, run_id, session, campaign, stream_hash, source))
            specs = originals
        else:
            specs = [
                (
                    "test",
                    replay.run_id,
                    replay.base_session_id,
                    replay.campaign_id,
                    replay.canonical_event_stream_hash,
                    path,
                )
                for replay, path in replay_sources
            ]
        shards = tuple(
            materialize_tabular_shard(
                path,
                package / "artifacts/tabular" / fold / (run_id + ".parquet"),
                artifact_root=package / "artifacts",
                root_sha256=root.canonical_hash(),
                assignment_sha256=root.assignment_sha256,
                replay_sha256=stream_hash,
                fold=fold,
                base_session_id=session,
                campaign_id=campaign,
                run_id=run_id,
            )
            for fold, run_id, session, campaign, stream_hash, path in specs
        )
        write_manifest(package / "manifests/frozen-root.json", root)
        write_manifest(
            package / "manifests/tabular-projection.json",
            old.model_copy(
                update={
                    "root_sha256": root.canonical_hash(),
                    "shards": shards,
                }
            ),
        )
        packages.append(package)
    receipt = C4MlflowDatasetReleaseReceipt.model_validate_json(
        (development / "manifests/c4-mlflow-dataset-release.json").read_bytes()
    )
    receipt = receipt.model_copy(
        update={
            "root_file_sha256": sha256_file(packages[0] / "manifests/frozen-root.json"),
            "root_identity_sha256": root.canonical_hash(),
            "tabular_development_sha256": sha256_file(packages[0] / "manifests/tabular-projection.json"),
            "tabular_final_sha256": sha256_file(packages[1] / "manifests/tabular-projection.json"),
        }
    )
    for package in packages:
        write_manifest(package / "manifests/c4-mlflow-dataset-release.json", receipt)
    return packages[0], packages[1], comparison_path
