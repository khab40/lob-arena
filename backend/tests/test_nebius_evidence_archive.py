import json
import subprocess
import time
from pathlib import Path
from typing import Any

from app.config import Settings
from app.nebius.client import NebiusClient
from app.nebius.evidence_archive import (
    NebiusEvidenceArchive,
    _redact,
    clear_default_evidence_archive,
    configure_default_evidence_archive,
)
from app.storage.local_store import LocalStore


class FakeResponse:
    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(
            {
                "scenario_type": "spoofing_like_wall",
                "title": "Synthetic scenario",
                "description": "Test response",
                "parameters": {},
                "expected_detector_risk": 0.5,
                "safety_note": "Synthetic only",
            }
        ).encode("utf-8")


def test_endpoint_calls_are_written_locally_and_redacted(monkeypatch: Any, tmp_path: Path) -> None:
    archive = configure_default_evidence_archive(LocalStore(tmp_path), Settings(_env_file=None))
    monkeypatch.setattr("app.nebius.client.urlopen", lambda *_args, **_kwargs: FakeResponse())
    try:
        response = NebiusClient(scenario_generator_url="https://endpoint.example/generate-scenario").generate_red_team_scenario(
            "Generate a synthetic scenario",
            {"api_token": "must-not-leak"},
        )
    finally:
        clear_default_evidence_archive()

    records = archive.list_records()
    assert response.mode == "nebius"
    assert len(records) == 1
    assert records[0].kind == "endpoint_call"
    assert records[0].s3_status == "local_only"
    request_text = Path(records[0].artifact_paths["request"]).read_text(encoding="utf-8")
    assert "must-not-leak" not in request_text
    assert "[REDACTED]" in request_text


def test_redaction_rejects_polynomial_backtracking_input_quickly() -> None:
    adversarial_non_match = '"aws_access_key_id"' + (" " * 20_000) + "x"

    started = time.perf_counter()
    redacted = _redact(adversarial_non_match)
    elapsed = time.perf_counter() - started

    assert redacted == adversarial_non_match
    assert elapsed < 0.5


