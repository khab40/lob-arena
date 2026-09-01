from __future__ import annotations

import hashlib
import json
import os
import urllib.parse
import urllib.request
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from collections.abc import Iterator
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from app.exchange.schemas import CanonicalExchangeEvent, exchange_event_from_dict
from app.features.models import (
    FeaturePipelineConfig,
    FeatureRunMetadata,
    LabelSpec,
    LabelWindow,
)
from app.features.pipeline import (
    FEATURE_COLUMNS,
    FEATURE_SCHEMA_V2,
    FEATURE_SCHEMA_VERSION,
    METADATA_COLUMNS,
    SUPPORTED_FEATURE_SCHEMA_VERSIONS,
    FeatureRunResult,
    feature_quality_report,
    feature_split_group,
)


def load_events_jsonl(path: Path) -> list[CanonicalExchangeEvent]:
    return list(iter_events_jsonl(path))


def iter_events_jsonl(path: Path) -> Iterator[CanonicalExchangeEvent]:
    event_count = 0
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
                if not isinstance(payload, dict):
                    raise ValueError("event must be a JSON object")
                yield exchange_event_from_dict(payload)
                event_count += 1
            except (json.JSONDecodeError, ValueError, TypeError) as exception:
                raise ValueError(f"{path}: invalid canonical event at line {line_number}: {exception}") from exception
    if event_count == 0:
        raise ValueError(f"{path}: canonical event stream is empty")


def fetch_events(url: str, *, page_size: int = 1000, timeout: float = 30.0) -> list[CanonicalExchangeEvent]:
    return list(iter_fetch_events(url, page_size=page_size, timeout=timeout))


def iter_fetch_events(
    url: str,
    *,
    page_size: int = 1000,
    timeout: float = 30.0,
) -> Iterator[CanonicalExchangeEvent]:
    parsed_url = urllib.parse.urlsplit(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("canonical event endpoint must be an absolute HTTP(S) URL")
    if not 1 <= page_size <= 10_000:
        raise ValueError("canonical event endpoint page_size must be between 1 and 10000")
    if timeout <= 0:
        raise ValueError("canonical event endpoint timeout must be positive")
    event_count = 0
    after_sequence = 0
    while True:
        separator = "&" if "?" in url else "?"
        page_url = f"{url}{separator}" + urllib.parse.urlencode({"afterSequence": after_sequence, "limit": page_size})
        try:
            with urllib.request.urlopen(page_url, timeout=timeout) as response:
                payload = json.load(response)
        except (OSError, json.JSONDecodeError) as exception:
            raise ValueError(f"failed to read canonical events from {page_url}: {exception}") from exception
        if not isinstance(payload, dict) or not isinstance(payload.get("events"), list):
            raise ValueError("canonical event endpoint returned an invalid replay envelope")
        page_events: list[CanonicalExchangeEvent] = []
        for item in payload["events"]:
            if not isinstance(item, dict):
                raise ValueError("canonical event endpoint returned a non-object event")
            page_events.append(exchange_event_from_dict(item))
        next_value = payload.get("next_after_sequence")
        has_more = payload.get("has_more")
        if not _is_plain_int(next_value) or not isinstance(has_more, bool):
            raise ValueError("canonical event endpoint returned invalid cursor metadata")
        next_sequence = next_value
        if next_sequence < after_sequence:
            raise ValueError("canonical event endpoint cursor regressed")
        if page_events and page_events[-1].sequence != next_sequence:
            raise ValueError("canonical event endpoint cursor does not match its last event")
        if has_more and not page_events:
            raise ValueError("canonical event endpoint returned an empty non-terminal page")
        yield from page_events
        event_count += len(page_events)
        if not has_more:
            break
        if next_sequence == after_sequence:
            raise ValueError("canonical event endpoint did not advance its cursor")
        after_sequence = next_sequence
    if event_count == 0:
        raise ValueError("canonical event endpoint returned an empty stream")


def load_config(path: Path) -> FeaturePipelineConfig:
    return FeaturePipelineConfig.model_validate_json(path.read_text(encoding="utf-8"))


def load_run_metadata(path: Path) -> FeatureRunMetadata:
    return FeatureRunMetadata.model_validate_json(path.read_text(encoding="utf-8"))


def load_labels(path: Path | None) -> LabelSpec:
    if path is None:
        return LabelSpec()
    text = path.read_text(encoding="utf-8")
    try:
        parsed = json.loads(text)
        payloads = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        payloads = []
        for line_number, line in enumerate(text.splitlines(), 1):
            if not line.strip():
                continue
            try:
                payloads.append(json.loads(line))
            except json.JSONDecodeError as exception:
                raise ValueError(
                    f"{path}: invalid ground-truth JSONL at line {line_number}: {exception}"
                ) from exception
    if not payloads:
        raise ValueError(f"{path}: label input is empty")
    if len(payloads) == 1 and isinstance(payloads[0], dict):
        payload = payloads[0]
        if payload.get("schema_version") in {"feature_labels_v1", "feature_labels_v2"}:
            return LabelSpec.model_validate(payload)
    windows: list[LabelWindow] = []
    for payload in payloads:
        if not isinstance(payload, dict):
            raise ValueError("label input records must be JSON objects")
        ground_truth = payload.get("ground_truth", payload)
        if ground_truth is None:
            continue
        if not isinstance(ground_truth, dict):
            raise ValueError("ground-truth label input must be a JSON object or null")
        has_attack = ground_truth.get("has_attack")
        if has_attack is not None and not isinstance(has_attack, bool):
            raise ValueError("ground truth has_attack must be a boolean when present")
        if has_attack is False:
            continue
        windows.append(ground_truth_window(ground_truth))
    return LabelSpec(labels=windows)


def ground_truth_window(ground_truth: dict[str, Any]) -> LabelWindow:
    family = ground_truth.get("scenario_family")
    start_tick = ground_truth.get("start_tick")
    end_tick = ground_truth.get("end_tick")
    if not isinstance(family, str) or not _is_plain_int(start_tick) or not _is_plain_int(end_tick):
        raise ValueError("ground truth requires scenario_family, start_tick, and end_tick")
    label_source = ground_truth.get("source") or "synthetic_scenario"
    if not isinstance(label_source, str) or not label_source:
        raise ValueError("ground truth source must be a non-empty string")
    phases_payload = ground_truth.get("phase_windows")
    if phases_payload is None:
        phases_payload = {}
    if not isinstance(phases_payload, dict):
        raise ValueError("ground truth phase_windows must be an object")
    phases: dict[str, tuple[int, int]] = {}
    for name, bounds in phases_payload.items():
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(bounds, dict)
            or not _is_plain_int(bounds.get("start_tick"))
            or not _is_plain_int(bounds.get("end_tick"))
        ):
            raise ValueError("ground truth phase windows require names and integer tick bounds")
        phases[name] = (bounds["start_tick"], bounds["end_tick"])
    return LabelWindow(
        attack_family=family,
        start_tick=start_tick,
        end_tick=end_tick,
        phases=phases,
        label_source=label_source,
    )


