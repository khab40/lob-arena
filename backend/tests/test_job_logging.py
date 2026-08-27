from __future__ import annotations

import json

import pytest

from app.nebius.job_logging import JobLogger


def test_job_phase_emits_explanatory_start_and_completion_records(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = JobLogger("test-job")

    with logger.phase(
        "model.train",
        "Train the governed model with frozen parameters.",
        run_id="run-1",
    ):
        pass

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [record["event"] for record in records] == [
        "model.train.started",
        "model.train.completed",
    ]
    assert all(record["job_type"] == "test-job" for record in records)
    assert all(record["description"] == "Train the governed model with frozen parameters." for record in records)
    assert records[1]["duration_ms"] >= 0


def test_job_phase_failure_logs_only_safe_error_type(
    capsys: pytest.CaptureFixture[str],
) -> None:
    logger = JobLogger("test-job")

    with pytest.raises(RuntimeError, match="must-not-appear"):
        with logger.phase("result.publish", "Publish verified artifacts."):
            raise RuntimeError("password=must-not-appear")

    output = capsys.readouterr().out
    records = [json.loads(line) for line in output.splitlines()]
    assert records[-1]["event"] == "result.publish.failed"
    assert records[-1]["error_type"] == "RuntimeError"
    assert "must-not-appear" not in output


def test_job_logger_rejects_sensitive_field_names() -> None:
    logger = JobLogger("test-job")

    with pytest.raises(ValueError, match="sensitive"):
        logger.info("request.ready", "Validate the request.", access_token="forbidden")
