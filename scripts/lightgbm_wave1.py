#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.lightgbm.artifacts import sha256_file  # noqa: E402
from app.ml.lightgbm.cloud_contracts import (  # noqa: E402
    CloudArtifact,
    LightGbmCloudJobRequest,
    Wave1ExperimentSpec,
    Wave1FinalAuthorization,
    Wave1FixtureInput,
)
from app.ml.lightgbm.cloud_fixture import fixture_hash  # noqa: E402
from app.ml.lightgbm.cloud_runner import execute_wave1_request, verify_wave1_result  # noqa: E402
from app.nebius.object_storage import (  # noqa: E402
    download_s3_release,
    inventory_directory,
    publish_s3_input_release,
    write_checksum_file,
)


PROJECT_ID = "project-e00g6zvxpr00waz8t3y51k"
SIGNER = "Alexey Khabalov — Wave 1 Release Approver"
LOCAL_IMAGE = "ghcr.io/khab40/lob-arena-jobs@sha256:" + "0" * 64
DEVELOPMENT_BUCKET = "aimada-wave1-dev-e00g6zvxpr00"
RESULTS_BUCKET = "aimada-wave1-results-e00g6zvxpr00"
OBJECT_STORAGE_ENDPOINT_URL = "https://storage.eu-north1.nebius.cloud"
DEFAULT_EXPERIMENT_CONFIG = ROOT / "configs" / "experiments" / "lightgbm-wave1" / "development-fixture.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare and verify local LightGBM Wave 1 evidence.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    e2e = subparsers.add_parser("local-e2e", help="Run the complete fixture-only G2 lifecycle")
    e2e.add_argument("--output", type=Path, required=True)
    stage = subparsers.add_parser("stage-fixture", help="Publish one immutable G3 fixture package")
    stage.add_argument("--release-id", required=True)
    stage.add_argument("--run-id", required=True)
    stage.add_argument("--image", required=True)
    stage.add_argument("--endpoint-url", default="https://storage.eu-north1.nebius.cloud")
    stage.add_argument("--experiment-config", type=Path, default=DEFAULT_EXPERIMENT_CONFIG)
    stage.add_argument("--mlflow-tracking-uri", required=True)
    stage.add_argument("--output", type=Path, required=True)
    collect = subparsers.add_parser("collect", help="Verify and inventory a completed result")
    collect.add_argument("--result", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)
    collect.add_argument("--nebius-job-id")
    collect.add_argument("--actual-project-id")
    collect.add_argument("--actual-image")
    collect.add_argument("--actual-platform")
    collect.add_argument("--actual-preset")
    collect.add_argument("--actual-disk-size-gib", type=int)
    collect.add_argument("--actual-timeout-seconds", type=int)
    collect.add_argument("--estimated-cost-usd", type=float)
    collect.add_argument("--campaign-spend-to-date-usd", type=float)
    collect_s3 = subparsers.add_parser(
        "collect-s3", help="Download and verify one completed G4 S3 result"
    )
    collect_s3.add_argument("--result-uri", required=True)
    collect_s3.add_argument("--result", type=Path, required=True)
    collect_s3.add_argument("--submission", type=Path, required=True)
    collect_s3.add_argument("--monitor", type=Path, required=True)
    collect_s3.add_argument("--estimated-cost-usd", type=float, required=True)
    collect_s3.add_argument("--campaign-spend-to-date-usd", type=float, required=True)
    collect_s3.add_argument("--endpoint-url", default="https://storage.eu-north1.nebius.cloud")
    collect_s3.add_argument("--output", type=Path, required=True)
    monitor = subparsers.add_parser("monitor-g4", help="Monitor one G4 Job with a 15-minute watchdog")
    monitor.add_argument("--submission", type=Path, required=True)
    monitor.add_argument("--poll-seconds", type=float, default=30)
    monitor.add_argument("--output", type=Path, required=True)
    g4_exit = subparsers.add_parser("g4-exit", help="Assemble and verify the G4 cloud-smoke exit record")
    g4_exit.add_argument("--stage-evidence", type=Path, required=True)
    g4_exit.add_argument("--dry-run-evidence", type=Path, required=True)
    g4_exit.add_argument("--submission", type=Path, required=True)
    g4_exit.add_argument("--monitor", type=Path, required=True)
    g4_exit.add_argument("--collection", type=Path, required=True)
    g4_exit.add_argument("--result", type=Path, required=True)
    g4_exit.add_argument("--output", type=Path, required=True)
    compare = subparsers.add_parser("compare", help="Compare deterministic evidence from development repeats")
    compare.add_argument("results", type=Path, nargs="+")
    compare.add_argument("--output", type=Path, required=True)
    exit_record = subparsers.add_parser("exit-record", help="Assemble a local Wave 1 exit record")
    exit_record.add_argument("--development", type=Path, required=True)
    exit_record.add_argument("--final", type=Path, required=True)
    exit_record.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "local-e2e":
        local_e2e(args.output)
    elif args.command == "stage-fixture":
        stage_fixture(
            args.release_id,
            args.run_id,
            args.image,
            args.endpoint_url,
            args.output,
            experiment_config=args.experiment_config,
            mlflow_tracking_uri=args.mlflow_tracking_uri,
        )
    elif args.command == "collect":
        collect_result(
            args.result,
            args.output,
            nebius_job_id=args.nebius_job_id,
            actual_project_id=args.actual_project_id,
            actual_image=args.actual_image,
            actual_platform=args.actual_platform,
            actual_preset=args.actual_preset,
            actual_disk_size_gib=args.actual_disk_size_gib,
            actual_timeout_seconds=args.actual_timeout_seconds,
            estimated_cost_usd=args.estimated_cost_usd,
            campaign_spend_to_date_usd=args.campaign_spend_to_date_usd,
        )
    elif args.command == "collect-s3":
        collect_s3_result(
            args.result_uri,
            args.result,
            args.output,
            submission_path=args.submission,
            monitor_path=args.monitor,
            estimated_cost_usd=args.estimated_cost_usd,
            campaign_spend_to_date_usd=args.campaign_spend_to_date_usd,
            endpoint_url=args.endpoint_url,
        )
    elif args.command == "monitor-g4":
        monitor_g4_job(
            args.submission,
            args.output,
            poll_seconds=args.poll_seconds,
        )
    elif args.command == "g4-exit":
        create_g4_exit_record(
            stage_evidence_path=args.stage_evidence,
            dry_run_evidence_path=args.dry_run_evidence,
            submission_path=args.submission,
            monitor_path=args.monitor,
            collection_path=args.collection,
            result=args.result,
            output=args.output,
        )
    elif args.command == "compare":
        compare_results(args.results, args.output)
    else:
        create_exit_record(args.development, args.final, args.output)
    return 0


