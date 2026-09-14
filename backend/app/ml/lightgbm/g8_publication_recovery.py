"""Retain and publish an already-completed G8 release; never score or log a run.

This is the post-MLflow publication boundary, not recovery from incomplete scoring
or tracking. Native filesystem durability and replacement approval are external
gates; a local checkpoint does not grant execution or cloud provisioning authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest, LightGbmCloudRun
from app.nebius import object_storage as storage

ENDPOINT = "https://storage.eu-north1.nebius.cloud"
RESULTS = "s3://aimada-wave1-results-e00g6zvxpr00"
SHA = r"^[a-f0-9]{64}$"
SINGLE_PUT_MAX_BYTES = 5 * 1024**3


class RecoveryBinding(BaseModel):
    """Must come from the reviewed package/retained execution receipt, not discovery."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["g8_publication_recovery_binding_v1"] = "g8_publication_recovery_binding_v1"
    execution_package_sha256: str = Field(pattern=SHA)
    request_sha256: str = Field(pattern=SHA)
    candidate_sha256: str = Field(pattern=SHA)
    c4_report_sha256: str = Field(pattern=SHA)
    mlflow_run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    result_uri: str


class PublicationCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["g8_publication_checkpoint_v1"] = "g8_publication_checkpoint_v1"
    binding: RecoveryBinding
    inventory: storage.ChecksumInventory


