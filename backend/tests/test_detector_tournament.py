import subprocess
from pathlib import Path
from types import SimpleNamespace

from fastapi import BackgroundTasks

from app.config import get_settings
from app.api.routes_nebius import read_detector_tournament, start_detector_tournament
from app.nebius.detector_tournament import (
    complete_queued_tournament,
    DetectorTournamentMetrics,
    DetectorTournamentStartRequest,
    _parse_job_id,
    get_tournament,
    queue_tournament,
    refresh_tournament,
    start_tournament,
)
from app.metrics import PrometheusTextRegistry
from app.storage.local_store import LocalStore


def test_detector_tournament_runs_local_mock_and_persists(tmp_path: Path) -> None:
    store = LocalStore(tmp_path)
    response = start_tournament(
        DetectorTournamentStartRequest(
            number_of_scenarios=2,
            manipulation_types=["spoofing_like_wall"],
            detector_set=["spoofing_like"],
            execution_mode="local_mock",
            random_seed=7,
        ),
        store=store,
        repo_root=Path(__file__).resolve().parents[2],
    )
    loaded = get_tournament(response.tournament_id, store=store)

    assert response.status == "completed"
    assert response.execution_mode == "local_mock"
    assert response.leaderboard
    assert response.leaderboard[0].false_positives >= 0
    assert response.leaderboard[0].false_negatives >= 0
    assert response.artifacts == {}
    assert response.fallback_reason
    assert loaded is not None
    assert loaded.tournament_id == response.tournament_id


def test_parse_job_id_accepts_nebius_cli_text_output() -> None:
    assert _parse_job_id("Job ID: aijob-e00chpkqr83hdbwgkr\n") == "aijob-e00chpkqr83hdbwgkr"


def test_detector_tournament_nebius_mode_falls_back_without_submit_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE", "")
    get_settings.cache_clear()
    try:
        response = start_tournament(
            DetectorTournamentStartRequest(
                number_of_scenarios=1,
                manipulation_types=["quote_stuffing"],
                detector_set=["quote_stuffing"],
                execution_mode="nebius",
            ),
            store=LocalStore(tmp_path),
            repo_root=Path(__file__).resolve().parents[2],
        )

        assert response.status == "completed"
        assert response.execution_mode == "local_mock"
        assert response.fallback_reason
    finally:
        get_settings.cache_clear()


def test_detector_tournament_local_background_lifecycle_updates_in_flight_metrics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = LocalStore(tmp_path)
    registry = PrometheusTextRegistry()
    observer = DetectorTournamentMetrics(registry)
    payload = DetectorTournamentStartRequest(
        number_of_scenarios=3,
        manipulation_types=["layering_like"],
        detector_set=["layering_like"],
        execution_mode="local",
    )
    queued = queue_tournament(
        payload,
        store=store,
        repo_root=Path(__file__).resolve().parents[2],
        observer=observer,
    )
    completed = queued.model_copy(
        update={
            "status": "completed",
            "completed_at": "2026-07-23T12:00:03+00:00",
            "metrics": {"total_scenarios": 3},
            "summary": "completed",
        }
    )
    monkeypatch.setattr(
        "app.nebius.detector_tournament._run_local_tournament",
        lambda *_args, **_kwargs: completed,
    )

    result = complete_queued_tournament(
        payload,
        tournament_id=queued.tournament_id,
        started_at=queued.started_at,
        store=store,
        repo_root=Path(__file__).resolve().parents[2],
        observer=observer,
    )

    assert result is not None
    assert result.status == "completed"
    rendered = registry.render()
    assert 'detector_tournament_in_flight{execution_mode="local"} 0' in rendered
    assert 'detector_tournament_runs_total{execution_mode="local",outcome="completed"} 1' in rendered
    assert 'detector_tournament_scenarios_total{execution_mode="local",outcome="completed"} 3' in rendered


