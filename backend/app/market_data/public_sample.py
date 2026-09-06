from __future__ import annotations

import hashlib
import http.client
import json
import os
import re
import tempfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import quote, urlsplit

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.ml.lightgbm.cloud_contracts import CloudArtifact, IMMUTABLE_IMAGE_PATTERN
from app.ml.lightgbm.contracts import GIT_COMMIT_PATTERN, IDENTIFIER_PATTERN, SHA256_PATTERN
from app.nebius.job_logging import JobLogger
from app.nebius.object_storage import (
    TransferLimits,
    _aws_json,
    _s3_bucket_prefix,
    download_s3_release,
    inventory_directory,
    publish_local_result,
    publish_s3_result,
    sha256_file,
    verify_complete_result,
)


SOURCE_HOST = "emi.nasdaq.com"
BASE_URL = "https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/"
OBJECT_STORAGE_ENDPOINT = "https://storage.eu-north1.nebius.cloud"
PROJECT_ID = "project-e00g6zvxpr00waz8t3y51k"
DEVELOPMENT_BUCKET = "aimada-wave1-dev-e00g6zvxpr00"
PUBLIC_SAMPLE_PREFIX = "data/public-sample-v1"
C0_PREFLIGHTED_SOURCES = {
    "01302019.NASDAQ_ITCH50.gz": (date(2019, 1, 30), "train", 4_764_426_091),
    "03272019.NASDAQ_ITCH50.gz": (date(2019, 3, 27), "train", 5_510_131_732),
    "07302019.NASDAQ_ITCH50.gz": (date(2019, 7, 30), "train", 3_662_140_094),
    "08302019.NASDAQ_ITCH50.gz": (date(2019, 8, 30), "train", 4_075_649_457),
    "10302019.NASDAQ_ITCH50.gz": (date(2019, 10, 30), "validation", 3_872_931_242),
    "12302019.NASDAQ_ITCH50.gz": (date(2019, 12, 30), "test", 3_524_013_057),
    "01302020.NASDAQ_ITCH50.gz": (date(2020, 1, 30), "test", 5_597_158_940),
}
EXPECTED_SOURCES = {
    filename: C0_PREFLIGHTED_SOURCES[filename]
    for filename in (
        "01302019.NASDAQ_ITCH50.gz",
        "03272019.NASDAQ_ITCH50.gz",
        "10302019.NASDAQ_ITCH50.gz",
        "12302019.NASDAQ_ITCH50.gz",
    )
}
EXPECTED_TOTAL_BYTES = 17_671_502_122
LEGACY_PREFLIGHT_TOTAL_BYTES = 31_006_450_613
JOB_LOG = JobLogger("market-data-wave1")


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class NasdaqPublicSource(_StrictModel):
    filename: str
    date: date
    fold: Literal["train", "validation", "test"]
    url: str
    expected_content_length: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_allowlist_entry(self) -> "NasdaqPublicSource":
        expected = C0_PREFLIGHTED_SOURCES.get(self.filename)
        if expected != (self.date, self.fold, self.expected_content_length):
            raise ValueError("source entry is not in the exact approved Nasdaq allowlist")
        if self.url != BASE_URL + self.filename:
            raise ValueError("source URL does not match the exact approved Nasdaq path")
        return self


class NasdaqPublicSampleConfig(_StrictModel):
    schema_version: Literal["nasdaq_public_sample_source_config_v1"]
    source_host: Literal["emi.nasdaq.com"]
    base_url: Literal["https://emi.nasdaq.com/ITCH/Nasdaq%20ITCH/"]
    instruments: tuple[Literal["AAPL", "MSFT", "NVDA"], ...]
    window_start_et: Literal["10:00:00"]
    window_end_et: Literal["10:30:00"]
    depth_levels: Literal[10]
    total_expected_bytes: Literal[17_671_502_122, 31_006_450_613]
    sources: tuple[NasdaqPublicSource, ...]

    @model_validator(mode="after")
    def validate_complete_allowlist(self) -> "NasdaqPublicSampleConfig":
        if self.instruments != ("AAPL", "MSFT", "NVDA"):
            raise ValueError("instruments must be the approved ordered AAPL/MSFT/NVDA set")
        filenames = tuple(item.filename for item in self.sources)
        active = filenames == tuple(EXPECTED_SOURCES)
        legacy_preflight = filenames == tuple(C0_PREFLIGHTED_SOURCES)
        if not active and not legacy_preflight:
            raise ValueError("source config must contain the active four-file corpus")
        if len({item.date for item in self.sources}) != len(self.sources):
            raise ValueError("source dates must be unique")
        expected_total = EXPECTED_TOTAL_BYTES if active else LEGACY_PREFLIGHT_TOTAL_BYTES
        if (
            self.total_expected_bytes != expected_total
            or sum(item.expected_content_length for item in self.sources) != expected_total
        ):
            raise ValueError("source content lengths do not match the approved total")
        folds = [item.fold for item in self.sources]
        expected_fold_counts = (2, 1, 1) if active else (4, 1, 2)
        if tuple(folds.count(name) for name in ("train", "validation", "test")) != expected_fold_counts:
            raise ValueError("source folds do not match the approved chronology")
        return self


