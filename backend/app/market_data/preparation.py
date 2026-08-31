from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from collections.abc import Callable
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.data_ingestion.itch import convert_itch_symbols
from app.data_ingestion.models import DatasetManifest
from app.evaluation.canonical_bundle import CanonicalJavaReplayManifest
from app.market_data.acquisition import (
    AcquisitionResourceRequest,
    NasdaqSourceReleaseManifest,
    _require_environment,
    _verify_gzip,
)
from app.market_data.public_sample import (
    DEVELOPMENT_BUCKET,
    OBJECT_STORAGE_ENDPOINT,
    PROJECT_ID,
    PUBLIC_SAMPLE_PREFIX,
    NasdaqPublicSource,
)
from app.market_data.replay_export import export_replay_comparison
from app.ml.lightgbm.cloud_contracts import IMMUTABLE_IMAGE_PATTERN
from app.ml.lightgbm.contracts import GIT_COMMIT_PATTERN, IDENTIFIER_PATTERN, SHA256_PATTERN
from app.nebius.job_logging import JobLogger
from app.nebius.object_storage import (
    TransferLimits,
    download_s3_release,
    inventory_directory,
    publish_local_result,
    publish_s3_result,
    sha256_file,
    verify_complete_result,
)


JOB_LOG = JobLogger("market-data-preparation")
ATTACK_FAMILIES = ("spoofing_like_wall", "layering_like", "quote_stuffing")
SEEDS = (41, 42, 43)
SYMBOLS = ("AAPL", "MSFT", "NVDA")
WINDOW_START_MS = 36_000_000
WINDOW_END_MS = 37_800_000


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(self.model_dump(mode="json"), allow_nan=False, sort_keys=True, separators=(",", ":")).encode()

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class NasdaqPreparationRequest(_StrictModel):
    schema_version: Literal["market_data_wave1_preparation_request_v1"] = "market_data_wave1_preparation_request_v1"
    run_id: str = Field(pattern=IDENTIFIER_PATTERN)
    sequence_number: int = Field(ge=1, le=7)
    project_id: Literal["project-e00g6zvxpr00waz8t3y51k"] = PROJECT_ID
    region: Literal["eu-north1"] = "eu-north1"
    image: str = Field(pattern=IMMUTABLE_IMAGE_PATTERN)
    git_commit: str = Field(pattern=GIT_COMMIT_PATTERN)
    created_at: AwareDatetime
    source: NasdaqPublicSource
    source_release_uri: str
    source_release_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    result_uri: str
    resource: AcquisitionResourceRequest = Field(default_factory=AcquisitionResourceRequest)
    symbols: tuple[Literal["AAPL", "MSFT", "NVDA"], ...] = SYMBOLS
    window_start_ms: Literal[36_000_000] = WINDOW_START_MS
    window_end_ms: Literal[37_800_000] = WINDOW_END_MS
    depth: Literal[10] = 10
    attack_families: tuple[Literal["spoofing_like_wall", "layering_like", "quote_stuffing"], ...] = ATTACK_FAMILIES
    seeds: tuple[Literal[41, 42, 43], ...] = SEEDS
    restart_policy: Literal["never"] = "never"

    @model_validator(mode="after")
    def validate_boundaries(self) -> "NasdaqPreparationRequest":
        if self.symbols != SYMBOLS or self.attack_families != ATTACK_FAMILIES or self.seeds != SEEDS:
            raise ValueError("preparation request changed the frozen symbols, attacks, or seeds")
        date_path = self.source.date.isoformat()
        source_pattern = (
            rf"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/quarantine/nasdaq/"
            rf"{re.escape(date_path)}/[a-z0-9][a-z0-9-]{{2,62}}"
        )
        if re.fullmatch(source_pattern, self.source_release_uri.rstrip("/")) is None:
            raise ValueError("preparation source URI escaped the exact quarantine date")
        expected_result = f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/prepared/{date_path}/{self.run_id}"
        if self.result_uri != expected_result:
            raise ValueError("preparation result URI escaped the exact date/run prefix")
        return self


