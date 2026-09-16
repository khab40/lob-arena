"""Prepare portable synthetic sources offline; never submit, score final or log MLflow.

The sealed package is a staging input, NOT an execution package or cloud receipt.
Use the pinned runtime with networking disabled. Retain the printed package hash
independently and use --verify after copying the package to another workspace.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.market_data.projections import (
    C4MlflowDatasetReleaseReceipt, FrozenPublicSampleRoot, verify_tabular_projection, write_manifest,
)
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.c4_evaluation import C4EvaluationInputs
from app.ml.lightgbm.c4_replay_evidence import verified_replay_paths
from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest, Wave1TabularProjectionInput
from app.ml.lightgbm.cloud_runner import FrozenCandidate, _verify_cloud_artifact, verify_wave1_result
from app.ml.lightgbm.g8_publication_recovery import _inventory
from app.nebius.object_storage import ChecksumInventory, TransferLimits, publish_local_result, verify_complete_result

if __package__:
    from .g8_rehearsal import IMAGE, prepare_sources
    from .run_lightgbm_g8 import _validate_c4_inputs, _validate_final_lineage, _verify_injected_authorization
else:
    from g8_rehearsal import IMAGE, prepare_sources
    from run_lightgbm_g8 import _validate_c4_inputs, _validate_final_lineage, _verify_injected_authorization

CAMPAIGN = "g8-native-rehearsal-20260914"
CANDIDATE_URI = f"s3://aimada-wave1-results-e00g6zvxpr00/campaigns/{CAMPAIGN}/development/synthetic-development"
INPUT_URI = f"s3://aimada-wave1-final-e00g6zvxpr00/releases/{CAMPAIGN}/staging"
RESULT_URI = f"s3://aimada-wave1-results-e00g6zvxpr00/campaigns/{CAMPAIGN}/final/synthetic-final"
PRODUCTION_CANDIDATE = "5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff"
LIMITS = TransferLimits(max_files=2000, max_bytes=64 * 1024**2)


class SourcePackage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["g8_native_synthetic_sources_v1"] = "g8_native_synthetic_sources_v1"
    campaign_id: Literal[CAMPAIGN] = CAMPAIGN
    image: Literal[IMAGE] = IMAGE
    candidate_uri: Literal[CANDIDATE_URI] = CANDIDATE_URI
    input_uri: Literal[INPUT_URI] = INPUT_URI
    result_uri: Literal[RESULT_URI] = RESULT_URI
    dataset_lineage_kind: Literal["synthetic_placeholder_not_remote_mlflow_registration"] = (
        "synthetic_placeholder_not_remote_mlflow_registration"
    )
    comparison_kind: Literal["synthetic_contract_fixtures_not_java_execution"] = (
        "synthetic_contract_fixtures_not_java_execution"
    )
    production_test_accessed: Literal[False] = False
    remote_sources_staged: Literal[False] = False
    remote_authentication_verified: Literal[False] = False
    native_storage_verified: Literal[False] = False
    submission_authorized: Literal[False] = False
    inventory: ChecksumInventory


def canonical(package: SourcePackage) -> bytes:
    return (json.dumps(package.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n").encode()


def verify(package_root: Path, *, expected_sha256: str) -> dict:
    """Verify a copy from retained bytes, never from the deleted build workspace."""
    if package_root.is_symlink() or package_root.resolve() != package_root.absolute():
        raise ValueError("source package must be a canonical real directory")
    if {p.name for p in package_root.iterdir()} != {"source-package.json", "payload"}:
        raise ValueError("source package has unexpected members")
    marker = package_root / "source-package.json"
    if marker.is_symlink() or marker.stat().st_size > 2 * 1024**2:
        raise ValueError("invalid source package marker")
    raw = marker.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("source package differs from independently retained SHA-256")
    package = SourcePackage.model_validate_json(raw)
    payload = package_root / "payload"
    if canonical(package) != raw or _inventory(payload, LIMITS) != package.inventory:
        raise ValueError("source package inventory differs from retained bytes")
    request = LightGbmCloudJobRequest.model_validate_json((payload / "request.json").read_bytes())
    if (
        request.campaign_id != CAMPAIGN or request.image != IMAGE
        or request.project_id != "project-e00g6zvxpr00waz8t3y51k"
        or request.run_id != "synthetic-final" or request.mode != "final-evaluation"
        or request.input_release_uri != INPUT_URI or request.result_uri != RESULT_URI
        or request.candidate is None or request.candidate.sha256 == PRODUCTION_CANDIDATE
        or request.mlflow_tracking_uri != "http://10.4.0.54:5500"
        or not isinstance(request.input, Wave1TabularProjectionInput)
        or request.input.projection_artifact_root != "artifacts"
    ):
        raise ValueError("source request is not the isolated synthetic rehearsal")
    # The paths themselves must also remain portable and bounded, even with a
    # newly supplied package hash. Never resolve arbitrary absolute C4 paths.
    expected_inputs = C4EvaluationInputs(
        profile=Path("c4-profile.json"),
        frozen_root=Path("sources/input/manifests/frozen-root.json"),
        projection=Path("sources/input/manifests/tabular-projection.json"),
        comparison=Path("sources/input/comparison-evidence/comparison.json"),
        candidate=Path("sources/candidate/candidate.json"),
    )
    inputs_file = payload / "c4-inputs.json"
    if C4EvaluationInputs.model_validate_json(inputs_file.read_bytes()) != expected_inputs:
        raise ValueError("C4 source paths are not the fixed portable layout")
    candidate_root = payload / "sources/candidate"
    input_root = payload / "sources/input"
    run = verify_wave1_result(candidate_root)
    candidate = FrozenCandidate.model_validate_json((candidate_root / "candidate.json").read_bytes())
    if (run.campaign_id != CAMPAIGN or run.run_id != "synthetic-development"
            or run.mode != "development" or candidate.test_fold_accessed):
        raise ValueError("candidate was not prepared in isolated synthetic development")
    verify_complete_result(input_root, limits=LIMITS)
    inputs = _validate_c4_inputs(request, inputs_file)
    root = FrozenPublicSampleRoot.model_validate_json(inputs.frozen_root.read_bytes())
    if root.release_id != CAMPAIGN or root.corpus_id != CAMPAIGN:
        raise ValueError("input root is not the synthetic corpus")
    lineage_path = _verify_cloud_artifact(input_root, request.input.dataset_lineage_receipt)
    lineage = C4MlflowDatasetReleaseReceipt.model_validate_json(lineage_path.read_bytes())
    _validate_final_lineage(request.input, root, lineage)
    if lineage.mlflow_run_id != "0" * 32:
        raise ValueError("source preparation must not claim remote MLflow dataset registration")
    projection = verify_tabular_projection(
        inputs.projection, expected_sha256=request.input.projection.sha256,
        root=root, artifact_root=input_root / "artifacts",
    )
    replays = verified_replay_paths(inputs.comparison, root=root)
    if len(replays) != 30 or set(replays) != {s.run_id for s in projection.shards}:
        raise ValueError("comparison does not cover the synthetic projection")
    auth = payload / "authorization"
    _verify_injected_authorization(
        request, argparse.Namespace(
            authorization=auth / "authorization.json",
            authorization_signature=auth / "authorization.sig",
            authorization_public_key=auth / "authorization-public.pem",
        ), sha256_file(auth / "authorization-public.pem"),
    )
    return {
        "schema_version": "g8_native_source_verification_v1",
        "source_package_sha256": expected_sha256,
        "candidate_sha256": request.candidate.sha256,
        "request_sha256": request.canonical_hash(),
        "candidate_uri": CANDIDATE_URI, "input_uri": INPUT_URI,
        "candidate_success_sha256": sha256_file(candidate_root / "SUCCESS"),
        "input_success_sha256": sha256_file(input_root / "SUCCESS"),
        "comparison_sha256": sha256_file(inputs.comparison),
        "checkpoint_count": 27, "replay_domain_count": len(replays),
        "synthetic_test_row_count": sum(s.supervised_row_count for s in projection.shards),
        "payload_file_count": len(package.inventory.files),
        "payload_size_bytes": sum(e.size_bytes for e in package.inventory.files),
        "local_source_verification_passed": True,
        "remote_sources_staged": False, "remote_authentication_verified": False,
        "native_storage_verified": False, "production_g8_complete": False,
        "dataset_lineage_kind": package.dataset_lineage_kind,
    }


def prepare(output: Path) -> dict:
    """Keep the build workspace separate from the portable, sealed sources."""
    if output.resolve() != output.absolute():
        raise ValueError("output must be canonical and must not traverse symlinks")
    output = output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    prepared = prepare_sources(output / "build", campaign=CAMPAIGN, c4=True)
    package = output / "package"
    payload = package / "payload"
    payload.mkdir(parents=True)
    shutil.copytree(prepared.selected, payload / "sources/candidate")
    staging = output / "input-staging"
    shutil.copytree(prepared.final_input, staging)
    shutil.copytree(prepared.comparison.parent, staging / "comparison-evidence")
    publish_local_result(staging, (payload / "sources/input").as_uri(), limits=LIMITS)
    shutil.copytree(output / "build/authorization", payload / "authorization")
    for name in ("request.json", "c4-profile.json"):
        shutil.copyfile(output / "build" / name, payload / name)
    write_manifest(payload / "c4-inputs.json", C4EvaluationInputs(
        profile=Path("c4-profile.json"),
        frozen_root=Path("sources/input/manifests/frozen-root.json"),
        projection=Path("sources/input/manifests/tabular-projection.json"),
        comparison=Path("sources/input/comparison-evidence/comparison.json"),
        candidate=Path("sources/candidate/candidate.json"),
    ))
    raw = canonical(SourcePackage(inventory=_inventory(payload, LIMITS)))
    (package / "source-package.json").write_bytes(raw)
    return verify(package, expected_sha256=hashlib.sha256(raw).hexdigest())


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="new preparation directory, or existing package directory with --verify")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--expected-sha256")
    args = parser.parse_args()
    if args.verify != (args.expected_sha256 is not None):
        parser.error("--verify and --expected-sha256 must be supplied together")
    result = verify(args.output, expected_sha256=args.expected_sha256) if args.verify else prepare(args.output)
    print(json.dumps(result, indent=2))
