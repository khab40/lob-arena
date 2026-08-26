import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest  # noqa: E402


WAVE1_ENDPOINT_URL = "https://storage.eu-north1.nebius.cloud"
WAVE1_PROJECT_ID = "project-e00g6zvxpr00waz8t3y51k"
WAVE1_PLATFORM = "cpu-d3"
WAVE1_PRESET = "4vcpu-16gb"
WAVE1_DISK_SIZE = "100Gi"
WAVE1_TIMEOUT = "1h"
WAVE1_INPUT_PATTERN = re.compile(
    r"s3://aimada-wave1-(?:dev|final)-e00g6zvxpr00/"
    r"releases/[a-z0-9][a-z0-9-]{2,62}/staging/?"
)
WAVE1_WORK_ROOT_PATTERN = re.compile(r"/job/[A-Za-z0-9._/-]+")


def main() -> None:
    parser = argparse.ArgumentParser(description="Submit the smart attack/detect batch as a Nebius Serverless AI Job.")
    parser.add_argument("--image", default=os.environ.get("NEBIUS_JOB_IMAGE", "ghcr.io/khab40/lob-arena-jobs:latest"))
    parser.add_argument("--name", default=os.environ.get("NEBIUS_JOB_NAME", "market-abuse-smart-batch"))
    parser.add_argument("--runs", type=int, default=int(os.environ.get("NEBIUS_JOB_RUNS", "1000")))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("NEBIUS_JOB_BATCH_SIZE", "100")))
    parser.add_argument("--subnet-id", default=os.environ.get("NEBIUS_SUBNET_ID"))
    parser.add_argument("--parent-id", default=os.environ.get("NEBIUS_PARENT_ID"))
    parser.add_argument("--platform", default=os.environ.get("NEBIUS_JOB_PLATFORM", "cpu-d3"))
    parser.add_argument("--preset", default=os.environ.get("NEBIUS_JOB_PRESET", "4vcpu-16gb"))
    parser.add_argument("--timeout", default=os.environ.get("NEBIUS_JOB_TIMEOUT", "1h"))
    parser.add_argument("--disk-size", default=os.environ.get("NEBIUS_JOB_DISK_SIZE", "100Gi"))
    parser.add_argument("--s3-output-uri", default=os.environ.get("NEBIUS_JOB_OUTPUT_URI", ""))
    parser.add_argument("--s3-endpoint-url", default=os.environ.get("NEBIUS_OBJECT_STORAGE_ENDPOINT_URL", ""))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--evidence-output",
        type=Path,
        default=(Path(value) if (value := os.environ.get("NEBIUS_WAVE1_EVIDENCE_OUTPUT")) else None),
    )
    parser.add_argument(
        "--reviewed-dry-run",
        type=Path,
        default=(Path(value) if (value := os.environ.get("NEBIUS_WAVE1_REVIEWED_DRY_RUN")) else None),
    )
    parser.add_argument(
        "--reviewed-dry-run-sha256",
        default=os.environ.get("NEBIUS_WAVE1_REVIEWED_DRY_RUN_SHA256"),
    )
    parser.add_argument(
        "--campaign-spend-usd",
        type=float,
        default=(float(value) if (value := os.environ.get("WAVE1_SPEND_TO_DATE_USD")) else None),
    )
    parser.add_argument(
        "--development-jobs-consumed",
        type=int,
        default=(int(value) if (value := os.environ.get("WAVE1_DEVELOPMENT_JOBS_CONSUMED")) else None),
    )
    parser.add_argument("--workload", choices=("synthetic", "lightgbm-wave1"), default="synthetic")
    parser.add_argument("--input-uri", default=os.environ.get("NEBIUS_WAVE1_INPUT_URI", ""))
    parser.add_argument(
        "--request-evidence",
        type=Path,
        default=(Path(value) if (value := os.environ.get("NEBIUS_WAVE1_REQUEST_EVIDENCE")) else None),
    )
    parser.add_argument("--work-root", default="/job/wave1")
    parser.add_argument(
        "--access-key-secret-id", default=os.environ.get("NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID")
    )
    parser.add_argument(
        "--secret-key-secret-id", default=os.environ.get("NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID")
    )
    parser.add_argument(
        "--session-token-secret-id", default=os.environ.get("NEBIUS_OBJECT_STORAGE_SESSION_TOKEN_SECRET_ID")
    )
    parser.add_argument(
        "--mlflow-username-secret-id", default=os.environ.get("NEBIUS_MLFLOW_USERNAME_SECRET_ID")
    )
    parser.add_argument(
        "--mlflow-password-secret-id", default=os.environ.get("NEBIUS_MLFLOW_PASSWORD_SECRET_ID")
    )
    parser.add_argument(
        "--trusted-authorization-public-key-sha256",
        default=os.environ.get("NEBIUS_WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256"),
    )
    args = parser.parse_args()

    if not args.subnet_id:
        raise SystemExit("NEBIUS_SUBNET_ID or --subnet-id is required")

    if any(
        os.environ.get(name)
        for name in (
            "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID",
            "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
            "NEBIUS_OBJECT_STORAGE_SESSION_TOKEN",
        )
    ):
        raise SystemExit("inline Object Storage credentials are forbidden; use MysteryBox secret IDs")
    if args.workload == "lightgbm-wave1":
        request = _load_wave1_request(args.request_evidence, args.input_uri)
        if request.mode in {"development", "final-evaluation"} and request.mlflow_tracking_uri is None:
            raise SystemExit("LightGBM Wave 1 cloud request requires an MLflow tracking URI")
        if (
            args.campaign_spend_usd is None
            or not math.isfinite(args.campaign_spend_usd)
            or not 0 <= args.campaign_spend_usd < 40
        ):
            raise SystemExit("LightGBM Wave 1 submission requires reconciled campaign spend below USD 40")
        if (
            args.development_jobs_consumed is None
            or not 0 <= args.development_jobs_consumed < 20
        ):
            raise SystemExit("LightGBM Wave 1 requires a reconciled development Job count below 20")
        if re.fullmatch(r".+@sha256:[0-9a-f]{64}", args.image) is None:
            raise SystemExit("LightGBM Wave 1 requires an immutable image digest")
        if request.image != args.image:
            raise SystemExit("LightGBM Wave 1 image must match the staged request evidence")
        if args.parent_id not in {None, WAVE1_PROJECT_ID}:
            raise SystemExit("LightGBM Wave 1 requires the approved project parent")
        if (
            args.platform != WAVE1_PLATFORM
            or args.preset != WAVE1_PRESET
            or args.disk_size != WAVE1_DISK_SIZE
            or args.timeout != WAVE1_TIMEOUT
        ):
            raise SystemExit("LightGBM Wave 1 requires cpu-d3, 4vcpu-16gb, 100Gi, and 1h")
        if WAVE1_INPUT_PATTERN.fullmatch(args.input_uri) is None:
            raise SystemExit("LightGBM Wave 1 requires an exact approved S3 release prefix")
        if args.s3_endpoint_url.rstrip("/") != WAVE1_ENDPOINT_URL:
            raise SystemExit("LightGBM Wave 1 requires the approved eu-north1 S3 endpoint")
        if (
            WAVE1_WORK_ROOT_PATTERN.fullmatch(args.work_root) is None
            or ".." in Path(args.work_root).parts
        ):
            raise SystemExit("LightGBM Wave 1 requires a bounded /job work root")
        if not args.access_key_secret_id or not args.secret_key_secret_id:
            raise SystemExit("LightGBM Wave 1 requires both MysteryBox credential selectors")
        if request.mlflow_tracking_uri and (
            not args.mlflow_username_secret_id or not args.mlflow_password_secret_id
        ):
            raise SystemExit("LightGBM Wave 1 requires both MysteryBox MLflow credential selectors")
        if request.mode == "final-evaluation" and re.fullmatch(
            r"[0-9a-f]{64}", args.trusted_authorization_public_key_sha256 or ""
        ) is None:
            raise SystemExit("final evaluation requires a trusted authorization public-key SHA-256")
        if os.environ.get("NEBIUS_VOLUME"):
            raise SystemExit("NEBIUS_VOLUME is forbidden for LightGBM Wave 1; use S3 API staging")
        job_args = (
            f"/job/serverless/jobs/run_lightgbm_wave1.py run-s3 --input-uri {args.input_uri} "
            f"--work-root {args.work_root} --endpoint-url {args.s3_endpoint_url}"
        )
        args.parent_id = WAVE1_PROJECT_ID
    else:
        job_args = f"/job/serverless/jobs/run_batch_experiments.py --runs {args.runs} --batch-size {args.batch_size} --output /job/outputs/serverless-batch"
    if args.s3_output_uri and args.workload != "lightgbm-wave1":
        job_args += f" --s3-output-uri {args.s3_output_uri.rstrip('/')}/serverless-batch"
    if args.s3_endpoint_url and args.workload != "lightgbm-wave1":
        job_args += f" --s3-endpoint-url {args.s3_endpoint_url}"

    command = [
        "nebius",
        "ai",
        "job",
        "create",
        "--name",
        args.name,
        "--image",
        args.image,
        "--container-command",
        "python",
        "--args",
        job_args,
        "--platform",
        args.platform,
        "--preset",
        args.preset,
        "--disk-size",
        args.disk_size,
        "--timeout",
        args.timeout,
        "--subnet-id",
        args.subnet_id,
        "--restart-policy",
        "never",
        "--format",
        "json",
    ]
    if args.parent_id:
        command.extend(["--parent-id", args.parent_id])
    if os.environ.get("NEBIUS_VOLUME") and args.workload != "lightgbm-wave1":
        command.extend(["--volume", os.environ["NEBIUS_VOLUME"]])
    for name, secret_id in (
        ("AWS_ACCESS_KEY_ID", args.access_key_secret_id),
        ("AWS_SECRET_ACCESS_KEY", args.secret_key_secret_id),
        ("AWS_SESSION_TOKEN", args.session_token_secret_id),
        ("MLFLOW_TRACKING_USERNAME", args.mlflow_username_secret_id),
        ("MLFLOW_TRACKING_PASSWORD", args.mlflow_password_secret_id),
    ):
        if secret_id:
            command.extend(["--env-secret", f"{name}={secret_id}"])
    region = (
        "eu-north1"
        if args.workload == "lightgbm-wave1"
        else os.environ.get("NEBIUS_OBJECT_STORAGE_REGION", "eu-north1")
    )
    command.extend(["--env", f"AWS_DEFAULT_REGION={region}"])
    command.extend(["--env", "AWS_EC2_METADATA_DISABLED=true"])
    if args.workload == "lightgbm-wave1":
        image_repository, image_sha256 = args.image.rsplit("@sha256:", maxsplit=1)
        if len(image_repository) > 64 or len(image_sha256) != 64:
            raise SystemExit(
                "LightGBM Wave 1 image context must fit Nebius label-safe repository/digest fields"
            )
        for name, value in (
            ("WAVE1_ACTUAL_PROJECT_ID", WAVE1_PROJECT_ID),
            ("WAVE1_ACTUAL_IMAGE_REPOSITORY", image_repository),
            ("WAVE1_ACTUAL_IMAGE_SHA256", image_sha256),
            ("WAVE1_ACTUAL_PLATFORM", WAVE1_PLATFORM),
            ("WAVE1_ACTUAL_PRESET", WAVE1_PRESET),
            ("WAVE1_ACTUAL_DISK_SIZE_GIB", "100"),
            ("WAVE1_ACTUAL_TIMEOUT_SECONDS", "3600"),
        ):
            command.extend(["--env", f"{name}={value}"])
        if args.trusted_authorization_public_key_sha256:
            command.extend(
                [
                    "--env",
                    "WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256="
                    f"{args.trusted_authorization_public_key_sha256}",
                ]
            )

    command_sha256 = _canonical_hash(command)
    if args.dry_run:
        payload = {
            "schema_version": "lightgbm_wave1_g4_dry_run_v1",
            "created_at": datetime.now(UTC).isoformat(),
            "request_sha256": request.canonical_hash() if args.workload == "lightgbm-wave1" else None,
            "input_uri": args.input_uri if args.workload == "lightgbm-wave1" else None,
            "result_uri": request.result_uri if args.workload == "lightgbm-wave1" else None,
            "project_id": WAVE1_PROJECT_ID if args.workload == "lightgbm-wave1" else args.parent_id,
            "image": args.image,
            "resource": request.resource.model_dump(mode="json") if args.workload == "lightgbm-wave1" else None,
            "command": _redacted_command(command),
            "command_sha256": command_sha256,
            "campaign_spend_usd": args.campaign_spend_usd,
            "development_jobs_consumed": args.development_jobs_consumed,
            "manual_review_required": args.workload == "lightgbm-wave1",
            "cloud_resources_created": False,
        }
        if args.evidence_output is not None:
            _write_evidence(args.evidence_output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return

    reviewed_sha256 = None
    if args.workload == "lightgbm-wave1":
        if args.evidence_output is None:
            raise SystemExit("LightGBM Wave 1 submission requires --evidence-output")
        if args.evidence_output.exists():
            raise SystemExit(f"Wave 1 evidence output already exists: {args.evidence_output}")
        reviewed = _load_reviewed_dry_run(args.reviewed_dry_run)
        reviewed_sha256 = hashlib.sha256(args.reviewed_dry_run.read_bytes()).hexdigest()
        if args.reviewed_dry_run_sha256 != reviewed_sha256:
            raise SystemExit("reviewed Wave 1 dry-run SHA-256 confirmation is missing or incorrect")
        if reviewed.get("request_sha256") != request.canonical_hash():
            raise SystemExit("reviewed Wave 1 dry run does not match the staged request")
        if reviewed.get("command_sha256") != command_sha256:
            raise SystemExit("reviewed Wave 1 dry run does not match the submission command")
        if reviewed.get("campaign_spend_usd") != args.campaign_spend_usd:
            raise SystemExit("reviewed Wave 1 dry run does not match reconciled campaign spend")
        if reviewed.get("development_jobs_consumed") != args.development_jobs_consumed:
            raise SystemExit("reviewed Wave 1 dry run does not match the development Job count")

    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        if args.workload == "lightgbm-wave1" and args.evidence_output is not None:
            _write_evidence(
                args.evidence_output,
                {
                    "schema_version": "lightgbm_wave1_g4_submission_v1",
                    "submitted_at": datetime.now(UTC).isoformat(),
                    "request_sha256": request.canonical_hash(),
                    "command_sha256": command_sha256,
                    "reviewed_dry_run_sha256": reviewed_sha256,
                    "status": "SUBMISSION_FAILED",
                    "return_code": completed.returncode,
                    "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
                },
            )
        raise SystemExit(completed.stderr)
    if args.workload == "lightgbm-wave1":
        job_id = _parse_job_id(completed.stdout)
        if job_id is None:
            raise SystemExit("Nebius Job creation response did not contain a canonical Job ID")
        submitted_at = datetime.now(UTC)
        payload = {
            "schema_version": "lightgbm_wave1_g4_submission_v1",
            "submitted_at": submitted_at.isoformat(),
            "watchdog_deadline": (submitted_at + timedelta(minutes=15)).isoformat(),
            "watchdog_seconds": 900,
            "request_sha256": request.canonical_hash(),
            "input_uri": args.input_uri,
            "result_uri": request.result_uri,
            "project_id": request.project_id,
            "image": request.image,
            "resource": request.resource.model_dump(mode="json"),
            "job_id": job_id,
            "status": "SUBMITTED",
            "command_sha256": command_sha256,
            "reviewed_dry_run_sha256": reviewed_sha256,
            "response_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
            "campaign_spend_usd": args.campaign_spend_usd,
            "development_jobs_consumed_before_submit": args.development_jobs_consumed,
            "development_jobs_consumed_after_submit": args.development_jobs_consumed + 1,
        }
        _write_evidence(args.evidence_output, payload)
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    Path("outputs/nebius").mkdir(parents=True, exist_ok=True)
    Path("outputs/nebius/latest_job_create.json").write_text(completed.stdout, encoding="utf-8")
    print(completed.stdout)


def _load_wave1_request(evidence_path: Path | None, input_uri: str) -> LightGbmCloudJobRequest:
    if evidence_path is None or not evidence_path.is_file():
        raise SystemExit("LightGBM Wave 1 requires --request-evidence from stage-fixture")
    try:
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        request = LightGbmCloudJobRequest.model_validate(evidence["request"])
    except (OSError, ValueError, KeyError) as exc:
        raise SystemExit("LightGBM Wave 1 request evidence is invalid") from exc
    if evidence.get("destination") != input_uri:
        raise SystemExit("LightGBM Wave 1 input URI does not match the request evidence")
    if evidence.get("request_sha256") != request.canonical_hash():
        raise SystemExit("LightGBM Wave 1 request evidence hash mismatch")
    if request.project_id != WAVE1_PROJECT_ID:
        raise SystemExit("LightGBM Wave 1 request does not target the approved project")
    return request


def _load_reviewed_dry_run(path: Path | None) -> dict[str, object]:
    if path is None or not path.is_file():
        raise SystemExit("LightGBM Wave 1 submission requires --reviewed-dry-run")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("reviewed Wave 1 dry-run evidence is invalid") from exc
    if payload.get("schema_version") != "lightgbm_wave1_g4_dry_run_v1":
        raise SystemExit("reviewed Wave 1 dry-run evidence has the wrong schema")
    if payload.get("manual_review_required") is not True:
        raise SystemExit("reviewed Wave 1 dry-run evidence is not reviewable")
    return payload


def _parse_job_id(raw: str) -> str | None:
    try:
        payload = json.loads(raw)
    except ValueError:
        payload = None

    def visit(value: object) -> str | None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in {"id", "job_id", "jobid"} and isinstance(item, str):
                    if re.fullmatch(r"aijob-[A-Za-z0-9]+", item):
                        return item
                found = visit(item)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for item in value:
                found = visit(item)
                if found is not None:
                    return found
        return None

    found = visit(payload)
    if found is not None:
        return found
    match = re.search(r"\baijob-[A-Za-z0-9]+\b", raw)
    return match.group(0) if match else None


def _redacted_command(command: list[str]) -> list[str]:
    redacted = list(command)
    for index, value in enumerate(redacted[:-1]):
        if value == "--env-secret":
            name = redacted[index + 1].partition("=")[0]
            redacted[index + 1] = f"{name}=[MYSTERYBOX_SELECTOR]"
    return redacted


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_evidence(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise SystemExit(f"Wave 1 evidence output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
