from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ml.lightgbm.contracts import IDENTIFIER_PATTERN, SHA256_PATTERN


S3_SINGLE_PUT_MAX_BYTES = 5 * 1024**3


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class InventoryEntry(_StrictModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN)
    size_bytes: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_path(self) -> "InventoryEntry":
        path = PurePosixPath(self.path)
        if (
            path.is_absolute()
            or "\\" in self.path
            or any(part in {"", ".", ".."} for part in path.parts)
            or path.as_posix() != self.path
        ):
            raise ValueError("inventory path must be a normalized relative POSIX path")
        return self


class ChecksumInventory(_StrictModel):
    schema_version: str = Field(default="lightgbm_wave1_input_inventory_v1", pattern=IDENTIFIER_PATTERN)
    files: tuple[InventoryEntry, ...]

    @model_validator(mode="after")
    def validate_unique_paths(self) -> "ChecksumInventory":
        paths = [item.path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("inventory paths must be unique")
        return self


@dataclass(frozen=True)
class TransferLimits:
    max_files: int = 10_000
    max_bytes: int = 20 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class S3ObjectEvidence:
    key: str
    sha256: str
    size_bytes: int
    etag: str
    version_id: str | None = None


@dataclass(frozen=True)
class VerifiedS3ReleaseMember:
    payload: bytes
    inventory: ChecksumInventory


@dataclass(frozen=True)
class VerifiedS3ReleaseSelection:
    inventory: ChecksumInventory
    selected_inventory: ChecksumInventory


def _aws_environment() -> dict[str, str]:
    """Disable AWS CLI paging without relying on version-specific command flags."""

    return {**os.environ, "AWS_PAGER": ""}


def _aws_failure_kind(stderr: str) -> str:
    """Classify aws-cli failures without propagating potentially sensitive output."""

    normalized = stderr.lower()
    classifications = (
        (("unknown option", "unknown options", "unrecognized arguments"), "unsupported_option"),
        (("invalidaccesskeyid", "invalid access key"), "invalid_access_key"),
        (("signaturedoesnotmatch", "signature mismatch"), "signature_mismatch"),
        (("accessdenied", "access denied"), "access_denied"),
        (("could not connect to the endpoint", "endpoint connection error"), "endpoint_connection"),
        (("ssl validation failed", "certificate verify failed"), "ssl_validation"),
        (("timed out", "timeout"), "timeout"),
        (
            ("entitytoolarge", "proposed upload exceeds the maximum allowed object size"),
            "single_put_too_large",
        ),
    )
    for needles, classification in classifications:
        if any(needle in normalized for needle in needles):
            return classification
    return "unclassified"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_directory(root: Path, *, exclude_markers: bool = False) -> ChecksumInventory:
    root = root.resolve()
    if not root.is_dir():
        raise ValueError(f"inventory root is not a directory: {root}")
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if exclude_markers and relative in {"SUCCESS", "FAILED", "checksums.sha256"}:
            continue
        entries.append(
            InventoryEntry(path=relative, sha256=sha256_file(path), size_bytes=path.stat().st_size)
        )
    return ChecksumInventory(files=tuple(entries))


def verify_inventory(root: Path, inventory: ChecksumInventory, *, limits: TransferLimits = TransferLimits()) -> None:
    root = root.resolve()
    observed_files = len(inventory.files)
    observed_bytes = sum(item.size_bytes for item in inventory.files)
    if observed_files > limits.max_files:
        raise ValueError(
            "input inventory exceeds the file-count limit: "
            f"observed_files={observed_files}, max_files={limits.max_files}"
        )
    if observed_bytes > limits.max_bytes:
        raise ValueError(
            "input inventory exceeds the byte limit: "
            f"observed_bytes={observed_bytes}, max_bytes={limits.max_bytes}"
        )
    for item in inventory.files:
        path = (root / item.path).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError(f"inventory file is missing or escapes the input root: {item.path}")
        if path.stat().st_size != item.size_bytes or sha256_file(path) != item.sha256:
            raise ValueError(f"inventory checksum mismatch: {item.path}")


def write_checksum_file(root: Path, inventory: ChecksumInventory) -> Path:
    target = root / "checksums.sha256"
    target.write_text(
        "".join(f"{item.sha256}  {item.path}\n" for item in inventory.files),
        encoding="utf-8",
    )
    return target


def publish_local_result(
    staging: Path,
    result_uri: str,
    *,
    limits: TransferLimits = TransferLimits(),
) -> Path:
    """Atomically publish a verified local result and create SUCCESS last."""

    destination = _file_uri_path(result_uri)
    staging = staging.resolve()
    if destination.exists():
        raise FileExistsError(f"result run prefix already exists: {destination}")
    if not staging.is_dir() or (staging / "SUCCESS").exists() or (staging / "FAILED").exists():
        raise ValueError("result staging directory is invalid")
    inventory = inventory_directory(staging, exclude_markers=True)
    verify_inventory(staging, inventory, limits=limits)
    write_checksum_file(staging, inventory)
    (staging / "SUCCESS").write_text(inventory.model_dump_json(indent=2), encoding="utf-8")
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staging, destination)
    verify_complete_result(destination, limits=limits)
    return destination