def _canonical(value: BaseModel) -> bytes:
    return (json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n").encode()


def _directory_sync(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _inventory(root: Path, limits: storage.TransferLimits) -> storage.ChecksumInventory:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("checkpoint source must be a real directory")
    paths = []
    total = 0
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISDIR(mode):
            continue
        if not stat.S_ISREG(mode):
            raise ValueError("checkpoint forbids symlinks and nonregular files")
        total += path.stat().st_size
        if len(paths) >= limits.max_files or total > limits.max_bytes:
            raise ValueError("checkpoint exceeds the approved transfer limits")
        paths.append(storage.InventoryEntry(
            path=path.relative_to(root).as_posix(), sha256=sha256_file(path), size_bytes=path.stat().st_size,
        ))
    return storage.ChecksumInventory(files=tuple(paths))


def _verify_release(root: Path, binding: RecoveryBinding, limits: storage.TransferLimits) -> LightGbmCloudJobRequest:
    storage.verify_complete_result(root, limits=limits)
    declared = storage.ChecksumInventory.model_validate_json((root / "SUCCESS").read_bytes())
    actual = _inventory(root, limits)
    if tuple(e for e in actual.files if e.path not in {"SUCCESS", "checksums.sha256"}) != declared.files:
        raise ValueError("completed release contains unlisted or noncanonical payload members")
    request = LightGbmCloudJobRequest.model_validate_json((root / "request.json").read_bytes())
    run = LightGbmCloudRun.model_validate_json((root / "cloud-run.json").read_bytes())
    if (
        request.mode != "final-evaluation" or run.mode != "final-evaluation" or run.status != "succeeded"
        or request.candidate is None
        or request.canonical_hash() != binding.request_sha256
        or run.request_sha256 != binding.request_sha256
        or run.run_id != request.run_id or run.campaign_id != request.campaign_id
        or request.candidate.sha256 != binding.candidate_sha256
        or run.candidate_hash != binding.candidate_sha256
        or run.mlflow_run_id != binding.mlflow_run_id
        or request.result_uri != binding.result_uri
        or request.result_uri != f"{RESULTS}/campaigns/{request.campaign_id}/final/{request.run_id}"
        or request.mlflow_tracking_uri != "http://10.4.0.54:5500"
        or sha256_file(root / "artifacts/c4-evaluation.json") != binding.c4_report_sha256
    ):
        raise ValueError("completed G8 release differs from the recovery binding")
    # Structural release verification is deliberately separate from scoring and
    # from MLflow logging. This also verifies the model/prediction artifact bytes.
    from app.ml.lightgbm.contracts import (
        CalibrationManifest, DetectorPredictionsManifest, LightGbmTrainingRun, ModelBundleManifest,
    )
    from app.ml.lightgbm.release import verify_complete_lightgbm_v1_release

    artifacts = root / "artifacts"
    verify_complete_lightgbm_v1_release(
        artifacts,
        training=LightGbmTrainingRun.model_validate_json((artifacts / "training/training-run.json").read_bytes()),
        calibration=CalibrationManifest.model_validate_json((artifacts / "calibration/calibration-manifest.json").read_bytes()),
        predictions=DetectorPredictionsManifest.model_validate_json((artifacts / "prediction/prediction-manifest.json").read_bytes()),
        bundle=ModelBundleManifest.model_validate_json((artifacts / "bundle/model-bundle.json").read_bytes()),
    )
    return request


def retain_completed_release(
    source: Path, destination: Path, *, binding: RecoveryBinding,
    limits: storage.TransferLimits = storage.TransferLimits(),
) -> str:
    """Copy, verify and fsync a complete release, sealing the checkpoint last.

    A failed copy remains unsealed for diagnosis; never overwrite/reuse its path.
    The caller must retain the returned digest independently before publication.
    """
    inventory = _inventory(source, limits)
    _verify_release(source, binding, limits)
    source = source.resolve()
    if destination.resolve().is_relative_to(source) or source.is_relative_to(destination.resolve()):
        raise ValueError("checkpoint and source directories must be disjoint")
    if not destination.parent.is_dir() or destination.parent.resolve() != destination.parent.absolute():
        raise ValueError("checkpoint parent must be an existing canonical directory")
    destination.mkdir(mode=0o700, exist_ok=False)
    _directory_sync(destination.parent)
    payload = destination / "payload"
    payload.mkdir(mode=0o700)
    for entry in inventory.files:
        target = payload / entry.path
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (source / entry.path).open("rb") as original, target.open("xb") as output:
            os.chmod(target, 0o600)
            shutil.copyfileobj(original, output)
            output.flush()
            os.fsync(output.fileno())
    if _inventory(payload, limits) != inventory:
        raise ValueError("checkpoint copy differs from the completed source")
    _verify_release(payload, binding, limits)
    for directory in sorted((p for p in payload.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
        _directory_sync(directory)
    _directory_sync(payload)
    checkpoint = _canonical(PublicationCheckpoint(binding=binding, inventory=inventory))
    pending = destination / ".checkpoint.pending"
    with pending.open("xb") as output:
        output.write(checkpoint)
        output.flush()
        os.fsync(output.fileno())
    os.rename(pending, destination / "checkpoint.json")
    _directory_sync(destination)
    return hashlib.sha256(checkpoint).hexdigest()


def verify_checkpoint(
    root: Path, *, expected_sha256: str, binding: RecoveryBinding,
    limits: storage.TransferLimits = storage.TransferLimits(),
) -> PublicationCheckpoint:
    if not re.fullmatch(SHA, expected_sha256):
        raise ValueError("an independently retained checkpoint SHA-256 is required")
    if root.is_symlink() or {p.name for p in root.iterdir()} != {"checkpoint.json", "payload"}:
        raise ValueError("checkpoint is unsealed or contains unexpected members")
    marker = root / "checkpoint.json"
    if marker.is_symlink() or marker.stat().st_size > 8 * 1024**2:
        raise ValueError("checkpoint marker is invalid")
    raw = marker.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("checkpoint identity differs from the retained receipt")
    checkpoint = PublicationCheckpoint.model_validate_json(raw)
    if _canonical(checkpoint) != raw or checkpoint.binding != binding:
        raise ValueError("checkpoint is noncanonical or belongs to another recovery binding")
    if _inventory(root / "payload", limits) != checkpoint.inventory:
        raise ValueError("checkpoint payload differs from its sealed inventory")
    _verify_release(root / "payload", binding, limits)
    return checkpoint


def _transfer_timeout(size: int) -> int:
    if not 0 <= size <= SINGLE_PUT_MAX_BYTES:
        raise ValueError("transfer size is outside the conditional single-object limit")
    # Same conservative 5 MiB/s envelope as the main storage publisher, rounded
    # up, with 120 seconds overhead. The 5 GiB limit receives 1,144 seconds.
    return max(300, (size + 5 * 1024**2 - 1) // (5 * 1024**2) + 120)


def _transfer_json(size: int, *args: str) -> dict:
    """Own the subprocess timeout: the frozen helper accepts no timeout keyword."""
    timeout = _transfer_timeout(size)
    aws = shutil.which("aws")
    if aws is None:
        raise RuntimeError("aws CLI is required for recovery transfers")
    try:
        completed = subprocess.run(
            [aws, "--endpoint-url", ENDPOINT, *args, "--output", "json"],
            check=False, capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "AWS_PAGER": ""},
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("recovery transfer exceeded its size-based timeout") from None
    if completed.returncode:
        raise RuntimeError(f"recovery transfer failed with exit code {completed.returncode}")
    try:
        result = json.loads(completed.stdout) if completed.stdout.strip() else {}
    except json.JSONDecodeError:
        raise RuntimeError("recovery transfer returned invalid JSON") from None
    if not isinstance(result, dict):
        raise RuntimeError("recovery transfer returned a non-object response")
    return result


@contextmanager
def _upload_snapshot(source: Path, entry: storage.InventoryEntry):
    """Never give the CLI a path in the concurrently mutable checkpoint tree.

    Copy (not link) into a private directory, validate the copied bytes against
    the seal, close its writer and make it read-only before handing it to AWS.
    The private copy stays alive through PUT and ambiguous-response read-back.
    """
    with tempfile.TemporaryDirectory(prefix="g8-verified-upload-") as directory:
        snapshot = Path(directory) / "object"
        with source.open("rb") as original, snapshot.open("xb") as output:
            shutil.copyfileobj(original, output)
        if snapshot.stat().st_size != entry.size_bytes or sha256_file(snapshot) != entry.sha256:
            raise ValueError("checkpoint changed while preparing upload snapshot")
        snapshot.chmod(0o400)
        yield snapshot


def _readback(bucket: str, key: str, *, digest: str, size: int, metadata_name: str = "sha256") -> None:
    head = storage._aws_json(ENDPOINT, "s3api", "head-object", "--bucket", bucket, "--key", key)
    metadata = {str(k).lower(): v for k, v in (head.get("Metadata") or {}).items()}
    # Intent metadata uses the canonical request hash, which omits no bytes in
    # the actual request.json emitted by the runner.
    if metadata.get(metadata_name) != digest or head.get("ContentLength") != size:
        raise ValueError("remote recovery object metadata conflicts with the checkpoint")
    with tempfile.TemporaryDirectory(prefix="g8-publication-readback-") as temporary:
        target = Path(temporary) / "object"
        _transfer_json(size, "s3api", "get-object", "--bucket", bucket, "--key", key, str(target))
        if sha256_file(target) != digest:
            raise ValueError("remote recovery object bytes conflict with the checkpoint")


def _listed_keys(bucket: str, prefix: str, allowed: set[str]) -> set[str]:
    keys: set[str] = set()
    tokens: set[str] = set()
    args = []
    while True:
        previous_count = len(keys)
        page = storage._aws_json(
            ENDPOINT, "s3api", "list-objects-v2", "--bucket", bucket, "--prefix", prefix + "/",
            "--max-keys", str(min(len(allowed) + 1, 1000)), "--no-paginate", *args,
        )
        for item in page.get("Contents", []):
            key = item["Key"]
            if key not in allowed or key in keys:
                raise ValueError("result prefix contains unexpected or duplicate objects")
            keys.add(key)
        if not page.get("IsTruncated"):
            return keys
        token = page.get("NextContinuationToken")
        if (
            not isinstance(token, str) or not token or token in tokens
            or len(keys) >= len(allowed) or len(keys) == previous_count
        ):
            raise ValueError("invalid or over-limit recovery listing pagination")
        tokens.add(token)
        args = ["--continuation-token", token]


def resume_publication(root: Path, *, expected_sha256: str, binding: RecoveryBinding,
                       limits: storage.TransferLimits = storage.TransferLimits()) -> dict:
    """Publish only matching missing objects; preserve every object on any failure.

    No final-input transfer, scoring, MLflow write or intent creation is possible.
    An existing intent and independently bound checkpoint are mandatory.
    """
    checkpoint = verify_checkpoint(root, expected_sha256=expected_sha256, binding=binding, limits=limits)
    payload = root / "payload"
    request = LightGbmCloudJobRequest.model_validate_json((payload / "request.json").read_bytes())
    bucket, prefix = binding.result_uri.removeprefix("s3://").split("/", 1)
    inventory = checkpoint.inventory.files
    if any(item.size_bytes > SINGLE_PUT_MAX_BYTES for item in inventory):
        raise ValueError("recovery cannot conditionally publish multipart objects")
    intent = prefix.rsplit("/", 1)[0] + "/.intents/" + request.run_id + ".json"
    _readback(
        bucket, intent, digest=binding.request_sha256, size=len(request.canonical_bytes()),
        metadata_name="request-sha256",
    )
    expected = {prefix + "/" + item.path: item for item in inventory}

    def readback(key):
        entry = expected[key]
        _readback(bucket, key, digest=entry.sha256, size=entry.size_bytes)
    existing = _listed_keys(bucket, prefix, set(expected))
    marker = prefix + "/SUCCESS"
    if marker in existing and existing != set(expected):
        raise ValueError("published SUCCESS exists with missing payload objects; refusing repair")
    for key in sorted(existing):
        readback(key)
    created = 0
    for key in sorted(set(expected) - existing, key=lambda key: (key == marker, key)):
        entry = expected[key]
        source = payload / entry.path
        if source.is_symlink() or source.stat().st_size != entry.size_bytes or sha256_file(source) != entry.sha256:
            raise ValueError("checkpoint changed during publication")
        if key == marker:
            verify_checkpoint(root, expected_sha256=expected_sha256, binding=binding, limits=limits)
        with _upload_snapshot(source, entry) as snapshot:
            try:
                _transfer_json(
                    entry.size_bytes, "s3api", "put-object", "--bucket", bucket, "--key", key,
                    "--body", str(snapshot), "--metadata", "sha256=" + entry.sha256, "--if-none-match", "*",
                )
            except RuntimeError:
                # May be a lost success response or a concurrent conditional create.
                # Accept only an exact read-back. Never overwrite, delete or rescore.
                readback(key)
            else:
                readback(key)
        created += 1
    if _listed_keys(bucket, prefix, set(expected)) != set(expected):
        raise ValueError("published recovery inventory is incomplete")
    for key in sorted(expected):
        readback(key)
    return {
        "schema_version": "g8_publication_recovery_receipt_v1",
        "checkpoint_sha256": expected_sha256,
        "request_sha256": binding.request_sha256,
        "mlflow_run_id": binding.mlflow_run_id,
        "result_uri": binding.result_uri,
        "object_count": len(expected),
        "previously_verified_objects": len(existing),
        "conditionally_published_objects": created,
        "scoring_invocations": 0,
        "mlflow_writes": 0,
        "mlflow_remote_state_verified": False,
    }
