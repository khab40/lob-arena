#!/usr/bin/env python3
from __future__ import annotations

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
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "backend"))

from app.market_data.public_sample import (  # noqa: E402
    C0PreflightRequest,
    DEVELOPMENT_BUCKET,
    OBJECT_STORAGE_ENDPOINT,
    PROJECT_ID,
    PUBLIC_SAMPLE_PREFIX,
)
from scripts.submit_nebius_job import (  # noqa: E402
    _canonical_hash,
    _parse_job_id,
    _redacted_command,
    _verify_created_short_tag_job,
    _verify_reviewed_registry_evidence,
    _verify_short_tag,
)


INPUT_PATTERN = re.compile(
    rf"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
    r"preflight-requests/[a-z0-9][a-z0-9-]{2,62}/staging/?"
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review or submit one bounded Nebius C0 preflight.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--deployment-image")
    parser.add_argument("--allow-short-tag-workaround", action="store_true")
    parser.add_argument("--name", required=True)
    parser.add_argument("--subnet-id", default=os.environ.get("NEBIUS_SUBNET_ID"))
    parser.add_argument("--input-uri", required=True)
    parser.add_argument("--request-evidence", type=Path, required=True)
    parser.add_argument("--publication-evidence", type=Path)
    parser.add_argument("--access-key-secret-id", required=True)
    parser.add_argument("--secret-key-secret-id", required=True)
    parser.add_argument("--data-prep-spend-usd", type=float, required=True)
    parser.add_argument("--data-prep-jobs-consumed", type=int, required=True)
    parser.add_argument("--approval-reference")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--reviewed-dry-run", type=Path)
    parser.add_argument("--reviewed-dry-run-sha256")
    args = parser.parse_args(argv)

    if not args.subnet_id:
        raise SystemExit("C0 requires --subnet-id or NEBIUS_SUBNET_ID")
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", args.name) is None:
        raise SystemExit("C0 Job name must be a bounded lowercase identifier")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", args.subnet_id) is None:
        raise SystemExit("C0 subnet ID is invalid")
    if os.environ.get("NEBIUS_VOLUME"):
        raise SystemExit("C0 forbids Object Storage mounts; use bounded S3 API calls")
    if any(
        os.environ.get(name)
        for name in (
            "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID",
            "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
            "NEBIUS_OBJECT_STORAGE_SESSION_TOKEN",
        )
    ):
        raise SystemExit("C0 forbids inline Object Storage credentials")
    if not math.isfinite(args.data_prep_spend_usd) or not 0 <= args.data_prep_spend_usd < 8:
        raise SystemExit("C0 requires reconciled data-preparation spend below the USD 8 stop gate")
    if not 0 <= args.data_prep_jobs_consumed < 18:
        raise SystemExit("C0 requires a reconciled public-data Job count below 18")
    if INPUT_PATTERN.fullmatch(args.input_uri) is None:
        raise SystemExit("C0 input URI is outside the exact preflight-request prefix")
    request, package_evidence = _load_request_evidence(args.request_evidence, args.input_uri)
    if request.image != args.image:
        raise SystemExit("C0 image does not match the immutable packaged request")
    if not re.fullmatch(r".+@sha256:[0-9a-f]{64}", args.image):
        raise SystemExit("C0 requires an immutable image digest")
    deployment_image = args.deployment_image or args.image
    short_tag_workaround = deployment_image != args.image
    registry_verification = None
    if short_tag_workaround:
        if not args.allow_short_tag_workaround:
            raise SystemExit("C0 short-tag deployment requires explicit workaround approval")
        registry_verification = _verify_short_tag(deployment_image, args.image)
    elif args.allow_short_tag_workaround:
        raise SystemExit("C0 workaround flag requires a distinct deployment image")

    repository, digest = args.image.rsplit("@sha256:", maxsplit=1)
    if len(repository) > 64:
        raise SystemExit("C0 image repository is too long for the verified Job context")
    job_args = (
        "/job/serverless/jobs/run_market_data_acquisition.py c0-s3 "
        f"--input-uri {args.input_uri} --work-root /job/market-data-c0 "
        f"--endpoint-url {OBJECT_STORAGE_ENDPOINT}"
    )
    command = [
        "nebius",
        "ai",
        "job",
        "create",
        "--name",
        args.name,
        "--parent-id",
        PROJECT_ID,
        "--image",
        deployment_image,
        "--container-command",
        "python",
        "--args",
        job_args,
        "--platform",
        request.resource.platform,
        "--preset",
        request.resource.preset,
        "--disk-size",
        f"{request.resource.disk_size_gib}Gi",
        "--timeout",
        "1h",
        "--subnet-id",
        args.subnet_id,
        "--restart-policy",
        "never",
        "--env-secret",
        f"AWS_ACCESS_KEY_ID={args.access_key_secret_id}",
        "--env-secret",
        f"AWS_SECRET_ACCESS_KEY={args.secret_key_secret_id}",
        "--env",
        "AWS_DEFAULT_REGION=eu-north1",
        "--env",
        "AWS_EC2_METADATA_DISABLED=true",
    ]
    for name, value in (
        ("MARKET_DATA_ACTUAL_PROJECT_ID", PROJECT_ID),
        ("MARKET_DATA_ACTUAL_IMAGE_REPOSITORY", repository),
        ("MARKET_DATA_ACTUAL_IMAGE_SHA256", digest),
        ("MARKET_DATA_ACTUAL_PLATFORM", request.resource.platform),
        ("MARKET_DATA_ACTUAL_PRESET", request.resource.preset),
        ("MARKET_DATA_ACTUAL_DISK_SIZE_GIB", str(request.resource.disk_size_gib)),
        ("MARKET_DATA_ACTUAL_TIMEOUT_SECONDS", str(request.resource.timeout_seconds)),
    ):
        command.extend(["--env", f"{name}={value}"])
    command.extend(["--format", "json"])
    command_sha256 = _canonical_hash(command)

    if args.dry_run:
        payload = {
            "schema_version": "market_data_wave1_c0_dry_run_v1",
            "created_at": datetime.now(UTC).isoformat(),
            "request_sha256": request.canonical_hash(),
            "package_inventory_sha256": package_evidence["package_inventory_sha256"],
            "input_uri": args.input_uri,
            "result_uri": request.result_uri,
            "image": args.image,
            "deployment_image": deployment_image,
            "short_tag_workaround": short_tag_workaround,
            "registry_verification": registry_verification,
            "resource": request.resource.model_dump(mode="json"),
            "command": _redacted_command(command),
            "command_sha256": command_sha256,
            "data_prep_spend_usd": args.data_prep_spend_usd,
            "data_prep_jobs_consumed": args.data_prep_jobs_consumed,
            "http_method": "HEAD",
            "max_http_requests": request.max_http_requests,
            "max_http_body_bytes": request.max_http_body_bytes,
            "s3_probe_size_limit_bytes": request.probe_size_limit_bytes,
            "restart_policy": "never",
            "storage_mounts": [],
            "manual_review_required": True,
            "cloud_resources_created": False,
            "market_data_transferred": False,
        }
        _write_new_json(args.evidence_output, payload)
        print("C0 dry-run evidence written; review the evidence file before submission.")
        return 0

    if not args.approval_reference or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", args.approval_reference
    ) is None:
        raise SystemExit("C0 submission requires an explicit bounded approval reference")
    publication = _load_publication_evidence(args.publication_evidence)
    if (
        publication.get("approval_reference") != args.approval_reference
        or publication.get("destination") != args.input_uri
        or publication.get("request_sha256") != request.canonical_hash()
        or publication.get("package_inventory_sha256")
        != package_evidence["package_inventory_sha256"]
    ):
        raise SystemExit("C0 publication evidence is not bound to this approved request")
    reviewed = _load_reviewed_dry_run(args.reviewed_dry_run)
    reviewed_sha256 = hashlib.sha256(args.reviewed_dry_run.read_bytes()).hexdigest()
    if reviewed_sha256 != args.reviewed_dry_run_sha256:
        raise SystemExit("C0 reviewed dry-run SHA-256 confirmation is missing or incorrect")
    for field, expected in (
        ("request_sha256", request.canonical_hash()),
        ("package_inventory_sha256", package_evidence["package_inventory_sha256"]),
        ("command_sha256", command_sha256),
        ("data_prep_spend_usd", args.data_prep_spend_usd),
        ("data_prep_jobs_consumed", args.data_prep_jobs_consumed),
        ("deployment_image", deployment_image),
        ("short_tag_workaround", short_tag_workaround),
    ):
        if reviewed.get(field) != expected:
            raise SystemExit(f"C0 reviewed dry run no longer matches {field}")
    _verify_reviewed_registry_evidence(reviewed, registry_verification)

    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode:
        raise SystemExit("C0 Nebius Job submission failed; inspect the separately hashed evidence")
    job_id = _parse_job_id(completed.stdout)
    if job_id is None:
        raise SystemExit("C0 Job response did not contain a canonical Job ID")
    observed_image = None
    post_verification = None
    if short_tag_workaround:
        try:
            observed_image, post_verification = _verify_created_short_tag_job(
                job_id, deployment_image, args.image
            )
        except RuntimeError as exc:
            subprocess.run(
                ["nebius", "ai", "job", "cancel", job_id, "--format", "json"],
                check=False,
                text=True,
                capture_output=True,
            )
            raise SystemExit("C0 post-submit digest verification failed; cancellation requested") from exc
    submitted_at = datetime.now(UTC)
    payload = {
        "schema_version": "market_data_wave1_c0_submission_v1",
        "submitted_at": submitted_at.isoformat(),
        "watchdog_deadline": (submitted_at + timedelta(minutes=15)).isoformat(),
        "watchdog_seconds": 900,
        "approval_reference": args.approval_reference,
        "request_sha256": request.canonical_hash(),
        "command_sha256": command_sha256,
        "reviewed_dry_run_sha256": reviewed_sha256,
        "job_id": job_id,
        "input_uri": args.input_uri,
        "result_uri": request.result_uri,
        "image": args.image,
        "deployment_image": deployment_image,
        "observed_job_image": observed_image,
        "short_tag_workaround": short_tag_workaround,
        "pre_submission_registry_verification": registry_verification,
        "post_submission_registry_verification": post_verification,
        "data_prep_spend_usd": args.data_prep_spend_usd,
        "data_prep_jobs_consumed_before_submit": args.data_prep_jobs_consumed,
        "data_prep_jobs_consumed_after_submit": args.data_prep_jobs_consumed + 1,
        "status": "SUBMITTED",
        "response_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
    }
    _write_new_json(args.evidence_output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _load_request_evidence(
    path: Path, input_uri: str
) -> tuple[C0PreflightRequest, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != "market_data_wave1_c0_package_v1"
        or payload.get("destination") != input_uri.rstrip("/")
        or payload.get("cloud_resources_mutated") is not False
        or payload.get("market_data_transferred") is not False
    ):
        raise SystemExit("C0 package evidence is invalid")
    request = C0PreflightRequest.model_validate(payload.get("request"))
    if payload.get("request_sha256") != request.canonical_hash():
        raise SystemExit("C0 package request hash is invalid")
    return request, payload


def _load_publication_evidence(path: Path | None) -> dict[str, object]:
    if path is None or not path.is_file():
        raise SystemExit("C0 submission requires approved input-publication evidence")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "market_data_wave1_c0_publication_v1":
        raise SystemExit("C0 publication evidence has the wrong schema")
    return payload


def _load_reviewed_dry_run(path: Path | None) -> dict[str, object]:
    if path is None or not path.is_file():
        raise SystemExit("C0 submission requires reviewed dry-run evidence")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != "market_data_wave1_c0_dry_run_v1"
        or payload.get("manual_review_required") is not True
        or payload.get("cloud_resources_created") is not False
        or payload.get("market_data_transferred") is not False
    ):
        raise SystemExit("C0 reviewed dry-run evidence is invalid")
    return payload


def _write_new_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise SystemExit(f"C0 evidence output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
