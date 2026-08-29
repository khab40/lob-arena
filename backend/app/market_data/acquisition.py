from __future__ import annotations

import gzip
import hashlib
import http.client
import json
import os
import re
import resource
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.market_data.public_sample import (
    DEVELOPMENT_BUCKET,
    OBJECT_STORAGE_ENDPOINT,
    PROJECT_ID,
    PUBLIC_SAMPLE_PREFIX,
    SOURCE_HOST,
    NasdaqPublicSource,
)
from app.ml.lightgbm.cloud_contracts import IMMUTABLE_IMAGE_PATTERN
from app.ml.lightgbm.contracts import GIT_COMMIT_PATTERN, IDENTIFIER_PATTERN, SHA256_PATTERN
from app.nebius.job_logging import JobLogger
from app.nebius.object_storage import (
    TransferLimits,
    download_s3_release,
    publish_local_result,
    publish_s3_result,
    sha256_file,
)


JOB_LOG = JobLogger("market-data-acquisition")
MAX_RESUME_REQUESTS = 3
CHUNK_BYTES = 8 * 1024 * 1024
QUARANTINE_DAYS = 3


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode()

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class AcquisitionResourceRequest(_StrictModel):
    platform: Literal["cpu-d3"] = "cpu-d3"
    preset: Literal["4vcpu-16gb"] = "4vcpu-16gb"
    cpu_count: Literal[4] = 4
    memory_gib: Literal[16] = 16
    disk_size_gib: Literal[100] = 100
    timeout_seconds: Literal[14400] = 14400
    gpu_count: Literal[0] = 0


class QuarantineLifecycleEvidence(_StrictModel):
    bucket_id: str = Field(pattern=r"^storagebucket-[A-Za-z0-9]+$")
    bucket_resource_version: str = Field(min_length=1)
    prefix: Literal["data/public-sample-v1/quarantine/nasdaq/"]
    expiration_days: Literal[3] = QUARANTINE_DAYS
    observed_at: AwareDatetime
    policy_sha256: str = Field(pattern=SHA256_PATTERN)


class NasdaqAcquisitionRequest(_StrictModel):
    schema_version: Literal["market_data_wave1_acquisition_request_v1"] = (
        "market_data_wave1_acquisition_request_v1"
    )
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    sequence_number: int = Field(ge=1, le=7)
    project_id: Literal["project-e00g6zvxpr00waz8t3y51k"] = PROJECT_ID
    region: Literal["eu-north1"] = "eu-north1"
    image: str = Field(pattern=IMMUTABLE_IMAGE_PATTERN)
    git_commit: str = Field(pattern=GIT_COMMIT_PATTERN)
    created_at: AwareDatetime
    source: NasdaqPublicSource
    lifecycle: QuarantineLifecycleEvidence
    quarantine_uri: str
    resource: AcquisitionResourceRequest = Field(default_factory=AcquisitionResourceRequest)
    max_resume_requests: Literal[3] = MAX_RESUME_REQUESTS
    max_download_bytes: int = Field(gt=0)
    restart_policy: Literal["never"] = "never"

    @model_validator(mode="after")
    def validate_boundaries(self) -> "NasdaqAcquisitionRequest":
        if self.max_download_bytes != self.source.expected_content_length:
            raise ValueError("acquisition byte ceiling must equal the declared source length")
        date_path = self.source.date.isoformat()
        expected = (
            f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
            f"quarantine/nasdaq/{date_path}/{self.run_id}"
        )
        if self.quarantine_uri != expected:
            raise ValueError("acquisition quarantine URI escaped the exact run prefix")
        return self


class NasdaqSourceReleaseManifest(_StrictModel):
    schema_version: Literal["nasdaq_source_release_v1"] = "nasdaq_source_release_v1"
    run_id: str
    source_filename: str
    source_url: str
    trade_date: str
    fold: Literal["train", "validation", "test"]
    expected_size_bytes: int
    observed_size_bytes: int
    sha256: str = Field(pattern=SHA256_PATTERN)
    etag: str | None = None
    last_modified: str | None = None
    http_request_count: int = Field(ge=1, le=MAX_RESUME_REQUESTS)
    resumed: bool
    gzip_verified: Literal[True] = True
    quarantine_expires_after_days: Literal[3] = QUARANTINE_DAYS
    acquired_at: AwareDatetime
    source_type: Literal["nasdaq_itch"] = "nasdaq_itch"
    redistribution_status: Literal["private_research_quarantine"] = (
        "private_research_quarantine"
    )


