#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.market_data.public_sample import (  # noqa: E402
    C0PreflightRequest,
    DEVELOPMENT_BUCKET,
    EXPECTED_SOURCES,
    OBJECT_STORAGE_ENDPOINT,
    PUBLIC_SAMPLE_PREFIX,
    config_artifact,
    load_source_config,
    verify_c0_result,
)
from app.market_data.acquisition import (  # noqa: E402
    NasdaqAcquisitionRequest,
    QuarantineLifecycleEvidence,
)
from app.market_data.preparation import NasdaqPreparationRequest  # noqa: E402
from app.market_data.projection_freeze import (  # noqa: E402
    FINAL_BUCKET,
    NasdaqProjectionFreezeRequest,
    PreparedReleaseBinding,
    verify_projection_candidate,
)
from app.market_data.projections import FinalAccessDenialEvidence  # noqa: E402
from app.nebius.object_storage import (  # noqa: E402
    TransferLimits,
    download_s3_release,
    inventory_directory,
    publish_local_result,
    publish_s3_input_release,
    verify_s3_members_access_denied,
    verify_complete_result,
)


DEFAULT_SOURCE_CONFIG = ROOT / "configs" / "data" / "nasdaq-public-sample-v1.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare, publish, and verify bounded C0 evidence.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare-c0", help="Build a local immutable C0 input package")
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--image", required=True)
    prepare.add_argument("--source-config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    projection = subparsers.add_parser(
        "prepare-projection", help="Build one immutable four-date C4 request package"
    )
    _request_arguments(projection)
    projection.add_argument("--release-id", required=True)
    projection.add_argument("--prepared-releases", type=Path, required=True)
    projection.add_argument("--source-config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    collect_projection = subparsers.add_parser(
        "collect-projection", help="Download and verify one C4 projection candidate"
    )
    collect_projection.add_argument("--result-uri", required=True)
    collect_projection.add_argument("--result", type=Path, required=True)
    collect_projection.add_argument("--endpoint-url", default=OBJECT_STORAGE_ENDPOINT)
    collect_projection.add_argument("--evidence-output", type=Path, required=True)
    publish_projection = subparsers.add_parser(
        "publish-projection", help="Publish one approved isolated C4 projection scope"
    )
    publish_projection.add_argument("--candidate", type=Path, required=True)
    publish_projection.add_argument("--scope", choices=("development", "final"), required=True)
    publish_projection.add_argument("--release-id", required=True)
    publish_projection.add_argument("--approval-reference", required=True)
    publish_projection.add_argument("--endpoint-url", default=OBJECT_STORAGE_ENDPOINT)
    publish_projection.add_argument("--evidence-output", type=Path, required=True)
    denial = subparsers.add_parser(
        "verify-final-denial",
        help="Prove the active development identity cannot read final projections",
    )
    denial.add_argument("--release-id", required=True)
    denial.add_argument("--development-identity-id", required=True)
    denial.add_argument("--endpoint-url", default=OBJECT_STORAGE_ENDPOINT)
    denial.add_argument("--evidence-output", type=Path, required=True)
    prepare.add_argument("--package", type=Path, required=True)
    prepare.add_argument("--evidence-output", type=Path, required=True)
    publish = subparsers.add_parser("publish-c0", help="Publish an approved C0 input package")
    publish.add_argument("--package", type=Path, required=True)
    publish.add_argument("--package-evidence", type=Path, required=True)
    publish.add_argument("--approval-reference", required=True)
    publish.add_argument("--endpoint-url", default=OBJECT_STORAGE_ENDPOINT)
    publish.add_argument("--evidence-output", type=Path, required=True)
    collect = subparsers.add_parser("collect-c0", help="Download and verify a C0 result")
    collect.add_argument("--result-uri", required=True)
    collect.add_argument("--result", type=Path, required=True)
    collect.add_argument("--endpoint-url", default=OBJECT_STORAGE_ENDPOINT)
    collect.add_argument("--evidence-output", type=Path, required=True)
    acquire = subparsers.add_parser(
        "prepare-acquisition", help="Build one immutable sequential C1/C2 request package"
    )
    _request_arguments(acquire)
    acquire.add_argument("--filename", required=True)
    acquire.add_argument("--sequence-number", type=int, required=True)
    acquire.add_argument("--lifecycle-evidence", type=Path, required=True)
    acquire.add_argument("--source-config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    prepare = subparsers.add_parser(
        "prepare-preparation", help="Build one immutable C3 request package"
    )
    _request_arguments(prepare)
    prepare.add_argument("--filename", required=True)
    prepare.add_argument("--sequence-number", type=int, required=True)
    prepare.add_argument("--source-release-uri", required=True)
    prepare.add_argument("--source-release-manifest-sha256", required=True)
    prepare.add_argument("--source-config", type=Path, default=DEFAULT_SOURCE_CONFIG)
    publish_request = subparsers.add_parser(
        "publish-request", help="Publish one reviewed C1/C2/C3 request package"
    )
    publish_request.add_argument("--package", type=Path, required=True)
    publish_request.add_argument("--package-evidence", type=Path, required=True)
    publish_request.add_argument("--approval-reference", required=True)
    publish_request.add_argument("--endpoint-url", default=OBJECT_STORAGE_ENDPOINT)
    publish_request.add_argument("--evidence-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare-c0":
        prepare_c0(
            run_id=args.run_id,
            image=args.image,
            source_config=args.source_config,
            package=args.package,
            evidence_output=args.evidence_output,
        )
    elif args.command == "publish-c0":
        publish_c0(
            package=args.package,
            package_evidence=args.package_evidence,
            approval_reference=args.approval_reference,
            endpoint_url=args.endpoint_url,
            evidence_output=args.evidence_output,
        )
    elif args.command == "collect-c0":
        collect_c0(
            result_uri=args.result_uri,
            result=args.result,
            endpoint_url=args.endpoint_url,
            evidence_output=args.evidence_output,
        )
    elif args.command == "prepare-acquisition":
        prepare_acquisition(
            run_id=args.run_id,
            image=args.image,
            filename=args.filename,
            sequence_number=args.sequence_number,
            lifecycle_evidence=args.lifecycle_evidence,
            source_config=args.source_config,
            package=args.package,
            evidence_output=args.evidence_output,
        )
    elif args.command == "prepare-preparation":
        prepare_preparation(
            run_id=args.run_id,
            image=args.image,
            filename=args.filename,
            sequence_number=args.sequence_number,
            source_release_uri=args.source_release_uri,
            source_release_manifest_sha256=args.source_release_manifest_sha256,
            source_config=args.source_config,
            package=args.package,
            evidence_output=args.evidence_output,
        )
    elif args.command == "prepare-projection":
        prepare_projection(
            run_id=args.run_id,
            release_id=args.release_id,
            image=args.image,
            prepared_releases=args.prepared_releases,
            source_config=args.source_config,
            package=args.package,
            evidence_output=args.evidence_output,
        )
    elif args.command == "collect-projection":
        collect_projection_candidate(
            result_uri=args.result_uri,
            result=args.result,
            endpoint_url=args.endpoint_url,
            evidence_output=args.evidence_output,
        )
    elif args.command == "publish-projection":
        publish_projection_scope(
            candidate=args.candidate,
            scope=args.scope,
            release_id=args.release_id,
            approval_reference=args.approval_reference,
            endpoint_url=args.endpoint_url,
            evidence_output=args.evidence_output,
        )
    elif args.command == "verify-final-denial":
        verify_final_projection_denial(
            release_id=args.release_id,
            development_identity_id=args.development_identity_id,
            endpoint_url=args.endpoint_url,
            evidence_output=args.evidence_output,
        )
    else:
        publish_request_package(
            package=args.package,
            package_evidence=args.package_evidence,
            approval_reference=args.approval_reference,
            endpoint_url=args.endpoint_url,
            evidence_output=args.evidence_output,
        )
    return 0


def _request_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--evidence-output", type=Path, required=True)


def prepare_acquisition(
    *,
    run_id: str,
    image: str,
    filename: str,
    sequence_number: int,
    lifecycle_evidence: Path,
    source_config: Path,
    package: Path,
    evidence_output: Path,
) -> None:
    config = load_source_config(source_config)
    source = _ordered_source(config.sources, filename, sequence_number)
    lifecycle = QuarantineLifecycleEvidence.model_validate_json(
        lifecycle_evidence.read_text(encoding="utf-8")
    )
    request = NasdaqAcquisitionRequest(
        run_id=run_id,
        sequence_number=sequence_number,
        image=image,
        git_commit=_git_commit(),
        created_at=datetime.now(UTC),
        source=source,
        lifecycle=lifecycle,
        quarantine_uri=(
            f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/quarantine/nasdaq/"
            f"{source.date.isoformat()}/{run_id}"
        ),
        max_download_bytes=source.expected_content_length,
    )
    _prepare_request_package(request, operation="acquisition", package=package, evidence=evidence_output)


def prepare_preparation(
    *,
    run_id: str,
    image: str,
    filename: str,
    sequence_number: int,
    source_release_uri: str,
    source_release_manifest_sha256: str,
    source_config: Path,
    package: Path,
    evidence_output: Path,
) -> None:
    config = load_source_config(source_config)
    source = _ordered_source(config.sources, filename, sequence_number)
    request = NasdaqPreparationRequest(
        run_id=run_id,
        sequence_number=sequence_number,
        image=image,
        git_commit=_git_commit(),
        created_at=datetime.now(UTC),
        source=source,
        source_release_uri=source_release_uri,
        source_release_manifest_sha256=source_release_manifest_sha256,
        result_uri=(
            f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/prepared/"
            f"{source.date.isoformat()}/{run_id}"
        ),
        checkpoint_uri=(
            f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/preparation-checkpoints/"
            f"{source.date.isoformat()}/{run_id}"
        ),
        feature_config_sha256=hashlib.sha256(
            (ROOT / "configs" / "features" / "lightgbm-v2.json").read_bytes()
        ).hexdigest(),
    )
    _prepare_request_package(request, operation="preparation", package=package, evidence=evidence_output)


def prepare_projection(
    *,
    run_id: str,
    release_id: str,
    image: str,
    prepared_releases: Path,
    source_config: Path,
    package: Path,
    evidence_output: Path,
) -> None:
    bindings_payload = json.loads(prepared_releases.read_text(encoding="utf-8"))
    if not isinstance(bindings_payload, list):
        raise ValueError("C4 prepared-release bindings must be a JSON array")
    bindings = tuple(PreparedReleaseBinding.model_validate(item) for item in bindings_payload)
    request = NasdaqProjectionFreezeRequest(
        run_id=run_id,
        release_id=release_id,
        image=image,
        git_commit=_git_commit(),
        created_at=datetime.now(UTC),
        source_config_sha256=hashlib.sha256(source_config.read_bytes()).hexdigest(),
        prepared_releases=bindings,
        result_uri=(
            f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
            f"projection-candidates/{run_id}"
        ),
    )
    _prepare_request_package(
        request,
        operation="projection",
        package=package,
        evidence=evidence_output,
    )


def collect_projection_candidate(
    *,
    result_uri: str,
    result: Path,
    endpoint_url: str,
    evidence_output: Path,
) -> None:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("C4 collection requires the approved eu-north1 endpoint")
    expected = (
        rf"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
        r"projection-candidates/[a-z0-9][a-z0-9-]{2,62}"
    )
    if re.fullmatch(expected, result_uri.rstrip("/")) is None:
        raise ValueError("C4 result URI is outside the exact projection-candidate prefix")
    download_s3_release(
        result_uri,
        result,
        endpoint_url=endpoint_url,
        limits=TransferLimits(max_files=512, max_bytes=2_147_483_648),
    )
    freeze = verify_projection_candidate(result)
    inventory = inventory_directory(result)
    _write_new_json(
        evidence_output,
        {
            "schema_version": "market_data_wave1_projection_collection_v1",
            "collected_at": datetime.now(UTC).isoformat(),
            "result_uri": result_uri.rstrip("/"),
            "run_id": freeze.run_id,
            "release_id": freeze.release_id,
            "frozen_root_identity_sha256": freeze.frozen_root_identity_sha256,
            "candidate_inventory_sha256": _canonical_hash(inventory.model_dump(mode="json")),
            "gate_passed": True,
        },
    )


def publish_projection_scope(
    *,
    candidate: Path,
    scope: str,
    release_id: str,
    approval_reference: str,
    endpoint_url: str,
    evidence_output: Path,
) -> None:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("projection publication requires the approved eu-north1 endpoint")
    if scope not in {"development", "final"}:
        raise ValueError("projection publication scope must be development or final")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", approval_reference) is None:
        raise ValueError("projection publication requires a bounded explicit approval reference")
    freeze = verify_projection_candidate(candidate)
    if freeze.release_id != release_id:
        raise ValueError("projection publication release ID differs from the frozen candidate")
    bucket = DEVELOPMENT_BUCKET if scope == "development" else FINAL_BUCKET
    destination = f"s3://{bucket}/releases/{release_id}/staging"
    objects = publish_s3_input_release(
        candidate / scope,
        destination,
        endpoint_url=endpoint_url,
    )
    expected_sha = (
        freeze.development_tabular_sha256
        if scope == "development"
        else freeze.final_tabular_sha256
    )
    sequence_sha = (
        freeze.development_sequence_sha256
        if scope == "development"
        else freeze.final_sequence_sha256
    )
    _write_new_json(
        evidence_output,
        {
            "schema_version": "market_data_wave1_projection_publication_v1",
            "published_at": datetime.now(UTC).isoformat(),
            "approval_reference": approval_reference,
            "scope": scope,
            "destination": destination,
            "release_id": release_id,
            "frozen_root_identity_sha256": freeze.frozen_root_identity_sha256,
            "tabular_projection_sha256": expected_sha,
            "sequence_projection_sha256": sequence_sha,
            "objects": [item.__dict__ for item in objects],
            "success_published_last": objects[-1].key.endswith("/SUCCESS"),
        },
    )


def verify_final_projection_denial(
    *,
    release_id: str,
    development_identity_id: str,
    endpoint_url: str,
    evidence_output: Path,
) -> None:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("final access-denial proof requires the approved eu-north1 endpoint")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{2,127}", release_id) is None:
        raise ValueError("final access-denial proof requires a canonical release ID")
    final_uri = f"s3://{FINAL_BUCKET}/releases/{release_id}/staging"
    tabular_uri = f"{final_uri}/manifests/tabular-projection.json"
    sequence_uri = f"{final_uri}/manifests/sequence-projection.json"
    verify_s3_members_access_denied(
        final_uri,
        ("manifests/tabular-projection.json", "manifests/sequence-projection.json"),
        endpoint_url=endpoint_url,
    )
    evidence = FinalAccessDenialEvidence(
        development_identity_id=development_identity_id,
        tabular_final_uri=tabular_uri,
        sequence_final_uri=sequence_uri,
    )
    _write_new_json(evidence_output, evidence.model_dump(mode="json"))


def _ordered_source(sources: tuple[object, ...], filename: str, sequence_number: int):
    expected_filenames = tuple(EXPECTED_SOURCES)
    observed_filenames = tuple(item.filename for item in sources)
    if observed_filenames != expected_filenames:
        raise ValueError("market-data request requires the active four-file corpus")
    if not 1 <= sequence_number <= len(sources):
        raise ValueError("market-data sequence number is outside the four-file campaign")
    source = sources[sequence_number - 1]
    if source.filename != filename:
        raise ValueError("market-data request is out of the frozen sequential source order")
    return source


def _prepare_request_package(
    request: NasdaqAcquisitionRequest | NasdaqPreparationRequest | NasdaqProjectionFreezeRequest,
    *,
    operation: str,
    package: Path,
    evidence: Path,
) -> None:
    if package.exists() or evidence.exists():
        raise FileExistsError("request package and evidence paths must be new")
    package.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"market-data-{operation}-", dir=package.parent) as value:
        staging = Path(value)
        (staging / "request.json").write_bytes(request.canonical_bytes())
        publish_local_result(staging, package.resolve().as_uri())
    inventory = verify_complete_result(package)
    request_prefix = "projection-requests" if operation == "projection" else f"{operation}-requests"
    destination = (
        f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
        f"{request_prefix}/{request.run_id}/staging"
    )
    payload = {
        "schema_version": "market_data_wave1_request_package_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "operation": operation,
        "run_id": request.run_id,
        "destination": destination,
        "request_sha256": request.canonical_hash(),
        "package_inventory_sha256": _canonical_hash(inventory.model_dump(mode="json")),
        "request": request.model_dump(mode="json"),
        "cloud_resources_mutated": False,
        "market_data_transferred": False,
    }
    _write_new_json(evidence, payload)


