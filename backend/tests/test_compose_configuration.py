from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "docker-compose.yml"
ENTRYPOINT = ROOT / "backend" / "compose-entrypoint.sh"


def _compose() -> dict[str, object]:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def _entrypoint_environment(enabled: str) -> dict[str, str]:
    keys = (
        "NEBIUS_ENDPOINT_MODE",
        "NEBIUS_ENDPOINT_BASE_URL",
        "NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE",
        "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY",
        "NEBIUS_EVIDENCE_ARCHIVE_ENABLED",
    )
    probe = "import json, os; print(json.dumps({key: os.environ.get(key) for key in " + repr(keys) + "}))"
    result = subprocess.run(
        ["sh", str(ENTRYPOINT), "python", "-c", probe],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "NEBIUS_SERVERLESS_ENABLED": enabled,
            "NEBIUS_ENDPOINT_MODE": "local_vllm",
            "NEBIUS_ENDPOINT_BASE_URL": "https://endpoint.example.test",
            "NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE": "submit {job_args}",
            "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY": "secret",
            "NEBIUS_EVIDENCE_ARCHIVE_ENABLED": "true",
        },
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_single_compose_file_contains_conditional_serverless_configuration() -> None:
    compose = _compose()
    backend = compose["services"]["backend"]

    assert sorted(path.name for path in ROOT.glob("docker-compose*.yml")) == ["docker-compose.yml"]
    assert backend["build"]["args"]["INSTALL_NEBIUS_CLI"] == "${NEBIUS_SERVERLESS_ENABLED:-false}"
    assert backend["environment"]["NEBIUS_SERVERLESS_ENABLED"] == "${NEBIUS_SERVERLESS_ENABLED:-false}"
    assert backend["environment"]["NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE"] == "${NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE:-}"
    assert backend["environment"]["NEBIUS_MARKET_ABUSE_SCENARIO_URL"] == "${NEBIUS_MARKET_ABUSE_SCENARIO_URL:-}"
    assert backend["volumes"][-2:] == [
        "${NEBIUS_CLI_CONFIG_DIR:-./deployments/nebius-cli-empty}/config.yaml:/root/.nebius/config.yaml:ro",
        "${NEBIUS_CLI_CONFIG_DIR:-./deployments/nebius-cli-empty}/credentials.yaml:/root/.nebius/credentials.yaml:ro",
    ]


def test_observability_profiles_support_prometheus_alone_or_grafana_stack() -> None:
    services = _compose()["services"]

    assert services["prometheus"]["profiles"] == ["prometheus", "grafana", "monitoring"]
    assert services["grafana"]["profiles"] == ["grafana", "monitoring"]
    assert "prometheus" in services["grafana"]["depends_on"]


def test_java_kernel_has_explicit_heap_container_and_duckdb_budgets() -> None:
    java = _compose()["services"]["java-kernel"]

    assert java["mem_limit"] == "${JAVA_KERNEL_MEMORY_LIMIT:-4g}"
    assert "-Xmx2g" in java["environment"]["JAVA_TOOL_OPTIONS"]
    assert "-XX:MaxDirectMemorySize=256m" in java["environment"]["JAVA_TOOL_OPTIONS"]
    assert java["environment"]["LOB_ARENA_EVENT_HISTORY_CAPACITY"] == (
        "${LOB_ARENA_EVENT_HISTORY_CAPACITY:-50000}"
    )
    assert java["environment"]["LOB_ARENA_DUCKDB_MEMORY_LIMIT"] == (
        "${LOB_ARENA_DUCKDB_MEMORY_LIMIT:-1GB}"
    )
    assert java["environment"]["LOB_ARENA_DUCKDB_MAX_TEMP_DIRECTORY_SIZE"] == (
        "${LOB_ARENA_DUCKDB_MAX_TEMP_DIRECTORY_SIZE:-8GB}"
    )


def test_detector_tournament_dashboard_uses_bounded_prometheus_metrics() -> None:
    dashboard_path = (
        Path(__file__).resolve().parents[2]
        / "monitoring"
        / "grafana"
        / "dashboards"
        / "lob-arena-detector-tournaments.json"
    )
    dashboard = json.loads(dashboard_path.read_text(encoding="utf-8"))
    expressions = [
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    ]
    rendered = "\n".join(expressions)

    assert dashboard["title"] == "LOB Arena Detector Tournaments"
    assert dashboard["uid"] == "lob-arena-detector-tournaments"
    assert "detector_tournament_in_flight" in rendered
    assert "detector_tournament_runs_total" in rendered
    assert "detector_tournament_duration_seconds_bucket" in rendered
    assert "detector_tournament_scenarios_total" in rendered
    assert "detector_tournament_artifact_collections_total" in rendered
    assert "tournament_id" not in rendered
    assert "job_id" not in rendered


def test_disabled_serverless_mode_clears_stale_cloud_configuration() -> None:
    environment = _entrypoint_environment("false")

    assert environment == {
        "NEBIUS_ENDPOINT_MODE": "mock",
        "NEBIUS_ENDPOINT_BASE_URL": "",
        "NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE": "",
        "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY": "",
        "NEBIUS_EVIDENCE_ARCHIVE_ENABLED": "false",
    }


def test_enabled_serverless_mode_preserves_cloud_configuration() -> None:
    environment = _entrypoint_environment("true")

    assert environment == {
        "NEBIUS_ENDPOINT_MODE": "local_vllm",
        "NEBIUS_ENDPOINT_BASE_URL": "https://endpoint.example.test",
        "NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE": "submit {job_args}",
        "NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY": "secret",
        "NEBIUS_EVIDENCE_ARCHIVE_ENABLED": "true",
    }


def test_invalid_serverless_switch_fails_closed() -> None:
    result = subprocess.run(
        ["sh", str(ENTRYPOINT), "true"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "NEBIUS_SERVERLESS_ENABLED": "sometimes"},
    )

    assert result.returncode == 2
    assert "Invalid NEBIUS_SERVERLESS_ENABLED" in result.stderr