def verify_complete_result(
    root: Path,
    *,
    limits: TransferLimits = TransferLimits(),
) -> VerifiedS3ReleaseSelection:
    root = root.resolve()
    success = root / "SUCCESS"
    if not success.is_file() or (root / "FAILED").exists():
        raise ValueError("result is partial or failed; SUCCESS is required and FAILED is forbidden")
    inventory = ChecksumInventory.model_validate_json(success.read_text(encoding="utf-8"))
    verify_inventory(root, inventory, limits=limits)
    checksum_lines = (root / "checksums.sha256").read_text(encoding="utf-8")
    expected = "".join(f"{item.sha256}  {item.path}\n" for item in inventory.files)
    if checksum_lines != expected:
        raise ValueError("result checksum inventory is not canonical")
    return inventory


def sync_s3(
    source: str,
    destination: str,
    *,
    endpoint_url: str | None = None,
    limits: TransferLimits = TransferLimits(),
) -> None:
    """Run one bounded aws-cli sync; credentials come only from the process environment."""

    _validate_transfer_endpoint(source)
    _validate_transfer_endpoint(destination)
    local_source = _local_endpoint(source)
    if local_source is not None:
        inventory = inventory_directory(local_source)
        verify_inventory(local_source, inventory, limits=limits)
    aws = shutil.which("aws")
    if aws is None:
        raise RuntimeError("aws CLI is required for Object Storage synchronization")
    command = [aws]
    if endpoint_url:
        command.extend(["--endpoint-url", endpoint_url])
    command.extend(["s3", "sync", source, destination, "--only-show-errors", "--no-follow-symlinks"])
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        capture_output=True,
        timeout=300,
        env=_aws_environment(),
    )
    if completed.returncode:
        failure_kind = _aws_failure_kind(completed.stderr or "")
        raise RuntimeError(
            "Object Storage synchronization failed with "
            f"exit code {completed.returncode} ({failure_kind})"
        )


def publish_s3_input_release(
    source: Path,
    destination: str,
    *,
    endpoint_url: str,
) -> tuple[S3ObjectEvidence, ...]:
    """Publish a bounded input package and verify every object before SUCCESS."""

    verify_complete_result(source)
    return _publish_s3_directory(source, destination, endpoint_url=endpoint_url, marker="SUCCESS")


def download_s3_release(
    source: str,
    destination: Path,
    *,
    endpoint_url: str,
    limits: TransferLimits = TransferLimits(),
) -> ChecksumInventory:
    """Download one prefix with S3 API calls and verify its completion contract."""

    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"local staging destination already exists: {destination}")
    bucket, prefix = _s3_bucket_prefix(source)
    objects = _list_s3_objects(bucket, prefix, endpoint_url=endpoint_url)
    if not objects:
        raise ValueError(f"S3 release prefix is empty: {source}")
    observed_files = len(objects)
    observed_bytes = sum(size for _, size in objects)
    if observed_files > limits.max_files:
        raise ValueError(
            "S3 release exceeds the file-count limit: "
            f"observed_files={observed_files}, max_files={limits.max_files}"
        )
    if observed_bytes > limits.max_bytes:
        raise ValueError(
            "S3 release exceeds the byte limit: "
            f"observed_bytes={observed_bytes}, max_bytes={limits.max_bytes}"
        )

    destination.mkdir(parents=True)
    try:
        for key, _ in objects:
            relative = _relative_s3_key(key, prefix)
            target = (destination / relative).resolve()
            if destination not in target.parents:
                raise ValueError(f"S3 object escapes the staging directory: {key}")
            target.parent.mkdir(parents=True, exist_ok=True)
            _aws_json(
                endpoint_url,
                "s3api",
                "get-object",
                "--bucket",
                bucket,
                "--key",
                key,
                str(target),
            )
        return verify_complete_result(destination, limits=limits)
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def read_verified_s3_release_member(
    source: str,
    member: str,
    *,
    endpoint_url: str,
    limits: TransferLimits = TransferLimits(),
) -> bytes | None:
    inspected = inspect_verified_s3_release_member(
        source,
        member,
        endpoint_url=endpoint_url,
        limits=limits,
    )
    return inspected.payload if inspected is not None else None


