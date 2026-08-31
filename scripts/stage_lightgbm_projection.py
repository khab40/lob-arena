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

from app.market_data.projections import (  # noqa: E402
    FrozenPublicSampleRoot,
    verify_tabular_projection,
)
from app.ml.lightgbm.artifacts import sha256_file  # noqa: E402
from app.ml.lightgbm.cloud_contracts import (  # noqa: E402
    CloudArtifact,
    LightGbmCloudJobRequest,
    Wave1ExperimentSpec,
    Wave1TabularProjectionInput,
)
from app.nebius.object_storage import (  # noqa: E402
    publish_local_result,
    publish_s3_input_release,
    verify_complete_result,
)


PROJECT_ID = "project-e00g6zvxpr00waz8t3y51k"
DEV_BUCKET = "aimada-wave1-dev-e00g6zvxpr00"
ENDPOINT = "https://storage.eu-north1.nebius.cloud"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Prepare locally or explicitly publish a fold-isolated G5 projection package."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser("prepare")
    prepare.add_argument("--release-id", required=True)
    prepare.add_argument("--campaign-id", required=True)
    prepare.add_argument("--run-id", required=True)
    prepare.add_argument("--image", required=True)
    prepare.add_argument("--frozen-root", type=Path, required=True)
    prepare.add_argument("--projection", type=Path, required=True)
    prepare.add_argument("--projection-artifact-root", type=Path, required=True)
    prepare.add_argument("--experiment-config", type=Path, required=True)
    prepare.add_argument("--mlflow-tracking-uri", required=True)
    prepare.add_argument("--package", type=Path, required=True)
    prepare.add_argument("--evidence-output", type=Path, required=True)
    publish = subparsers.add_parser("publish")
    publish.add_argument("--package", type=Path, required=True)
    publish.add_argument("--package-evidence", type=Path, required=True)
    publish.add_argument("--approval-reference", required=True)
    publish.add_argument("--endpoint-url", default=ENDPOINT)
    publish.add_argument("--evidence-output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "prepare":
        prepare_projection_package(
            release_id=args.release_id,
            campaign_id=args.campaign_id,
            run_id=args.run_id,
            image=args.image,
            frozen_root=args.frozen_root,
            projection=args.projection,
            projection_artifact_root=args.projection_artifact_root,
            experiment_config=args.experiment_config,
            mlflow_tracking_uri=args.mlflow_tracking_uri,
            package=args.package,
            evidence_output=args.evidence_output,
        )
    else:
        publish_projection_package(
            package=args.package,
            package_evidence=args.package_evidence,
            approval_reference=args.approval_reference,
            endpoint_url=args.endpoint_url,
            evidence_output=args.evidence_output,
        )
    return 0


def prepare_projection_package(
    *,
    release_id: str,
    campaign_id: str,
    run_id: str,
    image: str,
    frozen_root: Path,
    projection: Path,
    projection_artifact_root: Path,
    experiment_config: Path,
    mlflow_tracking_uri: str,
    package: Path,
    evidence_output: Path,
) -> None:
    for value in (release_id, campaign_id, run_id):
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", value) is None:
            raise ValueError("projection package identifiers must be canonical")
    if re.fullmatch(r"[a-z0-9][a-z0-9._/-]*@sha256:[0-9a-f]{64}", image) is None:
        raise ValueError("projection package requires an immutable image digest")
    if package.exists() or evidence_output.exists():
        raise FileExistsError("projection package and evidence outputs must be new")
    root = FrozenPublicSampleRoot.model_validate_json(frozen_root.read_text(encoding="utf-8"))
    root_sha = sha256_file(frozen_root)
    projection_sha = sha256_file(projection)
    manifest = verify_tabular_projection(
        projection,
        expected_sha256=projection_sha,
        root=root,
        artifact_root=projection_artifact_root,
    )
    if manifest.access_scope != "development":
        raise ValueError("G5 package preparation accepts development projection only")
    experiment = Wave1ExperimentSpec.model_validate_json(
        experiment_config.read_text(encoding="utf-8")
    )
    package.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="g5-projection-package-", dir=package.parent) as value:
        staging = Path(value)
        manifests = staging / "manifests"
        artifacts = staging / "projection-artifacts"
        manifests.mkdir()
        artifacts.mkdir()
        shutil.copyfile(frozen_root, manifests / "frozen-root.json")
        shutil.copyfile(projection, manifests / "development-projection.json")
        for shard in manifest.shards:
            source = (projection_artifact_root.resolve() / shard.rows.uri).resolve()
            if projection_artifact_root.resolve() not in source.parents:
                raise ValueError("projection shard escaped its reviewed artifact root")
            destination = artifacts / shard.rows.uri
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        request = LightGbmCloudJobRequest(
            campaign_id=campaign_id,
            run_id=run_id,
            mode="development",
            project_id=PROJECT_ID,
            image=image,
            created_at=datetime.now(UTC),
            git_commit=_git_commit(),
            experiment=experiment,
            input=Wave1TabularProjectionInput(
                frozen_root=_cloud_artifact(manifests / "frozen-root.json", staging, "frozen_root"),
                projection=_cloud_artifact(
                    manifests / "development-projection.json", staging, "development_projection"
                ),
                projection_artifact_root="projection-artifacts",
            ),
            result_uri=(
                f"s3://aimada-wave1-results-e00g6zvxpr00/campaigns/"
                f"{campaign_id}/development/{run_id}"
            ),
            mlflow_tracking_uri=mlflow_tracking_uri,
        )
        (staging / "request.json").write_bytes(request.canonical_bytes())
        publish_local_result(staging, package.resolve().as_uri())
    inventory = verify_complete_result(package)
    destination = f"s3://{DEV_BUCKET}/releases/{release_id}/staging"
    _write_once(
        evidence_output,
        {
            "schema_version": "lightgbm_tabular_projection_package_v1",
            "created_at": datetime.now(UTC).isoformat(),
            "release_id": release_id,
            "destination": destination,
            "request_sha256": request.canonical_hash(),
            "frozen_root_file_sha256": root_sha,
            "frozen_root_identity_sha256": root.canonical_hash(),
            "projection_sha256": projection_sha,
            "projection_id": manifest.projection_id,
            "folds": list(manifest.folds),
            "package_inventory_sha256": _canonical_hash(inventory.model_dump(mode="json")),
            "cloud_resources_mutated": False,
            "test_artifacts_staged": False,
        },
    )