def publish_request_package(
    *,
    package: Path,
    package_evidence: Path,
    approval_reference: str,
    endpoint_url: str,
    evidence_output: Path,
) -> None:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("request publication requires the approved eu-north1 endpoint")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", approval_reference) is None:
        raise ValueError("request publication requires a bounded explicit approval reference")
    payload = json.loads(package_evidence.read_text(encoding="utf-8"))
    if payload.get("schema_version") != "market_data_wave1_request_package_v1":
        raise ValueError("market-data package evidence is invalid")
    inventory = verify_complete_result(package)
    if _canonical_hash(inventory.model_dump(mode="json")) != payload["package_inventory_sha256"]:
        raise ValueError("market-data request package changed after review")
    objects = publish_s3_input_release(package, payload["destination"], endpoint_url=endpoint_url)
    _write_new_json(
        evidence_output,
        {
            "schema_version": "market_data_wave1_request_publication_v1",
            "published_at": datetime.now(UTC).isoformat(),
            "operation": payload["operation"],
            "approval_reference": approval_reference,
            "destination": payload["destination"],
            "request_sha256": payload["request_sha256"],
            "package_inventory_sha256": payload["package_inventory_sha256"],
            "objects": [item.__dict__ for item in objects],
        },
    )


def prepare_c0(
    *,
    run_id: str,
    image: str,
    source_config: Path,
    package: Path,
    evidence_output: Path,
) -> None:
    if re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", run_id) is None:
        raise ValueError("C0 run ID must be a lowercase immutable identifier")
    if re.fullmatch(r".+@sha256:[0-9a-f]{64}", image) is None:
        raise ValueError("C0 requires an immutable image digest")
    if package.exists() or evidence_output.exists():
        raise FileExistsError("C0 package and evidence paths must be new")
    config = load_source_config(source_config)
    package.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="market-data-c0-package-", dir=package.parent) as value:
        staging = Path(value)
        staged_config = staging / "nasdaq-public-sample-v1.json"
        shutil.copyfile(source_config, staged_config)
        request = C0PreflightRequest(
            run_id=run_id,
            image=image,
            git_commit=_git_commit(),
            created_at=datetime.now(UTC),
            source_config=config_artifact(staged_config),
            s3_probe_uri=(
                f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
                f"preflight/{run_id}/probe/probe.bin"
            ),
            result_uri=(
                f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/preflight/{run_id}/result"
            ),
            max_http_requests=len(config.sources),
        )
        (staging / "request.json").write_bytes(request.canonical_bytes())
        publish_local_result(staging, package.resolve().as_uri())
    inventory = verify_complete_result(package)
    package_bytes = sum(item.size_bytes for item in inventory.files)
    if len(inventory.files) > 8 or package_bytes > 1024 * 1024:
        raise ValueError("C0 package exceeds its fixed local publication ceiling")
    destination = (
        f"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
        f"preflight-requests/{run_id}/staging"
    )
    payload = {
        "schema_version": "market_data_wave1_c0_package_v1",
        "created_at": datetime.now(UTC).isoformat(),
        "run_id": run_id,
        "destination": destination,
        "result_uri": request.result_uri,
        "request_sha256": request.canonical_hash(),
        "package_inventory_sha256": _canonical_hash(inventory.model_dump(mode="json")),
        "package_bytes": package_bytes,
        "request": request.model_dump(mode="json"),
        "http_method": "HEAD",
        "max_http_requests": request.max_http_requests,
        "max_http_body_bytes": 0,
        "s3_probe_size_limit_bytes": 256,
        "cloud_resources_mutated": False,
        "market_data_transferred": False,
    }
    _write_new_json(evidence_output, payload)