def inspect_verified_s3_release_member(
    source: str,
    member: str,
    *,
    endpoint_url: str,
    limits: TransferLimits = TransferLimits(),
) -> VerifiedS3ReleaseMember | None:
    """Read one member only after verifying the immutable remote release envelope.

    An empty prefix is an absent checkpoint. A non-empty prefix must be a complete,
    canonical release; partial or modified checkpoints fail closed.
    """

    relative_member = _normalized_relative_path(member)
    bucket, prefix = _s3_bucket_prefix(source)
    objects = _list_s3_objects(bucket, prefix, endpoint_url=endpoint_url)
    if not objects:
        return None
    observed_files = len(objects)
    observed_bytes = sum(size for _, size in objects)
    if observed_files > limits.max_files:
        raise ValueError(
            "S3 release exceeds the file-count limit: "
            f"observed_files={observed_files}, max_files={limits.max_files}"
        )
    if observed_bytes > limits.max_bytes:
        raise ValueError(
            "S3 release exceeds the byte limit: "
            f"observed_bytes={observed_bytes}, max_bytes={limits.max_bytes}"
        )
    remote_sizes = {
        _relative_s3_key(key, prefix).as_posix(): size for key, size in objects
    }
    with tempfile.TemporaryDirectory(prefix="wave1-s3-envelope-") as directory:
        temporary = Path(directory)
        success_bytes = _download_s3_member(
            bucket,
            prefix,
            "SUCCESS",
            temporary / "SUCCESS",
            endpoint_url=endpoint_url,
        )
        inventory = ChecksumInventory.model_validate_json(success_bytes)
        inventory_bytes = sum(item.size_bytes for item in inventory.files)
        verify_inventory_limits = TransferLimits(
            max_files=max(0, limits.max_files - 2),
            max_bytes=limits.max_bytes,
        )
        if len(inventory.files) > verify_inventory_limits.max_files:
            raise ValueError(
                "S3 release inventory exceeds the file-count limit: "
                f"observed_files={len(inventory.files)}, "
                f"max_files={verify_inventory_limits.max_files}"
            )
        if inventory_bytes > verify_inventory_limits.max_bytes:
            raise ValueError(
                "S3 release inventory exceeds the byte limit: "
                f"observed_bytes={inventory_bytes}, "
                f"max_bytes={verify_inventory_limits.max_bytes}"
            )
        expected_paths = {item.path for item in inventory.files} | {
            "checksums.sha256",
            "SUCCESS",
        }
        if set(remote_sizes) != expected_paths:
            raise ValueError("remote S3 release objects do not match its SUCCESS inventory")
        expected_checksum_text = "".join(
            f"{item.sha256}  {item.path}\n" for item in inventory.files
        ).encode()
        checksums = _download_s3_member(
            bucket,
            prefix,
            "checksums.sha256",
            temporary / "checksums.sha256",
            endpoint_url=endpoint_url,
        )
        if checksums != expected_checksum_text:
            raise ValueError("remote S3 release checksum inventory is not canonical")
        entries = {item.path: item for item in inventory.files}
        selected = entries.get(relative_member.as_posix())
        if selected is None:
            raise ValueError(f"remote S3 release omits required member: {relative_member}")
        if any(remote_sizes[item.path] != item.size_bytes for item in inventory.files):
            raise ValueError("remote S3 release object size differs from its SUCCESS inventory")
        for item in inventory.files:
            head = _aws_json(
                endpoint_url,
                "s3api",
                "head-object",
                "--bucket",
                bucket,
                "--key",
                f"{prefix}/{item.path}",
            )
            metadata = {
                str(key).lower(): value for key, value in (head.get("Metadata") or {}).items()
            }
            if (
                int(head.get("ContentLength", -1)) != item.size_bytes
                or metadata.get("sha256") != item.sha256
            ):
                raise ValueError(f"remote S3 release metadata mismatch: {item.path}")
        payload = _download_s3_member(
            bucket,
            prefix,
            relative_member.as_posix(),
            temporary / "member",
            endpoint_url=endpoint_url,
        )
        if len(payload) != selected.size_bytes or hashlib.sha256(payload).hexdigest() != selected.sha256:
            raise ValueError(f"remote S3 release member checksum mismatch: {relative_member}")
        return VerifiedS3ReleaseMember(payload=payload, inventory=inventory)