def publish_projection_package(
    *,
    package: Path,
    package_evidence: Path,
    approval_reference: str,
    endpoint_url: str,
    evidence_output: Path,
) -> None:
    if endpoint_url.rstrip("/") != ENDPOINT:
        raise ValueError("projection publication requires the approved eu-north1 endpoint")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}", approval_reference) is None:
        raise ValueError("projection publication requires explicit bounded approval")
    evidence = json.loads(package_evidence.read_text(encoding="utf-8"))
    if (
        evidence.get("schema_version") != "lightgbm_tabular_projection_package_v1"
        or evidence.get("cloud_resources_mutated") is not False
        or evidence.get("test_artifacts_staged") is not False
    ):
        raise ValueError("projection package evidence is invalid")
    inventory = verify_complete_result(package)
    if _canonical_hash(inventory.model_dump(mode="json")) != evidence["package_inventory_sha256"]:
        raise ValueError("projection package changed after review")
    objects = publish_s3_input_release(package, evidence["destination"], endpoint_url=endpoint_url)
    _write_once(
        evidence_output,
        {
            "schema_version": "lightgbm_tabular_projection_publication_v1",
            "published_at": datetime.now(UTC).isoformat(),
            "approval_reference": approval_reference,
            "destination": evidence["destination"],
            "request_sha256": evidence["request_sha256"],
            "package_inventory_sha256": evidence["package_inventory_sha256"],
            "objects": [item.__dict__ for item in objects],
            "success_published_last": objects[-1].key.endswith("/SUCCESS"),
            "test_artifacts_staged": False,
        },
    )


def _cloud_artifact(path: Path, root: Path, logical_name: str) -> CloudArtifact:
    return CloudArtifact(
        logical_name=logical_name,
        uri=path.relative_to(root).as_posix(),
        sha256=sha256_file(path),
        size_bytes=path.stat().st_size,
    )


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], check=True, text=True, capture_output=True
    )
    return completed.stdout.strip()


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, allow_nan=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _write_once(path: Path, payload: object) -> None:
    if path.exists():
        raise FileExistsError(f"projection evidence already exists: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
