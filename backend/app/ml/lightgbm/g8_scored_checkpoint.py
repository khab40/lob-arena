"""Seal scored C4 evidence before logging; recover without model execution.

The checkpoint hash and original reservation ledger must be retained separately.
This is not a final-result SUCCESS marker, execution approval or native-mount proof.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.c4_evaluation import C4EvaluationInputs, C4EvaluationProfile
from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest, Wave1TabularProjectionInput
from app.ml.lightgbm.contracts import (
    CalibrationManifest, DetectorPredictionsManifest, LightGbmTrainingRun, ModelBundleManifest,
)
from app.ml.lightgbm.g8_mlflow_recovery import ReservationSpec, ResumeTarget, _locked
from app.ml.lightgbm.g8_publication_recovery import _directory_sync, _inventory
from app.nebius.object_storage import ChecksumInventory, InventoryEntry, TransferLimits

SHA = r"^[a-f0-9]{64}$"


class LoggingContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    bundle_path: str
    checksum_path: str
    prediction_manifest_path: str
    benchmark_results_path: str
    comparison_name: str
    dataset_source_uri: str
    cloud_metadata: dict[str, str | int | float] | None = None

    @field_validator("bundle_path", "checksum_path", "prediction_manifest_path", "benchmark_results_path",
                     "comparison_name")
    @classmethod
    def relative_path(cls, value):
        path = PurePosixPath(value)
        if (not path.parts or path.is_absolute() or ".." in path.parts or path.as_posix() != value
                or "\\" in value or "\x00" in value):
            raise ValueError("checkpoint paths must be canonical relative paths")
        return value


class ScoredCheckpoint(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal["g8_scored_checkpoint_v1"] = "g8_scored_checkpoint_v1"
    reservation: ReservationSpec
    mlflow_run_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    context: LoggingContext
    inventory: ChecksumInventory


def _canonical(value: BaseModel) -> bytes:
    return (json.dumps(value.model_dump(mode="json"), sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def _reservation_id(ledger: Path, target: ResumeTarget) -> str:
    if not ledger.is_dir() or ledger.resolve() != ledger.absolute():
        raise ValueError("reservation ledger must be an existing canonical directory")
    for name in ("spec.json", "create-intent.json", "run.json"):
        path = ledger / name
        if not path.is_file() or path.is_symlink():
            raise ValueError("an intact pre-scoring reservation ledger is required")
    spec = ReservationSpec.model_validate_json((ledger / "spec.json").read_bytes())
    intent = json.loads((ledger / "create-intent.json").read_bytes())
    record = json.loads((ledger / "run.json").read_bytes())
    if (spec != target.spec or intent != {"reservation_sha256": spec.identity()}
            or set(record) != {"reservation_sha256", "run_id"}
            or record["reservation_sha256"] != spec.identity()
            or not isinstance(record["run_id"], str) or not re.fullmatch(r"[a-f0-9]{32}", record["run_id"])):
        raise ValueError("scored checkpoint reservation ledger identity differs")
    return record["run_id"]


def _arguments(payload: Path, context: LoggingContext, target: ResumeTarget) -> dict:
    from app.ml.lightgbm.cloud_runner import FrozenCandidate

    metadata = payload / "metadata"
    artifacts = payload / "artifacts"
    candidate = FrozenCandidate.model_validate_json((metadata / "candidate.json").read_bytes())
    return dict(
        artifact_root=artifacts,
        training=LightGbmTrainingRun.model_validate_json((artifacts / candidate.training_manifest.uri).read_bytes()),
        calibration=CalibrationManifest.model_validate_json(
            (artifacts / candidate.calibration_manifest.uri).read_bytes()),
        predictions=DetectorPredictionsManifest.model_validate_json(
            (artifacts / context.prediction_manifest_path).read_bytes()),
        bundle=ModelBundleManifest.model_validate_json((artifacts / context.bundle_path).read_bytes()),
        bundle_path=artifacts / context.bundle_path,
        checksum_path=artifacts / context.checksum_path,
        prediction_manifest_path=artifacts / context.prediction_manifest_path,
        benchmark_results_path=artifacts / context.benchmark_results_path,
        c4_evaluation_inputs=C4EvaluationInputs(
            profile=metadata / "profile.json", frozen_root=metadata / "frozen-root.json",
            projection=metadata / "projection.json", candidate=metadata / "candidate.json",
            comparison=payload / "comparison" / context.comparison_name,
        ),
        tracking_uri=target.spec.tracking_uri,
        dataset_source_uri=context.dataset_source_uri,
        cloud_metadata=context.cloud_metadata,
    )


def _validate(payload: Path, context: LoggingContext, target: ResumeTarget) -> dict:
    from app.ml.dataset_lineage import feature_dataset_inputs
    from app.ml.lightgbm.release import verify_complete_lightgbm_v1_release
    from app.ml.lightgbm.tracking import _validated_cloud_metadata, _verified_benchmark_snapshot

    args = _arguments(payload, context, target)
    request = LightGbmCloudJobRequest.model_validate_json((payload / "metadata/request.json").read_bytes())
    inputs = args["c4_evaluation_inputs"]
    profile = C4EvaluationProfile.model_validate_json(inputs.profile.read_bytes())
    if (request.mode != "final-evaluation" or request.candidate is None
            or request.canonical_hash() != target.spec.request_sha256
            or request.run_id != target.spec.request_run_id
            or request.candidate.sha256 != target.spec.candidate_sha256
            or sha256_file(inputs.candidate) != target.spec.candidate_sha256
            or profile.canonical_hash() != target.spec.evaluation_profile_sha256
            or not isinstance(request.input, Wave1TabularProjectionInput)
            or request.input.frozen_root.sha256 != sha256_file(inputs.frozen_root)
            or request.input.projection.sha256 != sha256_file(inputs.projection)
            or (not target.spec.tracking_uri.startswith("file:")
                and request.mlflow_tracking_uri != target.spec.tracking_uri)):
        raise ValueError("scored evidence differs from the reserved request/candidate/C4 profile")
    verify_complete_lightgbm_v1_release(
        args["artifact_root"], training=args["training"], calibration=args["calibration"],
        predictions=args["predictions"], bundle=args["bundle"],
    )
    if (args["bundle_path"].read_bytes() != args["bundle"].canonical_bytes()
            or args["prediction_manifest_path"].read_bytes() != args["predictions"].canonical_bytes()
            or sha256_file(args["checksum_path"]) != args["bundle"].artifact_map()["checksums"].sha256):
        raise ValueError("scored checkpoint manifest bytes are not the verified release")
    _validated_cloud_metadata(context.cloud_metadata)
    feature_dataset_inputs(
        args["predictions"].input_features, source_root_uri=context.dataset_source_uri,
        feature_release_id=args["training"].feature_release_id,
        feature_release_sha256=args["training"].feature_release_sha256, expected_folds={"test"},
    )
    with _verified_benchmark_snapshot(
        args["benchmark_results_path"], artifact_root=args["artifact_root"],
        predictions=args["predictions"], c4_inputs=inputs,
    ):
        pass
    return args


def _copy_file(source: Path, target: Path, *, size_bytes: int):
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with source.open("rb") as original, target.open("xb") as output:
        os.chmod(target, 0o600)
        remaining = size_bytes
        while remaining:
            chunk = original.read(min(remaining, 1024**2))
            if not chunk:
                raise ValueError("checkpoint source truncated during copy")
            output.write(chunk)
            remaining -= len(chunk)
        if original.read(1):
            raise ValueError("checkpoint source grew beyond its inventoried size")
        output.flush()
        os.fsync(output.fileno())


def retain_scored_checkpoint(
    destination: Path, *, target: ResumeTarget, request_path: Path, workspace_root: Path,
    limits: TransferLimits = TransferLimits(), **logger_arguments,
) -> str:
    """Retain verified evidence before the first logging attempt; seal last.

    Destination is exclusive, outside the workspace. The reviewed caller must
    fsync/retain the returned SHA separately before allowing workspace disposal.
    A partial copy is left unsealed for diagnosis and cannot be reused.
    """
    inputs = logger_arguments.get("c4_evaluation_inputs")
    if not isinstance(inputs, C4EvaluationInputs) or inputs.source_result is not None:
        raise ValueError("pre-logging checkpoint requires original C4 inputs, not a completed source result")
    if logger_arguments.get("tracking_uri") != target.spec.tracking_uri:
        raise ValueError("checkpoint logger must use the reserved tracking URI")
    original_root = logger_arguments["artifact_root"]
    if original_root.resolve() != original_root.absolute():
        raise ValueError("checkpoint artifact source must be a canonical directory")
    source = original_root.resolve()
    if workspace_root.resolve() != workspace_root.absolute() or not source.is_relative_to(workspace_root):
        raise ValueError("explicit canonical workspace root must contain the scored artifacts")
    comparison = inputs.comparison.parent.resolve()
    if not logger_arguments.get("dataset_source_uri"):
        raise ValueError("checkpoint requires the original explicit dataset source URI")
    context = LoggingContext(
        **{name: logger_arguments[name].relative_to(source).as_posix() for name in
           ("bundle_path", "checksum_path", "prediction_manifest_path", "benchmark_results_path")},
        comparison_name=inputs.comparison.name,
        dataset_source_uri=logger_arguments["dataset_source_uri"],
        cloud_metadata=logger_arguments.get("cloud_metadata"),
    )
    if not destination.parent.is_dir() or destination.parent.absolute() != destination.parent.resolve():
        raise ValueError("checkpoint parent must be an existing canonical directory")
    roots = (workspace_root, comparison, target.ledger_root.resolve())
    if any(destination.resolve().is_relative_to(root) or root.is_relative_to(destination.resolve()) for root in roots):
        raise ValueError("checkpoint destination must be disjoint from workspace and reservation ledger")
    members = {}
    for entry in _inventory(source, limits).files:
        members["artifacts/" + entry.path] = (source / entry.path, entry.sha256, entry.size_bytes)
    # Copy only the comparison manifest, its preparation and the 27 declared
    # checkpoint trees, never unrelated contents of the manifest's parent.
    from app.ml.lightgbm.c4_replay_evidence import C4ComparisonPackage

    package = C4ComparisonPackage.model_validate_json(inputs.comparison.read_bytes())
    for relative in (inputs.comparison.name, package.preparation.uri):
        path = comparison / relative
        if path.is_symlink() or not path.is_file() or path.resolve() != path.absolute():
            raise ValueError("comparison metadata must be canonical regular files")
        members["comparison/" + relative] = (path, sha256_file(path), path.stat().st_size)
    for location in package.checkpoints:
        root = comparison / location.relative_root
        if root.resolve() != root.absolute():
            raise ValueError("comparison checkpoint paths must not traverse symlinks")
        for entry in _inventory(root, limits).files:
            name = "comparison/" + location.relative_root + "/" + entry.path
            if name in members:
                raise ValueError("overlapping comparison checkpoint paths")
            members[name] = (root / entry.path, entry.sha256, entry.size_bytes)
    for name, path in {
        "request.json": request_path, "candidate.json": inputs.candidate, "profile.json": inputs.profile,
        "frozen-root.json": inputs.frozen_root, "projection.json": inputs.projection,
    }.items():
        if path.is_symlink() or not path.is_file() or path.resolve() != path.absolute():
            raise ValueError("checkpoint metadata must be regular files")
        members["metadata/" + name] = (path, sha256_file(path), path.stat().st_size)
    inventory = ChecksumInventory(files=tuple(
        InventoryEntry(path=name, sha256=digest, size_bytes=size)
        for name, (_, digest, size) in sorted(members.items())
    ))
    if len(members) > limits.max_files or sum(e.size_bytes for e in inventory.files) > limits.max_bytes:
        raise ValueError("scored checkpoint exceeds approved limits")
    with _locked(target) as ledger:
        run_id = _reservation_id(ledger, target)
        if (ledger / "logging-plan.json").exists() or (ledger / "logging-complete.json").exists():
            raise ValueError("scored checkpoint must precede the first MLflow logging attempt")
        destination.mkdir(mode=0o700, exist_ok=False)
        _directory_sync(destination.parent)
        payload = destination / "payload"
        payload.mkdir(mode=0o700)
        for name, (path, _, size) in sorted(members.items()):
            _copy_file(path, payload / name, size_bytes=size)
        if _inventory(payload, limits) != inventory:
            raise ValueError("scored checkpoint copy changed during retention")
        args = _validate(payload, context, target)
        for name in ("training", "calibration", "predictions", "bundle"):
            if args[name] != logger_arguments[name]:
                raise ValueError("checkpoint differs from the scoring caller's manifests")
        for directory in sorted((p for p in payload.rglob("*") if p.is_dir()),
                                key=lambda p: len(p.parts), reverse=True):
            _directory_sync(directory)
        _directory_sync(payload)
        checkpoint = ScoredCheckpoint(
            reservation=target.spec, mlflow_run_id=run_id, context=context, inventory=inventory,
        )
        raw = _canonical(checkpoint)
        with (destination / ".checkpoint.pending").open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.rename(destination / ".checkpoint.pending", destination / "checkpoint.json")
        _directory_sync(destination)
        return hashlib.sha256(raw).hexdigest()


def verify_scored_checkpoint(
    root: Path, *, expected_sha256: str, target: ResumeTarget,
    limits: TransferLimits = TransferLimits(),
) -> ScoredCheckpoint:
    """Local-only verification. A digest read from this checkpoint is not authority."""
    if not re.fullmatch(SHA, expected_sha256):
        raise ValueError("independently retained checkpoint SHA-256 is required")
    if root.resolve() != root.absolute() or {p.name for p in root.iterdir()} != {"checkpoint.json", "payload"}:
        raise ValueError("scored checkpoint is unsealed or has unexpected members")
    marker = root / "checkpoint.json"
    if not marker.is_file() or marker.is_symlink() or marker.stat().st_size > 8 * 1024**2:
        raise ValueError("invalid scored checkpoint marker")
    raw = marker.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("scored checkpoint differs from independently retained hash")
    checkpoint = ScoredCheckpoint.model_validate_json(raw)
    if _canonical(checkpoint) != raw or checkpoint.reservation != target.spec:
        raise ValueError("scored checkpoint identity is noncanonical or mismatched")
    ledger = target.ledger_root / target.spec.identity()
    if _reservation_id(ledger, target) != checkpoint.mlflow_run_id:
        raise ValueError("scored checkpoint belongs to a different reserved MLflow run")
    if _inventory(root / "payload", limits) != checkpoint.inventory:
        raise ValueError("scored checkpoint payload differs from its sealed inventory")
    _validate(root / "payload", checkpoint.context, target)
    return checkpoint


def recover_scored_checkpoint(
    root: Path, *, expected_sha256: str, target: ResumeTarget,
    limits: TransferLimits = TransferLimits(),
) -> dict:
    """Log retained evidence without fetching final inputs or running a model."""
    from app.ml.lightgbm.tracking import log_governed_evaluation_run

    checkpoint = verify_scored_checkpoint(root, expected_sha256=expected_sha256, target=target, limits=limits)
    # A private copy prevents concurrent checkpoint mutation from supplying
    # different bytes between validation and logging. It is not a durable copy.
    with tempfile.TemporaryDirectory(prefix="g8-log-only-") as temporary:
        payload = Path(temporary) / "payload"
        payload.mkdir(mode=0o700)
        for entry in checkpoint.inventory.files:
            _copy_file(root / "payload" / entry.path, payload / entry.path, size_bytes=entry.size_bytes)
        if _inventory(payload, limits) != checkpoint.inventory:
            raise ValueError("scored checkpoint changed while creating private recovery snapshot")
        args = _validate(payload, checkpoint.context, target)
        for path in payload.rglob("*"):
            if path.is_file():
                path.chmod(0o400)
        run_id = log_governed_evaluation_run(**args, resume_target=target)
        if run_id != checkpoint.mlflow_run_id:
            raise ValueError("recovery did not use the checkpoint's reserved run")
    return {
        "schema_version": "g8_scored_checkpoint_recovery_v1",
        "checkpoint_sha256": expected_sha256, "reservation_sha256": target.spec.identity(),
        "mlflow_run_id": run_id, "mlflow_status": "FINISHED", "mlflow_evidence_verified": True,
        "scoring_invocations": 0, "creates_mlflow_run": False,
        "tracking_scope": "offline" if target.spec.tracking_uri.startswith("file:") else "governed",
        "final_result_published": False,
    }
