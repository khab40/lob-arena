import json
import os
import re
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, Field

from app.config import Settings
from app.storage.local_store import LocalStore


EvidenceKind = Literal["endpoint_call", "job"]
_ARCHIVE_LOCK = threading.Lock()
_DEFAULT_ARCHIVE: "NebiusEvidenceArchive | None" = None


class NebiusEvidenceRecord(BaseModel):
    evidence_id: str
    kind: EvidenceKind
    operation: str
    status: str
    created_at: str
    latency_seconds: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    estimated_cost_usd: float | None = None
    job_cost_usd: float = 0
    duration_seconds: float = 0
    job_runs: int = 0
    workloads: int = 0
    simulation_events: int = 0
    artifact_count: int = 0
    request_bytes: int = 0
    response_bytes: int = 0
    artifact_bytes: int = 0
    cpu_seconds: float = 0
    peak_rss_bytes: int = 0
    processed_rows: int = 0
    rows_per_second: float = 0
    cloud_project_id: str | None = None
    cloud_region: str | None = None
    cloud_platform: str | None = None
    cloud_preset: str | None = None
    image_digest: str | None = None
    run_id: str | None = None
    endpoint: str | None = None
    local_dir: str
    source_uri: str | None = None
    s3_status: Literal["uploaded", "local_only", "upload_failed"]
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class NebiusEvidenceSyncResponse(BaseModel):
    status: Literal["synced", "local_only", "failed"]
    source_uri: str | None = None
    local_dir: str
    uploaded_pending: int = 0
    record_count: int = 0
    artifact_count: int = 0
    message: str


