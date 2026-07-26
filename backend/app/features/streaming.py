from __future__ import annotations

import hashlib
import heapq
import json
import math
import os
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Annotated, Any, Iterable, Literal

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.exchange.schemas import CanonicalExchangeEvent
from app.features.io import feature_arrow_schema
from app.features.models import FeaturePipelineConfig, FeatureRunMetadata
from app.features.pipeline import (
    FEATURE_COLUMNS,
    FEATURE_SCHEMA_VERSION,
    METADATA_COLUMNS,
    FeaturePipeline,
    feature_split_group,
)


STREAMING_QUALITY_SCHEMA_VERSION = "feature_quality_report_v2_streaming"
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StreamingValidationEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["feature_streaming_validation_v1"] = "feature_streaming_validation_v1"
    verdict: Literal["pass"]
    protocol_hash: Sha256
    corpus_hash: Sha256
    base_session_id: str = Field(min_length=1)
    control_replay_manifest_sha256: Sha256
    canonical_event_stream_hash: Sha256
    full_session: Literal[True]
    canonical_event_count: int = Field(ge=1)
    memory_growth_fraction: float = Field(ge=0, allow_inf_nan=False)
    events_per_second: float = Field(gt=0, allow_inf_nan=False)
    logical_hashes_by_chunk_size: dict[int, Sha256] = Field(min_length=2)
    benchmark: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_evidence(self) -> "StreamingValidationEvidence":
        hashes = list(self.logical_hashes_by_chunk_size.values())
        if (
            len(self.logical_hashes_by_chunk_size) < 2
            or len(set(hashes)) != 1
        ):
            raise ValueError("streaming evidence must prove chunk-size logical equivalence")
        return self


class _RunningDistribution:
    def __init__(self, *, name: str, sample_size: int) -> None:
        self.name = name
        self.sample_size = sample_size
        self.count = 0
        self.missing = 0
        self.mean = 0.0
        self.m2 = 0.0
        self.minimum: float | None = None
        self.maximum: float | None = None
        self._sample_heap: list[tuple[int, float]] = []

    def observe(self, value: object, *, row_index: int) -> None:
        if value is None:
            self.missing += 1
            return
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            self.missing += 1
            return
        numeric = float(value)
        self.count += 1
        delta = numeric - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (numeric - self.mean)
        self.minimum = numeric if self.minimum is None else min(self.minimum, numeric)
        self.maximum = numeric if self.maximum is None else max(self.maximum, numeric)
        priority = int.from_bytes(
            hashlib.sha256(f"{self.name}|{row_index}".encode("utf-8")).digest()[:8],
            "big",
        )
        candidate = (-priority, numeric)
        if len(self._sample_heap) < self.sample_size:
            heapq.heappush(self._sample_heap, candidate)
        elif priority < -self._sample_heap[0][0]:
            heapq.heapreplace(self._sample_heap, candidate)

    def report(self) -> dict[str, float | int | None]:
        if self.count == 0:
            return {
                "count": 0,
                "min": None,
                "max": None,
                "mean": None,
                "stddev": None,
                "p01": None,
                "p50": None,
                "p99": None,
            }
        sample = sorted(value for _, value in self._sample_heap)
        return {
            "count": self.count,
            "min": self.minimum,
            "max": self.maximum,
            "mean": self.mean,
            "stddev": math.sqrt(self.m2 / self.count),
            "p01": _percentile(sample, 0.01),
            "p50": _percentile(sample, 0.50),
            "p99": _percentile(sample, 0.99),
        }

    @property
    def retained_sample_count(self) -> int:
        return len(self._sample_heap)


