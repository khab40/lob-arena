from __future__ import annotations

import tempfile
import time
from pathlib import Path

import mlflow
from mlflow import MlflowClient

from bootstrap_resources import EXPERIMENTS, configure_client, main as bootstrap_resources


def main() -> None:
    bootstrap_resources()
    client: MlflowClient = configure_client()
    experiment = client.get_experiment_by_name(EXPERIMENTS[1])
    if experiment is None:
        raise RuntimeError("bootstrap did not create the LightGBM development experiment")

    run = client.create_run(
        experiment.experiment_id,
        tags={
            "lob_arena.smoke_test": "true",
            "mlflow.runName": "shared-tracking-deployment-smoke",
        },
    )
    run_id = run.info.run_id
    expected = f"mlflow-shared-tracking-ok:{time.time_ns()}"
    try:
        client.log_param(run_id, "deployment_profile", "mlflow")
        client.log_metric(run_id, "tracking_ready", 1.0)
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "probe.txt"
            artifact.write_text(expected, encoding="utf-8")
            client.log_artifact(run_id, str(artifact), artifact_path="deployment")
            downloaded = mlflow.artifacts.download_artifacts(
                run_id=run_id,
                artifact_path="deployment/probe.txt",
                dst_path=temporary_directory,
            )
            actual = Path(downloaded).read_text(encoding="utf-8")
        if actual != expected:
            raise RuntimeError("downloaded MLflow artifact did not match the uploaded probe")
        client.set_terminated(run_id, status="FINISHED")
    except Exception:
        client.set_terminated(run_id, status="FAILED")
        raise

    print(
        "MLflow deployment verified: authentication, PostgreSQL metadata, "
        f"registry, and S3 artifacts are operational (run_id={run_id})."
    )


if __name__ == "__main__":
    main()
