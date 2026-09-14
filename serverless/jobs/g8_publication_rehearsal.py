"""Offline post-MLflow checkpoint/publication rehearsal; no live access."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

from app.ml.lightgbm import cloud_runner, g8_publication_recovery as recovery
from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest

class FakeS3:
    """Matches the frozen positional-only helper, with real bytes and fault injection."""

    def __init__(self, source, binding):
        self.prefix = binding.result_uri.removeprefix("s3://").split("/", 1)[1]
        run_id = self.prefix.rsplit("/", 1)[1]
        self.intent = self.prefix.rsplit("/", 1)[0] + "/.intents/" + run_id + ".json"
        self.objects = {self.intent: (source / "request.json").read_bytes()}
        self.metadata = {self.intent: {"request-sha256": binding.request_sha256}}
        self.calls = []
        self.fail_put = None
        self.lose_response = None

    def aws(self, endpoint, *args):
        assert endpoint == recovery.ENDPOINT
        operation = args[1]
        self.calls.append(args)
        if operation == "list-objects-v2":
            assert args[args.index("--prefix") + 1] == self.prefix + "/"
            return {"Contents": [{"Key": k} for k in sorted(self.objects) if k.startswith(self.prefix + "/")]}
        key = args[args.index("--key") + 1]
        if operation == "put-object":
            assert args[args.index("--if-none-match") + 1] == "*"
            if key == self.fail_put:
                raise RuntimeError("injected PUT failure before persistence")
            if key in self.objects:
                raise RuntimeError("PreconditionFailed")
            self.objects[key] = Path(args[args.index("--body") + 1]).read_bytes()
            self.metadata[key] = {"sha256": args[args.index("--metadata") + 1].removeprefix("sha256=")}
            if key == self.lose_response:
                raise RuntimeError("injected response loss after persistence")
            return {}
        if operation == "head-object":
            if key not in self.objects:
                raise RuntimeError("NoSuchKey")
            return {"ContentLength": len(self.objects[key]), "Metadata": self.metadata[key]}
        if operation == "get-object":
            Path(args[-1]).write_bytes(self.objects[key])
            return {}
        raise AssertionError("forbidden remote operation: " + operation)


def rehearse_recovery(output: Path) -> dict:
    from mlflow import MlflowClient
    import mlflow
    from g8_rehearsal import rehearse

    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    base = output / "scoring"
    previous = mlflow.get_tracking_uri()
    try:
        scored = rehearse(base, Path(__file__).with_name("run_lightgbm_g8.py"), c4=True)
    finally:
        mlflow.set_tracking_uri(previous)
    source = base / "published"
    request = LightGbmCloudJobRequest.model_validate_json((source / "request.json").read_bytes())
    binding = recovery.RecoveryBinding(
        execution_package_sha256=sha256_file(Path(__file__)),
        request_sha256=request.canonical_hash(), candidate_sha256=request.candidate.sha256,
        c4_report_sha256=scored["c4_report_sha256"], mlflow_run_id=scored["mlflow_run_id"],
        result_uri=request.result_uri,
    )
    checkpoint = output / "checkpoint"
    digest = recovery.retain_completed_release(source, checkpoint, binding=binding)
    binding_file = output / "synthetic-recovery-binding.json"
    binding_file.write_text(binding.model_dump_json(indent=2))
    # Remove the original path without destroying the original engineering evidence.
    source.rename(base / "retired-original-release")
    cli = Path(__file__).with_name("recover_lightgbm_g8_publication.py")
    child = subprocess.run(
        [sys.executable, str(cli), "--checkpoint", str(checkpoint), "--checkpoint-sha256", digest,
         "--binding", str(binding_file)], check=True, capture_output=True, text=True,
    )
    if not json.loads(child.stdout)["checkpoint_verified"]:
        raise AssertionError("new-process checkpoint verification failed")
    inventory = recovery.verify_checkpoint(checkpoint, expected_sha256=digest, binding=binding).inventory.files
    outcomes = {}
    for fault in ("middle_put", "lost_response", "marker"):
        fake = FakeS3(checkpoint / "payload", binding)
        key = fake.prefix + "/" + inventory[3].path
        if fault == "lost_response":
            fake.lose_response = key
        else:
            fake.fail_put = fake.prefix + "/SUCCESS" if fault == "marker" else key
        with (
            patch.object(recovery.storage, "_aws_json", fake.aws),
            patch.object(cloud_runner, "predict_governed_fold", side_effect=AssertionError("rescoring forbidden")),
            patch.object(mlflow, "start_run", side_effect=AssertionError("MLflow writes forbidden")),
        ):
            if fault != "lost_response":
                try:
                    recovery.resume_publication(checkpoint, expected_sha256=digest, binding=binding)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("injected publication failure did not occur")
                if len(fake.objects) <= 1 or fake.prefix + "/SUCCESS" in fake.objects:
                    raise AssertionError("partial publication was not preserved")
                fake.fail_put = None
            receipt = recovery.resume_publication(checkpoint, expected_sha256=digest, binding=binding)
            repeated = recovery.resume_publication(checkpoint, expected_sha256=digest, binding=binding)
            if repeated["conditionally_published_objects"] != 0:
                raise AssertionError("idempotent recovery wrote new objects")
            puts = [a[a.index("--key") + 1] for a in fake.calls if a[1] == "put-object"]
            if puts[-1] != fake.prefix + "/SUCCESS" or (fault == "lost_response" and puts.count(key) != 1):
                raise AssertionError("marker order or lost-response recovery failed")
        outcomes[fault] = receipt
    with patch.dict(os.environ, {"MLFLOW_ALLOW_FILE_STORE": "true"}):
        client = MlflowClient(tracking_uri=(base / "mlruns").as_uri())
        experiment = client.get_experiment_by_name("lob-arena/governed-evaluation")
        runs = client.search_runs([experiment.experiment_id])
        if len(runs) != 1 or runs[0].info.run_id != binding.mlflow_run_id or runs[0].info.status != "FINISHED":
            raise AssertionError("MLflow run identity/status changed")
    result = dict(
        schema_version="g8_synthetic_publication_recovery_v1",
        request_image=scored["request_image"],
        scoring_receipt_sha256=sha256_file(base / "rehearsal.json"),
        recovery_module_sha256=sha256_file(Path(recovery.__file__)),
        recovery_cli_sha256=sha256_file(cli),
        rehearsal_sha256=sha256_file(Path(__file__)),
        checkpoint_sha256=digest,
        c4_report_sha256=binding.c4_report_sha256,
        mlflow_run_id=binding.mlflow_run_id,
        final_scoring_call_count=scored["final_scoring_call_count"],
        local_mlflow_run_count=1,
        source_path_unavailable=True,
        new_process_checkpoint_verified=True,
        fault_cases=outcomes,
        production_test_accessed=False,
        remote_storage_verified=False,
        native_storage_durability_verified=False,
        mlflow_interruption_recovery_verified=False,
        production_g8_complete=False,
    )
    (output / "publication-recovery-rehearsal.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(rehearse_recovery(parser.parse_args().output), indent=2))
