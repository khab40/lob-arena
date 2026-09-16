"""Durable G8 lifecycle: score once; retain before logging; finalize and publish separately."""
from __future__ import annotations

import fcntl
import json
import os
import resource
import shutil
import tempfile
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from app.ml.lightgbm import cloud_runner
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest, LightGbmCloudRun, Wave1ResourceEvidence
from app.ml.lightgbm.g8_mlflow_recovery import ResumeTarget, _persist, reserve_run
from app.ml.lightgbm.g8_publication_recovery import (
    RecoveryBinding, _directory_sync, _inventory, resume_publication, retain_completed_release, verify_checkpoint,
)
from app.ml.lightgbm.g8_scored_checkpoint import (
    _copy_file, recover_scored_checkpoint, retain_scored_checkpoint, verify_scored_checkpoint,
)
from app.nebius.object_storage import TransferLimits, inventory_directory, write_checksum_file


@contextmanager
def execution_lock(root: Path, *, create: bool):
    if root.parent.resolve() != root.parent.absolute():
        raise ValueError("durable run parent must be canonical")
    if create:
        root.mkdir(mode=0o700, exist_ok=False)
        _directory_sync(root.parent)
    if not root.is_dir() or root.resolve() != root.absolute():
        raise ValueError("original durable run directory required")
    descriptor = os.open(root / "LOCK", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(descriptor)


class LiveCheckpointLogger:
    """Called by the frozen scorer after bundle creation, before any evidence logging."""

    def __init__(self, root, target, request_path, workspace, context, limits):
        self.root, self.target, self.request_path = root, target, request_path
        self.workspace, self.context, self.limits = workspace, context, limits
        self.started_at = datetime.now(UTC)
        self.wall_start, self.cpu_start = time.perf_counter(), time.process_time()

    def __call__(self, **kwargs):
        artifact_root = kwargs["artifact_root"]
        request = LightGbmCloudJobRequest.model_validate_json(self.request_path.read_bytes())
        wall = max(time.perf_counter() - self.wall_start, 1e-9)
        # Capture original scoring-process resource/Job identity now, not from the recovery process.
        evidence = {
            "schema_version": "g8_scoring_execution_v1",
            "started_at": self.started_at.isoformat(), "scored_at": datetime.now(UTC).isoformat(),
            "resource_scope": "original_process_through_prelogging_checkpoint",
            "resource": Wave1ResourceEvidence(
                wall_seconds=wall, cpu_seconds=max(time.process_time() - self.cpu_start, 0),
                peak_rss_bytes=int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
                                   * (1 if os.sys.platform == "darwin" else 1024)),
                processed_rows=kwargs["predictions"].row_count,
                rows_per_second=kwargs["predictions"].row_count / wall,
            ).model_dump(mode="json"),
            "execution_context": self.context.model_dump(mode="json"),
            "request_sha256": request.canonical_hash(),
            "execution_package_sha256": self.target.spec.execution_package_sha256,
        }
        _persist(artifact_root / "g8-scoring-execution.json", evidence)
        # Preserve environment and input inventory emitted before scoring inside the seal.
        for name in ("environment.json", "input-inventory.json"):
            source = artifact_root.parent / name
            if not source.is_file():
                raise ValueError("original scoring envelope is missing: " + name)
            _copy_file(source, artifact_root / ("g8-" + name), size_bytes=source.stat().st_size)
        digest = retain_scored_checkpoint(
            self.root / "scored", target=self.target, request_path=self.request_path,
            workspace_root=self.workspace, limits=self.limits, **kwargs,
        )
        _persist(self.root / "scored-receipt.json", {
            "checkpoint_sha256": digest, "reservation_sha256": self.target.spec.identity(),
        })
        # The exact same log-only operation is used on the normal and recovery paths.
        receipt = recover_scored_checkpoint(self.root / "scored", expected_sha256=digest,
                                             target=self.target, limits=self.limits)
        return receipt["mlflow_run_id"]