def test_detector_tournament_nebius_submit_renders_object_storage_env(tmp_path: Path, monkeypatch) -> None:
    captured: dict[str, list[str]] = {}

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        captured["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout='{"job_id":"job-test"}', stderr="")

    monkeypatch.setenv(
        "NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE",
        "nebius ai job create --image {image} {object_storage_env_args}",
    )
    monkeypatch.setenv("NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("NEBIUS_EVIDENCE_ARCHIVE_ENABLED", "false")
    monkeypatch.setattr("app.nebius.detector_tournament.subprocess.run", fake_run)
    get_settings.cache_clear()
    try:
        response = start_tournament(
            DetectorTournamentStartRequest(
                number_of_scenarios=1,
                manipulation_types=["spoofing_like_wall"],
                detector_set=["spoofing_like"],
                execution_mode="nebius",
            ),
            store=LocalStore(tmp_path),
            repo_root=Path(__file__).resolve().parents[2],
        )

        assert response.status == "queued"
        assert "AWS_ACCESS_KEY_ID=test-access" in captured["argv"]
        assert "AWS_SECRET_ACCESS_KEY=test-secret" in captured["argv"]
    finally:
        get_settings.cache_clear()


def test_detector_tournament_collects_completed_s3_artifacts(tmp_path: Path, monkeypatch) -> None:
    captured_submit: list[str] = []

    def fake_run(argv: list[str], **_kwargs) -> subprocess.CompletedProcess[str]:
        if argv[0] == "submit-job":
            captured_submit.extend(argv)
            return subprocess.CompletedProcess(argv, 0, stdout='{"job_id":"job-cloud"}', stderr="")
        if argv[0] == "status-job":
            return subprocess.CompletedProcess(argv, 0, stdout='{"status":{"state":"COMPLETED"}}', stderr="")
        if argv[0] == "logs-job":
            return subprocess.CompletedProcess(argv, 0, stdout="batch complete", stderr="")
        sync_index = argv.index("sync")
        destination = Path(argv[sync_index + 2])
        destination.mkdir(parents=True, exist_ok=True)
        payloads = {
            "order_book_events.jsonl": "{}\n",
            "trades.jsonl": "",
            "attack_labels.jsonl": "{}\n",
            "blue_team_alerts.jsonl": "{}\n",
            "detector_metrics.csv": (
                "scenario,runs,alerts,precision,recall,f1,avg_detection_latency_ms\n"
                    "spoofing_like_wall,1,1,1.0,1.0,1.0,1000.0\n"
            ),
            "generated_report.md": "# Report\n",
            "manifest.json": "{}\n",
        }
        for name, contents in payloads.items():
            (destination / name).write_text(contents, encoding="utf-8")
        return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

    monkeypatch.setenv(
        "NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE",
        "submit-job --args {job_args} {object_storage_env_args}",
    )
    monkeypatch.setenv("NEBIUS_JOB_STATUS_COMMAND_TEMPLATE", "status-job {job_id}")
    monkeypatch.setenv("NEBIUS_JOB_LOGS_COMMAND_TEMPLATE", "logs-job {job_id}")
    monkeypatch.setenv("NEBIUS_JOB_OUTPUT_URI", "s3://aimada-artifacts/aimada")
    monkeypatch.setenv("NEBIUS_OBJECT_STORAGE_ENDPOINT_URL", "https://storage.example")
    monkeypatch.setenv("NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID", "test-access")
    monkeypatch.setenv("NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY", "test-secret")
    monkeypatch.setenv("NEBIUS_EVIDENCE_ARCHIVE_ENABLED", "false")
    monkeypatch.setattr("app.nebius.detector_tournament.shutil.which", lambda _name: "/usr/bin/aws")
    monkeypatch.setattr("app.nebius.detector_tournament.subprocess.run", fake_run)
    get_settings.cache_clear()
    store = LocalStore(tmp_path)
    registry = PrometheusTextRegistry()
    observer = DetectorTournamentMetrics(registry)
    try:
        submitted = start_tournament(
            DetectorTournamentStartRequest(
                number_of_scenarios=1,
                manipulation_types=["spoofing_like_wall"],
                detector_set=["spoofing_like"],
                execution_mode="nebius",
            ),
            store=store,
            repo_root=Path(__file__).resolve().parents[2],
            observer=observer,
        )
        refreshed = refresh_tournament(
            submitted.tournament_id,
            store=store,
            observer=observer,
        )
    finally:
        get_settings.cache_clear()

    cloud_uri = f"s3://aimada-artifacts/aimada/tournaments/{submitted.tournament_id}/local-batch"
    assert cloud_uri in " ".join(captured_submit)
    assert submitted.metrics["cloud_output_uri"] == cloud_uri
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.metrics["artifact_count"] == 7
    assert refreshed.leaderboard[0].scenario == "spoofing_like_wall"
    assert Path(refreshed.artifacts["artifact_index"]).is_file()
    assert Path(refreshed.artifacts["nebius_job_logs"]).read_text(encoding="utf-8") == "batch complete"
    rendered = registry.render()
    assert (
        'detector_tournament_artifact_collections_total'
        '{execution_mode="nebius_serverless_job",outcome="success"} 1'
    ) in rendered
    assert (
        'detector_tournament_runs_total'
        '{execution_mode="nebius_serverless_job",outcome="completed"} 1'
    ) in rendered


def test_detector_tournament_api_facade_round_trip(tmp_path: Path) -> None:
    registry = PrometheusTextRegistry()
    request = SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(
                store=LocalStore(tmp_path),
                tournament_metrics=DetectorTournamentMetrics(registry),
            )
        )
    )
    response = start_detector_tournament(
        DetectorTournamentStartRequest(
            number_of_scenarios=1,
            manipulation_types=["layering_like"],
            detector_set=["layering_like"],
            execution_mode="local_mock",
        ),
        request,
        BackgroundTasks(),
    )
    loaded = read_detector_tournament(response.tournament_id, request)

    assert loaded.tournament_id == response.tournament_id
    assert loaded.status == "completed"
    assert loaded.execution_mode == "local_mock"
    assert (
        'detector_tournament_runs_total{execution_mode="local_mock",outcome="completed"} 1'
        in registry.render()
    )
