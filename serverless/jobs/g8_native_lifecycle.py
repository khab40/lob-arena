"""Actual synthetic scoring and authenticated recovery, called only after native gates."""
from __future__ import annotations

import json
import os
import shutil
import urllib.error
import urllib.request
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from app.ml.lightgbm import cloud_runner, g8_live_recovery as live, g8_mlflow_recovery as tracking
from app.ml.lightgbm import g8_publication_recovery as publication
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.g8_replacement import reservation
from app.nebius import object_storage

if __package__:
    from . import prepare_g8_native_sources as sources, run_lightgbm_g8 as legacy
    from .g8_native_source_capsule import hydrate, SOURCE_SHA256
else:
    import prepare_g8_native_sources as sources
    import run_lightgbm_g8 as legacy
    from g8_native_source_capsule import hydrate, SOURCE_SHA256


def authentication_probe():
    uri = "http://10.4.0.54:5500"
    legacy._verify_mlflow_ready(uri)
    request = urllib.request.Request(uri + "/api/2.0/mlflow/experiments/search",
        data=b'{"max_results":1}', headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10):
            raise ValueError("unauthenticated MLflow request unexpectedly accepted")
    except urllib.error.HTTPError as error:
        if error.code not in {401, 403}:
            raise ValueError("MLflow authentication denial not established") from None


def score(plan, request, package, context):
    root = Path(plan.mount_path)
    prepared = root / "native-sources"
    receipt = hydrate(package / "source-capsule", prepared)
    verified = sources.verify(prepared, expected_sha256=SOURCE_SHA256)
    if verified["request_sha256"] != plan.request_sha256:
        raise ValueError("synthetic request differs after source hydration")
    tracking._persist(root / "native-evidence/source-readback.json", receipt)
    payload = prepared / "payload"
    execution = root / "native-execution"
    execution.mkdir(mode=0o700)
    for name, source in {
        "request.json": payload / "request.json",
        "authorization.json": payload / "authorization/authorization.json",
        "authorization.sig": payload / "authorization/authorization.sig",
        "authorization-public.pem": payload / "authorization/authorization-public.pem",
        "dataset-lineage.json": payload / "sources/input/manifests/c4-mlflow-dataset-release.json",
    }.items():
        shutil.copyfile(source, execution / name)
    inputs = legacy._validate_c4_inputs(request, payload / "c4-inputs.json")
    tracking._persist(execution / "c4-inputs.json", inputs.model_dump(mode="json"))
    os.environ["WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256"] = sha256_file(execution / "authorization-public.pem")
    original_score = cloud_runner.predict_governed_fold

    def once(*args, **kwargs):
        count = root / "native-evidence/scoring-call.json"
        if count.exists():
            raise ValueError("native rehearsal scoring cannot repeat")
        tracking._persist(count, {"calls": 1, "job_id": context.nebius_job_id})
        return original_score(*args, **kwargs)

    def sealed_exit(*args, **kwargs):
        tracking._persist(root / "native-evidence/expected-score-exit.json", {"exit_code": 73})
        os._exit(73)  # LiveCheckpointLogger has already fsynced scored-receipt.json.

    # Only observed identity, call counting and the deliberate post-seal failure
    # are injected. Loaders, C4 evaluation, S3 and MLflow remain actual transports.
    with (patch.object(legacy, "_execution_context", return_value=context),
          patch.object(cloud_runner, "predict_governed_fold", once),
          patch.object(live, "recover_scored_checkpoint", sealed_exit)):
        live.run_live(plan, request, execution, legacy)
    raise AssertionError("native score did not reach the reviewed post-seal exit")


def recover(plan, request, *, interrupt):
    import mlflow
    from app.ml.lightgbm import scoring, training

    root = Path(plan.mount_path) / plan.run_id
    target = tracking.ResumeTarget(root / "ledger", reservation(plan, request))
    limits = object_storage.TransferLimits(max_files=plan.max_checkpoint_files, max_bytes=plan.max_checkpoint_bytes)

    def forbidden(*args, **kwargs):
        raise AssertionError("recovery attempted model execution, input download, new run or completed write")

    original_artifact = mlflow.MlflowClient.log_artifact

    def lose_artifact_response(client, *args, **kwargs):
        original_artifact(client, *args, **kwargs)
        tracking._persist(Path(plan.mount_path) / "native-evidence/expected-artifact-exit.json", {"exit_code": 74})
        os._exit(74)

    with ExitStack() as stack, live.execution_lock(root, create=False):
        for owner, name in ((cloud_runner, "_run_final"), (cloud_runner, "_load_dataset"),
                (cloud_runner, "execute_wave1_request"), (cloud_runner, "predict_governed_fold"),
                (scoring, "predict_governed_fold"), (training, "train_binary_attack_model"),
                (mlflow.MlflowClient, "create_run"), (mlflow, "start_run"),
                (object_storage, "download_s3_release"), (legacy, "download_s3_release")):
            stack.enter_context(patch.object(owner, name, forbidden))
        # Verify the independent seal before discarding only the original synthetic workspace.
        from app.ml.lightgbm.g8_scored_checkpoint import verify_scored_checkpoint
        digest = json.loads((root / "scored-receipt.json").read_bytes())["checkpoint_sha256"]
        verify_scored_checkpoint(root / "scored", expected_sha256=digest, target=target, limits=limits)
        workspace = root / "workspace"
        if workspace.exists():
            if workspace.is_symlink() or workspace.resolve() != workspace.absolute():
                raise ValueError("unsafe disposable synthetic workspace")
            shutil.rmtree(workspace)
        if interrupt:
            stack.enter_context(patch.object(mlflow.MlflowClient, "log_artifact", lose_artifact_response))
            live.finish_retained(root, target, limits=limits, publish=False)
            raise AssertionError("remote artifact interruption did not occur")
        transfer = publication._transfer_json
        marker_withheld = False

        def withhold_marker(size, *args):
            nonlocal marker_withheld
            if args[1] == "put-object" and args[args.index("--key") + 1].endswith("/SUCCESS"):
                marker_withheld = True
                raise RuntimeError("deliberate synthetic failure before SUCCESS publication")
            return transfer(size, *args)

        with patch.object(publication, "_transfer_json", withhold_marker):
            try:
                live.finish_retained(root, target, limits=limits)
            except RuntimeError:
                if not marker_withheld:
                    raise
            else:
                raise AssertionError("publication did not reach the withheld marker")
        receipt = live.finish_retained(root, target, limits=limits)
        for name in ("log_batch", "log_inputs", "log_artifact", "set_terminated", "set_tag"):
            stack.enter_context(patch.object(mlflow.MlflowClient, name, forbidden))
        original_transfer = publication._transfer_json

        def readonly(size, *args):
            if args[1] not in {"get-object", "head-object", "list-objects-v2"}:
                forbidden()
            return original_transfer(size, *args)

        stack.enter_context(patch.object(publication, "_transfer_json", readonly))
        repeat = live.finish_retained(root, target, limits=limits)
        if repeat["conditionally_published_objects"] != 0:
            raise AssertionError("completed publication performed writes")
        run = mlflow.MlflowClient(tracking_uri=request.mlflow_tracking_uri).get_run(receipt["mlflow_run_id"])
        if run.info.status != "FINISHED" or len(run.inputs.dataset_inputs) != 30:
            raise ValueError("remote synthetic MLflow completion/lineage differs")
        return {**receipt, "verified_metric_count": len(run.data.metrics), "verified_dataset_inputs": 30,
                "completed_repeat_writes": 0, "publication_marker_fault_recovered": marker_withheld,
                "original_workspace_absent": not workspace.exists()}
