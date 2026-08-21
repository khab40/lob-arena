#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.ml.lightgbm.artifacts import sha256_file  # noqa: E402
from app.ml.lightgbm.cloud_contracts import (  # noqa: E402
    CloudArtifact,
    LightGbmCloudJobRequest,
    Wave1FinalAuthorization,
    Wave1FixtureInput,
)
from app.ml.lightgbm.cloud_fixture import fixture_hash  # noqa: E402
from app.ml.lightgbm.cloud_runner import execute_wave1_request, verify_wave1_result  # noqa: E402
from app.nebius.object_storage import (  # noqa: E402
    inventory_directory,
    publish_s3_input_release,
    write_checksum_file,
)


PROJECT_ID = "project-e00g6zvxpr00waz8t3y51k"
SIGNER = "Alexey Khabalov — Wave 1 Release Approver"
LOCAL_IMAGE = "ghcr.io/khab40/lob-arena-jobs@sha256:" + "0" * 64
DEVELOPMENT_BUCKET = "aimada-wave1-dev-e00g6zvxpr00"
RESULTS_BUCKET = "aimada-wave1-results-e00g6zvxpr00"


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
    stage.add_argument("--output", type=Path, required=True)
    collect = subparsers.add_parser("collect", help="Verify and inventory a completed result")
    collect.add_argument("--result", type=Path, required=True)
    collect.add_argument("--output", type=Path, required=True)
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
        stage_fixture(args.release_id, args.run_id, args.image, args.endpoint_url, args.output)
    elif args.command == "collect":
        collect_result(args.result, args.output)
    elif args.command == "compare":
        compare_results(args.results, args.output)
    else:
        create_exit_record(args.development, args.final, args.output)
    return 0


def stage_fixture(release_id: str, run_id: str, image: str, endpoint_url: str, output: Path) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,62}", release_id):
        raise ValueError("release ID must be a lowercase immutable identifier")
    if any(
        name in os.environ
        for name in (
            "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID",
            "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
        )
    ):
        raise ValueError("inline Nebius credential variables are forbidden")
    created_at = datetime.now(UTC)
    destination = f"s3://{DEVELOPMENT_BUCKET}/releases/{release_id}/staging"
    request = LightGbmCloudJobRequest(
        campaign_id="wave1-research-20260816",
        run_id=run_id,
        mode="development",
        project_id=PROJECT_ID,
        image=image,
        created_at=created_at,
        git_commit=_git_commit(),
        input=Wave1FixtureInput(feature_release_sha256=fixture_hash("wave1-fixture-feature-release")),
        result_uri=(
            f"s3://{RESULTS_BUCKET}/campaigns/"
            f"wave1-research-20260816/development/{run_id}"
        ),
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
            "inventory_sha256": hashlib.sha256(
                (package / "input-inventory.json").read_bytes()
            ).hexdigest(),
            "objects": [item.__dict__ for item in evidence],
            "success_published_last": True,
            "read_back_verified": True,
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
    execute_wave1_request(final_request_path, input_root=final_inputs)
    verify_wave1_result(final)
    collect_result(final, output / "collection.json")
    create_exit_record(development, final, output / "exit-record.json")
    (output / "LOCAL-G2-SUCCESS").write_text("verified\n", encoding="utf-8")


def collect_result(result: Path, output: Path) -> None:
    run = verify_wave1_result(result)
    inventory = inventory_directory(result)
    payload = {
        "schema_version": "lightgbm_wave1_collection_v1",
        "run_id": run.run_id,
        "request_sha256": run.request_sha256,
        "result_sha256": _inventory_hash(inventory.model_dump(mode="json")),
        "file_count": len(inventory.files),
        "size_bytes": sum(item.size_bytes for item in inventory.files),
        "verified": True,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def compare_results(results: list[Path], output: Path) -> None:
    if len(results) < 2:
        raise ValueError("repeat comparison requires at least two results")
    records = []
    for result in results:
        run = verify_wave1_result(result)
        metrics = json.loads((result / "metrics.json").read_text(encoding="utf-8"))
        records.append(
            {
                "candidate_hash": run.candidate_hash,
                "best_iteration": metrics.get("best_iteration"),
                "validation_binary_logloss": metrics.get("validation_binary_logloss"),
            }
        )
    reproducible = all(record == records[0] for record in records[1:])
    output.write_text(
        json.dumps(
            {"schema_version": "lightgbm_wave1_repeat_comparison_v1", "reproducible": reproducible, "runs": records},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
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
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _request(
    *,
    campaign_id: str,
    run_id: str,
    mode: str,
    created_at: datetime,
    result: Path,
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


if __name__ == "__main__":
    raise SystemExit(main())