class MarketDataResourceRequest(_StrictModel):
    platform: Literal["cpu-d3"] = "cpu-d3"
    preset: Literal["4vcpu-16gb"] = "4vcpu-16gb"
    cpu_count: Literal[4] = 4
    memory_gib: Literal[16] = 16
    disk_size_gib: Literal[100] = 100
    timeout_seconds: Literal[3600] = 3600
    gpu_count: Literal[0] = 0


class C0PreflightRequest(_StrictModel):
    schema_version: Literal["market_data_wave1_c0_request_v1"] = "market_data_wave1_c0_request_v1"
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    project_id: Literal["project-e00g6zvxpr00waz8t3y51k"] = PROJECT_ID
    region: Literal["eu-north1"] = "eu-north1"
    image: str = Field(pattern=IMMUTABLE_IMAGE_PATTERN)
    git_commit: str = Field(pattern=GIT_COMMIT_PATTERN)
    created_at: AwareDatetime
    source_config: CloudArtifact
    s3_endpoint_url: Literal["https://storage.eu-north1.nebius.cloud"] = OBJECT_STORAGE_ENDPOINT
    s3_probe_uri: str
    result_uri: str
    resource: MarketDataResourceRequest = Field(default_factory=MarketDataResourceRequest)
    max_http_requests: Literal[4, 7] = 4
    max_http_body_bytes: Literal[0] = 0
    probe_size_limit_bytes: Literal[256] = 256

    @model_validator(mode="after")
    def validate_boundaries(self) -> "C0PreflightRequest":
        if self.source_config.uri != "nasdaq-public-sample-v1.json":
            raise ValueError("C0 source config must use the canonical staged path")
        expected_base = f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/preflight/{self.run_id}"
        if self.s3_probe_uri != f"{expected_base}/probe/probe.bin":
            raise ValueError("C0 probe URI must be the exact disposable object key")
        if self.result_uri != f"{expected_base}/result":
            raise ValueError("C0 result URI must use the exact immutable result prefix")
        return self


class HttpHeadEvidence(_StrictModel):
    filename: str
    status: Literal[200]
    content_length: int = Field(gt=0)
    etag: str | None = None
    last_modified: str | None = None
    redirect_followed: Literal[False] = False
    response_body_bytes: Literal[0] = 0


class S3ProbeEvidence(_StrictModel):
    uri: str
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(gt=0, le=256)
    etag: str = Field(min_length=1, max_length=256)
    read_back_verified: Literal[True] = True
    deleted: Literal[True] = True
    deletion_verified: Literal[True] = True


class C0PreflightEvidence(_StrictModel):
    schema_version: Literal["market_data_wave1_c0_evidence_v1"] = "market_data_wave1_c0_evidence_v1"
    run_id: str
    created_at: AwareDatetime
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    source_config_sha256: str = Field(pattern=SHA256_PATTERN)
    source_host: Literal["emi.nasdaq.com"] = SOURCE_HOST
    http_request_count: Literal[4, 7]
    http_body_bytes: Literal[0]
    sources: tuple[HttpHeadEvidence, ...]
    s3_probe: S3ProbeEvidence
    gates: dict[str, bool]
    disposition: Literal["c0_preflight_passed"] = "c0_preflight_passed"

    @model_validator(mode="after")
    def validate_gates(self) -> "C0PreflightEvidence":
        if (
            len(self.sources) != self.http_request_count
            or not self.gates
            or not all(self.gates.values())
        ):
            raise ValueError("C0 evidence requires all bounded preflight gates")
        return self


HeadRequester = Callable[[NasdaqPublicSource], HttpHeadEvidence]
S3Prober = Callable[[str, str, int], S3ProbeEvidence]