def test_redaction_preserves_supported_aws_credential_shapes() -> None:
    value = (
        '{"name":"AWS_ACCESS_KEY_ID","value":"access-value"},'
        '"AWS_SECRET_ACCESS_KEY": "secret-value" '
        "AWS_SESSION_TOKEN=session-value"
    )

    redacted = _redact(value)

    assert "access-value" not in redacted
    assert "secret-value" not in redacted
    assert "session-value" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_job_evidence_uploads_and_syncs_with_object_storage(monkeypatch: Any, tmp_path: Path) -> None:
    commands: list[list[str]] = []

    def fake_run(argv: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    settings = Settings(
        _env_file=None,
        NEBIUS_EVIDENCE_ARCHIVE_ENABLED=True,
        NEBIUS_JOB_OUTPUT_URI="s3://lob-arena-artifacts/lob-arena",
        NEBIUS_OBJECT_STORAGE_ENDPOINT_URL="https://storage.example",
        NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID="access-key",
        NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY="secret-key",
    )
    monkeypatch.setattr("app.nebius.evidence_archive.shutil.which", lambda _name: "/usr/bin/aws")
    monkeypatch.setattr("app.nebius.evidence_archive.subprocess.run", fake_run)
    archive = NebiusEvidenceArchive(LocalStore(tmp_path), settings)

    record = archive.record_job(
        operation="test_job_completed",
        run_id="job-123",
        status="completed",
        payload={"job_id": "job-123", "status": "completed"},
        artifact_paths={},
    )
    synced = archive.sync()

    assert record.s3_status == "uploaded"
    assert record.source_uri == f"s3://lob-arena-artifacts/lob-arena/evidence/job/{record.evidence_id}"
    assert synced.status == "synced"
    assert synced.record_count == 1
    assert any("s3://lob-arena-artifacts/lob-arena/evidence/job/" in " ".join(command) for command in commands)
    assert any("s3://lob-arena-artifacts/lob-arena/evidence" in " ".join(command) for command in commands)


def test_evidence_archive_uses_ambient_aws_credential_chain(
    monkeypatch: Any, tmp_path: Path
) -> None:
    environments: list[dict[str, str]] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        environments.append(kwargs["env"])
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    settings = Settings(
        _env_file=None,
        NEBIUS_EVIDENCE_ARCHIVE_ENABLED=True,
        NEBIUS_JOB_OUTPUT_URI="s3://lob-arena-artifacts/lob-arena",
        NEBIUS_OBJECT_STORAGE_ENDPOINT_URL="https://storage.example",
    )
    monkeypatch.delenv("AWS_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("AWS_SECRET_ACCESS_KEY", raising=False)
    monkeypatch.setenv("AWS_PROFILE", "nebius-evidence")
    monkeypatch.setattr("app.nebius.evidence_archive.shutil.which", lambda _name: "/usr/bin/aws")
    monkeypatch.setattr("app.nebius.evidence_archive.subprocess.run", fake_run)
    archive = NebiusEvidenceArchive(LocalStore(tmp_path), settings)

    record = archive.record_job(
        operation="test_job_completed",
        run_id="job-ambient",
        status="completed",
        payload={"job_id": "job-ambient", "status": "completed"},
        artifact_paths={},
    )

    assert record.s3_status == "uploaded"
    assert environments
    assert environments[0]["AWS_PROFILE"] == "nebius-evidence"
    assert "AWS_ACCESS_KEY_ID" not in environments[0]
    assert "AWS_SECRET_ACCESS_KEY" not in environments[0]


def test_endpoint_usage_tracks_tokens_bytes_and_configured_cost(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        NEBIUS_INPUT_TOKEN_COST_PER_MILLION_USD=2,
        NEBIUS_OUTPUT_TOKEN_COST_PER_MILLION_USD=4,
    )
    archive = NebiusEvidenceArchive(LocalStore(tmp_path), settings)

    record = archive.record(
        kind="endpoint_call",
        operation="explain_incident",
        status="completed",
        request_payload={"incident": "INC-1"},
        response_payload={
            "result": "ok",
            "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 500_000, "total_tokens": 1_500_000},
        },
    )

    assert record.prompt_tokens == 1_000_000
    assert record.completion_tokens == 500_000
    assert record.total_tokens == 1_500_000
    assert record.estimated_cost_usd == 4
    assert record.request_bytes > 0
    assert record.response_bytes > 0
    assert record.artifact_bytes >= record.request_bytes + record.response_bytes


def test_endpoint_usage_does_not_report_zero_cost_without_configured_rates(tmp_path: Path) -> None:
    archive = NebiusEvidenceArchive(LocalStore(tmp_path), Settings(_env_file=None))

    record = archive.record(
        kind="endpoint_call",
        operation="explain_incident",
        status="completed",
        request_payload={"incident": "INC-1"},
        response_payload={"usage": {"prompt_tokens": 100, "completion_tokens": 50}},
    )

    assert record.total_tokens == 150
    assert record.estimated_cost_usd is None


def test_completed_job_evidence_derives_measured_usage(tmp_path: Path) -> None:
    events = tmp_path / "events.jsonl"
    events.write_text('{"event": 1}\n{"event": 2}\n', encoding="utf-8")
    archive = NebiusEvidenceArchive(LocalStore(tmp_path), Settings(_env_file=None))

    record = archive.record_job(
        operation="cloud_job_completed",
        run_id="job-123",
        status="completed",
        payload={
            "created_at": "2026-07-15T15:35:02+00:00",
            "updated_at": "2026-07-15T15:37:41+00:00",
            "attack_count": 200,
        },
        artifact_paths={"events": str(events)},
    )

    assert record.duration_seconds == 159
    assert record.job_runs == 1
    assert record.workloads == 200
    assert record.simulation_events == 2
    assert record.artifact_count == 1
    assert record.job_cost_usd == 0
