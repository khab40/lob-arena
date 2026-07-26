import hashlib
import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from pydantic import ValidationError

from app.corpus.governance import ArtifactReference
from app.evaluation.canonical_bundle import (
    CanonicalJavaReplayManifest,
    canonical_java_event_stream_hash,
    load_canonical_evaluation_input,
)
from app.exchange.schemas import exchange_event_from_dict


def _write(path: Path, content: str) -> ArtifactReference:
    path.write_text(content, encoding="utf-8")
    payload = path.read_bytes()
    return ArtifactReference(
        name=path.name,
        uri=path.name,
        sha256=hashlib.sha256(payload).hexdigest(),
        size_bytes=len(payload),
        schema_version="fixture_v1",
    )


def _event(sequence: int, timestamp: int, *, snapshot: bool = False) -> dict[str, object]:
    base: dict[str, object] = {
        "schema_version": 1,
        "event_type": "snapshot" if snapshot else "add",
        "event_id": f"event-{sequence}",
        "sequence": sequence,
        "source": "simulation",
        "source_sequence": sequence,
        "symbol": "SPY",
        "venue": "LOBSTER",
        "tick": sequence,
        "exchange_timestamp_ns": timestamp,
        "received_timestamp_ns": timestamp,
        "scenario_id": "scenario-1",
        "scenario_name": "layering_like",
        "scenario_family": "layering_like",
    }
    if snapshot:
        base.update(
            {
                "depth": 1,
                "book": {
                    "bids": [{"price": 99.0, "quantity": 10.0}],
                    "asks": [{"price": 101.0, "quantity": 10.0}],
                    "best_bid": 99.0,
                    "best_ask": 101.0,
                    "mid": 100.0,
                    "spread": 2.0,
                },
            }
        )
    else:
        base.update(
            {
                "order_id": "SYN:order-1",
                "agent_id": "SYN:agent-1",
                "side": "buy",
                "price": 99.0,
                "quantity": 10.0,
                "owner": "abuser",
            }
        )
    return base


