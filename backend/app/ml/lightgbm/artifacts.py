from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app.ml.lightgbm.contracts import ArtifactDigest


def artifact_digest_for_destination(
    source: Path,
    *,
    destination: Path,
    artifact_root: Path,
    logical_name: str,
    schema_version: str,
) -> ArtifactDigest:
    """Digest staged bytes while binding them to their final artifact-root URI."""

    resolved_root = artifact_root.resolve()
    resolved_destination = destination.resolve()
    if (
        resolved_destination == resolved_root
        or resolved_root not in resolved_destination.parents
        or not source.is_file()
    ):
        raise ValueError("LightGBM artifact destination is outside its artifact root")
    return ArtifactDigest(
        logical_name=logical_name,
        uri=resolved_destination.relative_to(resolved_root).as_posix(),
        sha256=sha256_file(source),
        size_bytes=source.stat().st_size,
        schema_version=schema_version,
    )


def artifact_digest_at_path(
    path: Path,
    *,
    artifact_root: Path,
    logical_name: str,
    schema_version: str,
) -> ArtifactDigest:
    return artifact_digest_for_destination(
        path,
        destination=path,
        artifact_root=artifact_root,
        logical_name=logical_name,
        schema_version=schema_version,
    )


def resolve_verified_artifact(reference: ArtifactDigest, *, artifact_root: Path) -> Path:
    resolved_root = artifact_root.resolve()
    path = (resolved_root / reference.uri).resolve()
    if (
        path == resolved_root
        or resolved_root not in path.parents
        or not path.is_file()
        or path.stat().st_size != reference.size_bytes
        or sha256_file(path) != reference.sha256
    ):
        raise ValueError(
            f"LightGBM artifact failed integrity verification: {reference.logical_name}"
        )
    return path


def require_output_within_artifact_root(output: Path, artifact_root: Path) -> None:
    root = artifact_root.resolve()
    resolved = output.resolve()
    if resolved == root or root not in resolved.parents:
        raise ValueError("LightGBM output must be a child of the shared artifact root")


def write_canonical_json(path: Path, payload: Any) -> None:
    if hasattr(payload, "canonical_bytes"):
        path.write_bytes(payload.canonical_bytes())
        return
    path.write_text(
        json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
