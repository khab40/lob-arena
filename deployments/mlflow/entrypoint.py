from __future__ import annotations

import configparser
import os
from pathlib import Path
from urllib.parse import quote_plus

from mlflow.store.db.utils import _upgrade_db
from sqlalchemy import create_engine, inspect


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


def boolean(name: str, default: str = "false") -> bool:
    value = os.environ.get(name, default).strip().lower()
    if value not in {"true", "false"}:
        raise SystemExit(f"{name} must be true or false")
    return value == "true"


def postgres_uri() -> str:
    user = quote_plus(required("MLFLOW_POSTGRES_USER"))
    password = quote_plus(secret("MLFLOW_POSTGRES_PASSWORD"))
    host = required("MLFLOW_POSTGRES_HOST")
    port = required("MLFLOW_POSTGRES_PORT")
    database = quote_plus(required("MLFLOW_POSTGRES_DB"))
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"


def write_auth_config(uri: str) -> Path:
    config = configparser.ConfigParser(interpolation=None)
    config["mlflow"] = {
        "default_permission": "NO_PERMISSIONS",
        "grant_default_workspace_access": "false",
        "database_uri": uri,
        "admin_username": required("MLFLOW_ADMIN_USERNAME"),
        "admin_password": secret("MLFLOW_ADMIN_PASSWORD"),
        "authorization_function": "mlflow.server.auth:authenticate_request_basic_auth",
    }
    path = Path("/tmp/mlflow-auth.ini")
    with path.open("w", encoding="utf-8") as output:
        config.write(output)
    path.chmod(0o600)
    return path


def upgrade_existing_schema(uri: str) -> None:
    engine = create_engine(uri)
    try:
        tables = set(inspect(engine).get_table_names())
        if "alembic_version" not in tables:
            print("Fresh MLflow database detected; server will initialize it.", flush=True)
            return
        print("Applying MLflow database migrations.", flush=True)
        _upgrade_db(engine)
    finally:
        engine.dispose()


def main() -> None:
    secret("MLFLOW_FLASK_SERVER_SECRET_KEY", minimum_length=32)
    secret("AWS_SECRET_ACCESS_KEY")
    uri = postgres_uri()
    auth_config = write_auth_config(uri)
    os.environ["MLFLOW_AUTH_CONFIG_PATH"] = str(auth_config)

    upgrade_existing_schema(uri)

    command = [
        "mlflow",
        "server",
        "--host",
        "0.0.0.0",
        "--port",
        "5000",
        "--workers",
        required("MLFLOW_SERVER_WORKERS"),
        "--backend-store-uri",
        uri,
        "--serve-artifacts",
        "--artifacts-destination",
        required("MLFLOW_ARTIFACTS_DESTINATION"),
        "--allowed-hosts",
        required("MLFLOW_ALLOWED_HOSTS"),
        "--cors-allowed-origins",
        required("MLFLOW_CORS_ALLOWED_ORIGINS"),
        "--app-name",
        "basic-auth",
    ]
    if boolean("MLFLOW_ENABLE_WORKSPACES"):
        command.append("--enable-workspaces")

    print("Starting authenticated MLflow tracking server.", flush=True)
    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