def download_verified_s3_release_members(
    source: str,
    destination: Path,
    *,
    endpoint_url: str,
    required_members: tuple[str, ...] = (),
    include_prefixes: tuple[str, ...] = (),
    include_suffixes: tuple[str, ...] = (),
    limits: TransferLimits = TransferLimits(),
    selected_limits: TransferLimits = TransferLimits(),
) -> ChecksumInventory:
    """Verify a complete remote release while downloading only selected members.

    This is intended for large immutable shard releases whose small derived
    artifacts are sufficient for the next stage. The complete S3 key set,
    canonical SUCCESS/checksum envelope, object sizes, and SHA-256 metadata are
    still verified before any selected payload is accepted.
    """

    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"local staging destination already exists: {destination}")
    normalized_required = tuple(
        _normalized_relative_path(item).as_posix() for item in required_members
    )
    normalized_prefixes = tuple(
        _normalized_relative_path(item.rstrip("/")).as_posix() + "/"
        for item in include_prefixes
    )
    normalized_suffixes = tuple(
        _normalized_relative_path(item.lstrip("/")).as_posix()
        for item in include_suffixes
    )
    if not normalized_required and not normalized_prefixes and not normalized_suffixes:
        raise ValueError("selective S3 download requires a member or prefix")

    bucket, prefix = _s3_bucket_prefix(source)
    objects = _list_s3_objects(bucket, prefix, endpoint_url=endpoint_url)
    if not objects:
        raise ValueError(f"S3 release prefix is empty: {source}")
    if len(objects) > limits.max_files or sum(size for _, size in objects) > limits.max_bytes:
        raise ValueError("S3 release exceeds the selective-download envelope limits")
    remote_sizes = {
        _relative_s3_key(key, prefix).as_posix(): size for key, size in objects
    }

    with tempfile.TemporaryDirectory(prefix="wave1-s3-selective-envelope-") as directory:
        temporary = Path(directory)
        success_bytes = _download_s3_member(
            bucket, prefix, "SUCCESS", temporary / "SUCCESS", endpoint_url=endpoint_url
        )
        inventory = ChecksumInventory.model_validate_json(success_bytes)
        expected_paths = {item.path for item in inventory.files} | {
            "checksums.sha256",
            "SUCCESS",
        }
        if set(remote_sizes) != expected_paths:
            raise ValueError("remote S3 release objects do not match its SUCCESS inventory")
        if any(remote_sizes[item.path] != item.size_bytes for item in inventory.files):
            raise ValueError("remote S3 release object size differs from its SUCCESS inventory")
        expected_checksum_text = "".join(
            f"{item.sha256}  {item.path}\n" for item in inventory.files
        ).encode()
        checksums = _download_s3_member(
            bucket,
            prefix,
            "checksums.sha256",
            temporary / "checksums.sha256",
            endpoint_url=endpoint_url,
        )
        if checksums != expected_checksum_text:
            raise ValueError("remote S3 release checksum inventory is not canonical")

        entries = {item.path: item for item in inventory.files}
        missing = sorted(set(normalized_required) - set(entries))
        if missing:
            raise ValueError(f"remote S3 release omits required members: {', '.join(missing)}")
        selected = tuple(
            item
            for item in inventory.files
            if item.path in normalized_required
            or any(item.path.startswith(value) for value in normalized_prefixes)
            or any(item.path.endswith(value) for value in normalized_suffixes)
        )
        if len(selected) > selected_limits.max_files:
            raise ValueError("selected S3 members exceed the file-count limit")
        if sum(item.size_bytes for item in selected) > selected_limits.max_bytes:
            raise ValueError("selected S3 members exceed the byte limit")

        destination.mkdir(parents=True)
        try:
            for item in selected:
                head = _aws_json(
                    endpoint_url,
                    "s3api",
                    "head-object",
                    "--bucket",
                    bucket,
                    "--key",
                    f"{prefix}/{item.path}",
                )
                metadata = {
                    str(key).lower(): value
                    for key, value in (head.get("Metadata") or {}).items()
                }
                if (
                    int(head.get("ContentLength", -1)) != item.size_bytes
                    or metadata.get("sha256") != item.sha256
                ):
                    raise ValueError(f"remote S3 release metadata mismatch: {item.path}")
                target = (destination / item.path).resolve()
                if destination not in target.parents:
                    raise ValueError(f"selected S3 member escapes destination: {item.path}")
                target.parent.mkdir(parents=True, exist_ok=True)
                payload = _download_s3_member(
                    bucket, prefix, item.path, target, endpoint_url=endpoint_url
                )
                if len(payload) != item.size_bytes or hashlib.sha256(payload).hexdigest() != item.sha256:
                    raise ValueError(f"remote S3 release member checksum mismatch: {item.path}")
            return VerifiedS3ReleaseSelection(
                inventory=inventory,
                selected_inventory=ChecksumInventory(
                    schema_version=inventory.schema_version,
                    files=selected,
                ),
            )
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise


def verify_s3_members_access_denied(
    source: str,
    members: tuple[str, ...],
    *,
    endpoint_url: str,
) -> None:
    """Prove that the active AWS identity cannot read exact S3 members."""

    if not members:
        raise ValueError("access-denial verification requires exact members")
    bucket, prefix = _s3_bucket_prefix(source)
    aws = shutil.which("aws")
    if aws is None:
        raise RuntimeError("aws CLI is required for Object Storage access verification")
    for member in members:
        relative = _normalized_relative_path(member).as_posix()
        completed = subprocess.run(
            [
                aws,
                "--endpoint-url",
                endpoint_url,
                "s3api",
                "head-object",
                "--bucket",
                bucket,
                "--key",
                f"{prefix}/{relative}",
                "--output",
                "json",
            ],
            check=False,
            text=True,
            capture_output=True,
            timeout=60,
            env=_aws_environment(),
        )
        if completed.returncode == 0:
            raise PermissionError(f"active identity unexpectedly read final member: {relative}")
        if _aws_failure_kind(completed.stderr or "") != "access_denied":
            raise RuntimeError(f"final member denial was not an AccessDenied response: {relative}")


def publish_s3_result(
    source: Path,
    destination: str,
    *,
    endpoint_url: str,
    require_version_ids: bool = False,
    limits: TransferLimits = TransferLimits(),
) -> tuple[S3ObjectEvidence, ...]:
    """Publish a verified successful result, making SUCCESS visible last."""

    verify_complete_result(source, limits=limits)
    return _publish_s3_directory(
        source,
        destination,
        endpoint_url=endpoint_url,
        marker="SUCCESS",
        require_version_ids=require_version_ids,
        limits=limits,
    )


def publish_s3_failure(
    source: Path,
    destination: str,
    *,
    endpoint_url: str,
) -> tuple[S3ObjectEvidence, ...]:
    """Publish bounded failure evidence, making FAILED visible last."""

    source = source.resolve()
    if not (source / "FAILED").is_file() or (source / "SUCCESS").exists():
        raise ValueError("failure staging directory must contain FAILED and must not contain SUCCESS")
    return _publish_s3_directory(source, destination, endpoint_url=endpoint_url, marker="FAILED")


def _publish_s3_directory(
    source: Path,
    destination: str,
    *,
    endpoint_url: str,
    marker: str,
    require_version_ids: bool = False,
    limits: TransferLimits = TransferLimits(),
) -> tuple[S3ObjectEvidence, ...]:
    """Publish one immutable directory and expose its terminal marker last."""

    source = source.resolve()
    complete_inventory = inventory_directory(source)
    inventory = ChecksumInventory(
        files=tuple(item for item in complete_inventory.files if item.path != marker)
    )
    verify_inventory(source, inventory, limits=limits)
    bucket, prefix = _s3_bucket_prefix(destination)
    if _list_s3_keys(bucket, prefix, endpoint_url=endpoint_url, limit=1):
        raise FileExistsError(f"release prefix already exists: {destination}")

    evidence: list[S3ObjectEvidence] = []
    uploaded_keys: list[str] = []
    try:
        for item in inventory.files:
            key = f"{prefix}/{item.path}"
            uploaded_keys.append(key)
            evidence.append(
                _put_and_verify_s3_object(
                    source / item.path,
                    bucket=bucket,
                    key=key,
                    expected_sha256=item.sha256,
                    endpoint_url=endpoint_url,
                )
            )

        if require_version_ids and any(item.version_id is None for item in evidence):
            raise ValueError("versioned Object Storage publication omitted a version ID")

        terminal_marker = source / marker
        if not terminal_marker.is_file():
            raise ValueError(f"published directory must contain {marker}")
        marker_key = f"{prefix}/{marker}"
        evidence.append(
            _put_and_verify_s3_object(
                terminal_marker,
                bucket=bucket,
                key=marker_key,
                expected_sha256=sha256_file(terminal_marker),
                endpoint_url=endpoint_url,
            )
        )
        uploaded_keys.append(marker_key)
    except Exception:
        for key in uploaded_keys:
            _aws_json(
                endpoint_url,
                "s3api",
                "delete-object",
                "--bucket",
                bucket,
                "--key",
                key,
            )
        raise
    return tuple(evidence)


