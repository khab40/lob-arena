from __future__ import annotations

import hashlib
from pathlib import Path

from app.ml.lightgbm.contracts import (
    ArtifactDigest,
    CalibrationManifest,
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
    ModelBundleManifest,
    validate_phase_zero_compatibility,
)


def verify_phase_zero_release(
    artifact_root: Path,
    *,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    bundle: ModelBundleManifest,
    predictions: DetectorPredictionsManifest,
) -> None:
    validate_phase_zero_compatibility(
        training=training,
        calibration=calibration,
        bundle=bundle,
        predictions=predictions,
    )
    references = (
        training.model_artifact,
        *(item.artifact for item in training.input_features),
        *((training.preprocessing.transformer,) if training.preprocessing.transformer is not None else ()),
        calibration.input_predictions,
        *(item.artifact for item in predictions.input_features),
        predictions.predictions,
        *bundle.artifacts,
    )
    for reference in references:
        _verify_artifact(artifact_root, reference)

    artifacts = bundle.artifact_map()
    _require_exact_manifest(artifact_root, artifacts["training_manifest"], training.canonical_bytes())
    _require_exact_manifest(artifact_root, artifacts["calibration_manifest"], calibration.canonical_bytes())
    _require_exact_manifest(artifact_root, artifacts["prediction_manifest"], predictions.canonical_bytes())
    _verify_checksum_inventory(artifact_root, bundle)


def _verify_artifact(root: Path, reference: ArtifactDigest) -> None:
    path = _resolve_artifact(root, reference)
    if not path.is_file() or path.stat().st_size != reference.size_bytes or _sha256(path) != reference.sha256:
        raise ValueError(f"LightGBM release artifact failed integrity validation: {reference.logical_name}")


def _require_exact_manifest(root: Path, reference: ArtifactDigest, expected: bytes) -> None:
    path = _resolve_artifact(root, reference)
    if path.read_bytes() != expected:
        raise ValueError(f"LightGBM release {reference.logical_name} is not exact canonical manifest content")


def _verify_checksum_inventory(root: Path, bundle: ModelBundleManifest) -> None:
    checksum_reference = bundle.artifact_map()["checksums"]
    lines = _resolve_artifact(root, checksum_reference).read_text(encoding="utf-8").splitlines()
    observed: dict[str, str] = {}
    for line in lines:
        digest, separator, uri = line.partition("  ")
        if (
            separator != "  "
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not uri
            or uri in observed
        ):
            raise ValueError("LightGBM release checksum inventory is invalid")
        observed[uri] = digest
    expected = {artifact.uri: artifact.sha256 for artifact in bundle.artifacts if artifact.logical_name != "checksums"}
    if observed != expected:
        raise ValueError("LightGBM release checksum inventory does not match the model bundle")


def _resolve_artifact(root: Path, reference: ArtifactDigest) -> Path:
    resolved_root = root.resolve()
    path = (resolved_root / reference.uri).resolve()
    if path == resolved_root or resolved_root not in path.parents:
        raise ValueError(f"LightGBM release artifact escapes its root: {reference.logical_name}")
    return path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
