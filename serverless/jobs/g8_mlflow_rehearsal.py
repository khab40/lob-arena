"""Offline same-run logging faults around the real synthetic C4 scoring path.

This harness does not simulate Job loss or prove pre-logging payload retention.
No production data, remote tracking, credentials or native storage are accessed.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from unittest.mock import patch

from app.ml.lightgbm import cloud_runner, g8_mlflow_recovery as recovery
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.c4_evaluation import C4EvaluationProfile

try:
    from serverless.jobs.g8_rehearsal import rehearse
except ModuleNotFoundError:  # Direct execution of the read-only frozen-image overlay.
    from g8_rehearsal import rehearse


def rehearse_mlflow(output: Path) -> dict:
    import mlflow

    output = output.resolve()
    original_score = cloud_runner.predict_governed_fold
    original_log = cloud_runner.log_governed_evaluation_run
    state = {"create_calls": 0, "writes": 0, "faults": [], "logging_attempts": 0, "reordered_inputs": 0}
    pending = ["create_response", "metric_response", "artifact_response", "finish_response"]

    def lose_response(kind):
        if pending and pending[0] == kind:
            state["faults"].append(pending.pop(0))
            raise TimeoutError("synthetic lost MLflow response: " + kind)

    class FaultClient:
        def __init__(self, actual):
            self.actual = actual

        def __getattr__(self, name):
            original = getattr(self.actual, name)
            if name == "get_run":
                def reordered(*args, **kwargs):
                    run = original(*args, **kwargs)
                    for item in run.inputs.dataset_inputs:
                        item.tags.reverse()  # A backend need not preserve insertion order.
                        state["reordered_inputs"] += 1
                    return run
                return reordered
            if name not in {"create_run", "log_batch", "log_inputs", "log_artifact", "set_terminated"}:
                return original

            def call(*args, **kwargs):
                state["writes"] += 1
                result = original(*args, **kwargs)
                if name == "create_run":
                    state["create_calls"] += 1
                    lose_response("create_response")
                elif name == "log_batch" and kwargs.get("metrics"):
                    lose_response("metric_response")
                elif name == "log_artifact":
                    lose_response("artifact_response")
                elif name == "set_terminated":
                    lose_response("finish_response")
                return result

            return call

    def score(*args, **kwargs):
        if "target" in state:
            raise AssertionError("synthetic final scoring attempted more than once")
        profile = C4EvaluationProfile.model_validate_json((output / "c4-profile.json").read_bytes())
        ledger = output / "logging-ledger"
        ledger.mkdir()
        spec = recovery.ReservationSpec(
            execution_package_sha256=sha256_file(Path(__file__)),
            request_sha256=sha256_file(output / "request.json"),
            candidate_sha256=profile.candidate_sha256,
            evaluation_profile_sha256=profile.canonical_hash(),
            request_run_id="synthetic-final", tracking_uri=(output / "mlruns").as_uri(),
        )
        client = mlflow.MlflowClient(tracking_uri=spec.tracking_uri)
        client.create_experiment(recovery.EXPERIMENT)
        state["client"] = FaultClient(client)
        state["target"] = recovery.ResumeTarget(ledger, spec)
        try:
            recovery.reserve_run(state["target"])
        except TimeoutError:
            pass  # Reconcile only; reserve_run must never send a second create POST.
        state["run_id"] = recovery.reserve_run(state["target"])
        state["reserved_before_scoring"] = True
        return original_score(*args, **kwargs)

    def log(**kwargs):
        target = state["target"]
        for _ in range(4):  # Logging only; never loop around model execution.
            state["logging_attempts"] += 1
            try:
                run_id = original_log(**kwargs, resume_target=target)
                break
            except TimeoutError:
                continue
        else:
            raise AssertionError("same-run logging did not recover after bounded injected faults")
        writes = state["writes"]
        if original_log(**kwargs, resume_target=target) != run_id or state["writes"] != writes:
            raise AssertionError("completed recovery was not read-only")
        state["repeat_writes"] = state["writes"] - writes
        return run_id

    previous_uri = mlflow.get_tracking_uri()
    try:
        with (
            patch.dict(os.environ, {"MLFLOW_ALLOW_FILE_STORE": "true", "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0"}),
            patch.object(recovery, "_client", lambda spec: state["client"]),
            patch.object(cloud_runner, "predict_governed_fold", score),
            patch.object(cloud_runner, "log_governed_evaluation_run", log),
        ):
            source = rehearse(output, Path(__file__).with_name("run_lightgbm_g8.py"), c4=True)
            client = state["client"]
            run = client.get_run(state["run_id"])
            if pending or state["create_calls"] != 1 or source["final_scoring_call_count"] != 1:
                raise AssertionError("rehearsal failed the one-run/one-scoring fault contract")
            for key in run.data.metrics:
                if len(client.get_metric_history(run.info.run_id, key)) != 1:
                    raise AssertionError("logging recovery duplicated metric history")
            if len(run.inputs.dataset_inputs) != 30:
                raise AssertionError("logging recovery did not retain the exact 30-shard lineage")
            if state["reordered_inputs"] == 0:
                raise AssertionError("rehearsal did not exercise reordered remote dataset tags")
            target = state["target"]
            completed = target.ledger_root / target.spec.identity() / "logging-complete.json"
            receipt = {
                "schema_version": "g8_mlflow_recovery_rehearsal_v1",
                "request_image": source["request_image"],
                "mlflow_run_id": run.info.run_id, "local_mlflow_status": run.info.status,
                "reservation_sha256": target.spec.identity(),
                "logging_complete_sha256": sha256_file(completed),
                "create_run_call_count": state["create_calls"],
                "reserved_before_scoring": state["reserved_before_scoring"],
                "final_scoring_call_count": source["final_scoring_call_count"],
                "faults_recovered": state["faults"], "logging_attempts": state["logging_attempts"],
                "completed_recovery_write_count": state["repeat_writes"],
                "verified_metric_count": len(run.data.metrics),
                "metric_history_exactly_once": True, "verified_dataset_input_count": 30,
                "reordered_dataset_input_read_count": state["reordered_inputs"],
                "artifact_bytes_verified": True, "c4_report_sha256": source["c4_report_sha256"],
                "source_rehearsal_sha256": sha256_file(output / "rehearsal.json"),
                "rehearsal_sha256": sha256_file(Path(__file__)),
                "recovery_module_sha256": sha256_file(Path(recovery.__file__)),
                "evaluation_code_sha256": source["evaluation_code_sha256"],
                "production_test_accessed": False, "production_g8_complete": False,
                "remote_authentication_verified": False, "native_storage_verified": False,
                "pre_logging_payload_retention_verified": False,
            }
            (output / "mlflow-recovery-rehearsal.json").write_text(json.dumps(receipt, indent=2) + "\n")
            return receipt
    finally:
        mlflow.set_tracking_uri(previous_uri)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    print(json.dumps(rehearse_mlflow(parser.parse_args().output), indent=2))
