from __future__ import annotations

import os
from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).resolve().parents[2]
ROTATE = ROOT / "scripts" / "rotate-secrets.sh"
CHECK = ROOT / "scripts" / "check-secrets.sh"
CONFIGURE_ARTIFACTS = ROOT / "scripts" / "configure-nebius-artifact-storage.sh"
PROVISION_WAVE1 = ROOT / "scripts" / "provision-nebius-wave1-identities.sh"


def _run(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(script), *args],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "LC_ALL": "C"},
    )


def test_rotation_dry_run_does_not_modify_or_print_secrets(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    original = "ENDPOINT_TOKEN=old-token\nKEEP=value\n"
    env_file.write_text(original, encoding="utf-8")

    result = _run(ROTATE, "--env-file", str(env_file))

    assert result.returncode == 0
    assert env_file.read_text(encoding="utf-8") == original
    assert "old-token" not in result.stdout
    assert "Dry-run only" in result.stdout


def test_rotation_applies_generated_and_imported_values(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# local config\nENDPOINT_TOKEN=old\nKEEP=value\n",
        encoding="utf-8",
    )
    imported = tmp_path / "provider.env"
    imported.write_text(
        "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID=new-id\n"
        "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY=new-secret\n",
        encoding="utf-8",
    )

    result = _run(
        ROTATE,
        "--env-file",
        str(env_file),
        "--import-env",
        str(imported),
        "--apply",
    )

    updated = env_file.read_text(encoding="utf-8")
    assert result.returncode == 0
    assert "ENDPOINT_TOKEN=old" not in updated
    assert "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID=new-id" in updated
    assert "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY=new-secret" in updated
    assert "KEEP=value" in updated
    assert env_file.stat().st_mode & 0o777 == 0o600


def test_rotation_rejects_unknown_import_key(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("ENDPOINT_TOKEN=old\n", encoding="utf-8")
    imported = tmp_path / "provider.env"
    imported.write_text("UNSAFE_UNKNOWN=value\n", encoding="utf-8")

    result = _run(ROTATE, "--env-file", str(env_file), "--import-env", str(imported), "--apply")

    assert result.returncode == 2
    assert "not allowed" in result.stderr


def test_check_accepts_rotated_temp_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"

    entries = {
        "_".join(("ENDPOINT", "TOKEN")): "".join(("01234567", "89abcdef")),
    }

    env_file.write_text(
        "".join(f"{key}={value}\n" for key, value in entries.items()),
        encoding="utf-8",
    )

    result = _run(CHECK, str(env_file))

    assert result.returncode == 0, (
        f"stdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert "Secret checks passed" in result.stdout


def test_check_accepts_empty_endpoint_token_when_serverless_is_disabled(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NEBIUS_SERVERLESS_ENABLED=false\nENDPOINT_TOKEN=\n",
        encoding="utf-8",
    )

    result = _run(CHECK, str(env_file))

    assert result.returncode == 0, result.stderr
    assert "Secret checks passed" in result.stdout


def test_check_rejects_retained_endpoint_token_when_serverless_is_disabled(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NEBIUS_SERVERLESS_ENABLED=false\nENDPOINT_TOKEN=stale-provider-token\n",
        encoding="utf-8",
    )

    result = _run(CHECK, str(env_file))

    assert result.returncode == 1
    assert "must be empty" in result.stderr


def test_check_requires_endpoint_token_when_serverless_is_enabled(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NEBIUS_SERVERLESS_ENABLED=true\nENDPOINT_TOKEN=\n",
        encoding="utf-8",
    )

    result = _run(CHECK, str(env_file))

    assert result.returncode == 1
    assert "is required" in result.stderr


def test_artifact_storage_dry_run_does_not_modify_env(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    original = "KEEP=value\n"
    env_file.write_text(original, encoding="utf-8")

    result = _run(
        CONFIGURE_ARTIFACTS,
        "--env-file",
        str(env_file),
        "--project-id",
        "project-test",
        "--tenant-id",
        "tenant-test",
        "--bucket-name",
        "aimada-test-artifacts",
    )

    assert result.returncode == 0
    assert env_file.read_text(encoding="utf-8") == original
    assert "Dry-run only" in result.stdout


def test_artifact_storage_requires_apply_before_restart(tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("KEEP=value\n", encoding="utf-8")

    result = _run(
        CONFIGURE_ARTIFACTS,
        "--env-file",
        str(env_file),
        "--project-id",
        "project-test",
        "--tenant-id",
        "tenant-test",
        "--bucket-name",
        "aimada-test-artifacts",
        "--restart",
    )

    assert result.returncode == 2
    assert "--restart requires --apply" in result.stderr


def test_wave1_identity_dry_run_is_local_and_shows_exact_boundaries(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    result = _run(
        PROVISION_WAVE1,
        "--campaign-id",
        "wave1-research-20260816",
        "--state-file",
        str(state_file),
    )

    assert result.returncode == 0, result.stderr
    assert not state_file.exists()
    assert "Dry-run only" in result.stdout
    assert "no policy on aimada-wave1-final-e00g6zvxpr00" in result.stdout
    assert "campaigns/wave1-research-20260816/development/*" in result.stdout
    assert "campaigns/wave1-research-20260816/final/*" in result.stdout
    assert "access key deactivated" in result.stdout


def test_wave1_identity_script_uses_current_non_inline_secret_flow() -> None:
    source = PROVISION_WAVE1.read_text(encoding="utf-8")

    assert "iam v2 access-key create" in source
    assert "--secret-delivery-mode mystery_box" in source
    assert "iam v2 access-key get-secret" not in source
    assert "iam access-key create" not in source
    assert "group-membership create" in source
    assert "--member-id \"${service_account_id}\"" in source
    assert "--name editors" not in source
    assert "job_mounts" not in source
    assert "job_s3_api" in source
    assert "access_id_secret_reference_id" in source
    assert "secret_key_secret_reference_id" in source


def test_wave1_identity_script_rejects_wrong_project_and_region() -> None:
    wrong_project = _run(
        PROVISION_WAVE1,
        "--campaign-id",
        "wave1-research-20260816",
        "--project-id",
        "project-wrong",
    )
    wrong_region = _run(
        PROVISION_WAVE1,
        "--campaign-id",
        "wave1-research-20260816",
        "--region",
        "eu-west1",
    )

    assert wrong_project.returncode == 2
    assert "project ID is fixed" in wrong_project.stderr
    assert wrong_region.returncode == 2
    assert "region must be eu-north1" in wrong_region.stderr


def test_wave1_identity_apply_never_treats_lookup_failure_as_not_found(tmp_path: Path) -> None:
    fake_nebius = tmp_path / "nebius"
    command_log = tmp_path / "commands.log"
    fake_nebius.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >>\"${FAKE_NEBIUS_LOG}\"\n"
        "if [[ \"$*\" == *\"iam project get\"* ]]; then\n"
        "  printf '%s\\n' '{\"metadata\":{\"parent_id\":\"tenant-test\"}}'\n"
        "  exit 0\n"
        "fi\n"
        "printf '%s\\n' 'rpc error: code = Unavailable desc = simulated failure' >&2\n"
        "exit 1\n",
        encoding="utf-8",
    )
    fake_nebius.chmod(0o700)
    result = subprocess.run(
        [
            "bash",
            str(PROVISION_WAVE1),
            "--campaign-id",
            "wave1-research-20260816",
            "--apply",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "PATH": f"{tmp_path}:{os.environ['PATH']}",
            "FAKE_NEBIUS_LOG": str(command_log),
            "LC_ALL": "C",
        },
    )

    commands = command_log.read_text(encoding="utf-8")
    assert result.returncode == 70
    assert "Nebius lookup failed; no create fallback was attempted" in result.stderr
    assert "service-account get-by-name" in commands
    assert "service-account create" not in commands


def test_real_nebius_compose_passes_object_storage_credentials() -> None:
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    environment = compose["services"]["backend"]["environment"]

    assert "NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID" in environment
    assert "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY" in environment
    assert "NEBIUS_OBJECT_STORAGE_SESSION_TOKEN" in environment
    assert "NEBIUS_OBJECT_STORAGE_REGION" in environment
