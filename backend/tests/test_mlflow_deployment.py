from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "docker-compose.yml"
DEPLOYMENT = ROOT / "deployments" / "mlflow"
BOOTSTRAP = ROOT / "scripts" / "bootstrap-mlflow-env.sh"
NEBIUS_BOOTSTRAP = ROOT / "scripts" / "bootstrap-nebius-mlflow-env.sh"
NEBIUS_COMPOSE = DEPLOYMENT / "docker-compose.nebius.yml"
MAKEFILE = ROOT / "Makefile"


def _services() -> dict[str, object]:
    compose = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))
    return compose["services"]


def test_mlflow_profile_uses_pinned_private_stateful_services() -> None:
    services = _services()
    postgres = services["mlflow-postgres"]
    minio = services["mlflow-minio"]
    minio_init = services["mlflow-minio-init"]
    mlflow = services["mlflow"]

    assert postgres["image"] == "postgres:16.10-alpine"
    assert minio["image"] == "quay.io/minio/minio:RELEASE.2025-04-22T22-12-26Z"
    assert minio_init["image"] == "quay.io/minio/mc:RELEASE.2025-04-16T18-13-26Z"
    assert all(
        service["profiles"] == ["mlflow"]
        for service in (postgres, minio, minio_init, mlflow)
    )
    assert "ports" not in postgres
    assert "ports" not in minio
    assert mlflow["ports"] == [
        "${MLFLOW_BIND_ADDRESS:-127.0.0.1}:${MLFLOW_PORT:-5500}:5000"
    ]
    assert postgres["networks"] == ["mlflow-internal"]
    assert minio["networks"] == ["mlflow-internal"]
    assert mlflow["networks"] == ["mlflow-internal", "mlflow-edge"]
    assert minio_init["environment"]["MC_CONFIG_DIR"] == "/tmp/.mc"
    assert minio_init["user"] == "10001:10001"
    assert minio_init["read_only"] is True
    assert minio_init["cap_drop"] == ["ALL"]
    minio_init_script = minio_init["entrypoint"][-1]
    assert "mc anonymous set none" in minio_init_script
    assert 'mc admin user add local "$${MLFLOW_MINIO_ACCESS_KEY}"' in minio_init_script
    assert (
        'mc admin policy attach local readwrite --user "$${MLFLOW_MINIO_ACCESS_KEY}"'
        in minio_init_script
    )


def test_mlflow_metadata_artifacts_auth_and_hardening_are_explicit() -> None:
    services = _services()
    mlflow = services["mlflow"]
    environment = mlflow["environment"]

    assert environment["MLFLOW_POSTGRES_HOST"] == "mlflow-postgres"
    assert environment["MLFLOW_ARTIFACTS_DESTINATION"].startswith("s3://")
    assert environment["MLFLOW_S3_ENDPOINT_URL"] == "http://mlflow-minio:9000"
    assert environment["AWS_ACCESS_KEY_ID"] == (
        "${MLFLOW_MINIO_ACCESS_KEY:-mlflow-artifacts}"
    )
    assert environment["AWS_SECRET_ACCESS_KEY"] == (
        "${MLFLOW_MINIO_SECRET_KEY:-local-compose-validation-only}"
    )
    assert "ROOT" not in environment["AWS_ACCESS_KEY_ID"]
    assert "MLFLOW_ADMIN_PASSWORD" in environment
    assert "MLFLOW_FLASK_SERVER_SECRET_KEY" in environment
    assert "MLFLOW_ALLOWED_HOSTS" in environment
    assert mlflow["read_only"] is True
    assert mlflow["cap_drop"] == ["ALL"]
    assert mlflow["security_opt"] == ["no-new-privileges:true"]
    assert mlflow["depends_on"]["mlflow-postgres"]["condition"] == "service_healthy"
    assert (
        mlflow["depends_on"]["mlflow-minio-init"]["condition"]
        == "service_completed_successfully"
    )

    dockerfile = (DEPLOYMENT / "Dockerfile").read_text(encoding="utf-8")
    assert dockerfile.startswith("FROM ghcr.io/mlflow/mlflow:v3.15.2\n")
    assert '"mlflow[auth]==3.15.2"' in dockerfile
    assert '"psycopg2-binary==2.9.11"' in dockerfile
    assert "USER 10001:10001" in dockerfile

    entrypoint = (DEPLOYMENT / "entrypoint.py").read_text(encoding="utf-8")
    assert 'if "alembic_version" not in tables:' in entrypoint
    assert "_upgrade_db(engine)" in entrypoint
    assert '"--serve-artifacts"' in entrypoint
    assert '"--app-name"' in entrypoint
    assert '"basic-auth"' in entrypoint
    assert '"default_permission": "NO_PERMISSIONS"' in entrypoint
    assert '"grant_default_workspace_access": "false"' in entrypoint
    assert '"validation-only" in value' in entrypoint
    assert 'secret("MLFLOW_FLASK_SERVER_SECRET_KEY", minimum_length=32)' in entrypoint


