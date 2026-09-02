from __future__ import annotations

import gzip
import hashlib
import io
import json
import urllib.parse
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal, TextIO

import pyarrow as pa
import pyarrow.parquet as pq

from app.corpus.governance import ArtifactReference
from app.data_ingestion.models import DatasetManifest
from app.evaluation.canonical_bundle import (
    CanonicalJavaReplayManifest,
    open_canonical_evaluation_stream,
)
from app.features.io import ground_truth_window, load_labels


def export_replay_comparison(
    *,
    base_url: str,
    dataset: DatasetManifest,
    attack_family: Literal["spoofing_like_wall", "layering_like", "quote_stuffing"],
    seed: int,
    output_root: Path,
    timeout_seconds: float = 3600,
    compress_events: bool = False,
) -> tuple[Path, Path, dict[str, Any]]:
    payload = {
        "dataset_id": dataset.dataset_id,
        "scenario_family": attack_family,
        "max_ticks": 100_000,
        "master_seed": seed,
        "scenario_parameters": {},
    }
    comparison = _json_request(
        f"{base_url.rstrip('/')}/api/arena/replay-comparison",
        method="POST",
        payload=payload,
        timeout=timeout_seconds,
    )
    primary_error: BaseException | None = None
    try:
        if comparison.get("schema_version") != "historical_replay_comparison_v1":
            raise ValueError("Java replay returned an incompatible comparison schema")
        determinism = comparison.get("determinism")
        required = {
            "control_stream_match",
            "hybrid_stream_match",
            "control_trace_match",
            "hybrid_trace_match",
            "historical_snapshot_match",
        }
        if not isinstance(determinism, dict) or not all(determinism.get(name) is True for name in required):
            raise ValueError("Java replay repeat determinism gate failed")
        hybrid_summary = _object(comparison, "hybrid")
        hybrid_ground_truth = hybrid_summary.get("ground_truth")
        if not isinstance(hybrid_ground_truth, dict):
            raise ValueError("Java hybrid replay omitted ground truth")
        ground_truth_window(hybrid_ground_truth)
        base_session_id = f"xnas-{dataset.trade_date}-{dataset.symbol.lower()}"
        campaign_id = f"{base_session_id}-{attack_family}-s{seed}"
        control = _export_stream(
            base_url=base_url,
            summary=_object(comparison, "control"),
            dataset=dataset,
            mode="historical_control",
            run_id=f"{base_session_id}-control",
            base_session_id=base_session_id,
            campaign_id=None,
            attack_family=None,
            seed=None,
            output=output_root / "control",
            timeout_seconds=timeout_seconds,
            compress_events=compress_events,
        )
        hybrid = _export_stream(
            base_url=base_url,
            summary=hybrid_summary,
            dataset=dataset,
            mode="hybrid",
            run_id=campaign_id,
            base_session_id=base_session_id,
            campaign_id=campaign_id,
            attack_family=attack_family,
            seed=seed,
            output=output_root / "hybrid",
            timeout_seconds=timeout_seconds,
            compress_events=compress_events,
        )
        (output_root / "comparison.json").write_text(
            json.dumps(comparison, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return control, hybrid, comparison
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            _release_comparison_streams(base_url, comparison, timeout_seconds)
        except Exception as cleanup_error:
            if primary_error is None:
                raise
            primary_error.add_note(
                f"Java canonical stream cleanup also failed: {type(cleanup_error).__name__}: {cleanup_error}"
            )


def _export_stream(
    *,
    base_url: str,
    summary: dict[str, Any],
    dataset: DatasetManifest,
    mode: Literal["historical_control", "hybrid"],
    run_id: str,
    base_session_id: str,
    campaign_id: str | None,
    attack_family: str | None,
    seed: int | None,
    output: Path,
    timeout_seconds: float,
    compress_events: bool = False,
) -> Path:
    stream_id = summary.get("stream_id")
    if not isinstance(stream_id, str) or not stream_id:
        raise ValueError("Java replay summary omitted its canonical stream ID")
    output.mkdir(parents=True, exist_ok=False)
    events_path = output / ("events.jsonl.gz" if compress_events else "events.jsonl")
    snapshots_path = output / "snapshots.parquet"
    alerts_path = output / "alerts.jsonl"
    ground_truth_path = output / "ground-truth.jsonl"
    validation_path = output / "validation.json"
    label_count = 0
    ground_truth_reference = None
    if mode == "hybrid":
        ground_truth = summary.get("ground_truth")
        if not isinstance(ground_truth, dict):
            raise ValueError("Java hybrid replay omitted ground truth")
        ground_truth = {**ground_truth, "run_id": run_id, "campaign_id": campaign_id}
        ground_truth_path.write_text(json.dumps(ground_truth, sort_keys=True) + "\n", encoding="utf-8")
        label_count = len(load_labels(ground_truth_path).labels)
        if label_count != 1:
            raise ValueError("Java hybrid replay must provide exactly one attack label")
    event_count, snapshot_count, first_timestamp, last_timestamp = _write_stream_artifacts(
        base_url=base_url,
        stream_id=stream_id,
        events_path=events_path,
        snapshots_path=snapshots_path,
        timeout_seconds=timeout_seconds,
    )
    alert_rows = []
    for detector, ticks in sorted(_object(summary, "detector_alert_ticks").items()):
        if not isinstance(ticks, list):
            raise ValueError("Java detector alerts must be tick arrays")
        for tick in ticks:
            alert_rows.append(
                {
                    "run_id": run_id,
                    "campaign_id": campaign_id,
                    "detector": detector,
                    "tick": tick,
                }
            )
    alerts_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in alert_rows),
        encoding="utf-8",
    )
    if mode == "hybrid":
        ground_truth_reference = _artifact(
            ground_truth_path,
            output,
            "ground_truth",
            "scenario_ground_truth_jsonl_v1",
        )
    validation = {
        "schema_version": "canonical_java_replay_validation_v1",
        "verdict": "pass",
        "run_id": run_id,
        "base_session_id": base_session_id,
        "canonical_event_stream_hash": summary.get("stream_hash"),
        "repeat_determinism_verified": True,
        "historical_source_type": dataset.source_type,
        "source_stream_sha256": dataset.source_stream_sha256,
    }
    validation_path.write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest = CanonicalJavaReplayManifest(
        run_id=run_id,
        base_session_id=base_session_id,
        dataset_id=dataset.dataset_id,
        mode=mode,
        historical_source_type="nasdaq_itch",
        campaign_id=campaign_id,
        attack_family=attack_family,
        instrument=dataset.symbol,
        venue=dataset.venue,
        session_id=base_session_id,
        session_date=dataset.trade_date,
        seed=seed,
        price_tick_size=0.0001,
        quantity_lot_size=1.0,
        tick_interval_ns=500_000_000,
        java_engine_version="lob-arena-control-plane-0.1.0",
        canonical_event_stream_hash=str(summary.get("stream_hash")),
        event_count=event_count,
        snapshot_count=snapshot_count,
        alert_count=len(alert_rows),
        label_count=label_count,
        last_sequence=event_count,
        first_timestamp_ns=first_timestamp,
        last_timestamp_ns=last_timestamp,
        events=_artifact(events_path, output, "canonical_events", "canonical_exchange_events_v1"),
        snapshots=_artifact(snapshots_path, output, "snapshots", "canonical_lob_snapshots_v1"),
        alerts=_artifact(alerts_path, output, "alerts", "detector_alerts_jsonl_v1"),
        ground_truth=ground_truth_reference,
        validation=_artifact(validation_path, output, "replay_validation", "canonical_java_replay_validation_v1"),
    )
    if int(summary.get("canonical_event_count", -1)) != manifest.event_count:
        raise ValueError("Java replay summary count does not match its exported stream")
    manifest_path = output / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    validated_count = sum(
        1 for _ in open_canonical_evaluation_stream(manifest_path, artifact_root=output).iter_events()
    )
    if validated_count != event_count:
        raise ValueError("canonical replay validation count does not match the exported stream")
    return manifest_path