class AcquisitionRuntimeEvidence(_StrictModel):
    schema_version: Literal["nasdaq_acquisition_runtime_v1"] = (
        "nasdaq_acquisition_runtime_v1"
    )
    run_id: str
    elapsed_seconds: float = Field(gt=0, allow_inf_nan=False)
    downloaded_bytes: int = Field(gt=0)
    bytes_per_second: float = Field(gt=0, allow_inf_nan=False)
    peak_rss_bytes: int = Field(gt=0)
    http_request_count: int = Field(ge=1, le=MAX_RESUME_REQUESTS)


class AcquisitionCampaignState(_StrictModel):
    schema_version: Literal["market_data_wave1_acquisition_campaign_v1"] = (
        "market_data_wave1_acquisition_campaign_v1"
    )
    campaign_id: Literal["public-sample-v1"] = "public-sample-v1"
    ordered_filenames: tuple[str, ...]
    successful_filenames: tuple[str, ...] = ()
    failed_filename: str | None = None
    jobs_consumed: int = Field(default=0, ge=0, le=15)
    stopped: bool = False

    @model_validator(mode="after")
    def validate_sequence(self) -> "AcquisitionCampaignState":
        if len(self.ordered_filenames) != 7 or len(set(self.ordered_filenames)) != 7:
            raise ValueError("acquisition campaign requires the exact seven-source order")
        if self.successful_filenames != self.ordered_filenames[: len(self.successful_filenames)]:
            raise ValueError("successful acquisition files must form an ordered prefix")
        if self.failed_filename is not None:
            next_index = len(self.successful_filenames)
            if next_index >= 7 or self.failed_filename != self.ordered_filenames[next_index]:
                raise ValueError("failed acquisition must be the next sequential source")
            if not self.stopped:
                raise ValueError("an acquisition failure must stop the campaign")
        if self.jobs_consumed < len(self.successful_filenames) + int(self.failed_filename is not None):
            raise ValueError("acquisition Job count is inconsistent with terminal outcomes")
        return self

    def next_filename(self) -> str:
        if self.stopped or self.failed_filename or len(self.successful_filenames) == 7:
            raise ValueError("acquisition campaign has no authorized next source")
        if self.jobs_consumed >= 15:
            raise ValueError("public-data Job cap is exhausted")
        return self.ordered_filenames[len(self.successful_filenames)]

    def record(self, filename: str, *, succeeded: bool) -> "AcquisitionCampaignState":
        if filename != self.next_filename():
            raise ValueError("acquisition result is out of sequence")
        return AcquisitionCampaignState.model_validate(
            {
                **self.model_dump(mode="python"),
                "successful_filenames": (
                    (*self.successful_filenames, filename)
                    if succeeded
                    else self.successful_filenames
                ),
                "failed_filename": None if succeeded else filename,
                "jobs_consumed": self.jobs_consumed + 1,
                "stopped": not succeeded,
            }
        )


DownloadFunction = Callable[[NasdaqPublicSource, Path, int], tuple[int, str | None, str | None]]


def execute_acquisition(
    request_path: Path,
    *,
    result_root: Path,
    downloader: DownloadFunction | None = None,
) -> Path:
    request = NasdaqAcquisitionRequest.model_validate_json(
        request_path.read_text(encoding="utf-8")
    )
    wall_start = time.perf_counter()
    result_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{request.run_id}.", dir=result_root.parent))
    source_path = staging / request.source.filename
    try:
        JOB_LOG.info(
            "acquisition.started",
            "Download one exact allowlisted Nasdaq source into private short-lived quarantine.",
            run_id=request.run_id,
            filename=request.source.filename,
            expected_bytes=request.source.expected_content_length,
        )
        request_count, etag, last_modified = (downloader or download_nasdaq_source)(
            request.source, source_path, request.max_resume_requests
        )
        if source_path.stat().st_size != request.source.expected_content_length:
            raise ValueError("downloaded Nasdaq source length does not match its declaration")
        _verify_gzip(source_path)
        manifest = NasdaqSourceReleaseManifest(
            run_id=request.run_id,
            source_filename=request.source.filename,
            source_url=request.source.url,
            trade_date=request.source.date.isoformat(),
            fold=request.source.fold,
            expected_size_bytes=request.source.expected_content_length,
            observed_size_bytes=source_path.stat().st_size,
            sha256=sha256_file(source_path),
            etag=etag,
            last_modified=last_modified,
            http_request_count=request_count,
            resumed=request_count > 1,
            acquired_at=datetime.now(UTC),
        )
        (staging / "request.json").write_bytes(request.canonical_bytes())
        (staging / "source.json").write_bytes(manifest.canonical_bytes())
        elapsed = time.perf_counter() - wall_start
        runtime = AcquisitionRuntimeEvidence(
            run_id=request.run_id,
            elapsed_seconds=elapsed,
            downloaded_bytes=source_path.stat().st_size,
            bytes_per_second=source_path.stat().st_size / elapsed,
            peak_rss_bytes=_peak_rss_bytes(),
            http_request_count=request_count,
        )
        (staging / "runtime.json").write_bytes(runtime.canonical_bytes())
        published = publish_local_result(staging, result_root.resolve().as_uri())
        JOB_LOG.info(
            "acquisition.completed",
            "The exact source passed length, SHA-256, and gzip verification and is ready for private quarantine publication.",
            run_id=request.run_id,
            filename=request.source.filename,
            sha256=manifest.sha256,
        )
        return published
    except Exception:
        if staging.exists():
            for child in staging.iterdir():
                if child.is_file():
                    child.unlink(missing_ok=True)
            staging.rmdir()
        raise


