#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import os
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

from app.ml.lightgbm.artifacts import sha256_file
from app.market_data.projections import C4MlflowDatasetReleaseReceipt, FrozenPublicSampleRoot
from app.ml.lightgbm import cloud_runner
from app.ml.lightgbm.cloud_contracts import (
    LightGbmCloudJobRequest,
    Wave1ExecutionContext,
    Wave1FinalAuthorization,
    Wave1TabularProjectionInput,
)
from app.ml.lightgbm.cloud_runner import FrozenCandidate, _verify_signature, execute_wave1_request
from app.nebius.object_storage import (
    _list_s3_keys,
    download_s3_release,
    publish_s3_failure,
    publish_s3_result,
)


ENDPOINT = "https://storage.eu-north1.nebius.cloud"
FINAL_BUCKET = "aimada-wave1-final-e00g6zvxpr00"
RESULTS_BUCKET = "aimada-wave1-results-e00g6zvxpr00"
FINAL_RELEASE_PATH = re.compile(r"/releases/[a-z0-9][a-z0-9-]{2,62}/staging")
DEVELOPMENT_RESULT_PATH = re.compile(
    r"/campaigns/[A-Za-z0-9][A-Za-z0-9._:-]{0,127}/development/"
    r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}"
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute the one authorized LightGBM Wave 1 final evaluation."
    )
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--authorization-signature", type=Path, required=True)
    parser.add_argument("--authorization-public-key", type=Path, required=True)
    parser.add_argument("--dataset-lineage", type=Path, required=True)
    parser.add_argument("--final-input-uri", required=True)
    parser.add_argument("--candidate-uri", required=True)
    parser.add_argument("--work-root", type=Path, default=Path("/job/wave1-g8"))
    parser.add_argument("--endpoint-url", default=ENDPOINT)
    args = parser.parse_args()

    if args.endpoint_url.rstrip("/") != ENDPOINT:
        raise ValueError("G8 requires the approved eu-north1 Object Storage endpoint")
    request = LightGbmCloudJobRequest.model_validate_json(
        args.request.read_text(encoding="utf-8")
    )
    _validate_request(request, args.final_input_uri, args.candidate_uri)
    trusted_key = os.environ.get("WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256", "")
    _verify_injected_authorization(request, args, trusted_key)
    _verify_mlflow_ready(request.mlflow_tracking_uri)
    _require_empty_result(request.result_uri, args.endpoint_url)

    args.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="g8-", dir=args.work_root) as value:
        staging = Path(value)
        candidate_release = staging / "candidate-release"
        download_s3_release(
            args.candidate_uri,
            candidate_release,
            endpoint_url=args.endpoint_url,
        )
        candidate_path = candidate_release / "candidate.json"
        if request.candidate is None or sha256_file(candidate_path) != request.candidate.sha256:
            raise ValueError("G8 cloud candidate does not match the authorized candidate")
        candidate = FrozenCandidate.model_validate_json(candidate_path.read_text(encoding="utf-8"))
        if (
            candidate.campaign_id != request.campaign_id
            or candidate.experiment.canonical_hash() != request.experiment.canonical_hash()
            or candidate.test_fold_accessed
        ):
            raise ValueError("G8 candidate no longer matches the authorized final request")

        # Authorization, candidate, result-prefix, and MLflow readiness all verify
        # before this first and only download of the sealed final release.
        input_root = staging / "input"
        download_s3_release(
            args.final_input_uri,
            input_root,
            endpoint_url=args.endpoint_url,
        )
        shutil.copytree(candidate_release, input_root / "candidate")
        authorization_root = input_root / "authorization"
        authorization_root.mkdir()
        shutil.copyfile(args.authorization, authorization_root / "authorization.json")
        shutil.copyfile(
            args.authorization_signature, authorization_root / "authorization.sig"
        )
        shutil.copyfile(
            args.authorization_public_key,
            authorization_root / "authorization-public.pem",
        )
        manifests = input_root / "manifests"
        manifests.mkdir(exist_ok=True)
        shutil.copyfile(
            args.dataset_lineage, manifests / "c4-mlflow-dataset-release.json"
        )
        request_path = input_root / "request.json"
        request_path.write_bytes(request.canonical_bytes())
        local_result = staging / "result"
        original_lineage_validator = cloud_runner._validate_tabular_projection_lineage
        cloud_runner._validate_tabular_projection_lineage = _validate_final_lineage
        try:
            completed = execute_wave1_request(
                request_path,
                input_root=input_root,
                local_result_root=local_result,
                execution_context=_execution_context(),
                trusted_authorization_public_key_sha256=trusted_key,
            )
            publish_s3_result(completed, request.result_uri, endpoint_url=args.endpoint_url)
        except Exception:
            if (local_result / "FAILED").is_file():
                publish_s3_failure(local_result, request.result_uri, endpoint_url=args.endpoint_url)
            raise
        finally:
            cloud_runner._validate_tabular_projection_lineage = original_lineage_validator
    print(request.result_uri)
    return 0