def _put_and_verify_s3_object(
    source: Path,
    *,
    bucket: str,
    key: str,
    expected_sha256: str,
    endpoint_url: str,
) -> S3ObjectEvidence:
    transfer_timeout = max(300, int(source.stat().st_size / (5 * 1024 * 1024)) + 120)
    if source.stat().st_size > S3_SINGLE_PUT_MAX_BYTES:
        _aws_copy_file(
            endpoint_url,
            source,
            bucket=bucket,
            key=key,
            expected_sha256=expected_sha256,
            timeout_seconds=transfer_timeout,
        )
    else:
        _aws_json(
            endpoint_url,
            "s3api",
            "put-object",
            "--bucket",
            bucket,
            "--key",
            key,
            "--body",
            str(source),
            "--metadata",
            f"sha256={expected_sha256}",
            timeout_seconds=transfer_timeout,
        )
    head = _aws_json(
        endpoint_url,
        "s3api",
        "head-object",
        "--bucket",
        bucket,
        "--key",
        key,
    )
    size = int(head.get("ContentLength", -1))
    metadata = {str(key).lower(): value for key, value in (head.get("Metadata") or {}).items()}
    remote_hash = metadata.get("sha256")
    if size != source.stat().st_size or remote_hash != expected_sha256:
        raise ValueError(f"remote Object Storage metadata mismatch: {key}")
    with tempfile.TemporaryDirectory(prefix="wave1-s3-readback-") as directory:
        target = Path(directory) / "object"
        _aws_json(
            endpoint_url,
            "s3api",
            "get-object",
            "--bucket",
            bucket,
            "--key",
            key,
            str(target),
            timeout_seconds=transfer_timeout,
        )
        if sha256_file(target) != expected_sha256:
            raise ValueError(f"remote Object Storage read-back checksum mismatch: {key}")
    return S3ObjectEvidence(
        key=key,
        sha256=expected_sha256,
        size_bytes=size,
        etag=str(head.get("ETag", "")).strip('"'),
        version_id=(str(head["VersionId"]) if head.get("VersionId") else None),
    )


def _aws_copy_file(
    endpoint_url: str,
    source: Path,
    *,
    bucket: str,
    key: str,
    expected_sha256: str,
    timeout_seconds: int,
) -> None:
    """Upload a large file with the AWS CLI managed multipart transfer."""

    aws = shutil.which("aws")
    if aws is None:
        raise RuntimeError("aws CLI is required for Object Storage publication")
    completed = subprocess.run(
        [
            aws,
            "--endpoint-url",
            endpoint_url,
            "s3",
            "cp",
            str(source),
            f"s3://{bucket}/{key}",
            "--metadata",
            f"sha256={expected_sha256}",
            "--only-show-errors",
            "--no-progress",
        ],
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        env=_aws_environment(),
    )
    if completed.returncode:
        failure_kind = _aws_failure_kind(completed.stderr or "")
        raise RuntimeError(
            "Object Storage multipart upload failed with "
            f"exit code {completed.returncode} ({failure_kind})"
        )


def _list_s3_keys(bucket: str, prefix: str, *, endpoint_url: str, limit: int) -> tuple[str, ...]:
    payload = _aws_json(
        endpoint_url,
        "s3api",
        "list-objects-v2",
        "--bucket",
        bucket,
        "--prefix",
        f"{prefix}/",
        "--max-keys",
        str(limit),
    )
    return tuple(item["Key"] for item in payload.get("Contents", ()))