class PreparationManifest(_StrictModel):
    schema_version: Literal["market_data_wave1_preparation_result_v1"] = "market_data_wave1_preparation_result_v1"
    run_id: str
    source_filename: str
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    source_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    parser_version: str
    parser_config_sha256: str = Field(pattern=SHA256_PATTERN)
    itch_message_counts: dict[str, int]
    system_event_count: int = Field(ge=1)
    system_event_coverage_verified: Literal[True] = True
    normalized_in_one_pass: Literal[True] = True
    symbols: tuple[str, ...]
    dataset_ids: dict[str, str]
    control_run_ids: dict[str, str]
    campaign_run_ids: tuple[str, ...]
    comparison_count: Literal[27] = 27
    replay_domain_count: Literal[30] = 30
    repeat_determinism_verified: Literal[True] = True
    feature_run_count: Literal[30] = 30
    payload_inventory_sha256: str = Field(pattern=SHA256_PATTERN)
    created_at: AwareDatetime


ReplayExporter = Callable[..., tuple[Path, Path, dict[str, object]]]
FeatureGenerator = Callable[[Path, Path], None]


def execute_preparation(
    request_path: Path,
    *,
    source_root: Path,
    result_root: Path,
    java_base_url: str,
    java_jar: Path | None = None,
    replay_exporter: ReplayExporter | None = None,
    feature_generator: FeatureGenerator | None = None,
) -> Path:
    request = NasdaqPreparationRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    with JOB_LOG.phase(
        "source-validation",
        "Verify the downloaded source release inventory, identity, length, SHA-256, and gzip integrity.",
        run_id=request.run_id,
        source_filename=request.source.filename,
        expected_bytes=request.source.expected_content_length,
    ):
        verify_complete_result(source_root)
        source_manifest_path = source_root / "source.json"
        if sha256_file(source_manifest_path) != request.source_release_manifest_sha256:
            raise ValueError("preparation source manifest hash does not match its request")
        source_manifest = NasdaqSourceReleaseManifest.model_validate_json(
            source_manifest_path.read_text(encoding="utf-8")
        )
        source_path = source_root / request.source.filename
        if (
            source_manifest.source_filename != request.source.filename
            or source_manifest.trade_date != request.source.date.isoformat()
            or source_manifest.sha256 != sha256_file(source_path)
            or source_manifest.observed_size_bytes != source_path.stat().st_size
        ):
            raise ValueError("preparation source release is not bound to the request")
        _verify_gzip(source_path)
    result_root.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{request.run_id}.", dir=result_root.parent))
    try:
        normalized_root = staging / "normalized"
        with JOB_LOG.phase(
            "normalization",
            "Normalize all three allowlisted symbols from one bounded ITCH source pass.",
            run_id=request.run_id,
            symbol_count=len(SYMBOLS),
            window_start_ms=request.window_start_ms,
            window_end_ms=request.window_end_ms,
        ):
            manifests = convert_itch_symbols(
                source_path,
                normalized_root,
                symbols=SYMBOLS,
                trade_date=request.source.date.isoformat(),
                start_time_ms=request.window_start_ms,
                end_time_ms=request.window_end_ms,
                depth=request.depth,
                source_name=request.source.filename,
                min_free_bytes=10 * 1024**3,
                max_working_bytes=20 * 1024**3,
            )
        java_context = (
            _local_java_control_plane(java_jar, normalized_root, staging / "java")
            if java_jar is not None
            else nullcontext(java_base_url)
        )
        with JOB_LOG.phase(
            "replay-campaign",
            "Run the pinned Java control plane, repeat-determinism gates, and causal feature generation.",
            run_id=request.run_id,
            comparison_count=len(SYMBOLS) * len(ATTACK_FAMILIES) * len(SEEDS),
        ):
            with java_context as active_java_url:
                control_runs, campaign_runs = _run_replay_campaign(
                    java_base_url=active_java_url,
                    staging=staging,
                    manifests=manifests,
                    replay_exporter=replay_exporter or export_replay_comparison,
                    feature_generator=feature_generator or _generate_features,
                )
        with JOB_LOG.phase(
            "result-materialization",
            "Freeze the preparation manifest and checksummed local result inventory.",
            run_id=request.run_id,
        ):
            (staging / "request.json").write_bytes(request.canonical_bytes())
            inventory = inventory_directory(staging)
            inventory_hash = hashlib.sha256(
                json.dumps(inventory.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            shared_config_hashes = {item.parser_config_sha256 for item in manifests.values()}
            if len(shared_config_hashes) != 1:
                raise ValueError("one-pass normalization emitted divergent parser configs")
            message_counts = {json.dumps(item.message_counts, sort_keys=True) for item in manifests.values()}
            if len(message_counts) != 1:
                raise ValueError("one-pass normalization emitted divergent ITCH message coverage")
            shared_message_counts = next(iter(manifests.values())).message_counts
            if shared_message_counts.get("S", 0) < 1:
                raise ValueError("Nasdaq source omitted required ITCH system-event coverage")
            preparation = PreparationManifest(
                run_id=request.run_id,
                source_filename=request.source.filename,
                source_sha256=source_manifest.sha256,
                source_manifest_sha256=request.source_release_manifest_sha256,
                parser_version=next(iter(manifests.values())).parser_version or "",
                parser_config_sha256=next(iter(shared_config_hashes)),
                itch_message_counts=shared_message_counts,
                system_event_count=shared_message_counts["S"],
                symbols=SYMBOLS,
                dataset_ids={symbol: manifests[symbol].dataset_id for symbol in SYMBOLS},
                control_run_ids=control_runs,
                campaign_run_ids=tuple(campaign_runs),
                payload_inventory_sha256=inventory_hash,
                created_at=datetime.now(UTC),
            )
            (staging / "preparation.json").write_bytes(preparation.canonical_bytes())
            return publish_local_result(staging, result_root.resolve().as_uri())
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def execute_preparation_s3(
    input_uri: str,
    *,
    work_root: Path,
    java_base_url: str = "http://127.0.0.1:8080",
    java_jar: Path | None = None,
    endpoint_url: str = OBJECT_STORAGE_ENDPOINT,
) -> str:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("preparation requires the approved eu-north1 endpoint")
    _require_environment()
    pattern = (
        rf"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
        r"preparation-requests/[a-z0-9][a-z0-9-]{2,62}/staging"
    )
    if re.fullmatch(pattern, input_uri.rstrip("/")) is None:
        raise ValueError("preparation input escaped its exact request prefix")
    work_root = work_root.resolve()
    if str(work_root) in {"/", str(Path.home().resolve())}:
        raise ValueError("preparation work root is too broad")
    work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="market-data-prepare-", dir=work_root) as value:
        stage = Path(value)
        request_root = stage / "request"
        with JOB_LOG.phase(
            "request-download",
            "Download and verify the exact reviewed preparation request package.",
            input_uri=input_uri.rstrip("/"),
        ):
            download_s3_release(
                input_uri,
                request_root,
                endpoint_url=endpoint_url,
                limits=TransferLimits(max_files=8, max_bytes=1024 * 1024),
            )
        request_path = request_root / "request.json"
        request = NasdaqPreparationRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
        _verify_job_context(request)
        JOB_LOG.info(
            "request-verified",
            "The preparation request matches the reviewed Job resource and immutable image context.",
            run_id=request.run_id,
            sequence_number=request.sequence_number,
            source_filename=request.source.filename,
        )
        source_root = stage / "source"
        with JOB_LOG.phase(
            "source-download",
            "Download and inventory the immutable private Nasdaq source release.",
            run_id=request.run_id,
            source_filename=request.source.filename,
            expected_bytes=request.source.expected_content_length,
        ):
            download_s3_release(
                request.source_release_uri,
                source_root,
                endpoint_url=endpoint_url,
                limits=TransferLimits(
                    max_files=8,
                    max_bytes=request.source.expected_content_length + 1024 * 1024,
                ),
            )
        result = stage / "result"
        execute_preparation(
            request_path,
            source_root=source_root,
            result_root=result,
            java_base_url=java_base_url,
            java_jar=java_jar,
        )
        with JOB_LOG.phase(
            "result-publication",
            "Publish the verified prepared release with checksums and SUCCESS last.",
            run_id=request.run_id,
            result_uri=request.result_uri,
        ):
            publish_s3_result(result, request.result_uri, endpoint_url=endpoint_url)
        return request.result_uri


def _run_replay_campaign(
    *,
    java_base_url: str,
    staging: Path,
    manifests: dict[str, DatasetManifest],
    replay_exporter: ReplayExporter,
    feature_generator: FeatureGenerator,
) -> tuple[dict[str, str], list[str]]:
    control_hashes: dict[str, str] = {}
    control_runs: dict[str, str] = {}
    campaign_runs: list[str] = []
    comparison_number = 0
    comparison_total = len(SYMBOLS) * len(ATTACK_FAMILIES) * len(SEEDS)
    for symbol in SYMBOLS:
        dataset = manifests[symbol]
        base = staging / "replays" / f"xnas-{dataset.trade_date}-{symbol.lower()}"
        for family in ATTACK_FAMILIES:
            for seed in SEEDS:
                comparison_number += 1
                comparison_root = base / "comparisons" / f"{family}-s{seed}"
                with JOB_LOG.phase(
                    "replay-comparison",
                    "Export and validate one deterministic control/hybrid replay and its causal features.",
                    symbol=symbol,
                    attack_family=family,
                    seed=seed,
                    comparison_number=comparison_number,
                    comparison_total=comparison_total,
                ):
                    control_manifest, hybrid_manifest, comparison = replay_exporter(
                        base_url=java_base_url,
                        dataset=dataset,
                        attack_family=family,
                        seed=seed,
                        output_root=comparison_root,
                    )
                    _verify_comparison_determinism(comparison)
                    control = CanonicalJavaReplayManifest.model_validate_json(
                        control_manifest.read_text(encoding="utf-8")
                    )
                    hybrid = CanonicalJavaReplayManifest.model_validate_json(
                        hybrid_manifest.read_text(encoding="utf-8")
                    )
                    previous = control_hashes.setdefault(symbol, control.canonical_event_stream_hash)
                    if previous != control.canonical_event_stream_hash:
                        raise ValueError("control replay changed across campaign comparisons")
                    if symbol not in control_runs:
                        control_runs[symbol] = control.run_id
                        feature_generator(control_manifest, staging / "features" / control.run_id)
                    campaign_runs.append(hybrid.run_id)
                    feature_generator(hybrid_manifest, staging / "features" / hybrid.run_id)
    return control_runs, campaign_runs


@contextmanager
def _local_java_control_plane(jar: Path, registry_root: Path, runtime_root: Path) -> Iterator[str]:
    if not jar.is_file():
        raise FileNotFoundError(f"pinned Java control-plane JAR is missing: {jar}")
    runtime_root.mkdir(parents=True, exist_ok=False)
    environment = {
        **os.environ,
        "LOB_ARENA_HISTORICAL_DATA_DIR": str(registry_root.resolve()),
        "ARENA_OUTPUT_DIR": str((runtime_root / "outputs").resolve()),
        "LOB_ARENA_DUCKDB_TEMP_DIRECTORY": str((runtime_root / "duckdb").resolve()),
        "LOB_ARENA_DUCKDB_MEMORY_LIMIT": "8GB",
        "LOB_ARENA_DUCKDB_THREADS": "2",
        "LOB_ARENA_EVENT_ARCHIVE_MAX_STREAM_BYTES": str(12 * 1024**3),
        "LOB_KERNEL_GRPC_ENABLED": "false",
    }
    log_handle = (runtime_root / "control-plane.log").open("wb")
    process = subprocess.Popen(
        ["java", "-jar", str(jar.resolve())],
        cwd=runtime_root,
        env=environment,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
    )
    base_url = "http://127.0.0.1:8080"
    try:
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Java control plane exited before becoming healthy")
            try:
                with urllib.request.urlopen(f"{base_url}/actuator/health", timeout=2) as response:
                    if response.status == 200:
                        break
            except OSError:
                time.sleep(0.5)
        else:
            raise TimeoutError("Java control plane did not become healthy within 60 seconds")
        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log_handle.close()
        shutil.rmtree(runtime_root, ignore_errors=True)


def _generate_features(replay_manifest: Path, output: Path) -> None:
    root = Path(__file__).resolve().parents[3]
    command = [
        sys.executable,
        str(root / "scripts" / "generate_features.py"),
        "--replay-manifest",
        str(replay_manifest),
        "--artifact-root",
        str(replay_manifest.parent),
        "--config",
        str(root / "configs" / "features" / "lightgbm-v2.json"),
        "--output",
        str(output),
        "--streaming",
        "--research-control-assumption",
    ]
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode:
        raise RuntimeError("causal feature generation failed")


def _verify_comparison_determinism(comparison: dict[str, object]) -> None:
    determinism = comparison.get("determinism")
    if (
        not isinstance(determinism, dict)
        or not determinism
        or not all(value is True for key, value in determinism.items() if key.endswith("_match"))
    ):
        raise ValueError("Java comparison did not pass all repeat determinism gates")


def _verify_job_context(request: NasdaqPreparationRequest) -> None:
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
        raise RuntimeError("preparation Job context does not match its reviewed request")