class StreamingQualityAccumulator:
    """Bounded-memory exact counts/moments plus deterministic priority-sample quantiles."""

    def __init__(self, *, sample_size: int) -> None:
        if sample_size < 1:
            raise ValueError("streaming quality sample size must be positive")
        self.sample_size = sample_size
        self.row_count = 0
        self.invalid_count = 0
        self.invalid_rows: list[dict[str, object]] = []
        self.labels: Counter[str] = Counter()
        self.attack_families: Counter[str] = Counter()
        self.distributions = {
            name: _RunningDistribution(name=name, sample_size=sample_size)
            for name in FEATURE_COLUMNS
        }

    def observe(self, row: dict[str, Any]) -> None:
        row_index = self.row_count
        self.row_count += 1
        if not row.get("row_valid", False):
            self.invalid_count += 1
            if len(self.invalid_rows) < 100:
                self.invalid_rows.append(
                    {
                        "row_index": row_index,
                        "tick": row.get("tick"),
                        "prediction_timestamp_ns": row.get("prediction_timestamp_ns"),
                        "reason": row.get("invalid_reason"),
                    }
                )
        label = row.get("label")
        self.labels["positive" if label == 1 else "negative" if label == 0 else "unlabeled"] += 1
        family = row.get("attack_family")
        if family:
            self.attack_families[str(family)] += 1
        for name, distribution in self.distributions.items():
            distribution.observe(row.get(name), row_index=row_index)

    def report(self) -> dict[str, Any]:
        return {
            "schema_version": STREAMING_QUALITY_SCHEMA_VERSION,
            "row_count": self.row_count,
            "valid_row_count": self.row_count - self.invalid_count,
            "invalid_row_count": self.invalid_count,
            "invalid_rows": self.invalid_rows,
            "missing_values": {
                name: distribution.missing
                for name, distribution in self.distributions.items()
            },
            "distributions": {
                name: distribution.report()
                for name, distribution in self.distributions.items()
            },
            "class_balance": {
                "positive": self.labels["positive"],
                "negative": self.labels["negative"],
                "unlabeled": self.labels["unlabeled"],
                "attack_family_rows": dict(sorted(self.attack_families.items())),
            },
            "quantiles": {
                "method": "deterministic_priority_sample_v1",
                "configured_sample_size": self.sample_size,
                "maximum_retained_per_feature": max(
                    distribution.retained_sample_count
                    for distribution in self.distributions.values()
                ),
            },
        }