def finish_retained(root: Path, target: ResumeTarget, *, limits=TransferLimits(), publish=True):
    """No original workspace, input loader, model execution or run creation is reachable here.

    Caller holds execution_lock. An interrupted finalization is reconstructed only
    from the sealed scored checkpoint. Existing partial S3 objects are never deleted.
    """
    retained = json.loads((root / "scored-receipt.json").read_bytes())
    if set(retained) != {"checkpoint_sha256", "reservation_sha256"} or retained["reservation_sha256"] != target.spec.identity():
        raise ValueError("original scored receipt/reservation required")
    digest = retained["checkpoint_sha256"]
    scored = verify_scored_checkpoint(root / "scored", expected_sha256=digest, target=target, limits=limits)
    tracking = recover_scored_checkpoint(root / "scored", expected_sha256=digest, target=target, limits=limits)
    # Idempotent publication-only recovery still independently checks remote MLflow first.
    publication_receipt = root / "publication-checkpoint.json"
    if publication_receipt.exists():
        record = json.loads(publication_receipt.read_bytes())
        binding = RecoveryBinding.model_validate(record["binding"])
        if (binding.execution_package_sha256 != target.spec.execution_package_sha256
                or binding.request_sha256 != target.spec.request_sha256
                or binding.candidate_sha256 != target.spec.candidate_sha256
                or binding.mlflow_run_id != scored.mlflow_run_id):
            raise ValueError("publication receipt differs from original reservation")
        checkpoint = root / record["directory"]
        if checkpoint.parent != root or not record["directory"].startswith("publication-"):
            raise ValueError("publication checkpoint directory escaped durable run")
        verify_checkpoint(checkpoint, expected_sha256=record["sha256"], binding=binding, limits=limits)
    else:
        # Private bounded snapshot, reverified before finalization, prevents source races.
        if shutil.disk_usage(root).free < 2 * limits.max_bytes:
            raise ValueError("insufficient durable space for bounded recovery copies; preserve existing evidence")
        staging = Path(tempfile.mkdtemp(prefix="finalizing-", dir=root))
        snapshot = staging / "scored"
        snapshot.mkdir()
        for entry in _inventory(root / "scored", limits).files:
            _copy_file(root / "scored" / entry.path, snapshot / entry.path, size_bytes=entry.size_bytes)
        verified = verify_scored_checkpoint(snapshot, expected_sha256=digest, target=target, limits=limits)
        payload = snapshot / "payload"
        request = LightGbmCloudJobRequest.model_validate_json((payload / "metadata/request.json").read_bytes())
        candidate = cloud_runner.FrozenCandidate.model_validate_json((payload / "metadata/candidate.json").read_bytes())
        artifacts = payload / "artifacts"
        evidence = json.loads((artifacts / "g8-scoring-execution.json").read_bytes())
        from app.ml.lightgbm.cloud_contracts import Wave1ExecutionContext
        from app.ml.lightgbm.contracts import DetectorPredictionsManifest

        context = Wave1ExecutionContext.model_validate(evidence["execution_context"])
        cloud_runner._validate_execution_context(request, context)
        predictions = DetectorPredictionsManifest.model_validate_json(
            (artifacts / verified.context.prediction_manifest_path).read_bytes())
        resource_evidence = Wave1ResourceEvidence.model_validate(evidence["resource"])
        if (evidence["request_sha256"] != request.canonical_hash()
                or evidence["execution_package_sha256"] != target.spec.execution_package_sha256
                or resource_evidence.processed_rows != predictions.row_count
                or verified.context.cloud_metadata != cloud_runner._cloud_metadata(context)):
            raise ValueError("retained scoring execution identity differs")
        result = staging / "result"
        result.mkdir()
        shutil.move(str(artifacts), result / "artifacts")
        (result / "request.json").write_bytes(request.canonical_bytes())
        for name in ("environment.json", "input-inventory.json"):
            shutil.copyfile(result / "artifacts" / ("g8-" + name), result / name)
        metrics = {
            "candidate_hash": request.candidate.sha256, "reproducibility_hash": candidate.reproducibility_hash,
            "test_fold_accessed": True, "test_row_count": predictions.row_count,
            "test_alert_count": predictions.alert_count, "threshold": predictions.threshold, "release_verified": True,
        }
        _persist(result / "metrics.json", metrics)
        finalized = root / "finalization.json"
        if not finalized.exists():
            _persist(finalized, {"completed_at": datetime.now(UTC).isoformat(), "scored_checkpoint_sha256": digest})
        finalization = json.loads(finalized.read_bytes())
        if finalization["scored_checkpoint_sha256"] != digest:
            raise ValueError("finalization refers to another scored checkpoint")
        _persist(result / "g8-recovery.json", {
            "scored_checkpoint_sha256": digest, "execution_package_sha256": target.spec.execution_package_sha256,
            "reservation_sha256": target.spec.identity(), "original_scoring_job_id": context.nebius_job_id,
            "resource_scope": evidence["resource_scope"], "scored_at": evidence["scored_at"],
            "finalization": "verified_same_run_mlflow_then_release", "recovery_rescored": False,
        })
        run = LightGbmCloudRun(
            campaign_id=request.campaign_id, run_id=request.run_id, mode=request.mode, status="succeeded",
            request_sha256=request.canonical_hash(), image=request.image,
            started_at=evidence["started_at"], completed_at=finalization["completed_at"], resource=resource_evidence,
            outputs=tuple(cloud_runner._cloud_artifact(p, result, p.relative_to(result).as_posix().replace("/", "_"))
                          for p in sorted(result.rglob("*")) if p.is_file()),
            candidate_hash=request.candidate.sha256, reproducibility_hash=candidate.reproducibility_hash,
            mlflow_run_id=tracking["mlflow_run_id"], nebius_job_id=context.nebius_job_id,
            estimated_cost_usd=context.estimated_cost_usd,
        )
        (result / "cloud-run.json").write_bytes(run.canonical_bytes())
        _inventory(result, limits)
        inventory = inventory_directory(result, exclude_markers=True)
        write_checksum_file(result, inventory)
        (result / "SUCCESS").write_text(inventory.model_dump_json(indent=2))
        cloud_runner.verify_wave1_result(result)
        binding = RecoveryBinding(execution_package_sha256=target.spec.execution_package_sha256,
            request_sha256=request.canonical_hash(), candidate_sha256=request.candidate.sha256,
            c4_report_sha256=sha256_file(result / "artifacts/c4-evaluation.json"),
            mlflow_run_id=tracking["mlflow_run_id"], result_uri=request.result_uri)
        checkpoint = Path(tempfile.mkdtemp(prefix="publication-parent-", dir=root)) / "checkpoint"
        sha = retain_completed_release(result, checkpoint, binding=binding, limits=limits)
        # Rename the sealed directory before retaining its independent pointer. Keep failed staging for diagnosis.
        final_checkpoint = root / ("publication-" + checkpoint.parent.name.removeprefix("publication-parent-"))
        checkpoint.rename(final_checkpoint)
        _directory_sync(root)
        checkpoint = final_checkpoint
        record = {"binding": binding.model_dump(mode="json"), "directory": checkpoint.name, "sha256": sha}
        _persist(publication_receipt, record)
    # A publication pointer is not authority to substitute another structurally
    # valid prediction/report release. Bind every artifact back to the scored seal.
    completed_seal = verify_checkpoint(checkpoint, expected_sha256=record["sha256"], binding=binding, limits=limits)
    expected_artifacts = {entry.path: (entry.sha256, entry.size_bytes) for entry in scored.inventory.files
                          if entry.path.startswith("artifacts/")}
    completed_artifacts = {entry.path: (entry.sha256, entry.size_bytes) for entry in completed_seal.inventory.files
                           if entry.path.startswith("artifacts/")}
    if expected_artifacts != completed_artifacts:
        raise ValueError("completed publication artifacts differ from original scored seal")
    original_evidence = json.loads((root / "scored/payload/artifacts/g8-scoring-execution.json").read_bytes())
    completed_run = LightGbmCloudRun.model_validate_json((checkpoint / "payload/cloud-run.json").read_bytes())
    if (completed_run.resource != Wave1ResourceEvidence.model_validate(original_evidence["resource"])
            or completed_run.started_at != datetime.fromisoformat(original_evidence["started_at"])
            or completed_run.nebius_job_id != original_evidence["execution_context"]["nebius_job_id"]):
        raise ValueError("completed publication changed original scoring execution evidence")
    if not publish:
        return {**record, "mlflow_remote_verified": tracking["tracking_scope"] == "governed", "published": False}
    receipt = resume_publication(checkpoint, expected_sha256=record["sha256"], binding=binding, limits=limits)
    publication_writes = receipt.pop("mlflow_writes")
    return {**receipt, "publication_mlflow_writes": publication_writes,
            "mlflow_logging_mode": "resume_existing_run",
            "mlflow_remote_state_verified": tracking["tracking_scope"] == "governed"}


