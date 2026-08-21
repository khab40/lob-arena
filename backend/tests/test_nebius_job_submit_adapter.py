import subprocess
from pathlib import Path
from typing import Any

from app.config import Settings
from app.experiments.models import Experiment, utc_now
from app.experiments.nebius_orchestrator import (
    NebiusExperimentOrchestrator,
    _parse_job_id,
    _parse_job_status,
    _redact,
)
from app.experiments.repository import ExperimentRepository
from app.storage.local_store import LocalStore


def test_submit_without_template_stays_pending(tmp_path: Path) -> None:
    repository = _repository_with_experiment(tmp_path)
    orchestrator = NebiusExperimentOrchestrator(repository, Settings(_env_file=None))

    job = orchestrator.submit("EXP-SUBMIT")

    assert job is not None
    assert job.status == "real_nebius_pending"
    assert job.artifact_paths["nebius_job_config"].endswith("nebius_job_config.rendered.yaml")


def test_submit_with_template_persists_queued_job(monkeypatch: Any, tmp_path: Path) -> None:
    repository = _repository_with_experiment(tmp_path)
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            argv,
            0,
            stdout='{"job_id":"job-abc123","status":"queued"}',
            stderr="",
        )

    monkeypatch.setattr("app.experiments.nebius_orchestrator.subprocess.run", fake_run)
    settings = Settings(
        _env_file=None,
        NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE=(
            "nebius ai job create --config {config_path} --image {image} "
            "--output {output_dir} --label experiment={experiment_id}"
        ),
        NEBIUS_JOB_IMAGE="ghcr.io/acme/aimada-jobs:test",
    )
    orchestrator = NebiusExperimentOrchestrator(repository, settings)

    job = orchestrator.submit("EXP-SUBMIT")

    assert job is not None
    assert job.status == "queued"
    assert job.job_id == "job-abc123"
    assert "--config" in captured["argv"]
    assert str(tmp_path / "experiments" / "EXP-SUBMIT" / "nebius_job_config.rendered.yaml") in captured["argv"]
    assert "--image" in captured["argv"]
    assert "ghcr.io/acme/aimada-jobs:test" in captured["argv"]
    assert job.artifact_paths["submit_stdout"].endswith("nebius_submit_stdout.txt")
    assert "job-abc123" in Path(job.artifact_paths["submit_stdout"]).read_text(encoding="utf-8")
    assert repository.get("EXP-SUBMIT").smart_batch_id == "job-abc123"  # type: ignore[union-attr]


def test_submit_with_template_persists_failed_job_and_redacts(monkeypatch: Any, tmp_path: Path) -> None:
    repository = _repository_with_experiment(tmp_path)

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            argv,
            2,
            stdout="",
            stderr="Authorization=secret-token token=another-secret",
        )

    monkeypatch.setattr("app.experiments.nebius_orchestrator.subprocess.run", fake_run)
    settings = Settings(
        _env_file=None,
        NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE="nebius ai job create --config {config_path}",
    )
    orchestrator = NebiusExperimentOrchestrator(repository, settings)

    job = orchestrator.submit("EXP-SUBMIT")

    assert job is not None
    assert job.status == "failed"
    assert "secret-token" not in job.message
    assert "another-secret" not in job.message
    error_text = Path(job.artifact_paths["submit_error"]).read_text(encoding="utf-8")
    assert "secret-token" not in error_text
    assert "another-secret" not in error_text
    assert "[REDACTED]" in error_text
    assert repository.get("EXP-SUBMIT").status == "failed"  # type: ignore[union-attr]


def test_refresh_does_not_complete_without_artifact_confirmation(monkeypatch: Any, tmp_path: Path) -> None:
    repository = _repository_with_experiment(tmp_path)
    captured_status_argv: list[str] = []

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == "submit-job":
            return subprocess.CompletedProcess(argv, 0, stdout="job_id: job-refresh", stderr="")
        captured_status_argv.extend(argv)
        return subprocess.CompletedProcess(argv, 0, stdout='{"status":"completed"}', stderr="")

    monkeypatch.setattr("app.experiments.nebius_orchestrator.subprocess.run", fake_run)
    settings = Settings(
        _env_file=None,
        NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE="submit-job {config_path}",
        NEBIUS_JOB_STATUS_COMMAND_TEMPLATE="status-job {job_id}",
    )
    orchestrator = NebiusExperimentOrchestrator(repository, settings)

    submitted = orchestrator.submit("EXP-SUBMIT")
    refreshed = orchestrator.refresh("EXP-SUBMIT")

    assert submitted is not None
    assert submitted.status == "queued"
    assert captured_status_argv == ["status-job", "job-refresh"]
    assert refreshed is not None
    assert refreshed[0].status == "running"
    assert "artifact collection is not confirmed" in refreshed[0].message