_SNAPSHOT_SCHEMA = pa.schema(
    [
        ("sequence", pa.int64()),
        ("exchange_timestamp_ns", pa.int64()),
        ("depth", pa.int32()),
        ("book_json", pa.string()),
    ]
)


def _write_stream_artifacts(
    *,
    base_url: str,
    stream_id: str,
    events_path: Path,
    snapshots_path: Path,
    timeout_seconds: float,
) -> tuple[int, int, int, int]:
    event_count = 0
    snapshot_count = 0
    first_timestamp: int | None = None
    last_timestamp: int | None = None
    snapshot_writer: pq.ParquetWriter | None = None
    try:
        with _open_event_writer(events_path) as event_file:
            for page in _iter_stream_pages(base_url, stream_id, timeout_seconds=timeout_seconds):
                snapshots: list[dict[str, Any]] = []
                for event in page:
                    timestamp = _timestamp(event)
                    if first_timestamp is None:
                        first_timestamp = timestamp
                    last_timestamp = timestamp
                    event_file.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
                    event_count += 1
                    if event.get("event_type") == "snapshot":
                        snapshots.append(
                            {
                                "sequence": event["sequence"],
                                "exchange_timestamp_ns": event.get("exchange_timestamp_ns"),
                                "depth": event["depth"],
                                "book_json": json.dumps(event["book"], sort_keys=True, separators=(",", ":")),
                            }
                        )
                if snapshots:
                    if snapshot_writer is None:
                        snapshot_writer = pq.ParquetWriter(snapshots_path, _SNAPSHOT_SCHEMA, compression="zstd")
                    snapshot_writer.write_table(pa.Table.from_pylist(snapshots, schema=_SNAPSHOT_SCHEMA))
                    snapshot_count += len(snapshots)
    finally:
        if snapshot_writer is not None:
            snapshot_writer.close()
    if event_count == 0 or first_timestamp is None or last_timestamp is None:
        raise ValueError("Java canonical replay stream is empty")
    if snapshot_count == 0:
        raise ValueError("Java canonical replay stream contains no snapshots")
    return event_count, snapshot_count, first_timestamp, last_timestamp