def _peak_rss_bytes() -> int:
    observed = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # Linux reports KiB; macOS reports bytes. Nebius Jobs run on Linux.
    return int(observed if sys.platform == "darwin" else observed * 1024)


def execute_acquisition_s3(
    input_uri: str,
    *,
    work_root: Path,
    endpoint_url: str = OBJECT_STORAGE_ENDPOINT,
) -> dict[str, object]:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("acquisition requires the approved eu-north1 endpoint")
    _require_environment()
    pattern = (
        rf"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
        r"acquisition-requests/[a-z0-9][a-z0-9-]{2,62}/staging"
    )
    if re.fullmatch(pattern, input_uri.rstrip("/")) is None:
        raise ValueError("acquisition input escaped its exact request prefix")
    work_root = work_root.resolve()
    if str(work_root) in {"/", str(Path.home().resolve())}:
        raise ValueError("acquisition work root is too broad")
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="market-data-acquire-", dir=work_root) as value:
        stage = Path(value)
        input_root = stage / "input"
        download_s3_release(
            input_uri,
            input_root,
            endpoint_url=endpoint_url,
            limits=TransferLimits(max_files=8, max_bytes=1024 * 1024),
        )
        request_path = input_root / "request.json"
        request = NasdaqAcquisitionRequest.model_validate_json(
            request_path.read_text(encoding="utf-8")
        )
        expected_input = (
            f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
            f"acquisition-requests/{request.run_id}/staging"
        )
        if input_uri.rstrip("/") != expected_input:
            raise ValueError("acquisition input does not match the request run ID")
        _verify_job_context(request)
        local_result = stage / "quarantine"
        execute_acquisition(request_path, result_root=local_result)
        objects = publish_s3_result(
            local_result,
            request.quarantine_uri,
            endpoint_url=endpoint_url,
            require_version_ids=True,
        )
        source_key = f"{request.quarantine_uri.split('/', maxsplit=3)[-1]}/{request.source.filename}"
        source_objects = [item for item in objects if item.key == source_key]
        if len(source_objects) != 1 or not source_objects[0].version_id:
            raise ValueError("quarantine publication did not expose a versioned source object")
        evidence = {
            "schema_version": "nasdaq_quarantine_publication_v1",
            "run_id": request.run_id,
            "quarantine_uri": request.quarantine_uri,
            "source_sha256": next(
                item.sha256 for item in objects if item.key == source_key
            ),
            "source_object_version_id": source_objects[0].version_id,
            "lifecycle_policy_sha256": request.lifecycle.policy_sha256,
            "lifecycle_expiration_days": request.lifecycle.expiration_days,
            "objects": [item.__dict__ for item in objects],
            "success_published_last": objects[-1].key.endswith("/SUCCESS"),
        }
        JOB_LOG.info(
            "acquisition.published",
            "Publish the verified source to versioned private quarantine with SUCCESS last.",
            run_id=request.run_id,
            source_object_version_id=source_objects[0].version_id,
            object_count=len(objects),
        )
        return evidence


