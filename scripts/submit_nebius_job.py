import argparse
import json
import os
import subprocess
import re
import sys
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
        for name, value in (
            ("WAVE1_ACTUAL_PROJECT_ID", WAVE1_PROJECT_ID),
            ("WAVE1_ACTUAL_IMAGE", args.image),
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

    if args.dry_run:
        print(json.dumps({"command": command}, indent=2))
        return

    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise SystemExit(completed.stderr)
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


if __name__ == "__main__":
    main()