def stage_fixture(
    release_id: str,
    run_id: str,
    image: str,
    endpoint_url: str,
    output: Path,
    *,
    experiment_config: Path = DEFAULT_EXPERIMENT_CONFIG,
    mlflow_tracking_uri: str,
) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", release_id):
        raise ValueError("release ID must be a lowercase immutable identifier")
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT_URL:
        raise ValueError("Wave 1 staging requires the approved eu-north1 S3 endpoint")
    if any(
        name in os.environ
        for name in (
            "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID",
            "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
        )
    ):
        raise ValueError("inline Nebius credential variables are forbidden")
    created_at = datetime.now(UTC)
    experiment = Wave1ExperimentSpec.model_validate_json(
        experiment_config.read_text(encoding="utf-8")
    )
    destination = f"s3://{DEVELOPMENT_BUCKET}/releases/{release_id}/staging"
    request = LightGbmCloudJobRequest(
        campaign_id="wave1-research-20260816",
        run_id=run_id,
        mode="development",
        project_id=PROJECT_ID,
        image=image,
        created_at=created_at,
        git_commit=_git_commit(),
        experiment=experiment,
        input=Wave1FixtureInput(feature_release_sha256=fixture_hash("wave1-fixture-feature-release")),
        result_uri=(
            f"s3://{RESULTS_BUCKET}/campaigns/"
            f"wave1-research-20260816/development/{run_id}"
        ),
        mlflow_tracking_uri=mlflow_tracking_uri,
    )
    with tempfile.TemporaryDirectory(prefix="wave1-fixture-stage-") as directory:
        package = Path(directory)
        (package / "fixture-manifest.json").write_text(
            json.dumps(
                {
                    "schema_version": "lightgbm_wave1_fixture_release_v1",
                    "corpus_status": "APPROVED research-only non-commercial fixture/synthetic corpus",
                    "fixture_version": "lightgbm-wave1-fixture-v1",
                    "feature_release_sha256": request.input.feature_release_sha256,
                    "contains_licensed_market_data": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        (package / "request.json").write_bytes(request.canonical_bytes())
        inventory = inventory_directory(package)
        (package / "input-inventory.json").write_text(
            inventory.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        publish_inventory = inventory_directory(package, exclude_markers=True)
        write_checksum_file(package, publish_inventory)
        (package / "SUCCESS").write_text(
            publish_inventory.model_dump_json(indent=2) + "\n", encoding="utf-8"
        )
        evidence = publish_s3_input_release(package, destination, endpoint_url=endpoint_url)
        payload = {
            "schema_version": "lightgbm_wave1_g3_input_evidence_v1",
            "release_id": release_id,
            "run_id": run_id,
            "destination": destination,
            "request_sha256": request.canonical_hash(),
            "request": request.model_dump(mode="json"),
            "project_id": request.project_id,
            "image": request.image,
            "resource": request.resource.model_dump(mode="json"),
            "inventory_sha256": hashlib.sha256(
                (package / "input-inventory.json").read_bytes()
            ).hexdigest(),
            "objects": [item.__dict__ for item in evidence],
            "success_published_last": True,
            "read_back_verified": True,
        }
    _write_json_once(output, payload)


def local_e2e(output: Path) -> None:
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Wave 1 local output already exists: {output}")
    output.mkdir(parents=True)
    inputs = output / "inputs"
    inputs.mkdir()
    created_at = datetime.now(UTC)
    campaign_id = "wave1-local-fixture"
    development = output / "development"
    development_request = _request(
        campaign_id=campaign_id,
        run_id="wave1-local-development",
        mode="development",
        created_at=created_at,
        result=development,
    )
    development_request_path = inputs / "development-request.json"
    development_request_path.write_bytes(development_request.canonical_bytes())
    execute_wave1_request(development_request_path, input_root=inputs)
    verify_wave1_result(development)

    final_inputs = output / "final-inputs"
    candidate_root = final_inputs / "candidate"
    shutil.copytree(development, candidate_root)
    candidate_ref = _artifact(candidate_root / "candidate.json", final_inputs, "candidate")
    authorization_dir = final_inputs / "authorization"
    authorization_dir.mkdir(parents=True)
    signed_at = datetime.now(UTC)
    authorization = Wave1FinalAuthorization(
        campaign_id=campaign_id,
        candidate_hash=candidate_ref.sha256,
        signer=SIGNER,
        signed_at=signed_at,
        statement=f"APPROVE WAVE1 FINAL TEST {candidate_ref.sha256} {signed_at.isoformat()}",
    )
    authorization_path = authorization_dir / "authorization.json"
    authorization_path.write_bytes(authorization.canonical_bytes())
    signature_path = authorization_dir / "authorization.sig"
    public_key_path = authorization_dir / "authorization-public.pem"
    _sign_local_authorization(authorization_path, signature_path, public_key_path)

    final = output / "final"
    final_request = _request(
        campaign_id=campaign_id,
        run_id="wave1-local-final",
        mode="final-evaluation",
        created_at=created_at,
        result=final,
        candidate=candidate_ref,
        authorization=_artifact(authorization_path, final_inputs, "authorization"),
        authorization_signature=_artifact(signature_path, final_inputs, "authorization_signature"),
        authorization_public_key=_artifact(public_key_path, final_inputs, "authorization_public_key"),
    )
    final_request_path = inputs / "final-request.json"
    final_request_path.write_bytes(final_request.canonical_bytes())
    execute_wave1_request(
        final_request_path,
        input_root=final_inputs,
        trusted_authorization_public_key_sha256=sha256_file(public_key_path),
    )
    verify_wave1_result(final)
    collect_result(final, output / "collection.json")
    create_exit_record(development, final, output / "exit-record.json")
    (output / "LOCAL-G2-SUCCESS").write_text("verified\n", encoding="utf-8")


def collect_result(
    result: Path,
    output: Path,
    *,
    nebius_job_id: str | None = None,
    actual_project_id: str | None = None,
    actual_image: str | None = None,
    actual_platform: str | None = None,
    actual_preset: str | None = None,
    actual_disk_size_gib: int | None = None,
    actual_timeout_seconds: int | None = None,
    estimated_cost_usd: float | None = None,
    campaign_spend_to_date_usd: float | None = None,
) -> None:
    run = verify_wave1_result(result)
    request = LightGbmCloudJobRequest.model_validate_json(
        (result / "request.json").read_text(encoding="utf-8")
    )
    cloud_execution = request.result_uri.startswith("s3://")
    actual_context = {
        "project_id": actual_project_id,
        "image": actual_image,
        "platform": actual_platform,
        "preset": actual_preset,
        "disk_size_gib": actual_disk_size_gib,
        "timeout_seconds": actual_timeout_seconds,
    }
    if cloud_execution:
        if not nebius_job_id or any(value is None for value in actual_context.values()):
            raise ValueError("cloud collection requires the Nebius Job ID and actual Job context")
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", nebius_job_id) is None:
            raise ValueError("cloud collection requires a canonical Nebius Job ID")
        expected_context = {
            "project_id": request.project_id,
            "image": request.image,
            "platform": request.resource.platform,
            "preset": request.resource.preset,
            "disk_size_gib": request.resource.disk_size_gib,
            "timeout_seconds": request.resource.timeout_seconds,
        }
        if actual_context != expected_context:
            raise ValueError("collected Nebius Job context does not match the governed request")
        if (
            estimated_cost_usd is None
            or not math.isfinite(estimated_cost_usd)
            or estimated_cost_usd < 0
        ):
            raise ValueError("cloud collection requires a nonnegative Job cost estimate")
        if (
            campaign_spend_to_date_usd is None
            or not math.isfinite(campaign_spend_to_date_usd)
            or not 0 <= campaign_spend_to_date_usd <= 50
        ):
            raise ValueError("cloud collection requires reconciled campaign spend within USD 50")
        if run.mlflow_run_id is None:
            raise ValueError("cloud collection requires a bound MLflow run ID")
    inventory = inventory_directory(result)
    payload = {
        "schema_version": "lightgbm_wave1_collection_v1",
        "run_id": run.run_id,
        "request_sha256": run.request_sha256,
        "result_sha256": _inventory_hash(inventory.model_dump(mode="json")),
        "file_count": len(inventory.files),
        "size_bytes": sum(item.size_bytes for item in inventory.files),
        "nebius_job_id": nebius_job_id,
        "actual_job_context": actual_context if cloud_execution else None,
        "estimated_cost_usd": estimated_cost_usd,
        "campaign_spend_to_date_usd": campaign_spend_to_date_usd,
        "mlflow_run_id": run.mlflow_run_id,
        "verified": True,
    }
    _write_json_once(output, payload)


def monitor_g4_job(
    submission_path: Path,
    output: Path,
    *,
    poll_seconds: float = 30,
    command_runner: Callable[..., subprocess.CompletedProcess[str]] | None = None,
    monotonic: Callable[[], float] | None = None,
    sleeper: Callable[[float], None] | None = None,
    wall_clock: Callable[[], datetime] | None = None,
) -> None:
    submission = _load_evidence(
        submission_path,
        schema_version="lightgbm_wave1_g4_submission_v1",
    )
    job_id = _canonical_job_id(submission.get("job_id"))
    submitted_at = _parse_utc_timestamp(submission.get("submitted_at"), "submitted_at")
    watchdog_deadline = _parse_utc_timestamp(
        submission.get("watchdog_deadline"), "watchdog_deadline"
    )
    if (
        submission.get("status") != "SUBMITTED"
        or submission.get("watchdog_seconds") != 900
        or (watchdog_deadline - submitted_at).total_seconds() != 900
    ):
        raise ValueError("G4 monitor requires a submitted Job with the fixed watchdog")
    submission_resource = submission.get("resource")
    if not isinstance(submission_resource, dict):
        raise ValueError("G4 monitor requires submitted resource evidence")
    expected_context = {
        "project_id": submission.get("project_id"),
        "image": submission.get("deployment_image") or submission.get("image"),
        "platform": submission_resource.get("platform"),
        "preset": submission_resource.get("preset"),
        "disk_size_gib": submission_resource.get("disk_size_gib"),
        "timeout_seconds": submission_resource.get("timeout_seconds"),
    }
    if not 0 < poll_seconds <= 60:
        raise ValueError("G4 poll interval must be within 60 seconds")
    log_path = output.with_suffix(".logs.txt")
    if output.exists() or log_path.exists():
        raise FileExistsError("G4 monitor evidence output already exists")
    runner = command_runner or subprocess.run
    clock = monotonic or time.monotonic
    sleep = sleeper or time.sleep
    utc_now = wall_clock or (lambda: datetime.now(UTC))
    started = clock()

    def elapsed_since_submission() -> float:
        process_elapsed = max(0.0, float(clock()) - float(started))
        receipt_elapsed = max(0.0, (utc_now() - submitted_at).total_seconds())
        return max(process_elapsed, receipt_elapsed)

    history: list[dict[str, object]] = []
    terminal_status: str | None = None
    cancellation_requested = False
    observed_context: dict[str, object] | None = None
    while terminal_status is None:
        completed = runner(
            ["nebius", "ai", "job", "get", job_id, "--format", "json"],
            check=False,
            text=True,
            capture_output=True,
        )
        elapsed = elapsed_since_submission()
        if completed.returncode != 0:
            terminal_status = "STATUS_QUERY_FAILED"
            history.append({"elapsed_seconds": round(elapsed, 3), "status": terminal_status})
            break
        try:
            job_payload = json.loads(completed.stdout)
        except ValueError:
            terminal_status = "STATUS_QUERY_FAILED"
            history.append({"elapsed_seconds": round(elapsed, 3), "status": terminal_status})
            break
        status = _extract_job_status(job_payload)
        current_context = _extract_observed_job_context(job_payload)
        if current_context is not None:
            observed_context = current_context
        history.append({"elapsed_seconds": round(elapsed, 3), "status": status})
        if observed_context is not None and observed_context != expected_context:
            terminal_status = "RESOURCE_MISMATCH"
        elif status == "UNKNOWN":
            terminal_status = "STATUS_QUERY_FAILED"
        elif status in {"COMPLETED", "SUCCEEDED"}:
            if observed_context is None:
                terminal_status = "RESOURCE_EVIDENCE_MISSING"
            else:
                terminal_status = "COMPLETED" if elapsed <= 900 else "WATCHDOG_BREACHED"
        elif status in {"FAILED", "CANCELLED", "CANCELED", "ERROR"}:
            terminal_status = status
        elif elapsed >= 900:
            cancelled = runner(
                ["nebius", "ai", "job", "cancel", job_id, "--format", "json"],
                check=False,
                text=True,
                capture_output=True,
            )
            cancellation_requested = cancelled.returncode == 0
            terminal_status = "WATCHDOG_CANCELLED" if cancellation_requested else "CANCEL_FAILED"
        else:
            sleep(min(poll_seconds, 900 - elapsed))

    elapsed_seconds = elapsed_since_submission()
    logs = runner(
        ["nebius", "ai", "job", "logs", job_id, "--since", "1h", "--timestamps"],
        check=False,
        text=True,
        capture_output=True,
    )
    log_text = _redact_log_text(logs.stdout if logs.returncode == 0 else logs.stderr)
    _write_text_once(log_path, log_text)
    evidence = {
        "schema_version": "lightgbm_wave1_g4_monitor_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "job_id": job_id,
        "request_sha256": submission.get("request_sha256"),
        "submitted_at": submitted_at.isoformat(),
        "watchdog_deadline": watchdog_deadline.isoformat(),
        "status": terminal_status,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "watchdog_seconds": 900,
        "cancellation_requested": cancellation_requested,
        "logs_collected": logs.returncode == 0,
        "logs_path": str(log_path.resolve()),
        "logs_sha256": sha256_file(log_path),
        "observed_job_context": observed_context,
        "status_history": history,
    }
    _write_json_once(output, evidence)
    if terminal_status != "COMPLETED" or logs.returncode != 0:
        raise RuntimeError(f"G4 Job did not complete successfully: {terminal_status}")


def collect_s3_result(
    result_uri: str,
    result: Path,
    output: Path,
    *,
    submission_path: Path,
    monitor_path: Path,
    estimated_cost_usd: float,
    campaign_spend_to_date_usd: float,
    endpoint_url: str,
) -> None:
    submission = _load_evidence(
        submission_path,
        schema_version="lightgbm_wave1_g4_submission_v1",
    )
    monitor = _load_evidence(monitor_path, schema_version="lightgbm_wave1_g4_monitor_v1")
    job_id = _canonical_job_id(submission.get("job_id"))
    if monitor.get("job_id") != job_id or monitor.get("status") != "COMPLETED":
        raise ValueError("G4 collection requires a completed monitor record for the submitted Job")
    if submission.get("result_uri") != result_uri:
        raise ValueError("G4 result URI does not match the submitted governed request")
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT_URL:
        raise ValueError("G4 collection requires the approved eu-north1 S3 endpoint")
    campaign_spend_before = submission.get("campaign_spend_usd")
    if (
        not isinstance(campaign_spend_before, (int, float))
        or isinstance(campaign_spend_before, bool)
        or not math.isfinite(float(campaign_spend_before))
        or not 0 <= float(campaign_spend_before) < 40
        or not math.isfinite(campaign_spend_to_date_usd)
        or not float(campaign_spend_before) <= campaign_spend_to_date_usd <= 50
    ):
        raise ValueError("G4 collection requires reconciled post-Job spend within USD 50")
    observed_context = monitor.get("observed_job_context")
    if not isinstance(observed_context, dict):
        raise ValueError("G4 monitor did not capture actual Job resource evidence")
    download_s3_release(result_uri, result, endpoint_url=endpoint_url)
    request = LightGbmCloudJobRequest.model_validate_json(
        (result / "request.json").read_text(encoding="utf-8")
    )
    if request.canonical_hash() != submission.get("request_sha256"):
        raise ValueError("downloaded G4 result does not match the submitted request")
    collect_result(
        result,
        output,
        nebius_job_id=job_id,
        actual_project_id=str(observed_context.get("project_id")),
        actual_image=str(observed_context.get("image")),
        actual_platform=str(observed_context.get("platform")),
        actual_preset=str(observed_context.get("preset")),
        actual_disk_size_gib=int(observed_context.get("disk_size_gib", -1)),
        actual_timeout_seconds=int(observed_context.get("timeout_seconds", -1)),
        estimated_cost_usd=estimated_cost_usd,
        campaign_spend_to_date_usd=campaign_spend_to_date_usd,
    )


def create_g4_exit_record(
    *,
    stage_evidence_path: Path,
    dry_run_evidence_path: Path,
    submission_path: Path,
    monitor_path: Path,
    collection_path: Path,
    result: Path,
    output: Path,
) -> None:
    stage = _load_evidence(
        stage_evidence_path,
        schema_version="lightgbm_wave1_g3_input_evidence_v1",
    )
    dry_run = _load_evidence(
        dry_run_evidence_path,
        schema_version="lightgbm_wave1_g4_dry_run_v1",
    )
    submission = _load_evidence(
        submission_path,
        schema_version="lightgbm_wave1_g4_submission_v1",
    )
    monitor = _load_evidence(monitor_path, schema_version="lightgbm_wave1_g4_monitor_v1")
    collection = _load_evidence(
        collection_path,
        schema_version="lightgbm_wave1_collection_v1",
    )
    run = verify_wave1_result(result)
    request = LightGbmCloudJobRequest.model_validate_json(
        (result / "request.json").read_text(encoding="utf-8")
    )
    metrics = json.loads((result / "metrics.json").read_text(encoding="utf-8"))
    request_hash = request.canonical_hash()
    job_id = _canonical_job_id(submission.get("job_id"))
    hashes_match = all(
        payload.get("request_sha256") == request_hash
        for payload in (stage, dry_run, submission, monitor, collection)
    )
    reviewed_dry_run = submission.get("reviewed_dry_run_sha256") == sha256_file(
        dry_run_evidence_path
    )
    input_release_bound = (
        stage.get("destination")
        == dry_run.get("input_uri")
        == submission.get("input_uri")
    )
    result_prefix_bound = (
        dry_run.get("result_uri")
        == submission.get("result_uri")
        == request.result_uri
    )
    job_identity = monitor.get("job_id") == job_id == collection.get("nebius_job_id")
    fixed_resources = collection.get("actual_job_context") == {
        "project_id": request.project_id,
        "image": request.image,
        "platform": request.resource.platform,
        "preset": request.resource.preset,
        "disk_size_gib": request.resource.disk_size_gib,
        "timeout_seconds": request.resource.timeout_seconds,
    }
    log_path = Path(str(monitor.get("logs_path", "")))
    logs_verified = (
        monitor.get("logs_collected") is True
        and log_path.is_file()
        and monitor.get("logs_sha256") == sha256_file(log_path)
    )
    secret_free = logs_verified and not _contains_secret_material(log_path)
    for evidence_path in (
        stage_evidence_path,
        dry_run_evidence_path,
        submission_path,
        monitor_path,
        collection_path,
    ):
        if _contains_secret_material(evidence_path):
            secret_free = False
    for path in result.rglob("*"):
        if path.is_file() and _contains_secret_material(path):
            secret_free = False
            break
    result_inventory = inventory_directory(result)
    result_sha256 = _inventory_hash(result_inventory.model_dump(mode="json"))
    estimated_cost = collection.get("estimated_cost_usd")
    campaign_spend_before = submission.get("campaign_spend_usd")
    campaign_spend = collection.get("campaign_spend_to_date_usd")
    jobs_before_submit = submission.get("development_jobs_consumed_before_submit")
    jobs_after_submit = submission.get("development_jobs_consumed_after_submit")
    gates = {
        "staged_input_verified": stage.get("read_back_verified") is True
        and stage.get("success_published_last") is True,
        "reviewed_dry_run_bound": reviewed_dry_run
        and dry_run.get("command_sha256") == submission.get("command_sha256"),
        "request_hashes_match": hashes_match,
        "input_release_bound": input_release_bound,
        "result_prefix_bound": result_prefix_bound,
        "watchdog_receipt_bound": monitor.get("submitted_at") == submission.get("submitted_at")
        and monitor.get("watchdog_deadline") == submission.get("watchdog_deadline"),
        "job_completed_within_watchdog": monitor.get("status") == "COMPLETED"
        and float(monitor.get("elapsed_seconds", 901)) <= 900,
        "job_identity_bound": job_identity,
        "fixed_resources_verified": fixed_resources,
        "result_checksums_verified": collection.get("verified") is True,
        "result_inventory_bound": collection.get("result_sha256") == result_sha256,
        "mlflow_run_bound": run.mlflow_run_id is not None
        and collection.get("mlflow_run_id") == run.mlflow_run_id,
        "development_test_isolation": request.mode == "development"
        and metrics.get("test_fold_accessed") is False,
        "cost_reconciled": isinstance(estimated_cost, (int, float))
        and not isinstance(estimated_cost, bool)
        and math.isfinite(float(estimated_cost))
        and float(estimated_cost) >= 0
        and isinstance(campaign_spend_before, (int, float))
        and not isinstance(campaign_spend_before, bool)
        and math.isfinite(float(campaign_spend_before))
        and 0 <= float(campaign_spend_before) < 40
        and isinstance(campaign_spend, (int, float))
        and not isinstance(campaign_spend, bool)
        and math.isfinite(float(campaign_spend))
        and float(campaign_spend_before) <= float(campaign_spend) <= 50
        and dry_run.get("campaign_spend_usd") == campaign_spend_before,
        "development_job_ceiling_preserved": isinstance(jobs_before_submit, int)
        and not isinstance(jobs_before_submit, bool)
        and isinstance(jobs_after_submit, int)
        and not isinstance(jobs_after_submit, bool)
        and 0 <= jobs_before_submit < 20
        and jobs_after_submit == jobs_before_submit + 1
        and dry_run.get("development_jobs_consumed") == jobs_before_submit,
        "logs_and_artifacts_secret_free": secret_free,
    }
    if not all(gates.values()):
        failed = ", ".join(name for name, passed in gates.items() if not passed)
        raise ValueError(f"G4 exit gates failed: {failed}")
    payload = {
        "schema_version": "lightgbm_wave1_g4_exit_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "status": "passed",
        "campaign_id": request.campaign_id,
        "run_id": request.run_id,
        "request_sha256": request_hash,
        "job_id": job_id,
        "mlflow_run_id": run.mlflow_run_id,
        "result_sha256": result_sha256,
        "reproducibility_hash": run.reproducibility_hash,
        "estimated_cost_usd": collection.get("estimated_cost_usd"),
        "campaign_spend_to_date_usd": collection.get("campaign_spend_to_date_usd"),
        "gates": gates,
        "disposition": "g4_cloud_smoke_passed",
    }
    _write_json_once(output, payload)


def compare_results(results: list[Path], output: Path) -> None:
    if len(results) < 2:
        raise ValueError("repeat comparison requires at least two results")
    records = []
    for result in results:
        run = verify_wave1_result(result)
        metrics = json.loads((result / "metrics.json").read_text(encoding="utf-8"))
        records.append(
            {
                "candidate_package_hash": run.candidate_hash,
                "reproducibility_hash": run.reproducibility_hash,
                "best_iteration": metrics.get("best_iteration"),
                "validation_binary_logloss": metrics.get("validation_binary_logloss"),
            }
        )
    deterministic_records = [
        {key: value for key, value in record.items() if key != "candidate_package_hash"}
        for record in records
    ]
    reproducible = all(record == deterministic_records[0] for record in deterministic_records[1:])
    _write_json_once(
        output,
        {
            "schema_version": "lightgbm_wave1_repeat_comparison_v1",
            "reproducible": reproducible,
            "runs": records,
        },
    )
    if not reproducible:
        raise ValueError("development repeat evidence is not deterministic")


def create_exit_record(development: Path, final: Path, output: Path) -> None:
    development_run = verify_wave1_result(development)
    final_run = verify_wave1_result(final)
    if development_run.candidate_hash != final_run.candidate_hash:
        raise ValueError("final result does not match the frozen development candidate")
    payload = {
        "schema_version": "lightgbm_wave1_exit_v1",
        "scope": "local-fixture-g2-only",
        "corpus_status": "APPROVED research-only non-commercial fixture/synthetic corpus",
        "development_run_id": development_run.run_id,
        "final_run_id": final_run.run_id,
        "candidate_hash": final_run.candidate_hash,
        "local_gates": {"schemas": True, "checksums": True, "authorization": True, "release": True},
        "cloud_resources_created": False,
        "disposition": "cloud_pipeline_qualified_performance_pending",
    }
    _write_json_once(output, payload)


def _request(
    *,
    campaign_id: str,
    run_id: str,
    mode: str,
    created_at: datetime,
    result: Path,
    experiment: Wave1ExperimentSpec | None = None,
    candidate: CloudArtifact | None = None,
    authorization: CloudArtifact | None = None,
    authorization_signature: CloudArtifact | None = None,
    authorization_public_key: CloudArtifact | None = None,
) -> LightGbmCloudJobRequest:
    return LightGbmCloudJobRequest(
        campaign_id=campaign_id,
        run_id=run_id,
        mode=mode,
        project_id=PROJECT_ID,
        image=LOCAL_IMAGE,
        created_at=created_at,
        git_commit=_git_commit(),
        experiment=experiment or Wave1ExperimentSpec(),
        input=Wave1FixtureInput(feature_release_sha256=fixture_hash("wave1-fixture-feature-release")),
        result_uri=result.resolve().as_uri(),
        candidate=candidate,
        authorization=authorization,
        authorization_signature=authorization_signature,
        authorization_public_key=authorization_public_key,
    )


def _artifact(path: Path, root: Path, logical_name: str) -> CloudArtifact:
    return CloudArtifact(
        logical_name=logical_name,
        uri=path.resolve().relative_to(root.resolve()).as_posix(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _sign_local_authorization(document: Path, signature: Path, public_key: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="wave1-local-signing-") as directory:
        private_key = Path(directory) / "private.pem"
        subprocess.run(
            ["openssl", "genpkey", "-algorithm", "Ed25519", "-out", str(private_key)], check=True
        )
        subprocess.run(
            ["openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)], check=True
        )
        subprocess.run(
            [
                "openssl",
                "pkeyutl",
                "-sign",
                "-inkey",
                str(private_key),
                "-rawin",
                "-in",
                str(document),
                "-out",
                str(signature),
            ],
            check=True,
        )


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, check=False, text=True, capture_output=True
    )
    value = completed.stdout.strip().lower()
    return value if len(value) == 40 and all(character in "0123456789abcdef" for character in value) else "0" * 40


def _inventory_hash(payload: object) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _load_evidence(path: Path, *, schema_version: str) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError(f"evidence is unreadable: {path}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != schema_version:
        raise ValueError(f"evidence does not use {schema_version}: {path}")
    return payload


def _canonical_job_id(value: object) -> str:
    if not isinstance(value, str) or re.fullmatch(r"aijob-[A-Za-z0-9]+", value) is None:
        raise ValueError("G4 evidence requires a canonical Nebius Job ID")
    return value


def _parse_utc_timestamp(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"G4 evidence requires {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"G4 evidence has an invalid {field}") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"G4 evidence requires timezone-aware {field}")
    return parsed.astimezone(UTC)


def _extract_job_status(payload: object) -> str:
    candidates: list[str] = []

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = re.sub(r"[^a-z]", "", str(key).lower())
                if normalized in {"status", "state", "phase"} and isinstance(item, str):
                    candidates.append(item.upper().replace("-", "_"))
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    recognized = {
        "QUEUED",
        "PENDING",
        "STARTING",
        "RUNNING",
        "COMPLETED",
        "SUCCEEDED",
        "FAILED",
        "CANCELLED",
        "CANCELED",
        "ERROR",
    }
    return next((status for status in candidates if status in recognized), "UNKNOWN")


def _extract_observed_job_context(payload: object) -> dict[str, object] | None:
    flattened: dict[str, list[object]] = {}

    def visit(value: object) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = re.sub(r"[^a-z]", "", str(key).lower())
                flattened.setdefault(normalized, []).append(item)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)

    def text_value(*aliases: str) -> str | None:
        for alias in aliases:
            for value in flattened.get(alias, ()):
                if isinstance(value, str) and value.strip():
                    return value.strip()
                if isinstance(value, int):
                    return str(value)
        return None

    project_id = text_value("parentid", "projectid")
    image = text_value("image", "imagepath", "containerimage")
    platform = text_value("platform", "platformid")
    preset = text_value("preset", "presetid")
    disk_raw = text_value("disksize", "disksizegib", "sizebytes")
    timeout_raw = text_value("timeout", "timeoutseconds")
    disk_size_gib = _parse_gib(disk_raw)
    timeout_seconds = _parse_duration_seconds(timeout_raw)
    if None in (project_id, image, platform, preset, disk_size_gib, timeout_seconds):
        return None
    return {
        "project_id": project_id,
        "image": image,
        "platform": platform,
        "preset": preset,
        "disk_size_gib": disk_size_gib,
        "timeout_seconds": timeout_seconds,
    }


def _parse_gib(value: str | None) -> int | None:
    if value is None:
        return None
    match = re.fullmatch(r"([0-9]+)(?:Gi|GiB)?", value, re.IGNORECASE)
    if match is None:
        return None
    amount = int(match.group(1))
    if amount > 1024 and amount % (1024**3) == 0:
        return amount // (1024**3)
    return amount


def _parse_duration_seconds(value: str | None) -> int | None:
    if value is None:
        return None
    if re.fullmatch(r"[0-9]+", value):
        return int(value)
    match = re.fullmatch(r"([0-9]+)([hms])", value, re.IGNORECASE)
    if match is None:
        return None
    multiplier = {"h": 3600, "m": 60, "s": 1}[match.group(2).lower()]
    return int(match.group(1)) * multiplier


def _redact_log_text(value: str) -> str:
    redacted = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value)
    redacted = re.sub(
        r"(?i)((?:AWS_(?:ACCESS_KEY_ID|SECRET_ACCESS_KEY|SESSION_TOKEN)|"
        r"MLFLOW_TRACKING_(?:USERNAME|PASSWORD))\s*[=:]\s*)([^\s,;]+)",
        r"\1[REDACTED]",
        redacted,
    )
    return redacted


def _contains_secret_material(path: Path) -> bool:
    try:
        value = path.read_bytes()
    except OSError:
        return True
    patterns = (
        rb"AKIA[0-9A-Z]{16}",
        rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----",
        rb"(?i)Bearer\s+(?!\[REDACTED\])[A-Za-z0-9._~+/=-]{16,}",
        rb"(?i)(?:AWS_SECRET_ACCESS_KEY|AWS_SESSION_TOKEN|MLFLOW_TRACKING_PASSWORD)"
        rb"\s*[=:]\s*(?!\[(?:REDACTED|MYSTERYBOX_SELECTOR)\])[^\s,;]{8,}",
    )
    return any(re.search(pattern, value) is not None for pattern in patterns)


def _write_json_once(path: Path, payload: dict[str, object]) -> None:
    _write_text_once(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_text_once(path: Path, value: str) -> None:
    if path.exists():
        raise FileExistsError(f"evidence output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
