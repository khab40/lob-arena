from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class IngestionCandidate(BaseModel):
    candidate_id: str
    source_type: Literal["lobster", "nasdaq_itch"] = "lobster"
    venue: str = "LOBSTER"
    symbol: str
    trade_date: str
    start_time_ms: int
    end_time_ms: int
    start_time: str
    end_time: str
    depth: int
    message_file: str | None = None
    orderbook_file: str | None = None
    message_file_size: int | None = None
    orderbook_file_size: int | None = None
    source_file: str | None = None
    source_file_size: int | None = None
    status: Literal["ready", "invalid", "importing", "failed", "imported"]
    errors: list[str] = Field(default_factory=list)
    dataset_id: str | None = None


# Compatibility alias for callers of the original LOBSTER-only API.
LobsterCandidate = IngestionCandidate


class ValidationReport(BaseModel):
    valid: bool
    row_count: int = 0
    event_counts: dict[str, int] = Field(default_factory=dict)
    checks: dict[str, bool] = Field(default_factory=dict)
    statistics: dict[str, int | float] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DatasetFile(BaseModel):
    name: str
    size_bytes: int
    sha256: str


class DatasetManifest(BaseModel):
    manifest_version: int = 1
    dataset_schema_version: int = 1
    dataset_id: str
    status: Literal["ready"] = "ready"
    source_type: str = "lobster"
    format: str = "lobster_parquet_v1"
    venue: str = "LOBSTER"
    parser_version: str | None = None
    ingestion_mode: Literal["batch", "micro_batch", "streaming"] = "batch"
    symbol: str
    trade_date: str
    start_time_ms: int
    end_time_ms: int
    depth: int
    row_count: int
    event_counts: dict[str, int]
    price_scale: int = 10_000
    imported_at: datetime
    source_files: list[DatasetFile]
    output_files: list[DatasetFile]
    source_name: str | None = None
    source_url: str | None = None
    source_stream_sha256: str | None = None
    parser_config_sha256: str | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    message_counts: dict[str, int] = Field(default_factory=dict)
    truncation_limits: dict[str, int] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ImportedDataset(BaseModel):
    dataset_id: str
    source_type: str
    symbol: str
    trade_date: str
    start_time_ms: int
    end_time_ms: int
    start_time: str
    end_time: str
    depth: int
    row_count: int
    event_counts: dict[str, int]
    imported_at: datetime
    path: str

    @classmethod
    def from_manifest(cls, manifest: DatasetManifest, path: str) -> "ImportedDataset":
        return cls(
            dataset_id=manifest.dataset_id,
            source_type=manifest.source_type,
            symbol=manifest.symbol,
            trade_date=manifest.trade_date,
            start_time_ms=manifest.start_time_ms,
            end_time_ms=manifest.end_time_ms,
            start_time=format_milliseconds(manifest.start_time_ms),
            end_time=format_milliseconds(manifest.end_time_ms),
            depth=manifest.depth,
            row_count=manifest.row_count,
            event_counts=manifest.event_counts,
            imported_at=manifest.imported_at,
            path=path,
        )


class ImportAccepted(BaseModel):
    candidate_id: str
    status: Literal["importing", "imported"]
    dataset_id: str | None = None


class ImportWindowRequest(BaseModel):
    start_time_ms: int | None = Field(default=None, ge=0, lt=86_400_000)
    end_time_ms: int | None = Field(default=None, gt=0, le=86_400_000)

    @model_validator(mode="after")
    def validate_window(self) -> "ImportWindowRequest":
        if (self.start_time_ms is None) != (self.end_time_ms is None):
            raise ValueError("start_time_ms and end_time_ms must be supplied together")
        if (
            self.start_time_ms is not None
            and self.end_time_ms is not None
            and self.start_time_ms >= self.end_time_ms
        ):
            raise ValueError("start_time_ms must be before end_time_ms")
        return self


class SourceImportRequest(ImportWindowRequest):
    depth: int | None = Field(default=None, ge=1, le=100)


def format_milliseconds(value: int) -> str:
    hours, remainder = divmod(value, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{milliseconds:03d}"
