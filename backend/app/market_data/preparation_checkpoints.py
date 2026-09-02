from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
from pathlib import Path, PurePosixPath
from typing import Literal, TypeVar
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field

from app.data_ingestion.models import DatasetManifest
from app.ml.lightgbm.contracts import SHA256_PATTERN
from app.nebius.object_storage import (
    ChecksumInventory,
    TransferLimits,
    download_s3_release,
    inspect_verified_s3_release_member,
    inventory_directory,
    publish_local_result,
    publish_s3_result,
    verify_complete_result,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def canonical_hash(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


class PreparationCheckpointBinding(_StrictModel):
    schema_version: Literal["market_data_preparation_checkpoint_binding_v2"] = (
        "market_data_preparation_checkpoint_binding_v2"
    )
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    source_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    source_sha256: str = Field(pattern=SHA256_PATTERN)
    image: str
    git_commit: str
    feature_config_sha256: str = Field(pattern=SHA256_PATTERN)


class CheckpointReference(_StrictModel):
    schema_version: Literal["market_data_preparation_checkpoint_reference_v2"] = (
        "market_data_preparation_checkpoint_reference_v2"
    )
    kind: Literal["normalized", "comparison"]
    uri: str
    checkpoint_sha256: str = Field(pattern=SHA256_PATTERN)
    payload_inventory_sha256: str = Field(pattern=SHA256_PATTERN)
    payload_file_count: int = Field(ge=1)
    payload_size_bytes: int = Field(ge=1)


class NormalizedCheckpoint(_StrictModel):
    schema_version: Literal["market_data_normalized_checkpoint_v2"] = (
        "market_data_normalized_checkpoint_v2"
    )
    binding_sha256: str = Field(pattern=SHA256_PATTERN)
    manifests: dict[str, DatasetManifest]
    payload_inventory_sha256: str = Field(pattern=SHA256_PATTERN)
    payload_file_count: int = Field(ge=1)
    payload_size_bytes: int = Field(ge=1)


class ComparisonCheckpoint(_StrictModel):
    schema_version: Literal["market_data_comparison_checkpoint_v2"] = (
        "market_data_comparison_checkpoint_v2"
    )
    binding_sha256: str = Field(pattern=SHA256_PATTERN)
    comparison_number: int = Field(ge=1, le=27)
    symbol: Literal["AAPL", "MSFT", "NVDA"]
    attack_family: Literal["spoofing_like_wall", "layering_like", "quote_stuffing"]
    seed: Literal[41, 42, 43]
    control_run_id: str
    control_event_stream_sha256: str = Field(pattern=SHA256_PATTERN)
    hybrid_run_id: str
    hybrid_event_stream_sha256: str = Field(pattern=SHA256_PATTERN)
    includes_control_artifacts: bool
    repeat_determinism_verified: Literal[True] = True
    payload_inventory_sha256: str = Field(pattern=SHA256_PATTERN)
    payload_file_count: int = Field(ge=1)
    payload_size_bytes: int = Field(ge=1)


CheckpointRecord = NormalizedCheckpoint | ComparisonCheckpoint
RecordT = TypeVar("RecordT", NormalizedCheckpoint, ComparisonCheckpoint)


def inventory_evidence(
    root: Path,
    *,
    exclude_checkpoint: bool = False,
) -> tuple[str, int, int]:
    inventory = inventory_directory(root, exclude_markers=True)
    return inventory_model_evidence(inventory, exclude_checkpoint=exclude_checkpoint)


def inventory_model_evidence(
    inventory: ChecksumInventory,
    *,
    exclude_checkpoint: bool = False,
) -> tuple[str, int, int]:
    if exclude_checkpoint:
        inventory = inventory.model_copy(
            update={
                "files": tuple(
                    item for item in inventory.files if item.path != "checkpoint.json"
                )
            }
        )
    payload = json.dumps(
        inventory.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
    ).encode()
    return (
        hashlib.sha256(payload).hexdigest(),
        len(inventory.files),
        sum(item.size_bytes for item in inventory.files),
    )


class CheckpointRepository:
    """Immutable local/S3 checkpoint prefixes with small metadata-only resume probes."""

    def __init__(
        self,
        base_uri: str,
        *,
        work_root: Path,
        endpoint_url: str | None,
        limits: TransferLimits,
    ) -> None:
        parsed = urlsplit(base_uri.rstrip("/"))
        if parsed.scheme not in {"file", "s3"}:
            raise ValueError("checkpoint repository requires file:// or s3://")
        self.base_uri = base_uri.rstrip("/")
        self.work_root = work_root.resolve()
        self.endpoint_url = endpoint_url
        self.limits = limits
        if parsed.scheme == "s3" and not endpoint_url:
            raise ValueError("S3 checkpoint repository requires an endpoint URL")

    def load(self, shard_id: str, model: type[RecordT]) -> tuple[RecordT, CheckpointReference] | None:
        uri = self._uri(shard_id)
        parsed = urlsplit(uri)
        remote_inventory: ChecksumInventory | None = None
        if parsed.scheme == "file":
            root = Path(parsed.path).resolve()
            if not root.exists():
                return None
            verify_complete_result(root, limits=self.limits)
            payload = (root / "checkpoint.json").read_bytes()
        else:
            inspected = inspect_verified_s3_release_member(
                uri,
                "checkpoint.json",
                endpoint_url=self.endpoint_url or "",
                limits=self.limits,
            )
            if inspected is None:
                return None
            payload = inspected.payload
            remote_inventory = inspected.inventory
        record = model.model_validate_json(payload)
        if parsed.scheme == "file":
            observed = inventory_evidence(root, exclude_checkpoint=True)
            expected = (
                record.payload_inventory_sha256,
                record.payload_file_count,
                record.payload_size_bytes,
            )
            if observed != expected:
                raise ValueError("checkpoint payload does not match checkpoint.json")
        else:
            if remote_inventory is None:
                raise AssertionError("remote checkpoint inspection omitted its inventory")
            observed = inventory_model_evidence(
                remote_inventory,
                exclude_checkpoint=True,
            )
            expected = (
                record.payload_inventory_sha256,
                record.payload_file_count,
                record.payload_size_bytes,
            )
            if observed != expected:
                raise ValueError("remote checkpoint payload does not match checkpoint.json")
        return record, self._reference(uri, record, payload)

    def restore_normalized(
        self,
        destination: Path,
        *,
        expected_binding_sha256: str,
    ) -> tuple[NormalizedCheckpoint, CheckpointReference] | None:
        loaded = self.load("normalized", NormalizedCheckpoint)
        if loaded is None:
            return None
        record, reference = loaded
        if record.binding_sha256 != expected_binding_sha256:
            raise ValueError("normalized checkpoint binding does not match the exact request")
        uri = self._uri("normalized")
        parsed = urlsplit(uri)
        with tempfile.TemporaryDirectory(prefix="normalized-checkpoint-", dir=self.work_root) as value:
            downloaded = Path(value) / "release"
            if parsed.scheme == "file":
                source = Path(parsed.path).resolve()
                shutil.copytree(source, downloaded)
                verify_complete_result(downloaded, limits=self.limits)
            else:
                download_s3_release(
                    uri,
                    downloaded,
                    endpoint_url=self.endpoint_url or "",
                    limits=self.limits,
                )
            observed = inventory_evidence(downloaded, exclude_checkpoint=True)
            expected = (
                record.payload_inventory_sha256,
                record.payload_file_count,
                record.payload_size_bytes,
            )
            if observed != expected:
                raise ValueError("normalized checkpoint payload does not match checkpoint.json")
            source_data = downloaded / "normalized"
            if not source_data.is_dir():
                raise ValueError("normalized checkpoint omits its normalized dataset directory")
            shutil.copytree(source_data, destination)
        return record, reference

    def publish(
        self,
        shard_id: str,
        staging: Path,
        record: CheckpointRecord,
    ) -> CheckpointReference:
        _validate_shard_id(shard_id)
        observed_hash, observed_files, observed_bytes = inventory_evidence(staging)
        if (
            record.payload_inventory_sha256 != observed_hash
            or record.payload_file_count != observed_files
            or record.payload_size_bytes != observed_bytes
        ):
            raise ValueError("checkpoint record does not match its staged payload inventory")
        checkpoint_path = staging / "checkpoint.json"
        checkpoint_path.write_bytes(record.canonical_bytes())
        uri = self._uri(shard_id)
        parsed = urlsplit(uri)
        if parsed.scheme == "file":
            published = publish_local_result(staging, uri, limits=self.limits)
            payload = (published / "checkpoint.json").read_bytes()
        else:
            local_release = Path(
                tempfile.mkdtemp(prefix="checkpoint-release-", dir=self.work_root)
            )
            local_release.rmdir()
            try:
                published = publish_local_result(
                    staging,
                    local_release.resolve().as_uri(),
                    limits=self.limits,
                )
                publish_s3_result(
                    published,
                    uri,
                    endpoint_url=self.endpoint_url or "",
                    limits=self.limits,
                )
                payload = (published / "checkpoint.json").read_bytes()
            finally:
                shutil.rmtree(local_release, ignore_errors=True)
        return self._reference(uri, record, payload)

    def _uri(self, shard_id: str) -> str:
        _validate_shard_id(shard_id)
        return f"{self.base_uri}/{shard_id}"

    @staticmethod
    def _reference(
        uri: str,
        record: CheckpointRecord,
        payload: bytes,
    ) -> CheckpointReference:
        return CheckpointReference(
            kind="normalized" if isinstance(record, NormalizedCheckpoint) else "comparison",
            uri=uri,
            checkpoint_sha256=hashlib.sha256(payload).hexdigest(),
            payload_inventory_sha256=record.payload_inventory_sha256,
            payload_file_count=record.payload_file_count,
            payload_size_bytes=record.payload_size_bytes,
        )


def _validate_shard_id(shard_id: str) -> None:
    path = PurePosixPath(shard_id)
    if (
        not shard_id
        or path.is_absolute()
        or "\\" in shard_id
        or any(part in {"", ".", ".."} for part in path.parts)
        or path.as_posix() != shard_id
    ):
        raise ValueError("checkpoint shard ID must be a normalized relative POSIX path")