def _list_s3_objects(bucket: str, prefix: str, *, endpoint_url: str) -> tuple[tuple[str, int], ...]:
    objects: list[tuple[str, int]] = []
    continuation_token: str | None = None
    while True:
        args = [
            "s3api",
            "list-objects-v2",
            "--bucket",
            bucket,
            "--prefix",
            f"{prefix}/",
        ]
        if continuation_token is not None:
            args.extend(["--continuation-token", continuation_token])
        payload = _aws_json(endpoint_url, *args)
        objects.extend(
            (str(item["Key"]), int(item["Size"]))
            for item in payload.get("Contents", ())
            if isinstance(item, dict) and "Key" in item and "Size" in item
        )
        if not payload.get("IsTruncated"):
            return tuple(objects)
        next_token = payload.get("NextContinuationToken")
        if not isinstance(next_token, str) or not next_token:
            raise ValueError("truncated S3 listing omitted the continuation token")
        continuation_token = next_token


def _relative_s3_key(key: str, prefix: str) -> PurePosixPath:
    expected = f"{prefix}/"
    if not key.startswith(expected):
        raise ValueError(f"S3 object is outside the requested prefix: {key}")
    relative_value = key.removeprefix(expected)
    relative = PurePosixPath(relative_value)
    if (
        not relative_value
        or relative.is_absolute()
        or "\\" in relative_value
        or any(part in {"", ".", ".."} for part in relative.parts)
        or relative.as_posix() != relative_value
    ):
        raise ValueError(f"S3 object key is not a normalized relative path: {key}")
    return relative


def _normalized_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (
        not value
        or path.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise ValueError("S3 release member must be a normalized relative POSIX path")
    return path


def _download_s3_member(
    bucket: str,
    prefix: str,
    member: str,
    target: Path,
    *,
    endpoint_url: str,
) -> bytes:
    key = f"{prefix}/{member}"
    _aws_json(
        endpoint_url,
        "s3api",
        "get-object",
        "--bucket",
        bucket,
        "--key",
        key,
        str(target),
    )
    return target.read_bytes()


def _aws_json(
    endpoint_url: str, *args: str, timeout_seconds: int = 300
) -> dict[str, object]:
    aws = shutil.which("aws")
    if aws is None:
        raise RuntimeError("aws CLI is required for Object Storage publication")
    completed = subprocess.run(
        [aws, "--endpoint-url", endpoint_url, *args, "--output", "json"],
        check=False,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        env=_aws_environment(),
    )
    if completed.returncode:
        failure_kind = _aws_failure_kind(completed.stderr or "")
        raise RuntimeError(
            f"Object Storage command failed with exit code {completed.returncode} ({failure_kind})"
        )
    return json.loads(completed.stdout or "{}")


def _s3_bucket_prefix(uri: str) -> tuple[str, str]:
    parsed = urlsplit(uri)
    prefix = parsed.path.strip("/")
    if (
        parsed.scheme != "s3"
        or not parsed.netloc
        or not prefix
        or parsed.query
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.port is not None
    ):
        raise ValueError("S3 release URI requires a bucket and bounded prefix")
    if any(part in {"", ".", ".."} for part in PurePosixPath(prefix).parts):
        raise ValueError("S3 release URI contains an invalid path")
    return parsed.netloc, prefix.rstrip("/")


def _file_uri_path(uri: str) -> Path:
    parsed = urlsplit(uri)
    if parsed.scheme != "file" or parsed.netloc not in {"", "localhost"} or not parsed.path:
        raise ValueError("local result URI must be an absolute file:// URI")
    return Path(parsed.path).resolve()


def _validate_transfer_endpoint(value: str) -> None:
    if value.startswith("s3://"):
        parsed = urlsplit(value)
        if not parsed.netloc or not parsed.path.strip("/"):
            raise ValueError("S3 transfer endpoint requires a bucket and bounded prefix")
        if any(part in {".", ".."} for part in PurePosixPath(parsed.path).parts):
            raise ValueError("S3 transfer endpoint contains path traversal")
        return
    path = Path(value).resolve()
    if str(path) in {"/", str(Path.home().resolve())}:
        raise ValueError("local transfer endpoint is too broad")


def _local_endpoint(value: str) -> Path | None:
    return None if value.startswith("s3://") else Path(value).resolve()


def temporary_staging(parent: Path, run_id: str) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    return Path(tempfile.mkdtemp(prefix=f".{run_id}.", dir=parent))
