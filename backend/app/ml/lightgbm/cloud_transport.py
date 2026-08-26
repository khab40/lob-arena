from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest, Wave1ExecutionContext
from app.ml.lightgbm.cloud_runner import execute_wave1_request
from app.nebius.object_storage import (
    TransferLimits,
    download_s3_release,
    publish_s3_failure,
    publish_s3_result,
)


DEVELOPMENT_BUCKET = "aimada-wave1-dev-e00g6zvxpr00"
FINAL_BUCKET = "aimada-wave1-final-e00g6zvxpr00"
RESULTS_BUCKET = "aimada-wave1-results-e00g6zvxpr00"
DEFAULT_ENDPOINT_URL = "https://storage.eu-north1.nebius.cloud"


def execute_wave1_s3(
    input_uri: str,
    *,
    work_root: Path,
    endpoint_url: str = DEFAULT_ENDPOINT_URL,
    request_relative_path: str = "request.json",
    limits: TransferLimits = TransferLimits(),
) -> str:
    """Stage one governed S3 release, execute locally, and publish via S3 APIs."""

    if endpoint_url.rstrip("/") != DEFAULT_ENDPOINT_URL:
        raise ValueError("Wave 1 Object Storage endpoint must be the approved eu-north1 endpoint")
    _require_s3_environment()
    _validate_request_relative_path(request_relative_path)
    work_root = work_root.resolve()
    if str(work_root) in {"/", str(Path.home().resolve())}:
        raise ValueError("Wave 1 work root is too broad")
    work_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="wave1-s3-", dir=work_root) as directory:
        stage = Path(directory)
        input_root = stage / "input"
        download_s3_release(input_uri, input_root, endpoint_url=endpoint_url, limits=limits)
        request_path = (input_root / request_relative_path).resolve()
        if input_root not in request_path.parents or not request_path.is_file():
            raise ValueError("Wave 1 request is missing or outside the staged input prefix")
        request = LightGbmCloudJobRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
        _validate_s3_boundaries(input_uri, request)
        if request.mode in {"development", "final-evaluation"} and request.mlflow_tracking_uri is None:
            raise ValueError("cloud training and evaluation require a governed MLflow tracking URI")
        execution_context = _execution_context_from_environment()
        trusted_public_key_sha256 = os.environ.get(
            "WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256"
        )
        local_result = stage / "result"
        try:
            completed = execute_wave1_request(
                request_path,
                input_root=input_root,
                local_result_root=local_result,
                execution_context=execution_context,
                trusted_authorization_public_key_sha256=trusted_public_key_sha256,
            )
            publish_s3_result(completed, request.result_uri, endpoint_url=endpoint_url)
        except Exception:
            if (local_result / "FAILED").is_file():
                publish_s3_failure(local_result, request.result_uri, endpoint_url=endpoint_url)
            raise
    return request.result_uri


def _validate_s3_boundaries(input_uri: str, request: LightGbmCloudJobRequest) -> None:
    input_bucket, input_prefix = _bucket_prefix(input_uri)
    expected_bucket = FINAL_BUCKET if request.mode == "final-evaluation" else DEVELOPMENT_BUCKET
    if input_bucket != expected_bucket or not input_prefix.startswith("releases/"):
        raise ValueError("input URI is outside the approved Wave 1 release boundary")
    input_parts = PurePosixPath(input_prefix).parts
    if (
        len(input_parts) != 3
        or input_parts[0] != "releases"
        or re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", input_parts[1]) is None
        or input_parts[2] != "staging"
    ):
        raise ValueError("input URI must identify an immutable releases/<id>/staging prefix")

    result_bucket, result_prefix = _bucket_prefix(request.result_uri)
    expected_lane = "final" if request.mode == "final-evaluation" else "development"
    expected_result = f"campaigns/{request.campaign_id}/{expected_lane}/{request.run_id}"
    if result_bucket != RESULTS_BUCKET or result_prefix != expected_result:
        raise ValueError("result URI does not match the exact approved campaign/run prefix")


def _bucket_prefix(uri: str) -> tuple[str, str]:
    parsed = urlsplit(uri)
    prefix = parsed.path.strip("/")
    if (
        parsed.scheme != "s3"
        or not parsed.netloc
        or not prefix
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port is not None
    ):
        raise ValueError("Wave 1 cloud transport requires a bounded s3:// URI")
    return parsed.netloc, prefix.rstrip("/")


def _validate_request_relative_path(value: str) -> None:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise ValueError("request path must be a normalized relative POSIX path")


def _require_s3_environment() -> None:
    missing = [
        name
        for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        raise RuntimeError("Wave 1 requires MysteryBox-injected AWS credential environment values")
    if os.environ.get("AWS_DEFAULT_REGION") != "eu-north1":
        raise RuntimeError("Wave 1 AWS_DEFAULT_REGION must be eu-north1")
    if os.environ.get("AWS_EC2_METADATA_DISABLED", "").lower() != "true":
        raise RuntimeError("Wave 1 requires AWS_EC2_METADATA_DISABLED=true")


def _execution_context_from_environment() -> Wave1ExecutionContext:
    required = {
        "project_id": "WAVE1_ACTUAL_PROJECT_ID",
        "platform": "WAVE1_ACTUAL_PLATFORM",
        "preset": "WAVE1_ACTUAL_PRESET",
        "disk_size_gib": "WAVE1_ACTUAL_DISK_SIZE_GIB",
        "timeout_seconds": "WAVE1_ACTUAL_TIMEOUT_SECONDS",
    }
    image_repository = os.environ.get("WAVE1_ACTUAL_IMAGE_REPOSITORY", "").strip()
    image_sha256 = os.environ.get("WAVE1_ACTUAL_IMAGE_SHA256", "").strip()
    missing = [environment for environment in required.values() if not os.environ.get(environment, "").strip()]
    if not image_repository:
        missing.append("WAVE1_ACTUAL_IMAGE_REPOSITORY")
    if not image_sha256:
        missing.append("WAVE1_ACTUAL_IMAGE_SHA256")
    if missing:
        raise RuntimeError("Wave 1 Job context environment is incomplete")
    if (
        len(image_repository) > 64
        or "@" in image_repository
        or re.fullmatch(r"[0-9a-f]{64}", image_sha256) is None
    ):
        raise RuntimeError("Wave 1 Job image context is invalid")
    payload: dict[str, object] = {
        field: os.environ[environment].strip() for field, environment in required.items()
    }
    payload["image"] = f"{image_repository}@sha256:{image_sha256}"
    payload["disk_size_gib"] = int(str(payload["disk_size_gib"]))
    payload["timeout_seconds"] = int(str(payload["timeout_seconds"]))
    job_id = os.environ.get("NEBIUS_JOB_ID", "").strip()
    if job_id:
        payload["nebius_job_id"] = job_id
    estimated_cost = os.environ.get("WAVE1_ESTIMATED_COST_USD", "").strip()
    if estimated_cost:
        payload["estimated_cost_usd"] = float(estimated_cost)
    return Wave1ExecutionContext.model_validate(payload)