@contextmanager
def _open_event_writer(path: Path) -> Iterator[TextIO]:
    if path.suffix != ".gz":
        with path.open("w", encoding="utf-8", newline="") as text:
            yield text
        return
    with path.open("wb") as raw:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            fileobj=raw,
            compresslevel=1,
            mtime=0,
        ) as compressed:
            with io.TextIOWrapper(compressed, encoding="utf-8", newline="") as text:
                yield text


def _iter_stream_pages(base_url: str, stream_id: str, *, timeout_seconds: float) -> Iterator[list[dict[str, Any]]]:
    after = 0
    while True:
        query = urllib.parse.urlencode({"streamId": stream_id, "afterSequence": after, "limit": 1000})
        payload = _json_request(
            f"{base_url.rstrip('/')}/api/arena/exchange-events?{query}",
            method="GET",
            timeout=timeout_seconds,
        )
        page = payload.get("events")
        if not isinstance(page, list) or any(not isinstance(item, dict) for item in page):
            raise ValueError("Java canonical event page is invalid")
        next_after = payload.get("next_after_sequence")
        if isinstance(next_after, bool) or not isinstance(next_after, int) or next_after < after:
            raise ValueError("Java canonical event cursor regressed")
        has_more = payload.get("has_more")
        if not isinstance(has_more, bool):
            raise ValueError("Java canonical event page omitted its continuation state")
        if page:
            yield page
        if not has_more:
            return
        if not page:
            raise ValueError("Java canonical event page is empty before the end of the stream")
        if next_after == after:
            raise ValueError("Java canonical event cursor did not advance")
        after = next_after


def _json_request(
    url: str,
    *,
    method: Literal["DELETE", "GET", "POST"],
    payload: dict[str, Any] | None = None,
    timeout: float,
) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=None if payload is None else json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError("Java control plane returned a non-object response")
    return result


def _release_comparison_streams(base_url: str, comparison: dict[str, Any], timeout_seconds: float) -> None:
    determinism = _object(comparison, "determinism")
    stream_ids = (
        _object(comparison, "control").get("stream_id"),
        _object(comparison, "hybrid").get("stream_id"),
        determinism.get("control_repeat_stream_id"),
        determinism.get("hybrid_repeat_stream_id"),
    )
    if any(not isinstance(stream_id, str) or not stream_id for stream_id in stream_ids):
        raise ValueError("Java replay comparison omitted a canonical stream ID")
    for stream_id in dict.fromkeys(stream_ids):
        response = _json_request(
            f"{base_url.rstrip('/')}/internal/arena/exchange-events/{urllib.parse.quote(stream_id, safe='')}",
            method="DELETE",
            timeout=timeout_seconds,
        )
        if response.get("stream_id") != stream_id or response.get("released") is not True:
            raise ValueError("Java control plane did not confirm canonical stream release")


def _artifact(path: Path, root: Path, name: str, schema_version: str) -> ArtifactReference:
    return ArtifactReference(
        name=name,
        uri=path.relative_to(root).as_posix(),
        sha256=_sha256_file(path),
        size_bytes=path.stat().st_size,
        schema_version=schema_version,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _object(payload: dict[str, Any], name: str) -> dict[str, Any]:
    value = payload.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"Java replay omitted object: {name}")
    return value


def _timestamp(event: dict[str, Any]) -> int:
    value = event.get("exchange_timestamp_ns")
    if value is None:
        value = event.get("received_timestamp_ns")
    if not isinstance(value, int) or value < 0:
        raise ValueError("canonical event is missing its timestamp")
    return value