def download_nasdaq_source(
    source: NasdaqPublicSource,
    destination: Path,
    max_requests: int = MAX_RESUME_REQUESTS,
) -> tuple[int, str | None, str | None]:
    if not 1 <= max_requests <= MAX_RESUME_REQUESTS:
        raise ValueError("Nasdaq resume request ceiling is invalid")
    parsed = urlsplit(source.url)
    expected_path = "/ITCH/Nasdaq%20ITCH/" + quote(source.filename, safe="._-")
    if (
        parsed.scheme != "https"
        or parsed.hostname != SOURCE_HOST
        or parsed.port is not None
        or parsed.path != expected_path
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Nasdaq acquisition URL escaped the exact allowlist")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(f".{destination.name}.part")
    partial.unlink(missing_ok=True)
    request_count = 0
    etag: str | None = None
    last_modified: str | None = None
    try:
        while (partial.stat().st_size if partial.exists() else 0) < source.expected_content_length:
            offset = partial.stat().st_size if partial.exists() else 0
            if request_count >= max_requests:
                raise RuntimeError("Nasdaq download exhausted its bounded resume requests")
            request_count += 1
            connection = http.client.HTTPSConnection(SOURCE_HOST, timeout=60)
            headers = {"Host": SOURCE_HOST, "User-Agent": "lob-arena-acquisition/1"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            try:
                connection.request("GET", parsed.path, headers=headers)
                response = connection.getresponse()
                expected_status = 206 if offset else 200
                if response.status != expected_status:
                    if response.status in {301, 302, 303, 307, 308}:
                        raise ValueError("Nasdaq acquisition refuses redirects")
                    raise ValueError(f"Nasdaq acquisition returned status {response.status}")
                remaining = source.expected_content_length - offset
                length = response.getheader("Content-Length")
                if length is None or not length.isdigit() or int(length) != remaining:
                    raise ValueError("Nasdaq acquisition response length changed")
                if offset:
                    expected_range = f"bytes {offset}-{source.expected_content_length - 1}/{source.expected_content_length}"
                    if response.getheader("Content-Range") != expected_range:
                        raise ValueError("Nasdaq resume response has an invalid Content-Range")
                current_etag = _bounded_header(response.getheader("ETag"))
                current_modified = _bounded_header(response.getheader("Last-Modified"))
                if etag is not None and current_etag != etag:
                    raise ValueError("Nasdaq source ETag changed during resume")
                if last_modified is not None and current_modified != last_modified:
                    raise ValueError("Nasdaq source Last-Modified changed during resume")
                etag = current_etag
                last_modified = current_modified
                with partial.open("ab") as handle:
                    while chunk := response.read(CHUNK_BYTES):
                        handle.write(chunk)
                        if handle.tell() > source.expected_content_length:
                            raise ValueError("Nasdaq download exceeded its exact byte ceiling")
            except (http.client.IncompleteRead, TimeoutError, OSError):
                continue
            finally:
                connection.close()
        if partial.stat().st_size != source.expected_content_length:
            raise ValueError("Nasdaq download ended before its declared length")
        os.replace(partial, destination)
        return request_count, etag, last_modified
    except Exception:
        partial.unlink(missing_ok=True)
        raise


def _verify_gzip(path: Path) -> None:
    try:
        with gzip.open(path, "rb") as handle:
            while handle.read(CHUNK_BYTES):
                pass
    except (OSError, EOFError) as exc:
        raise ValueError("Nasdaq source failed gzip integrity verification") from exc


def _bounded_header(value: str | None) -> str | None:
    if value is None:
        return None
    result = value.strip()
    if not result or len(result) > 256 or "\n" in result or "\r" in result:
        raise ValueError("Nasdaq acquisition returned invalid bounded metadata")
    return result


def _require_environment() -> None:
    if any(not os.environ.get(name, "").strip() for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")):
        raise RuntimeError("acquisition requires MysteryBox-injected AWS credentials")
    if os.environ.get("AWS_DEFAULT_REGION") != "eu-north1":
        raise RuntimeError("acquisition AWS region must be eu-north1")
    if os.environ.get("AWS_EC2_METADATA_DISABLED", "").lower() != "true":
        raise RuntimeError("acquisition requires AWS_EC2_METADATA_DISABLED=true")


def _verify_job_context(request: NasdaqAcquisitionRequest) -> None:
    repository, digest = request.image.rsplit("@sha256:", maxsplit=1)
    expected = {
        "MARKET_DATA_ACTUAL_PROJECT_ID": request.project_id,
        "MARKET_DATA_ACTUAL_IMAGE_REPOSITORY": repository,
        "MARKET_DATA_ACTUAL_IMAGE_SHA256": digest,
        "MARKET_DATA_ACTUAL_PLATFORM": request.resource.platform,
        "MARKET_DATA_ACTUAL_PRESET": request.resource.preset,
        "MARKET_DATA_ACTUAL_DISK_SIZE_GIB": str(request.resource.disk_size_gib),
        "MARKET_DATA_ACTUAL_TIMEOUT_SECONDS": str(request.resource.timeout_seconds),
    }
    if any(os.environ.get(name, "").strip() != value for name, value in expected.items()):
        raise RuntimeError("acquisition Job context does not match its reviewed request")
