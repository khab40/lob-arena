"""Synthetic frozen-runtime exercise of the actual live lifecycle, never execution approval."""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.ml.lightgbm import cloud_runner, g8_live_recovery as live, g8_mlflow_recovery as tracking
from app.ml.lightgbm import g8_replacement, g8_publication_recovery as publication
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.c4_evaluation import C4EvaluationProfile

try:
    from serverless.jobs.g8_rehearsal import rehearse, IMAGE
    from serverless.jobs.g8_publication_rehearsal import FakeS3
except ModuleNotFoundError:
    from g8_rehearsal import rehearse, IMAGE
    from g8_publication_rehearsal import FakeS3


def score_worker(output):
    import mlflow

    def execute(legacy, request, workspace):
        package = workspace / "live-package"
        package.mkdir()
        for name, source in {
            "request.json": workspace / "request.json", "c4-inputs.json": workspace / "c4-inputs.json",
            "authorization.json": workspace / request.authorization.uri,
            "authorization.sig": workspace / request.authorization_signature.uri,
            "authorization-public.pem": workspace / request.authorization_public_key.uri,
            "dataset-lineage.json": workspace / "final-input/manifests/c4-mlflow-dataset-release.json",
        }.items():
            # Actual fixture input root is resolved through the already-reviewed C4 inputs.
            if name == "dataset-lineage.json":
                inputs = json.loads((workspace / "c4-inputs.json").read_bytes())
                source = Path(inputs["projection"]).parent / "c4-mlflow-dataset-release.json"
            shutil.copyfile(source, package / name)
        profile = C4EvaluationProfile.model_validate_json((workspace / "c4-profile.json").read_bytes())
        spec = tracking.ReservationSpec(execution_package_sha256=sha256_file(Path(__file__)),
            request_sha256=request.canonical_hash(), candidate_sha256=request.candidate.sha256,
            evaluation_profile_sha256=profile.canonical_hash(), request_run_id=request.run_id,
            tracking_uri=(output / "mlruns").as_uri())
        mlflow.MlflowClient(tracking_uri=spec.tracking_uri).create_experiment(tracking.EXPERIMENT)
        plan = SimpleNamespace(mount_path=str(output / "durable"), run_id=request.run_id,
            max_checkpoint_files=10000, max_checkpoint_bytes=64 * 1024**2,
            candidate_sha256=request.candidate.sha256,
            candidate_release_uri="s3://aimada-wave1-results-e00g6zvxpr00/campaigns/synthetic-g8/development/selected")
        # Use the actual synthetic request's selected development URI from the legacy argv.
        plan.candidate_release_uri = sys.argv[sys.argv.index("--candidate-uri") + 1]
        context = legacy._execution_context().model_copy(update={"nebius_job_id": "aijob-synthetic-original"})
        original_score = cloud_runner.predict_governed_fold
        original_logger = live.LiveCheckpointLogger.__call__

        def score(*a, **kw):
            tracking._persist(output / "score-count.json", {"calls": 1})
            if getattr(score, "called", False):
                raise AssertionError("second scoring call")
            score.called = True
            return original_score(*a, **kw)

        def logger(self, **kw):
            kw["tracking_uri"] = spec.tracking_uri  # Transport-only offline substitution.
            return original_logger(self, **kw)

        def abrupt(*a, **kw):
            os._exit(73)  # Real live logger has sealed + fsynced the independent receipt.

        with (patch.object(g8_replacement, "reservation", return_value=spec),
              patch.object(legacy, "_execution_context", return_value=context),
              patch.object(live.LiveCheckpointLogger, "__call__", logger),
              patch.object(cloud_runner, "predict_governed_fold", score),
              patch.object(live, "recover_scored_checkpoint", abrupt)):
            live.run_live(plan, request, package, legacy)
        raise AssertionError("prelogging fault was not reached")

    rehearse(output / "workspace", Path(__file__).with_name("run_lightgbm_g8.py"),
             c4=True, execution_hook=execute)