def publish_c0(
    *,
    package: Path,
    package_evidence: Path,
    approval_reference: str,
    endpoint_url: str,
    evidence_output: Path,
) -> None:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("C0 publication requires the approved eu-north1 endpoint")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", approval_reference) is None:
        raise ValueError("C0 publication requires a bounded explicit approval reference")
    evidence = _load_package_evidence(package_evidence)
    inventory = verify_complete_result(package)
    if len(inventory.files) > 8 or sum(item.size_bytes for item in inventory.files) > 1024 * 1024:
        raise ValueError("C0 package exceeds its fixed publication ceiling")
    if _canonical_hash(inventory.model_dump(mode="json")) != evidence["package_inventory_sha256"]:
        raise ValueError("C0 package changed after review")
    objects = publish_s3_input_release(package, evidence["destination"], endpoint_url=endpoint_url)
    payload = {
        "schema_version": "market_data_wave1_c0_publication_v1",
        "published_at": datetime.now(UTC).isoformat(),
        "approval_reference": approval_reference,
        "destination": evidence["destination"],
        "request_sha256": evidence["request_sha256"],
        "package_inventory_sha256": evidence["package_inventory_sha256"],
        "objects": [item.__dict__ for item in objects],
        "market_data_transferred": False,
    }
    _write_new_json(evidence_output, payload)


