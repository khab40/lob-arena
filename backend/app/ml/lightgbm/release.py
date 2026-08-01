from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.ml.lightgbm.contracts import (
    ArtifactDigest,
    CalibrationManifest,
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
    ModelBundleManifest,
    validate_phase_zero_compatibility,
)
from app.ml.lightgbm.artifacts import artifact_digest_at_path
from app.ml.lightgbm.evidence import validate_release_evidence
from app.ml.lightgbm.scoring import (
    CONTRIBUTIONS_SCHEMA_VERSION,
    FEATURE_IMPORTANCE_SCHEMA_VERSION,
    RELIABILITY_BINS_SCHEMA_VERSION,
    RELIABILITY_DIAGRAM_SCHEMA_VERSION,
    VALIDATION_METRICS_SCHEMA_VERSION,
    validate_prediction_parquet,
)


MODEL_BUNDLE_FILE = "model-bundle.json"
CHECKSUM_FILE = "checksums.sha256"


@dataclass(frozen=True)
class ModelBundleResult:
    bundle_path: Path
    checksum_path: Path
    bundle: ModelBundleManifest
    bundle_artifact: ArtifactDigest
    checksum_artifact: ArtifactDigest


def build_model_bundle(
    artifact_root: Path,
    *,
    output_dir: Path,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    predictions: DetectorPredictionsManifest,
    training_manifest_path: Path,
    calibration_manifest_path: Path,
    prediction_manifest_path: Path,
    feature_schema_path: Path,
    validation_metrics_path: Path,
    feature_importance_path: Path,
    contributions_path: Path,
    created_at: datetime,
    reliability_bins_path: Path | None = None,
    reliability_diagram_path: Path | None = None,
) -> ModelBundleResult:
    """Assemble and immediately verify the complete governed LightGBM bundle."""

    artifact_root = artifact_root.resolve()
    output_dir = output_dir.resolve()
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        raise ValueError("model bundle created_at must be timezone-aware")
    if output_dir == artifact_root or artifact_root not in output_dir.parents:
        raise ValueError("model bundle output must be inside the shared artifact root")
    if output_dir.exists():
        raise ValueError("model bundle output directory already exists")
    for path in (
        training_manifest_path,
        calibration_manifest_path,
        prediction_manifest_path,
        feature_schema_path,
        validation_metrics_path,
        feature_importance_path,
        contributions_path,
    ):
        if not path.is_file() or artifact_root not in path.resolve().parents:
            raise ValueError("model bundle source artifact is missing or outside its root")
    validate_prediction_parquet(
        _resolve_artifact(artifact_root, calibration.input_predictions),
        expected_rows=calibration.row_count,
        expected_fold="validation",
        require_decisions=False,
    )
    validate_prediction_parquet(
        _resolve_artifact(artifact_root, predictions.predictions),
        manifest=predictions,
    )
    validate_release_evidence(
        training=training,
        calibration=calibration,
        predictions=predictions,
        feature_schema_path=feature_schema_path,
        validation_metrics_path=validation_metrics_path,
        feature_importance_path=feature_importance_path,
        contributions_path=contributions_path,
        predictions_path=_resolve_artifact(artifact_root, predictions.predictions),
    )
    artifacts = [
        training.model_artifact,
        artifact_digest_at_path(
            training_manifest_path,
            artifact_root=artifact_root,
            logical_name="training_manifest",
            schema_version=training.schema_version,
        ),
        artifact_digest_at_path(
            calibration_manifest_path,
            artifact_root=artifact_root,
            logical_name="calibration_manifest",
            schema_version=calibration.schema_version,
        ),
        artifact_digest_at_path(
            prediction_manifest_path,
            artifact_root=artifact_root,
            logical_name="prediction_manifest",
            schema_version=predictions.schema_version,
        ),
        predictions.predictions,
        calibration.input_predictions,
        artifact_digest_at_path(
            feature_schema_path,
            artifact_root=artifact_root,
            logical_name="feature_schema",
            schema_version=training.binding.feature_schema_version,
        ),
        artifact_digest_at_path(
            validation_metrics_path,
            artifact_root=artifact_root,
            logical_name="validation_metrics",
            schema_version=VALIDATION_METRICS_SCHEMA_VERSION,
        ),
        artifact_digest_at_path(
            feature_importance_path,
            artifact_root=artifact_root,
            logical_name="feature_importance",
            schema_version=FEATURE_IMPORTANCE_SCHEMA_VERSION,
        ),
        artifact_digest_at_path(
            contributions_path,
            artifact_root=artifact_root,
            logical_name="feature_contributions",
            schema_version=CONTRIBUTIONS_SCHEMA_VERSION,
        ),
    ]
    if training.preprocessing.transformer is not None:
        artifacts.append(training.preprocessing.transformer)
    if reliability_bins_path is not None:
        artifacts.append(
            artifact_digest_at_path(
                reliability_bins_path,
                artifact_root=artifact_root,
                logical_name="reliability_bins",
                schema_version=RELIABILITY_BINS_SCHEMA_VERSION,
            )
        )
    if reliability_diagram_path is not None:
        artifacts.append(
            artifact_digest_at_path(
                reliability_diagram_path,
                artifact_root=artifact_root,
                logical_name="reliability_diagram",
                schema_version=RELIABILITY_DIAGRAM_SCHEMA_VERSION,
            )
        )

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_dir.name}.", dir=output_dir.parent))
    try:
        checksum_path = staging / CHECKSUM_FILE
        checksum_path.write_text(
            "".join(
                f"{artifact.sha256}  {artifact.uri}\n"
                for artifact in sorted(artifacts, key=lambda item: item.uri)
            ),
            encoding="utf-8",
        )
        checksum_artifact = ArtifactDigest(
            logical_name="checksums",
            uri=(output_dir / CHECKSUM_FILE).relative_to(artifact_root).as_posix(),
            sha256=_sha256(checksum_path),
            size_bytes=checksum_path.stat().st_size,
            schema_version="sha256_inventory_v1",
        )
        bundle = ModelBundleManifest(
            binding=training.binding,
            calibration_id=calibration.calibration_id,
            created_at=created_at,
            artifacts=tuple([*artifacts, checksum_artifact]),
        )
        bundle_path = staging / MODEL_BUNDLE_FILE
        bundle_path.write_bytes(bundle.canonical_bytes())
        bundle_artifact = ArtifactDigest(
            logical_name="model_bundle",
            uri=(output_dir / MODEL_BUNDLE_FILE).relative_to(artifact_root).as_posix(),
            sha256=_sha256(bundle_path),
            size_bytes=bundle_path.stat().st_size,
            schema_version=bundle.schema_version,
        )
        os.replace(staging, output_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging)

    try:
        verify_complete_lightgbm_v1_release(
            artifact_root,
            training=training,
            calibration=calibration,
            bundle=bundle,
            predictions=predictions,
        )
    except Exception:
        shutil.rmtree(output_dir)
        raise
    return ModelBundleResult(
        bundle_path=output_dir / MODEL_BUNDLE_FILE,
        checksum_path=output_dir / CHECKSUM_FILE,
        bundle=bundle,
        bundle_artifact=bundle_artifact,
        checksum_artifact=checksum_artifact,
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


def verify_complete_lightgbm_v1_release(
    artifact_root: Path,
    *,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    bundle: ModelBundleManifest,
    predictions: DetectorPredictionsManifest,
) -> None:
    """Verify Phase 0 bytes plus all Complete LightGBM v1 evidence semantics."""

    verify_phase_zero_release(
        artifact_root,
        training=training,
        calibration=calibration,
        bundle=bundle,
        predictions=predictions,
    )
    artifacts = bundle.artifact_map()
    validation_predictions = _resolve_artifact(
        artifact_root,
        calibration.input_predictions,
    )
    prediction_rows = _resolve_artifact(artifact_root, predictions.predictions)
    validate_prediction_parquet(
        validation_predictions,
        expected_rows=calibration.row_count,
        expected_fold="validation",
        require_decisions=False,
    )
    validate_prediction_parquet(prediction_rows, manifest=predictions)
    validate_release_evidence(
        training=training,
        calibration=calibration,
        predictions=predictions,
        feature_schema_path=_resolve_artifact(artifact_root, artifacts["feature_schema"]),
        validation_metrics_path=_resolve_artifact(
            artifact_root,
            artifacts["validation_metrics"],
        ),
        feature_importance_path=_resolve_artifact(
            artifact_root,
            artifacts["feature_importance"],
        ),
        contributions_path=_resolve_artifact(
            artifact_root,
            artifacts["feature_contributions"],
        ),
        predictions_path=prediction_rows,
    )


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