def load_source_config(path: Path) -> NasdaqPublicSampleConfig:
    return NasdaqPublicSampleConfig.model_validate_json(path.read_text(encoding="utf-8"))


def verify_c0_result(path: Path) -> C0PreflightEvidence:
    verify_complete_result(path)
    evidence_path = path / "preflight-evidence.json"
    request_path = path / "request.json"
    config_path = path / "source-config.json"
    if not evidence_path.is_file() or not request_path.is_file() or not config_path.is_file():
        raise ValueError("C0 result is missing its canonical evidence set")
    evidence = C0PreflightEvidence.model_validate_json(evidence_path.read_text(encoding="utf-8"))
    request = C0PreflightRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    config = load_source_config(config_path)
    if evidence.run_id != request.run_id or evidence.request_sha256 != request.canonical_hash():
        raise ValueError("C0 result is not bound to its request")
    if evidence.source_config_sha256 != config.canonical_hash():
        raise ValueError("C0 result is not bound to its source config")
    if evidence.http_body_bytes != 0 or any(item.response_body_bytes for item in evidence.sources):
        raise ValueError("C0 result reports a forbidden Nasdaq response body")
    return evidence


def execute_c0_preflight(
    request_path: Path,
    *,
    input_root: Path,
    result_root: Path,
    head_requester: HeadRequester | None = None,
    s3_prober: S3Prober | None = None,
) -> Path:
    request = C0PreflightRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    source_path = _verify_cloud_artifact(input_root, request.source_config)
    config = load_source_config(source_path)
    head = head_requester or _head_source
    probe = s3_prober or _probe_s3_object
    JOB_LOG.info(
        "c0.started",
        "Verify the exact Nasdaq allowlist with HEAD only and exercise one disposable prefix-scoped S3 object.",
        run_id=request.run_id,
        source_count=len(config.sources),
        max_http_body_bytes=request.max_http_body_bytes,
    )
    sources: list[HttpHeadEvidence] = []
    for source in config.sources:
        evidence = head(source)
        if evidence.filename != source.filename:
            raise ValueError("Nasdaq HEAD evidence is out of allowlist order")
        if evidence.content_length != source.expected_content_length:
            raise ValueError(f"declared Nasdaq content length changed: {source.filename}")
        sources.append(evidence)
    probe_payload = f"lob-arena-c0:{request.run_id}\n"
    if len(probe_payload.encode("utf-8")) > request.probe_size_limit_bytes:
        raise ValueError("C0 probe payload exceeds its fixed byte ceiling")
    s3_evidence = probe(request.s3_probe_uri, probe_payload, request.probe_size_limit_bytes)
    if (
        s3_evidence.uri != request.s3_probe_uri
        or s3_evidence.size_bytes > request.probe_size_limit_bytes
    ):
        raise ValueError("C0 S3 probe evidence escaped the reviewed boundary")
    gates = {
        "exact_allowlist": {item.filename for item in config.sources} == set(EXPECTED_SOURCES),
        "https_head_only": all(item.response_body_bytes == 0 for item in sources),
        "no_redirects": all(item.redirect_followed is False for item in sources),
        "declared_lengths_match": all(
            observed.content_length == declared.expected_content_length
            for observed, declared in zip(sources, config.sources, strict=True)
        ),
        "request_ceiling_preserved": len(sources) == request.max_http_requests,
        "s3_read_back_verified": s3_evidence.read_back_verified,
        "s3_probe_deleted": s3_evidence.deleted and s3_evidence.deletion_verified,
        "no_market_data_body_downloaded": request.max_http_body_bytes == 0,
    }
    evidence = C0PreflightEvidence(
        run_id=request.run_id,
        created_at=datetime.now(UTC),
        request_sha256=request.canonical_hash(),
        source_config_sha256=config.canonical_hash(),
        http_request_count=len(sources),
        http_body_bytes=0,
        sources=tuple(sources),
        s3_probe=s3_evidence,
        gates=gates,
    )
    result_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{request.run_id}.", dir=result_root.parent))
    (staging / "request.json").write_bytes(request.canonical_bytes())
    (staging / "source-config.json").write_bytes(config.canonical_bytes())
    (staging / "preflight-evidence.json").write_bytes(evidence.canonical_bytes())
    published = publish_local_result(staging, result_root.resolve().as_uri())
    JOB_LOG.info(
        "c0.completed",
        "The bounded C0 preflight passed without downloading a Nasdaq market-data body.",
        run_id=request.run_id,
        http_request_count=len(sources),
        http_body_bytes=0,
    )
    return published