def _validate_request(
    request: LightGbmCloudJobRequest,
    final_input_uri: str,
    candidate_uri: str,
) -> None:
    if request.mode != "final-evaluation" or request.input_release_uri != final_input_uri:
        raise ValueError("G8 runner requires the exact final-evaluation request")
    final = urlsplit(final_input_uri)
    candidate = urlsplit(candidate_uri)
    result = urlsplit(request.result_uri)
    if (
        final.scheme != "s3"
        or final.netloc != FINAL_BUCKET
        or FINAL_RELEASE_PATH.fullmatch(final.path) is None
        or any((final.username, final.password, final.query, final.fragment))
        or candidate.scheme != "s3"
        or candidate.netloc != RESULTS_BUCKET
        or DEVELOPMENT_RESULT_PATH.fullmatch(candidate.path) is None
        or any((candidate.username, candidate.password, candidate.query, candidate.fragment))
        or result.scheme != "s3"
        or result.netloc != RESULTS_BUCKET
        or result.path != f"/campaigns/{request.campaign_id}/final/{request.run_id}"
        or any((result.username, result.password, result.query, result.fragment))
    ):
        raise ValueError("G8 request escaped an approved Object Storage boundary")


def _verify_injected_authorization(
    request: LightGbmCloudJobRequest,
    args: argparse.Namespace,
    trusted_key: str,
) -> None:
    references = (
        (request.authorization, args.authorization),
        (request.authorization_signature, args.authorization_signature),
        (request.authorization_public_key, args.authorization_public_key),
    )
    for reference, path in references:
        if (
            reference is None
            or not path.is_file()
            or path.stat().st_size != reference.size_bytes
            or sha256_file(path) != reference.sha256
        ):
            raise ValueError("G8 injected authorization artifact changed after review")
    _verify_signature(
        args.authorization,
        args.authorization_signature,
        args.authorization_public_key,
        trusted_public_key_sha256=trusted_key,
    )
    authorization = Wave1FinalAuthorization.model_validate_json(
        args.authorization.read_text(encoding="utf-8")
    )
    if (
        request.candidate is None
        or authorization.campaign_id != request.campaign_id
        or authorization.candidate_hash != request.candidate.sha256
    ):
        raise ValueError("G8 authorization does not approve the exact request candidate")


def _verify_mlflow_ready(uri: str | None) -> None:
    if uri != "http://10.4.0.54:5500":
        raise ValueError("G8 requires the approved private MLflow endpoint")
    username = os.environ.get("MLFLOW_TRACKING_USERNAME", "")
    password = os.environ.get("MLFLOW_TRACKING_PASSWORD", "")
    if not username or not password:
        raise RuntimeError("G8 requires governed MLflow writer credentials")
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    for path in (
        "/health",
        "/api/2.0/mlflow/experiments/get-by-name?"
        + urllib.parse.urlencode({"experiment_name": "lob-arena/governed-evaluation"}),
    ):
        request = urllib.request.Request(uri.rstrip("/") + path, headers=headers)
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status != 200:
                raise RuntimeError("G8 MLflow preflight failed before final access")


def _require_empty_result(uri: str, endpoint_url: str) -> None:
    parsed = urlsplit(uri)
    prefix = parsed.path.strip("/")
    if _list_s3_keys(parsed.netloc, prefix, endpoint_url=endpoint_url, limit=1):
        raise FileExistsError("G8 final result prefix already exists; refusing a second run")


def _validate_final_lineage(
    projected: Wave1TabularProjectionInput,
    root: FrozenPublicSampleRoot,
    receipt: C4MlflowDatasetReleaseReceipt,
) -> None:
    if (
        receipt.release_id != root.release_id
        or receipt.root_file_sha256 != projected.frozen_root.sha256
        or receipt.root_identity_sha256 != root.canonical_hash()
        or receipt.tabular_final_sha256 != projected.projection.sha256
    ):
        raise ValueError("final tabular projection is not bound to its C4 MLflow release")


def _execution_context() -> Wave1ExecutionContext:
    image_repository = os.environ["WAVE1_ACTUAL_IMAGE_REPOSITORY"]
    image_sha256 = os.environ["WAVE1_ACTUAL_IMAGE_SHA256"]
    return Wave1ExecutionContext(
        project_id=os.environ["WAVE1_ACTUAL_PROJECT_ID"],
        image=f"{image_repository}@sha256:{image_sha256}",
        platform=os.environ["WAVE1_ACTUAL_PLATFORM"],
        preset=os.environ["WAVE1_ACTUAL_PRESET"],
        disk_size_gib=int(os.environ["WAVE1_ACTUAL_DISK_SIZE_GIB"]),
        timeout_seconds=int(os.environ["WAVE1_ACTUAL_TIMEOUT_SECONDS"]),
    )


if __name__ == "__main__":
    raise SystemExit(main())