def test_submit_with_s3_output_passes_upload_args_and_secret_refs(monkeypatch: Any, tmp_path: Path) -> None:
    repository = _repository_with_experiment(tmp_path)
    captured: dict[str, Any] = {}

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout='{"job_id":"job-s3"}', stderr="")

    monkeypatch.setattr("app.experiments.nebius_orchestrator.subprocess.run", fake_run)
    settings = Settings(
        _env_file=None,
        NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE=(
            "nebius ai job create --args {job_args} {object_storage_env_args}"
        ),
        NEBIUS_JOB_OUTPUT_URI="s3://aimada-artifacts",
        NEBIUS_OBJECT_STORAGE_ENDPOINT_URL="https://storage.eu-north1.nebius.cloud",
        NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID="mysterybox-access-ref",
        NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID="mysterybox-secret-ref",
    )
    orchestrator = NebiusExperimentOrchestrator(repository, settings)

    job = orchestrator.submit("EXP-SUBMIT")

    assert job is not None
    argv = captured["argv"]
    joined = " ".join(argv)
    assert "--s3-output-uri" in joined
    assert "--random-seed 42" in joined
    assert "s3://aimada-artifacts/experiments/EXP-SUBMIT/local-batch" in joined
    assert "--s3-endpoint-url" in joined
    assert "--env-secret" in argv
    assert "AWS_ACCESS_KEY_ID=mysterybox-access-ref" in argv
    assert "AWS_SECRET_ACCESS_KEY=mysterybox-secret-ref" in argv
    assert "access-key" not in joined
    assert "secret-key" not in joined


def test_refresh_completed_job_syncs_s3_artifacts(monkeypatch: Any, tmp_path: Path) -> None:
    repository = _repository_with_experiment(tmp_path)

    def fake_which(name: str) -> str | None:
        return "/usr/bin/aws" if name == "aws" else None

    def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if argv[0] == "submit-job":
            return subprocess.CompletedProcess(argv, 0, stdout="job_id: job-sync", stderr="")
        if argv[0] == "status-job":
            return subprocess.CompletedProcess(argv, 0, stdout='{"status":"completed"}', stderr="")
        if argv[0] == "/usr/bin/aws":
            destination = Path(argv[-2])
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "order_book_events.jsonl").write_text('{"tick":1}\n', encoding="utf-8")
            (destination / "trades.jsonl").write_text("", encoding="utf-8")
            (destination / "attack_labels.jsonl").write_text('{"label":"spoofing"}\n', encoding="utf-8")
            (destination / "blue_team_alerts.jsonl").write_text('{"alert_id":"a1"}\n', encoding="utf-8")
            (destination / "detector_metrics.csv").write_text("scenario,runs,alerts,precision,recall,f1,avg_detection_latency_ms\n", encoding="utf-8")
            (destination / "generated_report.md").write_text("# Report\n", encoding="utf-8")
            (destination / "manifest.json").write_text('{"runs":4}\n', encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")
        raise AssertionError(f"unexpected command: {argv}")

    monkeypatch.setattr("app.experiments.nebius_orchestrator.shutil.which", fake_which)
    monkeypatch.setattr("app.experiments.nebius_orchestrator.subprocess.run", fake_run)
    settings = Settings(
        _env_file=None,
        NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE="submit-job {config_path}",
        NEBIUS_JOB_STATUS_COMMAND_TEMPLATE="status-job {job_id}",
        NEBIUS_JOB_OUTPUT_URI="s3://aimada-artifacts",
        NEBIUS_OBJECT_STORAGE_ENDPOINT_URL="https://storage.eu-north1.nebius.cloud",
        NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID="access-key",
        NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY="secret-key",
    )
    orchestrator = NebiusExperimentOrchestrator(repository, settings)

    orchestrator.submit("EXP-SUBMIT")
    refreshed = orchestrator.refresh("EXP-SUBMIT")

    assert refreshed is not None
    assert refreshed[0].status == "completed"
    assert "cloud_artifact_evidence" in refreshed[0].artifact_paths
    experiment = repository.get("EXP-SUBMIT")
    assert experiment is not None
    assert experiment.status == "completed"
    assert Path(experiment.artifact_paths["cloud_artifact_evidence"]).exists()
    assert Path(experiment.artifact_paths["benchmark_report"]).read_text(encoding="utf-8") == "# Report\n"


def test_parse_job_id_from_json_and_text() -> None:
    assert _parse_job_id('{"id":"job-json"}') == "job-json"
    assert _parse_job_id('{"metadata":{"jobId":"job-nested"}}') == "job-nested"
    assert _parse_job_id("created job id: job-text-123") == "job-text-123"
    assert _parse_job_id("submitted NEB-ABC123") == "NEB-ABC123"


def test_parse_job_status_accepts_current_nebius_nested_state() -> None:
    assert _parse_job_status('{"status":{"state":"COMPLETED"}}') == "completed"
    assert _parse_job_status('{"status":{"state":"PROVISIONING"}}') is None


def test_redact_removes_object_storage_credentials_from_cli_output() -> None:
    raw = (
        '{"environment_variables":['
        '{"name":"AWS_ACCESS_KEY_ID","value":"access-value"},'
        '{"name":"AWS_SECRET_ACCESS_KEY","value":"secret-value"}]}'
        " AWS_SESSION_TOKEN=session-value"
    )

    redacted = _redact(raw)

    assert "access-value" not in redacted
    assert "secret-value" not in redacted
    assert "session-value" not in redacted
    assert redacted.count("[REDACTED]") == 3


def _repository_with_experiment(tmp_path: Path) -> ExperimentRepository:
    repository = ExperimentRepository(LocalStore(tmp_path))
    now = utc_now()
    repository.save(
        Experiment(
            id="EXP-SUBMIT",
            name="Submit adapter test",
            status="manifest_generated",
            attack_count=4,
            batch_size=2,
            scenarios=["normal_market", "spoofing_like_wall"],
            seed=42,
            nebius_mode="real_nebius_pending",
            artifact_dir=str(tmp_path / "experiments" / "EXP-SUBMIT"),
            created_at=now,
            updated_at=now,
        )
    )
    return repository
