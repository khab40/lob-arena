from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from app.ml.lightgbm.contracts import ArtifactDigest, FoldName, SHA256_PATTERN


FEATURE_RELEASE_SCHEMA_VERSION = "governed_feature_release_v1"
FEATURE_RUN_SCHEMA_VERSIONS = frozenset(
    {"feature_run_metadata_v1", "feature_stream_run_metadata_v1"}
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GovernedFeatureReleaseShard(_StrictModel):
    fold: FoldName
    base_session_id: str = Field(min_length=1)
    campaign_id: str | None = Field(default=None, min_length=1)
    run_id: str = Field(min_length=1)
    replay_manifest: ArtifactDigest
    run_metadata: ArtifactDigest
    features: ArtifactDigest
    quality: ArtifactDigest

    @model_validator(mode="after")
    def validate_artifacts(self) -> "GovernedFeatureReleaseShard":
        if self.replay_manifest.schema_version != "canonical_java_replay_bundle_v1":
            raise ValueError("feature release replay artifact has an incompatible schema")
        if self.run_metadata.schema_version not in FEATURE_RUN_SCHEMA_VERSIONS:
            raise ValueError("feature release run metadata schema is incompatible")
        if self.quality.schema_version != "feature_quality_report_v1":
            raise ValueError("feature release quality artifact has an incompatible schema")
        run_path = PurePosixPath(self.run_metadata.uri)
        feature_path = PurePosixPath(self.features.uri)
        quality_path = PurePosixPath(self.quality.uri)
        if (
            run_path.name != "run-metadata.json"
            or feature_path.name != "features.parquet"
            or quality_path.name != "feature-quality.json"
            or run_path.parent != feature_path.parent
            or run_path.parent != quality_path.parent
        ):
            raise ValueError(
                "feature release run artifacts must use canonical names in one directory"
            )
        return self


class GovernedFeatureReleaseManifest(_StrictModel):
    schema_version: Literal["governed_feature_release_v1"] = (
        FEATURE_RELEASE_SCHEMA_VERSION
    )
    release_id: str = Field(min_length=1)
    created_at: AwareDatetime
    protocol_id: str = Field(min_length=1)
    protocol_hash: str = Field(pattern=SHA256_PATTERN)
    corpus_id: str = Field(min_length=1)
    corpus_hash: str = Field(pattern=SHA256_PATTERN)
    split_id: str = Field(min_length=1)
    assignment_hash: str = Field(pattern=SHA256_PATTERN)
    feature_schema_version: str = Field(min_length=1)
    feature_config_hash: str = Field(pattern=SHA256_PATTERN)
    adjudications: ArtifactDigest
    shards: tuple[GovernedFeatureReleaseShard, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_inventory(self) -> "GovernedFeatureReleaseManifest":
        if (
            self.adjudications.schema_version
            != "clean_window_adjudications_jsonl_v1"
        ):
            raise ValueError("feature release adjudications schema is incompatible")
        if {shard.fold for shard in self.shards} != {
            "train",
            "validation",
            "test",
        }:
            raise ValueError("feature release must inventory every frozen fold")
        identities = [
            (shard.base_session_id, shard.campaign_id)
            for shard in self.shards
        ]
        run_ids = [shard.run_id for shard in self.shards]
        artifact_uris = [
            artifact.uri
            for shard in self.shards
            for artifact in (
                shard.replay_manifest,
                shard.run_metadata,
                shard.features,
                shard.quality,
            )
        ]
        if len(identities) != len(set(identities)):
            raise ValueError("feature release replay domains must be unique")
        if len(run_ids) != len(set(run_ids)):
            raise ValueError("feature release run IDs must be unique")
        if len(artifact_uris) != len(set(artifact_uris)):
            raise ValueError("feature release artifact paths must be unique")
        if self.adjudications.uri in artifact_uris:
            raise ValueError("feature release adjudications path must be unique")
        if any(
            shard.features.schema_version != self.feature_schema_version
            for shard in self.shards
        ):
            raise ValueError("feature release shard schema does not match the release")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def manifest_hash(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


def artifact_digest(
    path: Path,
    *,
    root: Path,
    logical_name: str,
    schema_version: str,
) -> ArtifactDigest:
    resolved_root = root.resolve()
    resolved = path.resolve()
    if (
        resolved == resolved_root
        or resolved_root not in resolved.parents
        or not resolved.is_file()
    ):
        raise ValueError(f"feature release artifact is missing or outside its root: {path}")
    return ArtifactDigest(
        logical_name=logical_name,
        uri=resolved.relative_to(resolved_root).as_posix(),
        sha256=_sha256(resolved),
        size_bytes=resolved.stat().st_size,
        schema_version=schema_version,
    )


def resolve_verified_artifact(
    artifact: ArtifactDigest,
    *,
    root: Path,
) -> Path:
    resolved_root = root.resolve()
    resolved = (resolved_root / artifact.uri).resolve()
    if (
        resolved == resolved_root
        or resolved_root not in resolved.parents
        or not resolved.is_file()
        or resolved.stat().st_size != artifact.size_bytes
        or _sha256(resolved) != artifact.sha256
    ):
        raise ValueError(
            f"feature release artifact failed verification: {artifact.logical_name}"
        )
    return resolved


def load_governed_feature_release(
    path: Path,
    *,
    expected_sha256: str,
) -> GovernedFeatureReleaseManifest:
    if (
        len(expected_sha256) != 64
        or any(character not in "0123456789abcdef" for character in expected_sha256)
    ):
        raise ValueError("expected feature release SHA-256 is invalid")
    if not path.is_file() or _sha256(path) != expected_sha256:
        raise ValueError("feature release manifest failed external SHA-256 verification")
    return GovernedFeatureReleaseManifest.model_validate(
        _load_json_object(path)
    )


def write_governed_feature_release(
    path: Path,
    manifest: GovernedFeatureReleaseManifest,
    *,
    overwrite: bool = False,
) -> str:
    if path.exists() and not overwrite:
        raise ValueError("feature release manifest already exists")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(
                manifest.model_dump(mode="json"),
                allow_nan=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return _sha256(path)


def _load_json_object(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
    except (OSError, json.JSONDecodeError) as exception:
        raise ValueError(f"failed to load feature release JSON: {path}") from exception
    if not isinstance(payload, dict):
        raise ValueError("feature release manifest must be a JSON object")
    return payload


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
