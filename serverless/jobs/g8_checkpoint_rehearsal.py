"""Synthetic process-loss proof for pre-logging checkpoints, never a live G8 run."""
from __future__ import annotations

import argparse
import importlib
import json
import os
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from app.ml.lightgbm import cloud_runner, g8_mlflow_recovery as tracking, g8_scored_checkpoint as checkpoints
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.c4_evaluation import C4EvaluationProfile

try:
    from serverless.jobs.g8_rehearsal import IMAGE, rehearse
except ModuleNotFoundError:
    from g8_rehearsal import IMAGE, rehearse


def _target(output):
    return tracking.ResumeTarget(
        output / "durable/ledger",
        tracking.ReservationSpec.model_validate_json((output / "reservation.json").read_bytes()),
    )


def _score_worker(output: Path):
    import mlflow

    workspace = output / "workspace"
    original_score = cloud_runner.predict_governed_fold
    state = {}

    def score(*args, **kwargs):
        if state:
            raise AssertionError("second scoring call forbidden")
        profile = C4EvaluationProfile.model_validate_json((workspace / "c4-profile.json").read_bytes())
        spec = tracking.ReservationSpec(
            execution_package_sha256=sha256_file(Path(__file__)),
            request_sha256=sha256_file(workspace / "request.json"),
            candidate_sha256=profile.candidate_sha256,
            evaluation_profile_sha256=profile.canonical_hash(),
            request_run_id="synthetic-final", tracking_uri=(output / "mlruns").as_uri(),
        )
        client = mlflow.MlflowClient(tracking_uri=spec.tracking_uri)
        client.create_experiment(tracking.EXPERIMENT)
        target = tracking.ResumeTarget(output / "durable/ledger", spec)
        run_id = tracking.reserve_run(target)
        state.update(target=target, run_id=run_id)
        tracking._persist(output / "reservation.json", spec.model_dump(mode="json"))
        tracking._persist(output / "scoring-started.json", {"calls": 1, "pid": os.getpid()})
        result = original_score(*args, **kwargs)
        tracking._persist(output / "scoring-finished.json", {"calls": 1, "pid": os.getpid()})
        return result

    def checkpoint(**kwargs):
        target = state["target"]
        kwargs["tracking_uri"] = target.spec.tracking_uri
        digest = checkpoints.retain_scored_checkpoint(
            output / "durable/checkpoint", target=target, request_path=workspace / "request.json",
            workspace_root=workspace, **kwargs,
        )
        tracking._persist(output / "checkpoint-receipt.json", {
            "checkpoint_sha256": digest, "mlflow_run_id": state["run_id"],
            "reservation_sha256": target.spec.identity(), "writer_pid": os.getpid(),
        })
        # Deliberately bypass Python finally/atexit cleanup. The parent must not
        # call the scorer again; only the retained checkpoint can be recovered.
        os._exit(73)

    with (
        patch.dict(os.environ, {"MLFLOW_ALLOW_FILE_STORE": "true", "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0"}),
        patch.object(cloud_runner, "predict_governed_fold", score),
        patch.object(cloud_runner, "log_governed_evaluation_run", checkpoint),
    ):
        rehearse(workspace, Path(__file__).with_name("run_lightgbm_g8.py"), c4=True)
    raise AssertionError("worker did not stop at the pre-logging boundary")


