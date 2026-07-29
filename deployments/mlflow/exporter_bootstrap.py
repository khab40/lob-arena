from __future__ import annotations

import os
from typing import Any


def required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"required environment variable is empty: {name}")
    return value


def secret(name: str, minimum_length: int = 16) -> str:
    value = required(name)
    if "validation-only" in value or "replace-with-generated-secret" in value:
        raise SystemExit(f"{name} contains a non-deployment placeholder")
    if len(value) < minimum_length:
        raise SystemExit(f"{name} must contain at least {minimum_length} characters")
    return value


def _csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    values = default if raw is None else tuple(item.strip() for item in raw.split(",") if item.strip())
    values = tuple(dict.fromkeys(values))
    if not values:
        raise SystemExit(f"{name} must contain at least one value")
    return values


def _configure_admin() -> tuple[Any, Any]:
    import mlflow
    from mlflow import MlflowClient
    from mlflow.server.auth.client import AuthServiceClient

    tracking_uri = required("MLFLOW_TRACKING_URI")
    os.environ["MLFLOW_TRACKING_USERNAME"] = required("MLFLOW_ADMIN_USERNAME")
    os.environ["MLFLOW_TRACKING_PASSWORD"] = secret("MLFLOW_ADMIN_PASSWORD")
    mlflow.set_tracking_uri(tracking_uri)
    return MlflowClient(tracking_uri=tracking_uri), AuthServiceClient(tracking_uri)


def _ensure_exporter_user(auth_client: Any, username: str, password: str) -> Any:
    try:
        user = auth_client.get_user(username)
    except Exception as error:
        if getattr(error, "error_code", None) != "RESOURCE_DOES_NOT_EXIST":
            raise
        user = auth_client.create_user(username, password)
        if user.is_admin:
            raise RuntimeError("MLflow exporter user must not be an administrator")
        print(f"Created non-admin MLflow exporter user {username}.")
    else:
        if user.is_admin:
            raise RuntimeError("MLflow exporter user must not be an administrator")
        auth_client.update_user_password(username, password)
        print(f"Updated MLflow exporter credentials for {username}.")
    return user


def _reconcile_permissions(
    auth_client: Any,
    user: Any,
    desired_permissions: set[tuple[str, str]],
) -> None:
    personal_role_name = f"__user_{user.id}__"
    personal_role = next(
        (role for role in auth_client.list_all_roles() if role.name == personal_role_name),
        None,
    )
    current_permissions = (
        auth_client.list_role_permissions(personal_role.id)
        if personal_role is not None
        else []
    )
    current_by_resource = {
        (permission.resource_type, permission.resource_pattern): permission.permission
        for permission in current_permissions
    }

    managed_resource_types = {"experiment", "registered_model"}
    for permission in current_permissions:
        key = (permission.resource_type, permission.resource_pattern)
        if permission.resource_type in managed_resource_types and key not in desired_permissions:
            auth_client.revoke_user_permission(
                user.username,
                resource_type=permission.resource_type,
                resource_id=permission.resource_pattern,
            )
            print(
                "Revoked stale MLflow exporter permission "
                f"{permission.resource_type}:{permission.resource_pattern}."
            )

    for resource_type, resource_id in sorted(desired_permissions):
        current_permission = current_by_resource.get((resource_type, resource_id))
        if current_permission == "READ":
            continue
        if current_permission is not None:
            auth_client.revoke_user_permission(
                user.username,
                resource_type=resource_type,
                resource_id=resource_id,
            )
        auth_client.grant_user_permission(
            user.username,
            resource_type=resource_type,
            resource_id=resource_id,
            permission="READ",
        )

def main() -> None:
    from bootstrap_resources import (
        EXPERIMENTS,
        REGISTERED_MODEL,
        main as bootstrap_resources,
    )

    bootstrap_resources()
    tracking_client, auth_client = _configure_admin()
    user = _ensure_exporter_user(
        auth_client,
        required("MLFLOW_EXPORTER_USERNAME"),
        secret("MLFLOW_EXPORTER_PASSWORD"),
    )

    experiments = _csv("MLFLOW_EXPORTER_EXPERIMENTS", EXPERIMENTS)
    models = _csv("MLFLOW_EXPORTER_MODEL_NAMES", (REGISTERED_MODEL,))
    experiment_ids: dict[str, str] = {}
    for experiment_name in experiments:
        experiment = tracking_client.get_experiment_by_name(experiment_name)
        if experiment is None:
            raise RuntimeError(f"configured MLflow exporter experiment does not exist: {experiment_name}")
        experiment_ids[experiment_name] = experiment.experiment_id

    for model_name in models:
        tracking_client.get_registered_model(model_name)

    desired_permissions = {
        *{("experiment", experiment_id) for experiment_id in experiment_ids.values()},
        *{("registered_model", model_name) for model_name in models},
    }
    _reconcile_permissions(auth_client, user, desired_permissions)

    for experiment_name in experiments:
        print(f"Granted MLflow exporter READ access to experiment {experiment_name}.")

    for model_name in models:
        print(f"Granted MLflow exporter READ access to registered model {model_name}.")


if __name__ == "__main__":
    main()