def execute_c0_s3(
    input_uri: str,
    *,
    work_root: Path,
    endpoint_url: str = OBJECT_STORAGE_ENDPOINT,
) -> str:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("C0 requires the approved eu-north1 Object Storage endpoint")
    _require_c0_environment()
    if re.fullmatch(
        rf"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/preflight-requests/"
        r"[a-z0-9][a-z0-9-]{2,62}/staging",
        input_uri.rstrip("/"),
    ) is None:
        raise ValueError("C0 input URI is outside the exact preflight-request prefix")
    work_root = work_root.resolve()
    if str(work_root) in {"/", str(Path.home().resolve())}:
        raise ValueError("C0 work root is too broad")
    input_root = work_root / "input"
    local_result = work_root / "result"
    download_s3_release(
        input_uri,
        input_root,
        endpoint_url=endpoint_url,
        limits=TransferLimits(max_files=8, max_bytes=1024 * 1024),
    )
    request = C0PreflightRequest.model_validate_json(
        (input_root / "request.json").read_text(encoding="utf-8")
    )
    expected_input_uri = (
        f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
        f"preflight-requests/{request.run_id}/staging"
    )
    if input_uri.rstrip("/") != expected_input_uri:
        raise ValueError("C0 input release does not match the request run ID")
    _verify_c0_job_context(request)
    execute_c0_preflight(
        input_root / "request.json",
        input_root=input_root,
        result_root=local_result,
    )
    publish_s3_result(local_result, request.result_uri, endpoint_url=endpoint_url)
    return request.result_uri