def recover_worker(output, *, fault):
    import mlflow
    from contextlib import ExitStack
    from app.ml.lightgbm import scoring, training
    from app.nebius import object_storage

    root = output / "durable/synthetic-final"
    target = tracking.ResumeTarget(root / "ledger", tracking.ReservationSpec.model_validate_json(
        (root / "reservation.json").read_bytes()))
    original_artifact = mlflow.MlflowClient.log_artifact

    def forbidden(*a, **kw):
        raise AssertionError("recovery reached model execution, input download or run creation")

    def artifact(client, *a, **kw):
        original_artifact(client, *a, **kw)
        os._exit(74)

    with ExitStack() as stack:
        for owner, name in ((cloud_runner, "_run_final"), (cloud_runner, "_load_dataset"),
                (cloud_runner, "execute_wave1_request"), (scoring, "predict_governed_fold"),
                (training, "train_binary_attack_model"), (mlflow.MlflowClient, "create_run"),
                (mlflow, "start_run"), (object_storage, "download_s3_release")):
            stack.enter_context(patch.object(owner, name, forbidden))
        if fault:
            stack.enter_context(patch.object(mlflow.MlflowClient, "log_artifact", artifact))
        with live.execution_lock(root, create=False):
            prepared = live.finish_retained(root, target, publish=False,
                limits=object_storage.TransferLimits(max_bytes=64 * 1024**2))
            binding = publication.RecoveryBinding.model_validate(prepared["binding"])
            source = root / prepared["directory"] / "payload"
            fake = FakeS3(source, binding)
            # Full publisher including readbacks/conditional writes; only remote transport is simulated.
            fake.fail_put = fake.prefix + "/SUCCESS"
            stack.enter_context(patch.object(publication.storage, "_aws_json", fake.aws))
            stack.enter_context(patch.object(publication.shutil, "which", return_value="/synthetic/aws"))
            stack.enter_context(patch.object(publication.subprocess, "run", fake.run))
            try:
                live.finish_retained(root, target)
            except RuntimeError:
                pass
            else:
                raise AssertionError("marker fault was not reached")
            assert fake.prefix + "/SUCCESS" not in fake.objects
            preserved = dict(fake.objects)
            fake.fail_put = None
            receipt = live.finish_retained(root, target)
            assert all(fake.objects[k] == v for k, v in preserved.items())
            for method in ("log_batch", "log_inputs", "log_artifact", "set_terminated"):
                stack.enter_context(patch.object(mlflow.MlflowClient, method, forbidden))
            repeat = live.finish_retained(root, target)
            assert repeat["conditionally_published_objects"] == 0
            for path in source.rglob("*"):
                if path.is_file():
                    assert fake.objects[fake.prefix + "/" + path.relative_to(source).as_posix()] == path.read_bytes()
            run = cloud_runner.verify_wave1_result(source)
            assert run.nebius_job_id == "aijob-synthetic-original"
            receipt.update(original_job_identity_verified=True, marker_failure_recovered=True,
                           completed_repeat_writes=0, original_workspace_absent=True)
            tracking._persist(output / "recovery.json", receipt)


def rehearse_live(output):
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    (output / "durable").mkdir()
    env = {**os.environ, "MLFLOW_ALLOW_FILE_STORE": "true", "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0",
           "PYTHONPATH": os.pathsep.join([str(Path(live.__file__).resolve().parents[3]),
                                         str(Path(live.__file__).resolve().parents[4])])}
    for mode, code in (("score", 73), ("interrupt", 74), ("recover", 0)):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--output", str(output),
                                 "--worker", mode], env=env, capture_output=True, text=True, timeout=240)
        if result.returncode != code:
            raise AssertionError(mode + " worker failed:\n" + result.stdout[-2500:] + result.stderr[-3500:])
        if mode == "score":
            # Remove only this harness's generated synthetic workspaces; keep the native-mount stand-in.
            shutil.rmtree(output / "workspace")
            shutil.rmtree(output / "durable/synthetic-final/workspace")
    receipt = json.loads((output / "recovery.json").read_bytes())
    receipt.update(schema_version="g8_live_integration_rehearsal_v1", request_image=IMAGE,
        final_scoring_call_count=json.loads((output / "score-count.json").read_bytes())["calls"],
        native_storage_verified=False, remote_authentication_verified=False, production_test_accessed=False,
        production_g8_complete=False,
        code_sha256={name: sha256_file(Path(__import__("app.ml.lightgbm." + name, fromlist=["x"]).__file__))
                     for name in g8_replacement.MODULES},
        rehearsal_sha256=sha256_file(Path(__file__)),
        runner_sha256=sha256_file(Path(__file__).with_name("run_lightgbm_g8_replacement.py")))
    tracking._persist(output / "rehearsal.json", receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worker", choices=("score", "interrupt", "recover"))
    args = parser.parse_args()
    args.output = args.output.resolve()
    if args.worker == "score":
        score_worker(args.output)
    elif args.worker:
        recover_worker(args.output, fault=args.worker == "interrupt")
    else:
        print(json.dumps(rehearse_live(args.output), indent=2))