def _is_plain_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def feature_arrow_schema(
    config_hash: str,
    schema_version: str = FEATURE_SCHEMA_VERSION,
) -> pa.Schema:
    if schema_version not in SUPPORTED_FEATURE_SCHEMA_VERSIONS:
        raise ValueError(f"unsupported feature schema version: {schema_version}")
    feature_type = pa.float32() if schema_version == FEATURE_SCHEMA_V2 else pa.float64()
    fields = [
        pa.field("feature_schema_version", pa.string(), nullable=False),
        pa.field("feature_config_hash", pa.string(), nullable=False),
        pa.field("run_id", pa.string(), nullable=False),
        pa.field("dataset_id", pa.string()),
        pa.field("source_type", pa.string(), nullable=False),
        pa.field("historical_source_type", pa.string()),
        pa.field("instrument", pa.string(), nullable=False),
        pa.field("venue", pa.string(), nullable=False),
        pa.field("session_id", pa.string(), nullable=False),
        pa.field("session_date", pa.date32(), nullable=False),
        pa.field("seed", pa.int64()),
        pa.field("prediction_timestamp_ns", pa.int64(), nullable=False),
        pa.field("tick", pa.int64(), nullable=False),
        pa.field("sequence", pa.int64(), nullable=False),
        pa.field("split_group", pa.string(), nullable=False),
        pa.field("attack_family", pa.string()),
        pa.field("attack_phase", pa.string()),
        pa.field("label", pa.int8()),
        pa.field("label_source", pa.string()),
        pa.field("row_valid", pa.bool_(), nullable=False),
        pa.field("invalid_reason", pa.string()),
        *(pa.field(name, feature_type) for name in FEATURE_COLUMNS),
    ]
    return pa.schema(
        fields,
        metadata={
            b"feature_schema_version": schema_version.encode(),
            b"feature_config_hash": config_hash.encode(),
            b"feature_columns": json.dumps(FEATURE_COLUMNS).encode(),
            b"split_policy": b"group_by_instrument_session_no_random_adjacent_rows",
        },
    )


