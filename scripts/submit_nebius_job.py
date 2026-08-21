import argparse
import json
import os
import subprocess
import re
from pathlib import Path


WAVE1_ENDPOINT_URL = "https://storage.eu-north1.nebius.cloud"
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
    parser.add_argument("--s3-output-uri", default=os.environ.get("NEBIUS_JOB_OUTPUT_URI", ""))
    parser.add_argument("--s3-endpoint-url", default=os.environ.get("NEBIUS_OBJECT_STORAGE_ENDPOINT_URL", ""))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--workload", choices=("synthetic", "lightgbm-wave1"), default="synthetic")
    parser.add_argument("--input-uri", default=os.environ.get("NEBIUS_WAVE1_INPUT_URI", ""))
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
        if re.fullmatch(r".+@sha256:[0-9a-f]{64}", args.image) is None:
            raise SystemExit("LightGBM Wave 1 requires an immutable image digest")
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
        if os.environ.get("NEBIUS_VOLUME"):
            raise SystemExit("NEBIUS_VOLUME is forbidden for LightGBM Wave 1; use S3 API staging")
        job_args = (
            f"/job/serverless/jobs/run_lightgbm_wave1.py run-s3 --input-uri {args.input_uri} "
            f"--work-root {args.work_root} --endpoint-url {args.s3_endpoint_url}"
        )
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
    ):
        if secret_id:
            command.extend(["--env-secret", f"{name}={secret_id}"])
    command.extend(["--env", f"AWS_DEFAULT_REGION={os.environ.get('NEBIUS_OBJECT_STORAGE_REGION', 'eu-north1')}"])
    command.extend(["--env", "AWS_EC2_METADATA_DISABLED=true"])

    if args.dry_run:
        print(json.dumps({"command": command}, indent=2))
        return

    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode != 0:
        raise SystemExit(completed.stderr)
    Path("outputs/nebius").mkdir(parents=True, exist_ok=True)
    Path("outputs/nebius/latest_job_create.json").write_text(completed.stdout, encoding="utf-8")
    print(completed.stdout)


if __name__ == "__main__":
    main()
