from __future__ import annotations

import hashlib
import json
import os
import resource
import shutil
import subprocess
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.ml.lightgbm.artifacts import sha256_file, write_canonical_json
from app.ml.lightgbm.cloud_contracts import (
    CloudArtifact,
    LightGbmCloudJobRequest,
    LightGbmCloudRun,
    Wave1ExecutionContext,
    Wave1ExperimentSpec,
    Wave1FinalAuthorization,
    Wave1ResourceEvidence,
)
from app.ml.lightgbm.cloud_fixture import build_wave1_fixture_dataset
from app.ml.lightgbm.contracts import (
    CalibrationManifest,
    DetectorPredictionsManifest,
    LightGbmTrainingRun,
    ModelBundleManifest,
)
from app.ml.lightgbm.data import GovernedFeatureDataset, load_governed_feature_dataset
from app.ml.lightgbm.release import build_model_bundle, verify_complete_lightgbm_v1_release
from app.ml.lightgbm.scoring import calibrate_validation_predictions, predict_governed_fold
from app.ml.lightgbm.training import train_binary_attack_model
from app.ml.lightgbm.tracking import log_development_run, log_governed_evaluation_run
from app.nebius.object_storage import (
    ChecksumInventory,
    InventoryEntry,
    publish_local_result,
    temporary_staging,
    verify_complete_result,
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class FrozenCandidate(_StrictModel):
    schema_version: str = "lightgbm_wave1_candidate_v1"
    campaign_id: str
    experiment: Wave1ExperimentSpec
    reproducibility_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    training_manifest: CloudArtifact
    calibration_manifest: CloudArtifact
    validation_metrics: CloudArtifact
    feature_importance: CloudArtifact
    feature_schema: CloudArtifact
    reliability_bins: CloudArtifact
    reliability_diagram: CloudArtifact
    test_fold_accessed: bool = False

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")


def execute_wave1_request(
    request_path: Path,
    *,
    input_root: Path,
    local_result_root: Path | None = None,
    execution_context: Wave1ExecutionContext | None = None,
    trusted_authorization_public_key_sha256: str | None = None,
) -> Path:
    request = LightGbmCloudJobRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    _validate_execution_context(request, execution_context)
    destination = _execution_destination(request, local_result_root)
    input_root = input_root.resolve()
    started_at = datetime.now(UTC)
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    staging = temporary_staging(destination.parent, request.run_id)
    try:
        (staging / "artifacts").mkdir()
        (staging / "request.json").write_bytes(request.canonical_bytes())
        input_inventory = _request_inventory(input_root, request)
        (staging / "input-inventory.json").write_text(input_inventory.model_dump_json(indent=2), encoding="utf-8")
        _write_environment(staging, request, execution_context)
        if request.mode == "preflight":
            processed_rows = 0
            candidate_hash = None
            reproducibility_hash = None
            mlflow_run_id = None
            metrics: dict[str, Any] = {"preflight_verified": True, "test_fold_accessed": False}
        elif request.mode == "development":
            (
                processed_rows,
                candidate_hash,
                reproducibility_hash,
                mlflow_run_id,
                metrics,
            ) = _run_development(staging, input_root, request, execution_context)
        elif request.mode == "final-evaluation":
            (
                processed_rows,
                candidate_hash,
                reproducibility_hash,
                mlflow_run_id,
                metrics,
            ) = _run_final(
                staging,
                input_root,
                request,
                execution_context,
                trusted_authorization_public_key_sha256,
            )
        else:
            raise ValueError("verify mode uses verify_wave1_result() and does not execute a new run")
        (staging / "metrics.json").write_text(
            json.dumps(metrics, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8"
        )
        _write_cloud_run(
            staging,
            request=request,
            started_at=started_at,
            wall_start=wall_start,
            cpu_start=cpu_start,
            processed_rows=processed_rows,
            candidate_hash=candidate_hash,
            reproducibility_hash=reproducibility_hash,
            mlflow_run_id=mlflow_run_id,
            execution_context=execution_context,
        )
        return publish_local_result(staging, destination.as_uri())
    except Exception as exc:
        _publish_failure(staging, destination, exc)
        raise


def verify_wave1_result(result_root: Path) -> LightGbmCloudRun:
    verify_complete_result(result_root)
    run = LightGbmCloudRun.model_validate_json((result_root / "cloud-run.json").read_text(encoding="utf-8"))
    request = LightGbmCloudJobRequest.model_validate_json((result_root / "request.json").read_text(encoding="utf-8"))
    if run.request_sha256 != request.canonical_hash() or run.run_id != request.run_id:
        raise ValueError("cloud run is not bound to its request")
    if request.mode == "development":
        candidate_path = result_root / "candidate.json"
        candidate = FrozenCandidate.model_validate_json(candidate_path.read_text(encoding="utf-8"))
        if run.candidate_hash != sha256_file(candidate_path):
            raise ValueError("cloud run candidate hash does not match candidate.json")
        if run.reproducibility_hash != candidate.reproducibility_hash:
            raise ValueError("cloud run reproducibility hash does not match candidate.json")
        if candidate.experiment.canonical_hash() != request.experiment.canonical_hash():
            raise ValueError("cloud run candidate experiment does not match its request")
    if request.mode == "final-evaluation":
        artifacts = result_root / "artifacts"
        training = _load(LightGbmTrainingRun, artifacts / "training" / "training-run.json")
        calibration = _load(CalibrationManifest, artifacts / "calibration" / "calibration-manifest.json")
        predictions = _load(DetectorPredictionsManifest, artifacts / "prediction" / "prediction-manifest.json")
        bundle = _load(ModelBundleManifest, artifacts / "bundle" / "model-bundle.json")
        verify_complete_lightgbm_v1_release(
            artifacts,
            training=training,
            calibration=calibration,
            predictions=predictions,
            bundle=bundle,
        )
    return run


def _run_development(
    staging: Path,
    input_root: Path,
    request: LightGbmCloudJobRequest,
    execution_context: Wave1ExecutionContext | None,
) -> tuple[int, str, str, str | None, dict[str, Any]]:
    artifact_root = staging / "artifacts"
    dataset = _load_dataset(request, input_root=input_root, artifact_root=artifact_root, access_mode="development")
    dataset = _apply_experiment(dataset, request.experiment)
    training = train_binary_attack_model(
        dataset,
        artifact_root=artifact_root,
        output_dir=artifact_root / "training",
        created_at=request.created_at,
        git_commit=request.git_commit,
        training_seed=request.random_seed,
        hyperparameters=request.experiment.hyperparameters,
        early_stopping_rounds=request.experiment.early_stopping_rounds,
    )
    calibration = calibrate_validation_predictions(
        dataset,
        training=training.training_manifest,
        artifact_root=artifact_root,
        output_dir=artifact_root / "calibration",
        created_at=request.created_at,
        method=request.experiment.calibration_method,
        precision_floor=request.experiment.precision_floor,
        recall_floor=request.experiment.recall_floor,
    )
    reproducibility_hash = _reproducibility_hash(
        request.experiment,
        training.training_manifest,
        calibration.manifest,
        calibration.feature_importance_path,
        calibration.feature_schema_path,
        calibration.reliability_bins_path,
        calibration.reliability_diagram_path,
    )
    candidate = FrozenCandidate(
        campaign_id=request.campaign_id,
        experiment=request.experiment,
        reproducibility_hash=reproducibility_hash,
        training_manifest=_cloud_artifact(training.training_manifest_path, artifact_root, "training_manifest"),
        calibration_manifest=_cloud_artifact(calibration.manifest_path, artifact_root, "calibration_manifest"),
        validation_metrics=_cloud_artifact(calibration.validation_metrics_path, artifact_root, "validation_metrics"),
        feature_importance=_cloud_artifact(calibration.feature_importance_path, artifact_root, "feature_importance"),
        feature_schema=_cloud_artifact(calibration.feature_schema_path, artifact_root, "feature_schema"),
        reliability_bins=_cloud_artifact(calibration.reliability_bins_path, artifact_root, "reliability_bins"),
        reliability_diagram=_cloud_artifact(
            calibration.reliability_diagram_path, artifact_root, "reliability_diagram"
        ),
    )
    candidate_path = staging / "candidate.json"
    candidate_path.write_bytes(candidate.canonical_bytes())
    candidate_hash = sha256_file(candidate_path)
    mlflow_run_id = None
    if request.mlflow_tracking_uri is not None:
        mlflow_run_id = log_development_run(
            artifact_root=artifact_root,
            training=training.training_manifest,
            calibration=calibration.manifest,
            training_manifest_path=training.training_manifest_path,
            calibration_manifest_path=calibration.manifest_path,
            validation_metrics_path=calibration.validation_metrics_path,
            feature_importance_path=calibration.feature_importance_path,
            reliability_bins_path=calibration.reliability_bins_path,
            reliability_diagram_path=calibration.reliability_diagram_path,
            model_path=training.model_path,
            tracking_uri=request.mlflow_tracking_uri,
            cloud_metadata=_cloud_metadata(execution_context),
        )
    rows = sum(fold.row_count for fold in dataset.folds)
    metrics = {
        "best_iteration": training.training_manifest.early_stopping.best_iteration,
        "validation_binary_logloss": training.training_manifest.early_stopping.best_score,
        "candidate_hash": candidate_hash,
        "reproducibility_hash": reproducibility_hash,
        "test_fold_accessed": False,
    }
    return rows, candidate_hash, reproducibility_hash, mlflow_run_id, metrics


def _run_final(
    staging: Path,
    input_root: Path,
    request: LightGbmCloudJobRequest,
    execution_context: Wave1ExecutionContext | None,
    trusted_authorization_public_key_sha256: str | None,
) -> tuple[int, str, str, str | None, dict[str, Any]]:
    candidate_ref = _required(request.candidate, "candidate")
    authorization_ref = _required(request.authorization, "authorization")
    signature_ref = _required(request.authorization_signature, "authorization signature")
    public_key_ref = _required(request.authorization_public_key, "authorization public key")
    candidate_path = _verify_cloud_artifact(input_root, candidate_ref)
    authorization_path = _verify_cloud_artifact(input_root, authorization_ref)
    signature_path = _verify_cloud_artifact(input_root, signature_ref)
    public_key_path = _verify_cloud_artifact(input_root, public_key_ref)
    candidate = FrozenCandidate.model_validate_json(candidate_path.read_text(encoding="utf-8"))
    authorization = Wave1FinalAuthorization.model_validate_json(authorization_path.read_text(encoding="utf-8"))
    if candidate.campaign_id != request.campaign_id or authorization.campaign_id != request.campaign_id:
        raise ValueError("candidate/authorization campaign binding mismatch")
    if authorization.candidate_hash != candidate_ref.sha256:
        raise ValueError("authorization does not approve the exact candidate hash")
    _verify_signature(
        authorization_path,
        signature_path,
        public_key_path,
        trusted_public_key_sha256=trusted_authorization_public_key_sha256,
    )
    if candidate.experiment.canonical_hash() != request.experiment.canonical_hash():
        raise ValueError("final request experiment does not match the frozen candidate")

    candidate_root = candidate_path.parent
    source_artifacts = candidate_root / "artifacts"
    if not source_artifacts.is_dir():
        raise ValueError("candidate artifact package is missing")
    for reference in (
        candidate.training_manifest,
        candidate.calibration_manifest,
        candidate.validation_metrics,
        candidate.feature_importance,
        candidate.feature_schema,
        candidate.reliability_bins,
        candidate.reliability_diagram,
    ):
        _verify_cloud_artifact(source_artifacts, reference)
    artifact_root = staging / "artifacts"
    shutil.rmtree(artifact_root)
    shutil.copytree(source_artifacts, artifact_root)
    training = _load(LightGbmTrainingRun, artifact_root / candidate.training_manifest.uri)
    calibration = _load(CalibrationManifest, artifact_root / candidate.calibration_manifest.uri)
    dataset = _load_dataset(request, input_root=input_root, artifact_root=artifact_root, access_mode="final_test")
    dataset = _apply_experiment(dataset, candidate.experiment)
    prediction = predict_governed_fold(
        dataset,
        training=training,
        calibration=calibration,
        artifact_root=artifact_root,
        output_dir=artifact_root / "prediction",
        created_at=request.created_at,
        operating_mode=candidate.experiment.operating_mode,
    )
    bundle = build_model_bundle(
        artifact_root,
        output_dir=artifact_root / "bundle",
        training=training,
        calibration=calibration,
        predictions=prediction.manifest,
        training_manifest_path=artifact_root / candidate.training_manifest.uri,
        calibration_manifest_path=artifact_root / candidate.calibration_manifest.uri,
        prediction_manifest_path=prediction.manifest_path,
        feature_schema_path=artifact_root / candidate.feature_schema.uri,
        validation_metrics_path=artifact_root / candidate.validation_metrics.uri,
        feature_importance_path=artifact_root / candidate.feature_importance.uri,
        contributions_path=prediction.contributions_path,
        reliability_bins_path=artifact_root / candidate.reliability_bins.uri,
        reliability_diagram_path=artifact_root / candidate.reliability_diagram.uri,
        created_at=request.created_at,
    )
    verify_complete_lightgbm_v1_release(
        artifact_root,
        training=training,
        calibration=calibration,
        predictions=prediction.manifest,
        bundle=bundle.bundle,
    )
    mlflow_run_id = None
    if request.mlflow_tracking_uri is not None:
        mlflow_run_id = log_governed_evaluation_run(
            artifact_root=artifact_root,
            training=training,
            calibration=calibration,
            predictions=prediction.manifest,
            bundle=bundle.bundle,
            bundle_path=bundle.bundle_path,
            checksum_path=bundle.checksum_path,
            prediction_manifest_path=prediction.manifest_path,
            tracking_uri=request.mlflow_tracking_uri,
            cloud_metadata=_cloud_metadata(execution_context),
        )
    return dataset.fold("test").row_count, candidate_ref.sha256, candidate.reproducibility_hash, mlflow_run_id, {
        "candidate_hash": candidate_ref.sha256,
        "reproducibility_hash": candidate.reproducibility_hash,
        "test_fold_accessed": True,
        "test_row_count": prediction.manifest.row_count,
        "test_alert_count": prediction.manifest.alert_count,
        "threshold": prediction.manifest.threshold,
        "release_verified": True,
    }


def _request_inventory(input_root: Path, request: LightGbmCloudJobRequest) -> ChecksumInventory:
    references = [
        item
        for item in (
            request.candidate,
            request.authorization,
            request.authorization_signature,
            request.authorization_public_key,
        )
        if item is not None
    ]
    if request.input.kind == "governed-feature-release":
        references.extend(
            (
                request.input.protocol,
                request.input.corpus,
                request.input.corpus_validation,
                request.input.split,
                request.input.feature_config,
                request.input.feature_release,
            )
        )
    for reference in references:
        _verify_cloud_artifact(input_root, reference)
    return ChecksumInventory(
        files=tuple(
            InventoryEntry(path=item.uri, sha256=item.sha256, size_bytes=item.size_bytes)
            for item in references
        )
    )


def _validate_execution_context(
    request: LightGbmCloudJobRequest,
    execution_context: Wave1ExecutionContext | None,
) -> None:
    if request.result_uri.startswith("s3://") and execution_context is None:
        raise ValueError("cloud execution requires an independently supplied Job context")
    if execution_context is None:
        return
    expected = (
        request.project_id,
        request.image,
        request.resource.platform,
        request.resource.preset,
        request.resource.disk_size_gib,
        request.resource.timeout_seconds,
    )
    actual = (
        execution_context.project_id,
        execution_context.image,
        execution_context.platform,
        execution_context.preset,
        execution_context.disk_size_gib,
        execution_context.timeout_seconds,
    )
    if actual != expected:
        raise ValueError("actual Nebius Job context does not match the governed request")


def _apply_experiment(
    dataset: GovernedFeatureDataset,
    experiment: Wave1ExperimentSpec,
) -> GovernedFeatureDataset:
    available = dataset.ordered_feature_columns
    unknown = set(experiment.excluded_features) - set(available)
    if unknown:
        raise ValueError(f"experiment excludes unknown features: {', '.join(sorted(unknown))}")
    selected = tuple(name for name in available if name not in set(experiment.excluded_features))
    if not selected:
        raise ValueError("experiment must retain at least one governed feature")
    return replace(dataset, ordered_feature_columns=selected)


def _reproducibility_hash(
    experiment: Wave1ExperimentSpec,
    training: LightGbmTrainingRun,
    calibration: CalibrationManifest,
    feature_importance_path: Path,
    feature_schema_path: Path,
    reliability_bins_path: Path,
    reliability_diagram_path: Path,
) -> str:
    training_payload = training.model_dump(mode="json")
    calibration_payload = calibration.model_dump(mode="json")
    training_payload.pop("created_at", None)
    calibration_payload.pop("created_at", None)
    payload = {
        "schema_version": "lightgbm_wave1_reproducibility_v1",
        "experiment": experiment.model_dump(mode="json"),
        "training": training_payload,
        "calibration": calibration_payload,
        "derived_artifacts": {
            "feature_importance": sha256_file(feature_importance_path),
            "feature_schema": sha256_file(feature_schema_path),
            "reliability_bins": sha256_file(reliability_bins_path),
            "reliability_diagram": sha256_file(reliability_diagram_path),
        },
    }
    return hashlib.sha256(
        json.dumps(payload, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _cloud_metadata(
    execution_context: Wave1ExecutionContext | None,
) -> dict[str, str | int | float] | None:
    if execution_context is None:
        return None
    values: dict[str, str | int | float] = {
        "cloud_provider": "nebius",
        "cloud_region": "eu-north1",
        "cloud_platform": execution_context.platform,
        "cloud_preset": execution_context.preset,
        "image_digest": execution_context.image,
    }
    if execution_context.nebius_job_id is not None:
        values["cloud_job_id"] = execution_context.nebius_job_id
    if execution_context.estimated_cost_usd is not None:
        values["cloud_estimated_cost_usd"] = execution_context.estimated_cost_usd
    return values


def _load_dataset(
    request: LightGbmCloudJobRequest,
    *,
    input_root: Path,
    artifact_root: Path,
    access_mode: str,
):
    if request.input.kind == "approved-research-fixture":
        return build_wave1_fixture_dataset(artifact_root, access_mode=access_mode)
    governed = request.input
    feature_source = (input_root / governed.feature_artifact_root).resolve()
    corpus_source = (input_root / governed.corpus_artifact_root).resolve()
    for source in (feature_source, corpus_source):
        if input_root not in source.parents or not source.is_dir():
            raise ValueError("governed artifact root is missing or outside the staged input root")
        shutil.copytree(source, artifact_root, dirs_exist_ok=True)
    return load_governed_feature_dataset(
        protocol_path=_verify_cloud_artifact(input_root, governed.protocol),
        corpus_manifest_path=_verify_cloud_artifact(input_root, governed.corpus),
        corpus_validation_path=_verify_cloud_artifact(input_root, governed.corpus_validation),
        split_manifest_path=_verify_cloud_artifact(input_root, governed.split),
        feature_config_path=_verify_cloud_artifact(input_root, governed.feature_config),
        feature_release_manifest_path=_verify_cloud_artifact(input_root, governed.feature_release),
        expected_feature_release_sha256=governed.feature_release.sha256,
        feature_artifact_root=artifact_root,
        corpus_artifact_root=artifact_root,
        access_mode=access_mode,
    )


def _write_environment(
    staging: Path,
    request: LightGbmCloudJobRequest,
    execution_context: Wave1ExecutionContext | None,
) -> None:
    payload = {
        "schema_version": "lightgbm_wave1_environment_v1",
        "project_id": request.project_id,
        "region": request.region,
        "image": request.image,
        "platform": request.resource.platform,
        "preset": request.resource.preset,
        "cpu_count": request.resource.cpu_count,
        "memory_gib": request.resource.memory_gib,
        "disk_size_gib": request.resource.disk_size_gib,
        "gpu_count": request.resource.gpu_count,
        "python": os.sys.version.split()[0],
    }
    if execution_context is not None:
        payload["execution_context"] = execution_context.model_dump(mode="json")
    (staging / "environment.json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _write_cloud_run(
    staging: Path,
    *,
    request: LightGbmCloudJobRequest,
    started_at: datetime,
    wall_start: float,
    cpu_start: float,
    processed_rows: int,
    candidate_hash: str | None,
    reproducibility_hash: str | None,
    mlflow_run_id: str | None,
    execution_context: Wave1ExecutionContext | None,
) -> None:
    wall_seconds = max(time.perf_counter() - wall_start, 1e-9)
    usage = resource.getrusage(resource.RUSAGE_SELF)
    peak_rss = int(usage.ru_maxrss * (1024 if os.sys.platform != "darwin" else 1))
    outputs = tuple(
        _cloud_artifact(path, staging, path.relative_to(staging).as_posix().replace("/", "_"))
        for path in sorted(item for item in staging.rglob("*") if item.is_file())
        if path.name != "cloud-run.json"
    )
    run = LightGbmCloudRun(
        campaign_id=request.campaign_id,
        run_id=request.run_id,
        mode=request.mode,
        status="succeeded",
        request_sha256=request.canonical_hash(),
        image=request.image,
        started_at=started_at,
        completed_at=datetime.now(UTC),
        resource=Wave1ResourceEvidence(
            disk_size_gib=request.resource.disk_size_gib,
            wall_seconds=wall_seconds,
            cpu_seconds=max(time.process_time() - cpu_start, 0.0),
            peak_rss_bytes=peak_rss,
            processed_rows=processed_rows,
            rows_per_second=processed_rows / wall_seconds,
        ),
        outputs=outputs,
        candidate_hash=candidate_hash,
        reproducibility_hash=reproducibility_hash,
        mlflow_run_id=mlflow_run_id,
        nebius_job_id=execution_context.nebius_job_id if execution_context else None,
        estimated_cost_usd=execution_context.estimated_cost_usd if execution_context else None,
    )
    write_canonical_json(staging / "cloud-run.json", run)


def _cloud_artifact(path: Path, root: Path, logical_name: str) -> CloudArtifact:
    resolved = path.resolve()
    root = root.resolve()
    if root not in resolved.parents or not resolved.is_file():
        raise ValueError("cloud artifact is outside its root")
    safe_name = logical_name.replace("/", "_")[:128]
    return CloudArtifact(
        logical_name=safe_name,
        uri=resolved.relative_to(root).as_posix(),
        sha256=sha256_file(resolved),
        size_bytes=resolved.stat().st_size,
    )


def _verify_cloud_artifact(root: Path, artifact: CloudArtifact) -> Path:
    path = (root.resolve() / artifact.uri).resolve()
    if root.resolve() not in path.parents or not path.is_file():
        raise ValueError(f"cloud artifact is missing or outside input root: {artifact.logical_name}")
    if path.stat().st_size != artifact.size_bytes or sha256_file(path) != artifact.sha256:
        raise ValueError(f"cloud artifact integrity failed: {artifact.logical_name}")
    return path


def _verify_signature(
    document: Path,
    signature: Path,
    public_key: Path,
    *,
    trusted_public_key_sha256: str | None,
) -> None:
    if trusted_public_key_sha256 is None:
        raise ValueError("final authorization requires an out-of-band trusted public-key hash")
    if sha256_file(public_key) != trusted_public_key_sha256:
        raise ValueError("final authorization public key does not match the trusted hash")
    completed = subprocess.run(
        [
            "openssl",
            "pkeyutl",
            "-verify",
            "-pubin",
            "-inkey",
            str(public_key),
            "-sigfile",
            str(signature),
            "-rawin",
            "-in",
            str(document),
        ],
        check=False,
        text=True,
        capture_output=True,
    )
    if completed.returncode:
        raise ValueError("final authorization signature verification failed")


def _execution_destination(
    request: LightGbmCloudJobRequest,
    local_result_root: Path | None,
) -> Path:
    if request.result_uri.startswith("file://"):
        if local_result_root is not None:
            raise ValueError("local result override is only valid for an s3:// result URI")
        return Path(request.result_uri.removeprefix("file://")).resolve()
    if local_result_root is None:
        raise ValueError("s3:// execution requires an explicit ephemeral local result root")
    destination = local_result_root.resolve()
    if str(destination) in {"/", str(Path.home().resolve())}:
        raise ValueError("ephemeral local result root is too broad")
    return destination


def _publish_failure(staging: Path, destination: Path, exc: Exception) -> None:
    if not staging.exists():
        return
    failure = {"schema_version": "lightgbm_wave1_failure_v1", "error_type": type(exc).__name__}
    (staging / "failure.json").write_text(json.dumps(failure, sort_keys=True) + "\n", encoding="utf-8")
    (staging / "FAILED").write_text("failed\n", encoding="utf-8")
    if not destination.exists():
        destination.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, destination)


def _required(value: CloudArtifact | None, label: str) -> CloudArtifact:
    if value is None:
        raise ValueError(f"{label} is required")
    return value


def _load(model: type[BaseModel], path: Path):
    return model.model_validate_json(path.read_text(encoding="utf-8"))
