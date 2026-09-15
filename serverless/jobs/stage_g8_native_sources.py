"""Conditionally stage or independently download the two sealed synthetic sources.

Default is local verification. Explicit --publish needs separately approved
staging-writer authority; --readback uses the rehearsal reader. Neither mode
changes IAM, provisions Jobs, scores, logs MLflow, or retrieves credentials.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm import g8_publication_recovery as transport
from app.nebius.object_storage import InventoryEntry

if __package__:
    from . import prepare_g8_native_sources as sources
else:
    import prepare_g8_native_sources as sources

PRODUCTION_BUCKET = "aimada-wave1-final-e00g6zvxpr00"
PRODUCTION_KEY = "releases/nasdaq-public-sample-v1-c4-5c85182-20260905/staging/manifests/frozen-root.json"


def _credential_identity() -> str:
    key = os.environ.get("AWS_ACCESS_KEY_ID", "")
    if not key or not os.environ.get("AWS_SECRET_ACCESS_KEY"):
        raise ValueError("explicit AWS environment credentials required; no profile/instance-role fallback")
    return hashlib.sha256(key.encode()).hexdigest()


def _plans(package: Path, digest: str):
    verified = sources.verify(package, expected_sha256=digest)
    # Read the trusted inventory, not an inventory freshly derived from mutable
    # files after verification. A second digest check closes the marker swap gap.
    raw = (package / "source-package.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != digest:
        raise ValueError("source marker changed after verification")
    manifest = sources.SourcePackage.model_validate_json(raw)
    plans = []
    for name, uri in (("candidate", sources.CANDIDATE_URI), ("input", sources.INPUT_URI)):
        bucket, prefix = uri.removeprefix("s3://").split("/", 1)
        base = f"sources/{name}/"
        entries = {
            prefix + "/" + entry.path.removeprefix(base): InventoryEntry(
                path=entry.path, sha256=entry.sha256, size_bytes=entry.size_bytes,
            ) for entry in manifest.inventory.files if entry.path.startswith(base)
        }
        if prefix + "/SUCCESS" not in entries:
            raise ValueError("source inventory has no completion marker")
        plans.append((uri, bucket, prefix, entries))
    return verified, manifest, plans


def _check_existing(bucket, prefix, entries, *, complete=False, s3=transport):
    existing = s3._listed_keys(bucket, prefix, set(entries))
    if (complete or prefix + "/SUCCESS" in existing) and existing != set(entries):
        raise ValueError("source SUCCESS is missing or its payload is incomplete; refusing repair")
    for key in sorted(existing):
        item = entries[key]
        s3._readback(bucket, key, digest=item.sha256, size=item.size_bytes)
    return existing


def publish(package: Path, *, expected_sha256: str, s3=transport) -> dict:
    verified, _, plans = _plans(package, expected_sha256)
    identity = _credential_identity()
    # Check BOTH prefixes before the first write; never alter the candidate if
    # the input prefix already contains an incompatible or premature release.
    preflight = [_check_existing(bucket, prefix, entries, s3=s3) for _, bucket, prefix, entries in plans]
    results = []
    for (uri, bucket, prefix, entries), existing in zip(plans, preflight, strict=True):
        puts = 0
        for key in sorted(set(entries) - existing, key=lambda key: (key == prefix + "/SUCCESS", key)):
            item = entries[key]
            if key == prefix + "/SUCCESS":
                sources.verify(package, expected_sha256=expected_sha256)
                # Recheck every remote payload immediately before exposing SUCCESS.
                observed = _check_existing(bucket, prefix, entries, s3=s3)
                if not (set(entries) - {key}) <= observed:
                    raise ValueError("remote source changed before completion")
            with transport._upload_snapshot(package / "payload" / item.path, item) as snapshot:
                try:
                    s3._transfer_json(
                        item.size_bytes, "s3api", "put-object", "--bucket", bucket, "--key", key,
                        "--body", str(snapshot), "--metadata", "sha256=" + item.sha256,
                        "--if-none-match", "*",
                    )
                except RuntimeError:
                    # Lost success/conditional race: read-only resolution, never a
                    # second PUT, overwrite, deletion or model execution.
                    s3._readback(bucket, key, digest=item.sha256, size=item.size_bytes)
                else:
                    s3._readback(bucket, key, digest=item.sha256, size=item.size_bytes)
            puts += 1
        _check_existing(bucket, prefix, entries, complete=True, s3=s3)
        results.append({"uri": uri, "object_count": len(entries), "put_attempts": puts,
                        "matching_preexisting_objects": len(existing)})
    return {
        "schema_version": "g8_synthetic_source_staging_v1",
        "verified_at": datetime.now(UTC).isoformat(),
        "source_package_sha256": expected_sha256,
        "candidate_sha256": verified["candidate_sha256"],
        "credential_access_key_sha256": identity,
        "credential_source": "explicit_process_environment_not_version_attested",
        "releases": results, "conditional_source_publication_verified": True,
        "pinned_job_credentials_verified": False, "production_g8_complete": False,
    }


def _production_head_denied() -> None:
    aws = shutil.which("aws")
    if aws is None:
        raise RuntimeError("aws CLI required for production-object HEAD denial")
    try:
        result = subprocess.run(
            [aws, "--endpoint-url", transport.ENDPOINT, "s3api", "head-object",
             "--bucket", PRODUCTION_BUCKET, "--key", PRODUCTION_KEY, "--output", "json"],
            capture_output=True, text=True, check=False, timeout=30,
            env={**os.environ, "AWS_PAGER": "", "AWS_MAX_ATTEMPTS": "1"},
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("production HEAD timed out; denial is not verified") from None
    # 404, connectivity errors, bad signatures and invalid credentials are NOT
    # access-denial evidence. No production object body is ever requested.
    if result.returncode == 0 or not re.search(
        r"An error occurred \((?:403|AccessDenied|Forbidden)\) when calling the HeadObject operation",
        result.stderr or "",
    ):
        raise ValueError("production HEAD did not return an explicit access denial")


def readback(package: Path, destination: Path, *, expected_sha256: str, s3=transport, head_denied=None) -> dict:
    verified, manifest, plans = _plans(package, expected_sha256)
    identity = _credential_identity()
    if destination.resolve() != destination.absolute():
        raise ValueError("readback destination must be canonical")
    destination = destination.absolute()
    original = package.resolve()
    if destination.is_relative_to(original) or original.is_relative_to(destination):
        raise ValueError("readback must be disjoint from the retained source package")
    if destination.exists():
        raise FileExistsError("readback destination exists; preserve prior evidence")
    for _, bucket, prefix, entries in plans:
        _check_existing(bucket, prefix, entries, complete=True, s3=s3)
    destination.mkdir(parents=True, mode=0o700)
    # Retain the independently downloaded bytes, not only HEAD metadata or IDs.
    for _, bucket, _, entries in plans:
        for key, item in sorted(entries.items()):
            target = destination / "payload" / item.path
            target.parent.mkdir(parents=True, exist_ok=True)
            s3._transfer_json(item.size_bytes, "s3api", "get-object",
                              "--bucket", bucket, "--key", key, str(target))
            if target.stat().st_size != item.size_bytes or sha256_file(target) != item.sha256:
                raise ValueError("downloaded synthetic source differs from retained inventory")
    # Non-S3 execution metadata stays explicitly local; only sources/ is remote.
    for item in manifest.inventory.files:
        if item.path.startswith("sources/"):
            continue
        with transport._upload_snapshot(package / "payload" / item.path, item) as snapshot:
            target = destination / "payload" / item.path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(snapshot, target)
    raw = sources.canonical(manifest)
    (destination / "source-package.json").write_bytes(raw)
    observed = sources.verify(destination, expected_sha256=expected_sha256)
    if observed != verified:
        raise ValueError("remote source verification differs from the original package")
    for _, bucket, prefix, entries in plans:
        _check_existing(bucket, prefix, entries, complete=True, s3=s3)
    (head_denied or _production_head_denied)()
    return {
        "schema_version": "g8_synthetic_source_readback_v1", "verified_at": datetime.now(UTC).isoformat(),
        "source_package_sha256": expected_sha256, "candidate_sha256": verified["candidate_sha256"],
        "credential_access_key_sha256": identity,
        "credential_source": "explicit_process_environment_not_version_attested",
        "remote_source_bytes_verified": True, "comparison_replay_domains_verified": 30,
        "remote_source_uris": [uri for uri, _, _, _ in plans],
        "local_only_metadata": [e.path for e in manifest.inventory.files if not e.path.startswith("sources/")],
        "production_head_denial_verified": True,
        "production_head_uri": f"s3://{PRODUCTION_BUCKET}/{PRODUCTION_KEY}",
        "production_body_downloaded": False, "pinned_job_credentials_verified": False,
        "native_storage_verified": False, "mlflow_remote_verified": False, "production_g8_complete": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--publish", action="store_true")
    mode.add_argument("--readback", action="store_true")
    parser.add_argument("--destination", type=Path)
    parser.add_argument("--sdk", action="store_true", help="reuse one frozen AWS SDK client")
    parser.add_argument("--session-seconds", type=int, default=900, help="SDK deadline, at most 1800 seconds")
    args = parser.parse_args()
    if args.readback != (args.destination is not None):
        parser.error("--destination is required only with --readback")
    if args.sdk and not (args.publish or args.readback):
        parser.error("--sdk requires --publish or --readback")
    if args.sdk:
        if __package__:
            from .g8_source_sdk import SourceSDK, session_deadline
        else:
            from g8_source_sdk import SourceSDK, session_deadline
        with session_deadline(args.session_seconds):
            s3 = SourceSDK()
            try:
                if args.publish:
                    receipt = publish(args.package, expected_sha256=args.expected_sha256, s3=s3)
                else:
                    receipt = readback(args.package, args.destination, expected_sha256=args.expected_sha256, s3=s3,
                                       head_denied=lambda: s3.production_head_denied(PRODUCTION_BUCKET, PRODUCTION_KEY))
            finally:
                s3.client.close()
        receipt.update(transport="single_client_frozen_aws_sdk", session_limit_seconds=args.session_seconds)
    elif args.publish:
        receipt = publish(args.package, expected_sha256=args.expected_sha256)
    elif args.readback:
        receipt = readback(args.package, args.destination, expected_sha256=args.expected_sha256)
    else:
        receipt = sources.verify(args.package, expected_sha256=args.expected_sha256)
    print(json.dumps(receipt, indent=2))