def collect_c0(
    *, result_uri: str, result: Path, endpoint_url: str, evidence_output: Path
) -> None:
    if endpoint_url.rstrip("/") != OBJECT_STORAGE_ENDPOINT:
        raise ValueError("C0 collection requires the approved eu-north1 endpoint")
    expected = (
        rf"s3://{DEVELOPMENT_BUCKET}/{PUBLIC_SAMPLE_PREFIX}/"
        r"preflight/[a-z0-9][a-z0-9-]{2,62}/result"
    )
    if re.fullmatch(expected, result_uri.rstrip("/")) is None:
        raise ValueError("C0 result URI is outside the exact preflight prefix")
    download_s3_release(
        result_uri,
        result,
        endpoint_url=endpoint_url,
        limits=TransferLimits(max_files=8, max_bytes=1024 * 1024),
    )
    evidence = verify_c0_result(result)
    payload = {
        "schema_version": "market_data_wave1_c0_collection_v1",
        "collected_at": datetime.now(UTC).isoformat(),
        "result_uri": result_uri.rstrip("/"),
        "result_inventory": inventory_directory(result).model_dump(mode="json"),
        "preflight": evidence.model_dump(mode="json"),
        "gate_passed": True,
    }
    _write_new_json(evidence_output, payload)


def _load_package_evidence(path: Path) -> dict[str, object]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != "market_data_wave1_c0_package_v1"
        or payload.get("cloud_resources_mutated") is not False
        or payload.get("market_data_transferred") is not False
    ):
        raise ValueError("C0 package evidence is invalid")
    return payload


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    )
    commit = completed.stdout.strip()
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise RuntimeError("C0 requires a canonical Git commit")
    return commit


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_new_json(path: Path, payload: dict[str, object]) -> None:
    if path.exists():
        raise FileExistsError(f"C0 evidence output already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