def write_feature_run(
    output_dir: Path,
    *,
    result: FeatureRunResult,
    config: FeaturePipelineConfig,
    metadata: FeatureRunMetadata,
    overwrite: bool = False,
) -> dict[str, Any]:
    _validate_feature_run(result, config, metadata)
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_dir = output_dir / ".feature-write.lock"
    try:
        lock_dir.mkdir()
    except FileExistsError as exception:
        raise ValueError("feature output is locked by another writer or an interrupted run") from exception
    try:
        return _write_feature_run_locked(
            output_dir,
            result=result,
            config=config,
            metadata=metadata,
            overwrite=overwrite,
        )
    finally:
        lock_dir.rmdir()


def _write_feature_run_locked(
    output_dir: Path,
    *,
    result: FeatureRunResult,
    config: FeaturePipelineConfig,
    metadata: FeatureRunMetadata,
    overwrite: bool,
) -> dict[str, Any]:
    targets = {
        "features": output_dir / "features.parquet",
        "quality": output_dir / "feature-quality.json",
        "metadata": output_dir / "run-metadata.json",
    }
    if not overwrite and any(path.exists() for path in targets.values()):
        raise ValueError("feature output already exists; select a new directory or use --overwrite")
    write_token = uuid.uuid4().hex
    temporary = {name: path.with_name(f".{path.name}.{write_token}.tmp") for name, path in targets.items()}
    try:
        schema = feature_arrow_schema(config.config_hash(), config.schema_version)
        table = pa.Table.from_pylist(result.rows, schema=schema)
        pq.write_table(table, temporary["features"], compression="zstd")
        _write_json(temporary["quality"], result.quality_report)
        run_manifest = {
            "schema_version": "feature_run_metadata_v1",
            "feature_schema_version": config.schema_version,
            "feature_config_hash": config.config_hash(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run": metadata.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
            "input": {
                "canonical_event_stream_sha256": result.input_sha256,
                **result.input_provenance,
            },
            "output": {
                "feature_file": targets["features"].name,
                "feature_file_sha256": _sha256(temporary["features"]),
                "feature_file_size_bytes": temporary["features"].stat().st_size,
                "quality_file": targets["quality"].name,
                "quality_file_sha256": _sha256(temporary["quality"]),
                "row_count": len(result.rows),
                "valid_row_count": result.quality_report["valid_row_count"],
                "invalid_row_count": result.quality_report["invalid_row_count"],
            },
            "columns": {
                "metadata": list(METADATA_COLUMNS),
                "features": list(FEATURE_COLUMNS),
                "label": ["attack_family", "attack_phase", "label", "label_source"],
            },
            "split_policy": {
                "group_column": "split_group",
                "rule": "group by instrument/session; never randomly split adjacent rows",
                "purging": "future trainer must purge at least long_window_ns around split boundaries",
            },
        }
        _write_json(temporary["metadata"], run_manifest)
        for name in ("features", "quality", "metadata"):
            os.replace(temporary[name], targets[name])
        return run_manifest
    finally:
        for path in temporary.values():
            path.unlink(missing_ok=True)


def _validate_feature_run(
    result: FeatureRunResult,
    config: FeaturePipelineConfig,
    metadata: FeatureRunMetadata,
) -> None:
    if not result.rows:
        raise ValueError("feature output requires at least one snapshot row")
    expected_columns = {*METADATA_COLUMNS, *FEATURE_COLUMNS}
    expected_values: dict[str, Any] = {
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
        "split_group": feature_split_group(metadata),
    }
    for row_index, row in enumerate(result.rows):
        if set(row) != expected_columns:
            raise ValueError(f"feature row {row_index} does not match the versioned column contract")
        for field_name, expected in expected_values.items():
            if row[field_name] != expected:
                raise ValueError(f"feature row {row_index} {field_name} does not match the supplied run contract")
    expected_quality = feature_quality_report(result.rows, FEATURE_COLUMNS)
    if result.quality_report != expected_quality:
        raise ValueError("feature quality report does not match the supplied rows")
    if result.input_provenance.get("feature_checkpoint_count") != len(result.rows):
        raise ValueError("feature provenance checkpoint count does not match feature rows")
    if len(result.input_sha256) != 64:
        raise ValueError("feature input SHA-256 must contain 64 hexadecimal characters")
    try:
        int(result.input_sha256, 16)
    except ValueError as exception:
        raise ValueError("feature input SHA-256 must be hexadecimal") from exception


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True, default=_json_default) + "\n",
        encoding="utf-8",
    )


def _json_default(value: object) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    raise TypeError(f"unsupported JSON value: {type(value).__name__}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