def _head_source(source: NasdaqPublicSource) -> HttpHeadEvidence:
    parsed = urlsplit(source.url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != SOURCE_HOST
        or parsed.port is not None
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("Nasdaq source escaped the approved HTTPS origin")
    expected_path = "/ITCH/Nasdaq%20ITCH/" + quote(source.filename, safe="._-")
    if parsed.path != expected_path:
        raise ValueError("Nasdaq source escaped the approved path allowlist")
    connection = http.client.HTTPSConnection(SOURCE_HOST, timeout=30)
    try:
        connection.request(
            "HEAD",
            parsed.path,
            headers={"Host": SOURCE_HOST, "User-Agent": "lob-arena-c0-preflight/1"},
        )
        response = connection.getresponse()
        if response.status != 200:
            if response.status in {301, 302, 303, 307, 308}:
                raise ValueError("Nasdaq preflight refuses redirects")
            raise ValueError(f"Nasdaq HEAD failed with bounded status {response.status}")
        length_value = response.getheader("Content-Length")
        if length_value is None or not length_value.isdigit():
            raise ValueError("Nasdaq HEAD omitted a canonical Content-Length")
        return HttpHeadEvidence(
            filename=source.filename,
            status=200,
            content_length=int(length_value),
            etag=_bounded_header(response.getheader("ETag")),
            last_modified=_bounded_header(response.getheader("Last-Modified")),
        )
    finally:
        connection.close()


def _probe_s3_object(uri: str, payload: str, max_bytes: int) -> S3ProbeEvidence:
    content = payload.encode("utf-8")
    if not 0 < len(content) <= max_bytes <= 256:
        raise ValueError("C0 S3 probe payload exceeds its fixed byte limit")
    bucket, key = _s3_bucket_prefix(uri)
    expected_prefix = f"{PUBLIC_SAMPLE_PREFIX}/preflight/"
    if (
        bucket != DEVELOPMENT_BUCKET
        or not key.startswith(expected_prefix)
        or not key.endswith("/probe/probe.bin")
    ):
        raise ValueError("C0 S3 probe key is outside the disposable allowlist")
    digest = hashlib.sha256(content).hexdigest()
    with tempfile.TemporaryDirectory(prefix="market-data-c0-probe-") as directory:
        source = Path(directory) / "probe.bin"
        target = Path(directory) / "readback.bin"
        source.write_bytes(content)
        uploaded = False
        try:
            _aws_json(
                OBJECT_STORAGE_ENDPOINT,
                "s3api",
                "put-object",
                "--bucket",
                bucket,
                "--key",
                key,
                "--body",
                str(source),
                "--metadata",
                f"sha256={digest},purpose=c0-disposable-probe",
            )
            uploaded = True
            head = _aws_json(
                OBJECT_STORAGE_ENDPOINT,
                "s3api",
                "head-object",
                "--bucket",
                bucket,
                "--key",
                key,
            )
            metadata = {str(name).lower(): value for name, value in (head.get("Metadata") or {}).items()}
            if int(head.get("ContentLength", -1)) != len(content) or metadata.get("sha256") != digest:
                raise ValueError("C0 S3 probe metadata read-back mismatch")
            _aws_json(
                OBJECT_STORAGE_ENDPOINT,
                "s3api",
                "get-object",
                "--bucket",
                bucket,
                "--key",
                key,
                str(target),
            )
            if sha256_file(target) != digest:
                raise ValueError("C0 S3 probe body read-back mismatch")
            _aws_json(
                OBJECT_STORAGE_ENDPOINT,
                "s3api",
                "delete-object",
                "--bucket",
                bucket,
                "--key",
                key,
            )
            uploaded = False
            listing = _aws_json(
                OBJECT_STORAGE_ENDPOINT,
                "s3api",
                "list-objects-v2",
                "--bucket",
                bucket,
                "--prefix",
                key,
                "--max-keys",
                "1",
            )
            if any(item.get("Key") == key for item in listing.get("Contents", ()) if isinstance(item, dict)):
                raise ValueError("C0 S3 probe deletion was not observable")
            return S3ProbeEvidence(
                uri=uri,
                sha256=digest,
                size_bytes=len(content),
                etag=str(head.get("ETag", "")).strip('"'),
            )
        finally:
            if uploaded:
                try:
                    _aws_json(
                        OBJECT_STORAGE_ENDPOINT,
                        "s3api",
                        "delete-object",
                        "--bucket",
                        bucket,
                        "--key",
                        key,
                    )
                except Exception:
                    JOB_LOG.error(
                        "c0.probe_cleanup_failed",
                        "The disposable C0 probe could not be removed; stop and inspect the exact key.",
                        key=key,
                    )


def _verify_cloud_artifact(root: Path, artifact: CloudArtifact) -> Path:
    root = root.resolve()
    path = (root / PurePosixPath(artifact.uri)).resolve()
    if root not in path.parents or not path.is_file():
        raise ValueError("C0 source config is missing or outside the input root")
    if path.stat().st_size != artifact.size_bytes or sha256_file(path) != artifact.sha256:
        raise ValueError("C0 source config integrity failed")
    return path


def _bounded_header(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or len(stripped) > 256 or "\n" in stripped or "\r" in stripped:
        raise ValueError("Nasdaq HEAD returned an invalid bounded metadata header")
    return stripped


def _require_c0_environment() -> None:
    missing = [
        name
        for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise RuntimeError("C0 requires MysteryBox-injected AWS credential environment values")
    if os.environ.get("AWS_DEFAULT_REGION") != "eu-north1":
        raise RuntimeError("C0 AWS_DEFAULT_REGION must be eu-north1")
    if os.environ.get("AWS_EC2_METADATA_DISABLED", "").lower() != "true":
        raise RuntimeError("C0 requires AWS_EC2_METADATA_DISABLED=true")


def _verify_c0_job_context(request: C0PreflightRequest) -> None:
    expected = {
        "MARKET_DATA_ACTUAL_PROJECT_ID": request.project_id,
        "MARKET_DATA_ACTUAL_PLATFORM": request.resource.platform,
        "MARKET_DATA_ACTUAL_PRESET": request.resource.preset,
        "MARKET_DATA_ACTUAL_DISK_SIZE_GIB": str(request.resource.disk_size_gib),
        "MARKET_DATA_ACTUAL_TIMEOUT_SECONDS": str(request.resource.timeout_seconds),
    }
    for name, value in expected.items():
        if os.environ.get(name, "").strip() != value:
            raise RuntimeError("C0 Job context does not match the reviewed request")
    repository, digest = request.image.rsplit("@sha256:", maxsplit=1)
    if (
        len(repository) > 64
        or os.environ.get("MARKET_DATA_ACTUAL_IMAGE_REPOSITORY", "").strip() != repository
        or os.environ.get("MARKET_DATA_ACTUAL_IMAGE_SHA256", "").strip() != digest
    ):
        raise RuntimeError("C0 Job image context does not match the reviewed request")


def config_artifact(path: Path) -> CloudArtifact:
    return CloudArtifact(
        logical_name="nasdaq_public_sample_config",
        uri="nasdaq-public-sample-v1.json",
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def package_inventory_hash(path: Path) -> str:
    payload = inventory_directory(path).model_dump(mode="json")
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