def _bundle(tmp_path: Path) -> Path:
    events = [_event(1, 100), _event(2, 200, snapshot=True)]
    events_ref = _write(
        tmp_path / "events.jsonl",
        "".join(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n" for event in events),
    )
    snapshot_path = tmp_path / "snapshots.parquet"
    pq.write_table(pa.Table.from_pylist([{"tick": 2}]), snapshot_path)
    snapshot_payload = snapshot_path.read_bytes()
    snapshots_ref = ArtifactReference(
        name=snapshot_path.name,
        uri=snapshot_path.name,
        sha256=hashlib.sha256(snapshot_payload).hexdigest(),
        size_bytes=len(snapshot_payload),
        schema_version="canonical_snapshots_v1",
    )
    alerts_ref = _write(
        tmp_path / "alerts.jsonl",
        json.dumps({"run_id": "run-1", "campaign_id": "campaign-1", "tick": 2}) + "\n",
    )
    labels_ref = _write(
        tmp_path / "labels.jsonl",
        json.dumps(
            {
                "run_id": "run-1",
                "campaign_id": "campaign-1",
                "ground_truth": {
                    "scenario_family": "layering_like",
                    "start_tick": 1,
                    "end_tick": 2,
                    "source": "synthetic_scenario",
                },
            }
        )
        + "\n",
    )
    stream_hash = canonical_java_event_stream_hash(
        [exchange_event_from_dict(event) for event in events],
        price_tick_size=0.01,
        quantity_lot_size=1.0,
    )
    validation_ref = _write(
        tmp_path / "validation.json",
        json.dumps(
            {
                "verdict": "pass",
                "run_id": "run-1",
                "base_session_id": "base-1",
                "canonical_event_stream_hash": stream_hash,
            }
        ),
    )
    manifest = CanonicalJavaReplayManifest(
        run_id="run-1",
        base_session_id="base-1",
        dataset_id="dataset-1",
        mode="hybrid",
        campaign_id="campaign-1",
        attack_family="layering_like",
        instrument="SPY",
        venue="LOBSTER",
        session_id="regular",
        session_date="2012-06-21",
        seed=42,
        price_tick_size=0.01,
        quantity_lot_size=1.0,
        tick_interval_ns=100,
        java_engine_version="java-kernel-test",
        canonical_event_stream_hash=stream_hash,
        event_count=2,
        snapshot_count=1,
        alert_count=1,
        label_count=1,
        last_sequence=2,
        first_timestamp_ns=100,
        last_timestamp_ns=200,
        events=events_ref,
        snapshots=snapshots_ref,
        alerts=alerts_ref,
        ground_truth=labels_ref,
        validation=validation_ref,
    )
    manifest_path = tmp_path / "replay-manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest_path


def test_canonical_bundle_is_the_complete_feature_and_evaluation_input(tmp_path: Path) -> None:
    manifest_path = _bundle(tmp_path)

    replay = load_canonical_evaluation_input(manifest_path)

    assert [event.sequence for event in replay.events] == [1, 2]
    assert replay.labels.labels[0].attack_family == "layering_like"
    assert replay.alerts[0]["run_id"] == "run-1"
    assert replay.feature_metadata().source_type == "hybrid"
    assert len(replay.feature_input_sha256) == 64


def test_bundle_rejects_tampered_event_artifact(tmp_path: Path) -> None:
    manifest_path = _bundle(tmp_path)
    (tmp_path / "events.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="size mismatch|SHA-256 mismatch"):
        load_canonical_evaluation_input(manifest_path)


def test_bundle_rejects_alert_identity_mismatch_even_with_updated_digest(tmp_path: Path) -> None:
    manifest_path = _bundle(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    alerts = tmp_path / "alerts.jsonl"
    alerts.write_text(
        json.dumps({"run_id": "other-run", "campaign_id": "campaign-1"}) + "\n",
        encoding="utf-8",
    )
    manifest["alerts"]["size_bytes"] = alerts.stat().st_size
    manifest["alerts"]["sha256"] = hashlib.sha256(alerts.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="alerts run identity"):
        load_canonical_evaluation_input(manifest_path)


def test_hybrid_bundle_rejects_declared_but_null_attack_ground_truth(tmp_path: Path) -> None:
    manifest_path = _bundle(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    labels = tmp_path / "labels.jsonl"
    labels.write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "campaign_id": "campaign-1",
                "ground_truth": None,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    payload = labels.read_bytes()
    manifest["ground_truth"]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest["ground_truth"]["size_bytes"] = len(payload)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="attack ground truth"):
        load_canonical_evaluation_input(manifest_path)


def test_bundle_recomputes_canonical_java_stream_hash_from_events(tmp_path: Path) -> None:
    manifest_path = _bundle(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    events_path = tmp_path / "events.jsonl"
    records = [json.loads(line) for line in events_path.read_text().splitlines()]
    records[0]["quantity"] = 11.0
    events_path.write_text(
        "".join(json.dumps(item, sort_keys=True, separators=(",", ":")) + "\n" for item in records),
        encoding="utf-8",
    )
    payload = events_path.read_bytes()
    manifest["events"]["sha256"] = hashlib.sha256(payload).hexdigest()
    manifest["events"]["size_bytes"] = len(payload)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="stream hash does not match replay events"):
        load_canonical_evaluation_input(manifest_path)


def test_bundle_rejects_non_passing_java_validation(tmp_path: Path) -> None:
    manifest_path = _bundle(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    validation = tmp_path / "validation.json"
    payload = json.loads(validation.read_text())
    payload["verdict"] = "fail"
    validation.write_text(json.dumps(payload), encoding="utf-8")
    manifest["validation"]["size_bytes"] = validation.stat().st_size
    manifest["validation"]["sha256"] = hashlib.sha256(validation.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="pass verdict"):
        load_canonical_evaluation_input(manifest_path)


def test_historical_control_cannot_smuggle_synthetic_labels() -> None:
    with pytest.raises(ValidationError, match="historical control"):
        CanonicalJavaReplayManifest(
            run_id="run",
            base_session_id="base",
            dataset_id="dataset",
            mode="historical_control",
            campaign_id="smuggled",
            instrument="SPY",
            venue="LOBSTER",
            session_id="regular",
            session_date="2012-06-21",
            price_tick_size=0.01,
            quantity_lot_size=1,
            tick_interval_ns=1,
            java_engine_version="test",
            canonical_event_stream_hash="a" * 64,
            event_count=1,
            snapshot_count=1,
            alert_count=0,
            label_count=1,
            last_sequence=1,
            first_timestamp_ns=1,
            last_timestamp_ns=1,
            events={
                "name": "events",
                "uri": "events",
                "sha256": "a" * 64,
                "size_bytes": 1,
                "schema_version": "v1",
            },
            snapshots={
                "name": "snapshots",
                "uri": "snapshots",
                "sha256": "a" * 64,
                "size_bytes": 1,
                "schema_version": "v1",
            },
            alerts={
                "name": "alerts",
                "uri": "alerts",
                "sha256": "a" * 64,
                "size_bytes": 0,
                "schema_version": "v1",
            },
            ground_truth={
                "name": "labels",
                "uri": "labels",
                "sha256": "a" * 64,
                "size_bytes": 1,
                "schema_version": "v1",
            },
            validation={
                "name": "validation",
                "uri": "validation",
                "sha256": "a" * 64,
                "size_bytes": 1,
                "schema_version": "v1",
            },
        )