def _recover_worker(output: Path, fault: str):
    import mlflow
    from contextlib import ExitStack
    from app.ml.lightgbm import scoring, training
    from app.nebius import object_storage

    if (output / "workspace").exists():
        raise AssertionError("original workspace must be absent during recovery")
    receipt = json.loads((output / "checkpoint-receipt.json").read_bytes())
    writes = []
    original_artifact = mlflow.MlflowClient.log_artifact

    def forbidden(*args, **kwargs):
        raise AssertionError("recovery called a forbidden loader/scorer/trainer/run creator")

    def artifact(client, *args, **kwargs):
        original_artifact(client, *args, **kwargs)
        os._exit(74)  # Lost process after a successful artifact upload.

    with ExitStack() as stack:
        for owner, name in (
            (cloud_runner, "predict_governed_fold"), (scoring, "predict_governed_fold"),
            (cloud_runner, "execute_wave1_request"), (cloud_runner, "_load_dataset"),
            (training, "train_binary_attack_model"), (mlflow.MlflowClient, "create_run"),
            (mlflow, "start_run"), (object_storage, "download_s3_release"),
        ):
            stack.enter_context(patch.object(owner, name, forbidden))
        for name in ("log_batch", "log_inputs", "log_artifact", "set_terminated"):
            original = getattr(mlflow.MlflowClient, name)

            def count(*args, _name=name, _original=original, **kwargs):
                if fault == "read-only":
                    raise AssertionError("completed recovery attempted an MLflow write")
                writes.append(_name)
                return _original(*args, **kwargs)

            stack.enter_context(patch.object(mlflow.MlflowClient, name, count))
        if fault == "artifact":
            stack.enter_context(patch.object(mlflow.MlflowClient, "log_artifact", artifact))
        stack.enter_context(patch.object(sys, "argv", [
            "recover_lightgbm_g8_scored.py", "--checkpoint", str(output / "durable/checkpoint"),
            "--checkpoint-sha256", receipt["checkpoint_sha256"],
            "--reservation", str(output / "reservation.json"), "--ledger-root", str(output / "durable/ledger"), "--log",
        ]))
        runpy.run_path(str(Path(__file__).with_name("recover_lightgbm_g8_scored.py")), run_name="__main__")
    tracking._persist(output / ("recovery-" + fault + ".json"), {
        "pid": os.getpid(), "mlflow_write_calls": len(writes), "forbidden_calls": 0,
    })


def worker(output: Path, mode: str, *, fault="none"):
    env = {
        **os.environ, "MLFLOW_ALLOW_FILE_STORE": "true", "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0",
        "PYTHONPATH": os.pathsep.join([
            str(Path(checkpoints.__file__).resolve().parents[3]),
            str(Path(checkpoints.__file__).resolve().parents[4]),
        ]),
    }
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--output", str(output), "--worker", mode, "--fault", fault],
        cwd=output / "fresh-process", env=env, capture_output=True, text=True, timeout=180,
    )


def prepare(output: Path) -> dict:
    output.mkdir(exist_ok=False, parents=True)
    (output / "durable/ledger").mkdir(parents=True)
    (output / "fresh-process").mkdir()
    result = worker(output, "score")
    if result.returncode != 73:
        raise AssertionError("synthetic score worker failed before sealed checkpoint:\n" + result.stdout[-3000:] + result.stderr[-3000:])
    return json.loads((output / "checkpoint-receipt.json").read_bytes())