def test_mlflow_bootstrap_generates_private_untracked_secrets(tmp_path: Path) -> None:
    output = tmp_path / "mlflow.env"
    first = subprocess.run(
        [str(BOOTSTRAP), "--output", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    assert stat.S_IMODE(output.stat().st_mode) == 0o600

    values = dict(
        line.split("=", 1)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    assert len(values["MLFLOW_POSTGRES_PASSWORD"]) >= 48
    assert len(values["MLFLOW_MINIO_ROOT_PASSWORD"]) >= 48
    assert values["MLFLOW_MINIO_ACCESS_KEY"] == "mlflow-artifacts"
    assert len(values["MLFLOW_MINIO_SECRET_KEY"]) >= 48
    assert len(values["MLFLOW_ADMIN_PASSWORD"]) >= 48
    assert len(values["MLFLOW_FLASK_SERVER_SECRET_KEY"]) >= 64
    assert all(
        secret not in first.stdout
        for key, secret in values.items()
        if "PASSWORD" in key or "SECRET" in key
    )

    second = subprocess.run(
        [str(BOOTSTRAP), "--output", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert second.returncode == 1
    assert "refusing to overwrite" in second.stderr

    ignored = subprocess.run(
        ["git", "check-ignore", str(ROOT / "deployments" / "mlflow" / ".env")],
        cwd=ROOT,
        env=os.environ,
        check=False,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0


def test_mlflow_bootstrap_can_add_service_credentials_without_rotating_state(
    tmp_path: Path,
) -> None:
    output = tmp_path / "legacy.env"
    original = (
        "MLFLOW_POSTGRES_PASSWORD=preserve-postgres\n"
        "MLFLOW_MINIO_ROOT_PASSWORD=preserve-minio\n"
    )
    output.write_text(original, encoding="utf-8")

    result = subprocess.run(
        [
            str(BOOTSTRAP),
            "--output",
            str(output),
            "--upgrade-service-credentials",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    updated = output.read_text(encoding="utf-8")
    assert result.returncode == 0, result.stderr
    assert original in updated
    assert "MLFLOW_MINIO_ACCESS_KEY=mlflow-artifacts" in updated
    assert "MLFLOW_MINIO_SECRET_KEY=" in updated
    assert "preserve-postgres" not in result.stdout
    assert "preserve-minio" not in result.stdout
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


def test_mlflow_smoke_provisions_roadmap_resources() -> None:
    bootstrap = (DEPLOYMENT / "bootstrap_resources.py").read_text(encoding="utf-8")
    smoke = (DEPLOYMENT / "smoke_test.py").read_text(encoding="utf-8")

    assert "lob-arena/corpus-releases" in bootstrap
    assert "lob-arena/lightgbm-development" in bootstrap
    assert "lob-arena/governed-evaluation" in bootstrap
    assert "lob-arena-lightgbm-attack-active" in bootstrap
    assert "client.log_metric" in smoke
    assert "client.log_artifact" in smoke
    assert "download_artifacts" in smoke


def test_mlflow_operational_targets_include_initializer_diagnostics() -> None:
    makefile = MAKEFILE.read_text(encoding="utf-8")
    status_target = makefile.split("mlflow-status:", maxsplit=1)[1].split(
        "\n\n", maxsplit=1
    )[0]
    logs_target = makefile.split("mlflow-logs:", maxsplit=1)[1].split(
        "\n\n", maxsplit=1
    )[0]
    diagnostic_services = {
        "mlflow",
        "mlflow-exporter",
        "mlflow-exporter-init",
        "mlflow-postgres",
        "mlflow-minio",
        "mlflow-minio-init",
    }

    assert " ps -a " in status_target
    assert " logs --tail=200 " in logs_target
    assert diagnostic_services <= set(status_target.split())
    assert diagnostic_services <= set(logs_target.split())


def test_nebius_mlflow_profile_uses_object_storage_without_minio() -> None:
    compose = yaml.safe_load(NEBIUS_COMPOSE.read_text(encoding="utf-8"))
    services = compose["services"]

    assert "mlflow-minio" not in services
    assert "mlflow-minio-init" not in services
    assert services["mlflow"]["depends_on"] == {
        "mlflow-postgres": {"condition": "service_healthy"}
    }
    environment = services["mlflow"]["environment"]
    assert environment["MLFLOW_S3_ENDPOINT_URL"] == "${MLFLOW_S3_ENDPOINT_URL:?required}"
    assert environment["MLFLOW_ARTIFACTS_DESTINATION"].startswith("s3://")
    assert environment["AWS_ACCESS_KEY_ID"] == "${AWS_ACCESS_KEY_ID:?required}"
    assert environment["AWS_SECRET_ACCESS_KEY"] == "${AWS_SECRET_ACCESS_KEY:?required}"
    assert services["mlflow-postgres"]["networks"] == ["mlflow-internal"]
    assert services["mlflow"]["ports"] == [
        "${MLFLOW_BIND_ADDRESS:-0.0.0.0}:${MLFLOW_PORT:-5500}:5000"
    ]


def test_nebius_mlflow_bootstrap_reads_s3_secret_from_stdin(tmp_path: Path) -> None:
    output = tmp_path / "nebius-mlflow.env"
    secret = "s" * 48
    result = subprocess.run(
        [
            str(NEBIUS_BOOTSTRAP),
            "--output",
            str(output),
            "--access-key-id",
            "NAKIREDACTED",
            "--bucket",
            "aimada-mlflow-e00g6zvxpr00",
            "--private-host",
            "10.0.0.10",
        ],
        input=f"{secret}\n",
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    values = dict(
        line.split("=", 1)
        for line in output.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    assert values["MLFLOW_S3_BUCKET"] == "aimada-mlflow-e00g6zvxpr00"
    assert values["MLFLOW_S3_ENDPOINT_URL"] == (
        "https://storage.eu-north1.nebius.cloud"
    )
    assert values["AWS_ACCESS_KEY_ID"] == "NAKIREDACTED"
    assert values["AWS_SECRET_ACCESS_KEY"] == secret
    assert "10.0.0.10:*" in values["MLFLOW_ALLOWED_HOSTS"]
    assert secret not in result.stdout