class NebiusEvidenceArchive:
    def __init__(self, store: LocalStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.local_root = store.output_dir / "nebius" / "evidence"

    def record_endpoint_call(
        self,
        *,
        url: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        status: str,
        latency_seconds: float,
        error: str | None = None,
    ) -> NebiusEvidenceRecord:
        endpoint = urlsplit(url)
        return self.record(
            kind="endpoint_call",
            operation=endpoint.path.strip("/").replace("/", "_") or "endpoint",
            status=status,
            request_payload=request_payload,
            response_payload=response_payload,
            latency_seconds=latency_seconds,
            endpoint=f"{endpoint.scheme}://{endpoint.netloc}{endpoint.path}",
            error=error,
        )

    def record_job(
        self,
        *,
        operation: str,
        run_id: str,
        status: str,
        payload: dict[str, Any],
        artifact_paths: dict[str, str],
    ) -> NebiusEvidenceRecord:
        response_payload = dict(payload)
        usage = dict(payload.get("usage")) if isinstance(payload.get("usage"), dict) else {}
        duration_seconds = _elapsed_between(payload.get("created_at"), payload.get("updated_at"))
        workload_count = _nonnegative_int(payload.get("attack_count"))
        event_path = artifact_paths.get("events") or artifact_paths.get("order_book_event_logs")
        usage.setdefault("duration_seconds", duration_seconds)
        usage.setdefault("job_runs", 1 if status in {"completed", "failed"} else 0)
        usage.setdefault("workloads", workload_count)
        usage.setdefault("simulation_events", _line_count(event_path))
        usage.setdefault(
            "artifact_count",
            sum(1 for path in artifact_paths.values() if Path(path).is_file()),
        )
        if duration_seconds > 0 and self.settings.nebius_job_cost_per_hour_usd > 0:
            usage.setdefault(
                "job_cost_usd",
                round(duration_seconds / 3600 * self.settings.nebius_job_cost_per_hour_usd, 8),
            )
        response_payload["usage"] = usage
        evidence_files = {
            key: path
            for key, path in artifact_paths.items()
            if any(token in key for token in ("submit", "logs", "sync", "evidence", "config", "request"))
        }
        return self.record(
            kind="job",
            operation=operation,
            status=status,
            request_payload={"run_id": run_id, "operation": operation},
            response_payload=response_payload,
            run_id=run_id,
            evidence_files=evidence_files,
        )

    def record(
        self,
        *,
        kind: EvidenceKind,
        operation: str,
        status: str,
        request_payload: dict[str, Any],
        response_payload: dict[str, Any],
        latency_seconds: float | None = None,
        run_id: str | None = None,
        endpoint: str | None = None,
        error: str | None = None,
        evidence_files: dict[str, str] | None = None,
    ) -> NebiusEvidenceRecord:
        evidence_id = f"EVD-{uuid4().hex[:12].upper()}"
        created_at = _now()
        local_dir = self.local_root / kind / evidence_id
        local_dir.mkdir(parents=True, exist_ok=True)
        request_path = local_dir / "request.json"
        response_path = local_dir / "response.json"
        request_text = json.dumps(_sanitize(request_payload), indent=2)
        response_text = json.dumps(_sanitize(response_payload), indent=2)
        request_path.write_text(request_text, encoding="utf-8")
        response_path.write_text(response_text, encoding="utf-8")
        artifact_paths = {"request": str(request_path), "response": str(response_path)}
        for label, raw_path in (evidence_files or {}).items():
            source = Path(raw_path)
            if not source.exists() or not source.is_file():
                continue
            target = local_dir / f"{_safe_name(label)}-{source.name}"
            _copy_redacted(source, target)
            artifact_paths[label] = str(target)

        usage = response_payload.get("usage") if isinstance(response_payload.get("usage"), dict) else {}
        prompt_tokens = _nonnegative_int(usage.get("prompt_tokens"))
        completion_tokens = _nonnegative_int(usage.get("completion_tokens"))
        total_tokens = _nonnegative_int(usage.get("total_tokens")) or prompt_tokens + completion_tokens
        estimated_cost_usd = _optional_nonnegative_float(usage.get("estimated_cost_usd"))
        token_rates_configured = (
            self.settings.nebius_input_token_cost_per_million_usd > 0
            or self.settings.nebius_output_token_cost_per_million_usd > 0
        )
        if estimated_cost_usd is None and token_rates_configured and (prompt_tokens or completion_tokens):
            estimated_cost_usd = round(
                prompt_tokens / 1_000_000 * self.settings.nebius_input_token_cost_per_million_usd
                + completion_tokens / 1_000_000 * self.settings.nebius_output_token_cost_per_million_usd,
                8,
            )
        job_cost_usd = _optional_nonnegative_float(usage.get("job_cost_usd")) or 0.0
        duration_seconds = _optional_nonnegative_float(usage.get("duration_seconds")) or 0.0
        artifact_bytes = sum(
            Path(path).stat().st_size
            for path in artifact_paths.values()
            if Path(path).exists() and Path(path).is_file()
        )

        source_uri = self._record_source_uri(kind, evidence_id)
        s3_status: Literal["uploaded", "local_only", "upload_failed"] = (
            "uploaded" if self._s3_enabled() else "local_only"
        )
        record = NebiusEvidenceRecord(
            evidence_id=evidence_id,
            kind=kind,
            operation=operation,
            status=status,
            created_at=created_at,
            latency_seconds=latency_seconds,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            estimated_cost_usd=estimated_cost_usd,
            job_cost_usd=job_cost_usd,
            duration_seconds=duration_seconds,
            job_runs=_nonnegative_int(usage.get("job_runs")),
            workloads=_nonnegative_int(usage.get("workloads")),
            simulation_events=_nonnegative_int(usage.get("simulation_events")),
            artifact_count=_nonnegative_int(usage.get("artifact_count")),
            request_bytes=len(request_text.encode("utf-8")),
            response_bytes=len(response_text.encode("utf-8")),
            artifact_bytes=artifact_bytes,
            cpu_seconds=_optional_nonnegative_float(usage.get("cpu_seconds")) or 0.0,
            peak_rss_bytes=_nonnegative_int(usage.get("peak_rss_bytes")),
            processed_rows=_nonnegative_int(usage.get("processed_rows")),
            rows_per_second=_optional_nonnegative_float(usage.get("rows_per_second")) or 0.0,
            cloud_project_id=_optional_text(usage.get("cloud_project_id")),
            cloud_region=_optional_text(usage.get("cloud_region")),
            cloud_platform=_optional_text(usage.get("cloud_platform")),
            cloud_preset=_optional_text(usage.get("cloud_preset")),
            image_digest=_optional_text(usage.get("image_digest")),
            run_id=run_id,
            endpoint=endpoint,
            local_dir=str(local_dir),
            source_uri=source_uri,
            s3_status=s3_status,
            artifact_paths=artifact_paths,
            error=_redact(error) if error else None,
        )
        metadata_path = local_dir / "metadata.json"
        artifact_paths["metadata"] = str(metadata_path)
        record = record.model_copy(update={"artifact_paths": artifact_paths})
        metadata_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        if self._s3_enabled():
            try:
                self._sync_directory(local_dir, source_uri or "", upload=True)
            except RuntimeError as exc:
                record = record.model_copy(update={"s3_status": "upload_failed", "error": _redact(str(exc))})
                metadata_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        self._register(record)
        return record

    def list_records(self, *, limit: int = 200) -> list[NebiusEvidenceRecord]:
        records: list[NebiusEvidenceRecord] = []
        if not self.local_root.exists():
            return records
        for path in self.local_root.glob("*/*/metadata.json"):
            try:
                record = NebiusEvidenceRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                continue
            local_dir = path.parent
            artifact_paths = {
                name: str(local_dir / Path(stored_path).name)
                for name, stored_path in record.artifact_paths.items()
            }
            records.append(
                record.model_copy(update={"local_dir": str(local_dir), "artifact_paths": artifact_paths})
            )
        return sorted(records, key=lambda item: item.created_at, reverse=True)[:limit]

    def sync(self) -> NebiusEvidenceSyncResponse:
        if not self._s3_enabled():
            records = self.list_records(limit=10_000)
            return NebiusEvidenceSyncResponse(
                status="local_only",
                local_dir=str(self.local_root),
                record_count=len(records),
                artifact_count=sum(len(record.artifact_paths) for record in records),
                message="Evidence is stored locally; Nebius Object Storage evidence archiving is disabled.",
            )
        uploaded_pending = 0
        with _ARCHIVE_LOCK:
            for record in self.list_records(limit=10_000):
                if record.s3_status == "uploaded":
                    continue
                self._sync_directory(Path(record.local_dir), record.source_uri or "", upload=True)
                metadata_path = Path(record.artifact_paths["metadata"])
                updated = record.model_copy(update={"s3_status": "uploaded", "error": None})
                metadata_path.write_text(updated.model_dump_json(indent=2), encoding="utf-8")
                self._sync_directory(Path(record.local_dir), record.source_uri or "", upload=True)
                uploaded_pending += 1
            source_uri = f"{self._base_uri()}/evidence"
            self._sync_directory(self.local_root, source_uri, upload=False)
        records = self.list_records(limit=10_000)
        for record in records:
            self._register(record)
        return NebiusEvidenceSyncResponse(
            status="synced",
            source_uri=source_uri,
            local_dir=str(self.local_root),
            uploaded_pending=uploaded_pending,
            record_count=len(records),
            artifact_count=sum(len(record.artifact_paths) for record in records),
            message="Nebius evidence synchronized between Object Storage, backend local disk, and UI index.",
        )

    def _register(self, record: NebiusEvidenceRecord) -> None:
        with _ARCHIVE_LOCK:
            registered_ids = {
                str(row.get("evidence_id"))
                for row in self.store.read_jsonl("nebius/evidence.jsonl", limit=None)
            }
            if record.evidence_id in registered_ids:
                return
            self.store.append_jsonl("nebius/evidence.jsonl", record.model_dump(mode="json"))
            for name, path in record.artifact_paths.items():
                self.store.append_jsonl(
                    "nebius/artifacts.jsonl",
                    {
                        "created_at": record.created_at,
                        "type": f"{record.kind}_{name}",
                        "path": path,
                        "status": "stored" if record.s3_status != "upload_failed" else "failed",
                        "source_uri": record.source_uri,
                        "evidence_id": record.evidence_id,
                        "run_id": record.run_id,
                    },
                )

    def _s3_enabled(self) -> bool:
        return bool(
            self.settings.nebius_evidence_archive_enabled
            and self._base_uri()
            and shutil.which("aws")
            and self._aws_credentials_configured()
        )

    def _aws_credentials_configured(self) -> bool:
        if (
            self.settings.nebius_object_storage_access_key_id
            and self.settings.nebius_object_storage_secret_access_key
        ):
            return True
        if os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"):
            return True
        return any(
            os.environ.get(name)
            for name in (
                "AWS_PROFILE",
                "AWS_CONFIG_FILE",
                "AWS_SHARED_CREDENTIALS_FILE",
                "AWS_WEB_IDENTITY_TOKEN_FILE",
                "AWS_CONTAINER_CREDENTIALS_RELATIVE_URI",
                "AWS_CONTAINER_CREDENTIALS_FULL_URI",
            )
        )

    def _base_uri(self) -> str:
        return str(self.settings.nebius_job_output_uri or "").rstrip("/")

    def _record_source_uri(self, kind: EvidenceKind, evidence_id: str) -> str | None:
        base_uri = self._base_uri()
        return f"{base_uri}/evidence/{kind}/{evidence_id}" if base_uri else None

    def _sync_directory(self, local_dir: Path, source_uri: str, *, upload: bool) -> None:
        aws = shutil.which("aws")
        if aws is None:
            raise RuntimeError("aws CLI is required for Nebius evidence synchronization")
        command = [aws]
        if self.settings.nebius_object_storage_endpoint_url:
            command.extend(["--endpoint-url", self.settings.nebius_object_storage_endpoint_url])
        source, destination = (str(local_dir), source_uri) if upload else (source_uri, str(local_dir))
        command.extend(["s3", "sync", source, destination, "--only-show-errors"])
        env = os.environ.copy()
        if self.settings.nebius_object_storage_access_key_id:
            env["AWS_ACCESS_KEY_ID"] = self.settings.nebius_object_storage_access_key_id
        if self.settings.nebius_object_storage_secret_access_key:
            env["AWS_SECRET_ACCESS_KEY"] = self.settings.nebius_object_storage_secret_access_key
        if self.settings.nebius_object_storage_session_token:
            env["AWS_SESSION_TOKEN"] = self.settings.nebius_object_storage_session_token
        env["AWS_DEFAULT_REGION"] = self.settings.nebius_object_storage_region
        env["AWS_EC2_METADATA_DISABLED"] = "true"
        completed = subprocess.run(command, capture_output=True, check=False, text=True, timeout=300, env=env)
        if completed.returncode != 0:
            raise RuntimeError(f"aws s3 sync exited {completed.returncode}: {completed.stderr or completed.stdout}")


def configure_default_evidence_archive(store: LocalStore, settings: Settings) -> NebiusEvidenceArchive:
    global _DEFAULT_ARCHIVE
    _DEFAULT_ARCHIVE = NebiusEvidenceArchive(store, settings)
    return _DEFAULT_ARCHIVE


def get_default_evidence_archive() -> NebiusEvidenceArchive | None:
    return _DEFAULT_ARCHIVE


def clear_default_evidence_archive() -> None:
    global _DEFAULT_ARCHIVE
    _DEFAULT_ARCHIVE = None


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "[REDACTED]" if _sensitive_key(str(key)) else _sanitize(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return _redact(value)
    return value


def _sensitive_key(value: str) -> bool:
    normalized = value.lower().replace("-", "_")
    return any(token in normalized for token in ("authorization", "api_key", "token", "secret", "access_key"))


def _redact(value: str | None) -> str:
    if not value:
        return ""
    redacted = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value)
    redacted = re.sub(
        r'(?i)(["\']?name["\']?\s*:\s*["\']AWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)["\']'
        r'\s*,\s*["\']?value["\']?\s*:\s*["\'])([^"\']+)(["\'])',
        lambda match: f"{match.group(1)}[REDACTED]{match.group(3)}",
        redacted,
    )
    redacted = re.sub(
        r'(?i)(["\']AWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)["\']'
        r'\s*:\s*["\'])([^"\']+)(["\'])',
        lambda match: f"{match.group(1)}[REDACTED]{match.group(3)}",
        redacted,
    )
    redacted = re.sub(
        r"(?i)(AWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)\s*=\s*)([^\s,\"']+)",
        r"\1[REDACTED]",
        redacted,
    )
    return re.sub(
        r"(?i)(api[_-]?key|token|secret|authorization)(\s*[:=]\s*)([^\s\"']+)",
        r"\1\2[REDACTED]",
        redacted,
    )


def _copy_redacted(source: Path, target: Path) -> None:
    try:
        contents = source.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        shutil.copy2(source, target)
        return
    target.write_text(_redact(contents), encoding="utf-8")


def _safe_name(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_.-]+", "_", value).strip("_") or "artifact"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _optional_nonnegative_float(value: Any) -> float | None:
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return _redact(value.strip())[:512]


def _elapsed_between(started_at: Any, finished_at: Any) -> float:
    if not isinstance(started_at, str) or not isinstance(finished_at, str):
        return 0.0
    try:
        started = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return round(max(0.0, (finished - started).total_seconds()), 6)


def _line_count(raw_path: str | None) -> int:
    if not raw_path:
        return 0
    path = Path(raw_path)
    if not path.is_file():
        return 0
    try:
        with path.open("rb") as handle:
            return sum(1 for _line in handle)
    except OSError:
        return 0


def measure_started_at() -> float:
    return time.perf_counter()


def elapsed_since(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 6)
