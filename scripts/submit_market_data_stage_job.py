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

from app.market_data.acquisition import NasdaqAcquisitionRequest  # noqa: E402
from app.market_data.preparation import NasdaqPreparationRequest  # noqa: E402
from app.market_data.public_sample import OBJECT_STORAGE_ENDPOINT, PROJECT_ID  # noqa: E402
from scripts.submit_nebius_job import (  # noqa: E402
    _canonical_hash,
    _parse_job_id,
    _redacted_command,
    _verify_created_short_tag_job,
    _verify_reviewed_registry_evidence,
    _verify_short_tag,
)


Request = NasdaqAcquisitionRequest | NasdaqPreparationRequest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Review or submit one sequential C1/C2 acquisition or C3 preparation Job."
    )
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
    parser.add_argument(
        "--data-prep-spend-usd",
        type=float,
        help="Optional observed campaign spend; informational and not a submission gate.",
    )
    parser.add_argument("--data-prep-jobs-consumed", type=int, required=True)
    parser.add_argument("--approval-reference")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--evidence-output", type=Path, required=True)
    parser.add_argument("--reviewed-dry-run", type=Path)
    parser.add_argument("--reviewed-dry-run-sha256")
    parser.add_argument(
        "--max-new-comparisons",
        type=int,
        choices=(1,),
        help="Preparation-only canary limit; the final prepared result remains unpublished.",
    )
    args = parser.parse_args(argv)
    _validate_arguments(args)
    request, package = _load_request(args.request_evidence, args.input_uri)
    if args.max_new_comparisons is not None and not isinstance(
        request, NasdaqPreparationRequest
    ):
        raise SystemExit("comparison canary limit is valid only for C3 preparation")
    if request.image != args.image:
        raise SystemExit("market-data image does not match the packaged immutable request")
    deployment_image = args.deployment_image or args.image
    workaround = deployment_image != args.image
    registry_verification = _workaround_evidence(args, deployment_image)
    command = _job_command(args, request, deployment_image)
    command_sha256 = _canonical_hash(command)
    common = {
        "operation": package["operation"],
        "request_sha256": request.canonical_hash(),
        "package_inventory_sha256": package["package_inventory_sha256"],
        "input_uri": args.input_uri.rstrip("/"),
        "output_uri": _output_uri(request),
        "image": args.image,
        "deployment_image": deployment_image,
        "short_tag_workaround": workaround,
        "registry_verification": registry_verification,
        "resource": request.resource.model_dump(mode="json"),
        "command_sha256": command_sha256,
        "data_prep_spend_usd": args.data_prep_spend_usd,
        "data_prep_jobs_consumed": args.data_prep_jobs_consumed,
        "sequence_number": request.sequence_number,
        "restart_policy": "never",
        "max_new_comparisons": args.max_new_comparisons,
    }
    if args.dry_run:
        payload = {
            "schema_version": "market_data_wave1_stage_dry_run_v1",
            "created_at": datetime.now(UTC).isoformat(),
            **common,
            "command": _redacted_command(command),
            "manual_review_required": True,
            "cloud_resources_created": False,
            "market_data_transferred": False,
        }
        _write_once(args.evidence_output, payload)
        print("Market-data stage dry-run evidence written; review the evidence file before submission.")
        return 0
    reviewed_sha, publication_approval_reference = _verify_submission_gate(
        args, request, package, common
    )
    completed = subprocess.run(command, check=False, text=True, capture_output=True)
    if completed.returncode:
        raise SystemExit("market-data Nebius Job submission failed; inspect bounded CLI logs")
    job_id = _parse_job_id(completed.stdout)
    if job_id is None:
        raise SystemExit("market-data Job response omitted its canonical Job ID")
    observed_image = None
    post_verification = None
    if workaround:
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
            raise SystemExit(
                "market-data post-submit digest verification failed; cancellation requested"
            ) from exc
    submitted_at = datetime.now(UTC)
    payload = {
        "schema_version": "market_data_wave1_stage_submission_v1",
        "submitted_at": submitted_at.isoformat(),
        "watchdog_deadline": (
            submitted_at + timedelta(seconds=request.resource.timeout_seconds)
        ).isoformat(),
        "approval_reference": args.approval_reference,
        "request_publication_approval_reference": publication_approval_reference,
        **common,
        "reviewed_dry_run_sha256": reviewed_sha,
        "job_id": job_id,
        "observed_job_image": observed_image,
        "post_submission_registry_verification": post_verification,
        "data_prep_jobs_consumed_after_submit": args.data_prep_jobs_consumed + 1,
        "status": "SUBMITTED",
        "response_sha256": hashlib.sha256(completed.stdout.encode()).hexdigest(),
    }
    _write_once(args.evidence_output, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def _validate_arguments(args: argparse.Namespace) -> None:
    if not args.subnet_id:
        raise SystemExit("market-data Job requires --subnet-id or NEBIUS_SUBNET_ID")
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", args.name) is None:
        raise SystemExit("market-data Job name must be a bounded lowercase identifier")
    if args.data_prep_spend_usd is not None and (
        not math.isfinite(args.data_prep_spend_usd) or args.data_prep_spend_usd < 0
    ):
        raise SystemExit("observed data-preparation spend must be finite and non-negative")
    if not 0 <= args.data_prep_jobs_consumed < 15:
        raise SystemExit("public-data Job count must be reconciled below the 15-Job cap")
    if os.environ.get("NEBIUS_VOLUME"):
        raise SystemExit("market-data Jobs forbid Object Storage mounts")
    if any(
        os.environ.get(name)
        for name in (
            "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID",
            "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
        )
    ):
        raise SystemExit("market-data Jobs forbid inline Object Storage credentials")


def _load_request(path: Path, input_uri: str) -> tuple[Request, dict[str, object]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    operation = payload.get("operation")
    model = {
        "acquisition": NasdaqAcquisitionRequest,
        "preparation": NasdaqPreparationRequest,
    }.get(operation)
    if (
        payload.get("schema_version") != "market_data_wave1_request_package_v1"
        or model is None
        or payload.get("destination") != input_uri.rstrip("/")
        or payload.get("cloud_resources_mutated") is not False
        or payload.get("market_data_transferred") is not False
    ):
        raise SystemExit("market-data package evidence is invalid")
    request = model.model_validate(payload.get("request"))
    if payload.get("request_sha256") != request.canonical_hash():
        raise SystemExit("market-data packaged request hash is invalid")
    return request, payload


def _workaround_evidence(args: argparse.Namespace, deployment_image: str):
    workaround = deployment_image != args.image
    if workaround and not args.allow_short_tag_workaround:
        raise SystemExit("short-tag deployment requires explicit workaround approval")
    if not workaround and args.allow_short_tag_workaround:
        raise SystemExit("workaround flag requires a distinct deployment image")
    return _verify_short_tag(deployment_image, args.image) if workaround else None


def _job_command(
    args: argparse.Namespace, request: Request, deployment_image: str
) -> list[str]:
    repository, digest = args.image.rsplit("@sha256:", maxsplit=1)
    if isinstance(request, NasdaqAcquisitionRequest):
        runner = "/job/serverless/jobs/run_market_data_acquisition.py"
        operation = "acquire-s3"
        work_root = "/job/market-data-acquire"
    else:
        runner = "/job/serverless/jobs/run_market_data_preparation.py"
        operation = "prepare-s3"
        work_root = "/job/market-data-prepare"
    job_args = (
        f"{runner} {operation} "
        f"--input-uri {args.input_uri.rstrip('/')} --work-root {work_root} "
        f"--endpoint-url {OBJECT_STORAGE_ENDPOINT}"
    )
    max_new_comparisons = getattr(args, "max_new_comparisons", None)
    if isinstance(request, NasdaqPreparationRequest) and max_new_comparisons is not None:
        job_args += f" --max-new-comparisons {max_new_comparisons}"
    command = [
        "nebius", "ai", "job", "create", "--name", args.name,
        "--parent-id", PROJECT_ID, "--image", deployment_image,
        "--container-command", "python", "--args", job_args,
        "--platform", request.resource.platform, "--preset", request.resource.preset,
        "--disk-size", f"{request.resource.disk_size_gib}Gi",
        "--timeout", _format_timeout(request.resource.timeout_seconds),
        "--subnet-id", args.subnet_id, "--restart-policy", "never",
        "--env-secret", f"AWS_ACCESS_KEY_ID={args.access_key_secret_id}",
        "--env-secret", f"AWS_SECRET_ACCESS_KEY={args.secret_key_secret_id}",
        "--env", "AWS_DEFAULT_REGION=eu-north1",
        "--env", "AWS_EC2_METADATA_DISABLED=true",
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
    return command


def _verify_submission_gate(
    args: argparse.Namespace,
    request: Request,
    package: dict[str, object],
    common: dict[str, object],
) -> tuple[str, str]:
    if not args.approval_reference or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", args.approval_reference
    ) is None:
        raise SystemExit("market-data submission requires an explicit approval reference")
    if args.publication_evidence is None or args.reviewed_dry_run is None:
        raise SystemExit("market-data submission requires publication and reviewed dry-run evidence")
    publication = json.loads(args.publication_evidence.read_text(encoding="utf-8"))
    if any(
        publication.get(name) != value
        for name, value in (
            ("schema_version", "market_data_wave1_request_publication_v1"),
            ("destination", args.input_uri.rstrip("/")),
            ("request_sha256", request.canonical_hash()),
            ("package_inventory_sha256", package["package_inventory_sha256"]),
        )
    ):
        raise SystemExit("market-data publication evidence is not bound to this request")
    publication_approval_reference = publication.get("approval_reference")
    if not isinstance(publication_approval_reference, str) or re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", publication_approval_reference
    ) is None:
        raise SystemExit("market-data publication evidence lacks a valid approval reference")
    reviewed_sha = hashlib.sha256(args.reviewed_dry_run.read_bytes()).hexdigest()
    if reviewed_sha != args.reviewed_dry_run_sha256:
        raise SystemExit("reviewed market-data dry-run SHA-256 is missing or incorrect")
    reviewed = json.loads(args.reviewed_dry_run.read_text(encoding="utf-8"))
    if reviewed.get("schema_version") != "market_data_wave1_stage_dry_run_v1":
        raise SystemExit("reviewed market-data dry run has the wrong schema")
    for name, value in common.items():
        if name != "registry_verification" and reviewed.get(name) != value:
            raise SystemExit(f"reviewed market-data dry run no longer matches {name}")
    _verify_reviewed_registry_evidence(reviewed, common["registry_verification"])
    return reviewed_sha, publication_approval_reference


def _output_uri(request: Request) -> str:
    return (
        request.quarantine_uri
        if isinstance(request, NasdaqAcquisitionRequest)
        else request.result_uri
    )


def _format_timeout(timeout_seconds: int) -> str:
    if timeout_seconds % 3600 == 0:
        return f"{timeout_seconds // 3600}h"
    return f"{timeout_seconds}s"


def _write_once(path: Path, payload: object) -> None:
    if path.exists():
        raise SystemExit(f"market-data evidence output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