def rehearse_checkpoint(output: Path) -> dict:
    import mlflow

    output = output.resolve()
    retained = prepare(output)
    target = _target(output)
    with patch.dict(os.environ, {"MLFLOW_ALLOW_FILE_STORE": "true", "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0"}):
        client = mlflow.MlflowClient(tracking_uri=target.spec.tracking_uri)
        run = client.get_run(retained["mlflow_run_id"])
        if run.info.status != "RUNNING" or run.data.metrics or run.inputs.dataset_inputs or client.list_artifacts(run.info.run_id):
            raise AssertionError("checkpoint was not sealed before evidence logging")
        checkpoints.verify_scored_checkpoint(
            output / "durable/checkpoint", expected_sha256=retained["checkpoint_sha256"], target=target,
        )
        # Only the synthetic workspace created by prepare() above is removed.
        # Ledger, checkpoint, tracking store and independent receipts are siblings.
        shutil.rmtree(output / "workspace")
        interrupted = worker(output, "recover", fault="artifact")
        if interrupted.returncode != 74:
            raise AssertionError("artifact-loss injection failed:\n" + interrupted.stdout[-3000:] + interrupted.stderr[-3000:])
        recovered = worker(output, "recover")
        if recovered.returncode:
            raise AssertionError("fresh-process recovery failed:\n" + recovered.stdout[-3000:] + recovered.stderr[-3000:])
        repeated = worker(output, "recover", fault="read-only")
        if repeated.returncode:
            raise AssertionError("read-only recovery failed:\n" + repeated.stdout[-3000:] + repeated.stderr[-3000:])
        recovery_receipt = json.loads(recovered.stdout)
        repeat_receipt = json.loads(repeated.stdout)
        if recovery_receipt != repeat_receipt:
            raise AssertionError("repeated recovery returned different evidence")
        run = client.get_run(retained["mlflow_run_id"])
        experiment = client.get_experiment_by_name(tracking.EXPERIMENT)
        if len(client.search_runs([experiment.experiment_id])) != 1 or run.info.status != "FINISHED":
            raise AssertionError("recovery did not finish exactly one run")
        for name in run.data.metrics:
            if len(client.get_metric_history(run.info.run_id, name)) != 1:
                raise AssertionError("recovery duplicated metric history")
        if len(run.inputs.dataset_inputs) != 30:
            raise AssertionError("recovery changed 30-shard dataset lineage")
        for name in ("scoring-started", "scoring-finished"):
            if json.loads((output / (name + ".json")).read_bytes())["calls"] != 1:
                raise AssertionError("scoring invocation count changed")
        recovered_process = json.loads((output / "recovery-none.json").read_bytes())
        repeated_process = json.loads((output / "recovery-read-only.json").read_bytes())
        if retained["writer_pid"] == recovered_process["pid"] or repeated_process["mlflow_write_calls"] != 0:
            raise AssertionError("recovery was not a fresh process or wrote on completed replay")
        sealed = checkpoints.ScoredCheckpoint.model_validate_json(
            (output / "durable/checkpoint/checkpoint.json").read_bytes())
        result = {
            "schema_version": "g8_prelogging_checkpoint_rehearsal_v1", "request_image": IMAGE,
            **retained, "mlflow_status": run.info.status, "final_scoring_call_count": 1,
            "workspace_removed_before_recovery": not (output / "workspace").exists(),
            "pre_logging_checkpoint_verified": True, "fresh_process_recovery_verified": True,
            "worker_exit_before_logging": 73, "recovery_exit_after_artifact_upload": 74,
            "recovery_process": recovered_process, "repeat_process": repeated_process,
            "verified_metric_count": len(run.data.metrics), "verified_dataset_input_count": 30,
            "artifact_readback_verified": recovery_receipt["mlflow_evidence_verified"],
            "checkpoint_file_count": len(sealed.inventory.files),
            "checkpoint_size_bytes": sum(entry.size_bytes for entry in sealed.inventory.files),
            "c4_report_sha256": sha256_file(
                output / "durable/checkpoint/payload/artifacts" / sealed.context.benchmark_results_path),
            "code_sha256": {
                name: sha256_file(Path(importlib.import_module("app.ml.lightgbm." + name).__file__))
                for name in ("g8_scored_checkpoint", "g8_mlflow_recovery", "g8_publication_recovery",
                             "tracking", "c4_evaluation", "c4_replay_evidence", "g8_c4_fixture", "g8_benchmark_readiness")
            },
            "rehearsal_sha256": sha256_file(Path(__file__)),
            "recovery_cli_sha256": sha256_file(Path(__file__).with_name("recover_lightgbm_g8_scored.py")),
            "production_test_accessed": False, "native_storage_verified": False,
            "remote_authentication_verified": False, "production_g8_complete": False,
        }
        tracking._persist(output / "rehearsal.json", result)
        return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--worker", choices=("score", "recover"))
    parser.add_argument("--fault", choices=("none", "artifact", "read-only"), default="none")
    args = parser.parse_args()
    if args.worker == "score":
        _score_worker(args.output.resolve())
    elif args.worker == "recover":
        _recover_worker(args.output.resolve(), args.fault)
    else:
        print(json.dumps(rehearse_checkpoint(args.output), indent=2))
