from __future__ import annotations

import os

import mlflow
from mlflow import MlflowClient
from mlflow.exceptions import MlflowException


EXPERIMENTS = (
    "lob-arena/corpus-releases",
    "lob-arena/lightgbm-development",
    "lob-arena/governed-evaluation",
)
REGISTERED_MODEL = "lob-arena-lightgbm-attack-active"


def configure_client() -> MlflowClient:
    os.environ["MLFLOW_TRACKING_USERNAME"] = os.environ["MLFLOW_ADMIN_USERNAME"]
    os.environ["MLFLOW_TRACKING_PASSWORD"] = os.environ["MLFLOW_ADMIN_PASSWORD"]
    tracking_uri = os.environ.get("MLFLOW_TRACKING_URI", "http://127.0.0.1:5000")
    mlflow.set_tracking_uri(tracking_uri)
    return MlflowClient(tracking_uri=tracking_uri)


def main() -> None:
    client = configure_client()
    for name in EXPERIMENTS:
        if client.get_experiment_by_name(name) is None:
            experiment_id = client.create_experiment(
                name,
                tags={
                    "lob_arena.governance": "required",
                    "lob_arena.lifecycle": "shared-tracking",
                },
            )
            print(f"Created MLflow experiment {name} ({experiment_id}).")
        else:
            print(f"MLflow experiment already exists: {name}.")

    try:
        client.create_registered_model(
            REGISTERED_MODEL,
            tags={
                "lob_arena.target": "attack_active",
                "lob_arena.release_contract": "lightgbm-phase0-v1",
            },
            description=(
                "Governed binary attack_active LightGBM releases. Production aliases "
                "must refer only to checksum-verified release bundles."
            ),
        )
        print(f"Created MLflow registered model {REGISTERED_MODEL}.")
    except MlflowException as error:
        if "already exists" not in str(error).lower():
            raise
        print(f"MLflow registered model already exists: {REGISTERED_MODEL}.")


if __name__ == "__main__":
    main()