def write_streaming_feature_run(
    output_dir: Path,
    *,
    events: Iterable[CanonicalExchangeEvent],
    pipeline: FeaturePipeline,
    config: FeaturePipelineConfig,
    metadata: FeatureRunMetadata,
    row_group_size: int = 25_000,
    quantile_sample_size: int = 2_048,
    overwrite: bool = False,
    extra_input_provenance: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if row_group_size < 1:
        raise ValueError("Parquet row group size must be positive")
    output_dir.mkdir(parents=True, exist_ok=True)
    lock_dir = output_dir / ".feature-write.lock"
    try:
        lock_dir.mkdir()
    except FileExistsError as exception:
        raise ValueError("feature output is locked by another writer or an interrupted run") from exception
    try:
        return _write_streaming_locked(
            output_dir,
            events=events,
            pipeline=pipeline,
            config=config,
            metadata=metadata,
            row_group_size=row_group_size,
            quantile_sample_size=quantile_sample_size,
            overwrite=overwrite,
            extra_input_provenance=extra_input_provenance or {},
        )
    finally:
        lock_dir.rmdir()


def _write_streaming_locked(
    output_dir: Path,
    *,
    events: Iterable[CanonicalExchangeEvent],
    pipeline: FeaturePipeline,
    config: FeaturePipelineConfig,
    metadata: FeatureRunMetadata,
    row_group_size: int,
    quantile_sample_size: int,
    overwrite: bool,
    extra_input_provenance: dict[str, Any],
) -> dict[str, Any]:
    targets = {
        "features": output_dir / "features.parquet",
        "quality": output_dir / "feature-quality.json",
        "metadata": output_dir / "run-metadata.json",
    }
    if not overwrite and any(path.exists() for path in targets.values()):
        raise ValueError("feature output already exists; select a new directory or use --overwrite")
    token = uuid.uuid4().hex
    temporary = {
        name: path.with_name(f".{path.name}.{token}.tmp")
        for name, path in targets.items()
    }
    schema = feature_arrow_schema(config.config_hash())
    writer: pq.ParquetWriter | None = None
    buffer: list[dict[str, Any]] = []
    quality = StreamingQualityAccumulator(sample_size=quantile_sample_size)
    logical_digest = hashlib.sha256()
    try:
        writer = pq.ParquetWriter(temporary["features"], schema, compression="zstd")
        for row in pipeline.iter_rows(events):
            _validate_stream_row(row, config=config, metadata=metadata)
            quality.observe(row)
            logical_digest.update(_canonical_row(row))
            buffer.append(row)
            if len(buffer) >= row_group_size:
                _write_row_group(writer, schema, buffer)
                buffer.clear()
        if buffer:
            _write_row_group(writer, schema, buffer)
            buffer.clear()
        writer.close()
        writer = None
        if quality.row_count == 0:
            raise ValueError("feature output requires at least one simulation-source snapshot row")
        provenance = {**pipeline.stream_provenance(), **extra_input_provenance}
        if provenance["feature_checkpoint_count"] != quality.row_count:
            raise ValueError("streaming checkpoint count does not match emitted feature rows")
        quality_report = quality.report()
        _write_json(temporary["quality"], quality_report)
        run_manifest = {
            "schema_version": "feature_stream_run_metadata_v1",
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_config_hash": config.config_hash(),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run": metadata.model_dump(mode="json"),
            "config": config.model_dump(mode="json"),
            "input": {
                "canonical_event_stream_sha256": pipeline.input_sha256,
                **provenance,
            },
            "output": {
                "feature_file": targets["features"].name,
                "feature_file_sha256": _sha256(temporary["features"]),
                "feature_file_size_bytes": temporary["features"].stat().st_size,
                "logical_feature_rows_sha256": logical_digest.hexdigest(),
                "quality_file": targets["quality"].name,
                "quality_file_sha256": _sha256(temporary["quality"]),
                "row_count": quality.row_count,
                "valid_row_count": quality.row_count - quality.invalid_count,
                "invalid_row_count": quality.invalid_count,
            },
            "columns": {
                "metadata": list(METADATA_COLUMNS),
                "features": list(FEATURE_COLUMNS),
                "label": ["attack_family", "attack_phase", "label", "label_source"],
            },
            "streaming": {
                "event_processing": "single_pass_iterable",
                "parquet_row_group_size": row_group_size,
                "quantile_method": "deterministic_priority_sample_v1",
                "quantile_sample_size": quantile_sample_size,
                "bounded_state": "active_book_plus_longest_rolling_window_plus_row_group",
            },
            "split_policy": {
                "group_column": "split_group",
                "rule": "group by instrument/session; never randomly split adjacent rows",
                "purging": "purge at least long_window_ns around any within-session boundary",
            },
        }
        _write_json(temporary["metadata"], run_manifest)
        for name in ("features", "quality", "metadata"):
            os.replace(temporary[name], targets[name])
        return run_manifest
    finally:
        if writer is not None:
            writer.close()
        for path in temporary.values():
            path.unlink(missing_ok=True)


def _validate_stream_row(
    row: dict[str, Any],
    *,
    config: FeaturePipelineConfig,
    metadata: FeatureRunMetadata,
) -> None:
    expected_columns = {*METADATA_COLUMNS, *FEATURE_COLUMNS}
    if set(row) != expected_columns:
        raise ValueError("streaming feature row does not match the versioned column contract")
    expected = {
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
        "split_group": feature_split_group(metadata),
    }
    for name, value in expected.items():
        if row[name] != value:
            raise ValueError(f"streaming feature row {name} does not match run metadata")


def _write_row_group(
    writer: pq.ParquetWriter,
    schema: pa.Schema,
    rows: list[dict[str, Any]],
) -> None:
    writer.write_table(pa.Table.from_pylist(rows, schema=schema), row_group_size=len(rows))


def _canonical_row(row: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            row,
            sort_keys=True,
            separators=(",", ":"),
            default=lambda value: value.isoformat() if isinstance(value, date) else str(value),
            allow_nan=False,
        ).encode("utf-8")
        + b"\n"
    )


def _percentile(values: list[float], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    weight = position - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