def run_live(plan, request, package: Path, legacy):
    """Single-use entry, called only after signed package, runtime and mount verification."""
    from app.ml.lightgbm.g8_replacement import reservation

    root = Path(plan.mount_path) / plan.run_id
    # No occupied directory can invoke the scorer, even after an ambiguous crash.
    with execution_lock(root, create=True):
        ledger = root / "ledger"
        ledger.mkdir(mode=0o700)
        _directory_sync(root)
        target = ResumeTarget(ledger, reservation(plan, request))
        _persist(root / "reservation.json", target.spec.model_dump(mode="json"))
        legacy._verify_mlflow_ready(request.mlflow_tracking_uri)
        legacy._require_empty_result(request, legacy.ENDPOINT)  # Conditional remote single-execution intent.
        reserve_run(target)  # Fsynced unique ID before any final download/scoring.
        workspace = root / "workspace"
        workspace.mkdir(mode=0o700)
        _directory_sync(root)
        limits = TransferLimits(max_files=plan.max_checkpoint_files, max_bytes=plan.max_checkpoint_bytes)
        context = legacy._execution_context()
        cloud_runner._validate_execution_context(request, context)
        logger = LiveCheckpointLogger(root, target, package / "request.json", workspace, context, limits)
        inputs = legacy._validate_c4_inputs(request, package / "c4-inputs.json")
        if shutil.disk_usage(root).free < 5 * limits.max_bytes:
            raise ValueError("insufficient durable capacity before final access")
        input_root = workspace / "input"
        candidate_root = workspace / "candidate"
        legacy.download_s3_release(plan.candidate_release_uri, candidate_root, endpoint_url=legacy.ENDPOINT)
        if sha256_file(candidate_root / "candidate.json") != plan.candidate_sha256:
            raise ValueError("downloaded candidate differs from signed freeze")
        _persist(root / "final-access-started.json", {"request_sha256": request.canonical_hash()})
        legacy.download_s3_release(request.input_release_uri, input_root, endpoint_url=legacy.ENDPOINT)
        shutil.copytree(candidate_root, input_root / "candidate")
        for reference, name in ((request.authorization, "authorization.json"),
                (request.authorization_signature, "authorization.sig"),
                (request.authorization_public_key, "authorization-public.pem"),
                (request.input.dataset_lineage_receipt, "dataset-lineage.json")):
            target_path = input_root / reference.uri
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package / name, target_path)
        staging = workspace / "scoring"
        staging.mkdir()
        (staging / "artifacts").mkdir()
        _persist(staging / "input-inventory.json", cloud_runner._request_inventory(input_root, request).model_dump(mode="json"))
        cloud_runner._write_environment(staging, request, context)
        original_logger = cloud_runner.log_governed_evaluation_run
        original_lineage = cloud_runner._validate_tabular_projection_lineage
        cloud_runner.log_governed_evaluation_run = lambda **kw: legacy._log_final_with_c4(inputs, logger, **kw)
        cloud_runner._validate_tabular_projection_lineage = legacy._validate_final_lineage
        try:
            _persist(root / "scoring-started.json", {"request_sha256": request.canonical_hash(), "scoring_calls_allowed": 1})
            cloud_runner._run_final(staging, input_root, request, context,
                os.environ["WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256"])
        finally:
            cloud_runner.log_governed_evaluation_run = original_logger
            cloud_runner._validate_tabular_projection_lineage = original_lineage
        return finish_retained(root, target, limits=limits)
