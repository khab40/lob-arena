"""Inert attester startup and safe diagnostic tests; no cloud or model calls."""
from datetime import UTC, datetime
import json

import pytest

pytest.importorskip("numpy")
from test_transformer_research_operator import fixture, operator  # noqa: E402
from test_transformer_research_storage import S3  # noqa: E402
from app.ml.transformer.research_storage import Store  # noqa: E402


def failure(monkeypatch, capsys, operation):
    monkeypatch.setattr(operator, "main", operation)
    with pytest.raises(SystemExit) as stopped:
        operator.run()
    assert stopped.value.code == 1
    output = capsys.readouterr().out
    assert "PRIVATE_VALUE" not in output
    records = [json.loads(line) for line in output.splitlines()]
    assert all("status" not in item for item in records[:-1])
    terminal = records[-1]
    assert set(terminal) == {"status", "stage", "error_type", "cause_type", "frames", "cause_frames"}
    assert terminal["status"] == "failed" and terminal["frames"]
    for frame in terminal["frames"] + terminal["cause_frames"]:
        assert set(frame) == {"file", "function", "line"}
        assert "/" not in frame["file"] and frame["line"] > 0
    return terminal, records[:-1]


def clock(monkeypatch):
    elapsed = [0]
    monkeypatch.setattr(operator.time, "monotonic", lambda: elapsed[0])
    monkeypatch.setattr(operator.time, "sleep", lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    return elapsed


@pytest.mark.parametrize("code", ["NoSuchKey", "404"])
def test_absent_job_provisioning_missing_intent_then_exactly_one_context(monkeypatch, tmp_path, capsys, code):
    key, store, writes = fixture(monkeypatch)
    job = operator.cli()
    provisioning = {**job, "status": {"state": "PROVISIONING"}}
    jobs = iter((None, provisioning, job, job))
    monkeypatch.setattr(operator, "cli", lambda *args: next(jobs))
    read = store.read
    attempts = []
    def delayed_intent(*args, **kwargs):
        attempts.append(True)
        if len(attempts) == 1:
            error = OSError("PRIVATE_VALUE")
            error.response = {"Error": {"Code": code}}
            raise error
        return read(*args, **kwargs)
    store.read = delayed_intent
    elapsed = clock(monkeypatch)
    result = operator.attest(store, tmp_path, key)
    assert result == {"job_id": "aijob-abc123", "context_delivered": True}
    assert len(writes) == 1 and len(attempts) == 2 and elapsed[0] == 10
    assert (tmp_path / "provider-context.json").exists()
    events = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [(e["event"], e["stage"]) for e in events] == [
        ("attester_ready", "provider_read"), ("attester_waiting", "provider_read"),
        ("provider_observed", "provider_validation"), ("attester_waiting", "intent_read"),
        ("provider_observed", "provider_validation"), ("context_publication_started", "context_publish"),
        ("context_published", "context_publish")]
    assert all(e["evidence_status"] == "progress_not_independent_verification" for e in events)


@pytest.mark.parametrize("response", [None, {}, {"Error": None}, {"Error": "PRIVATE_VALUE"},
    {"Error": {"Code": "AccessDenied"}}])
def test_malformed_or_denied_s3_error_preserves_original_failure_without_retry(
        monkeypatch, tmp_path, capsys, response):
    key, store, writes = fixture(monkeypatch)
    attempts = []
    def fail_read(*args, **kwargs):
        attempts.append(True)
        error = OSError("PRIVATE_VALUE")
        error.response = response
        raise error
    store.read = fail_read
    terminal, _ = failure(monkeypatch, capsys, lambda: operator.attest(store, tmp_path, key))
    assert terminal["stage"] == "intent_read" and terminal["error_type"] == "OSError"
    assert terminal["frames"][-1]["function"] == "fail_read"
    assert attempts == [True] and not writes


@pytest.mark.parametrize("field,value", [("metadata", None), ("status", None),
    ("instances", ["PRIVATE_VALUE"]), ("instances", {"PRIVATE_VALUE": {}}), ("instances", [None])])
def test_malformed_provider_fails_closed_with_validation_origin(monkeypatch, tmp_path, capsys, field, value):
    key, store, writes = fixture(monkeypatch)
    job = operator.cli()
    if field == "instances":
        job["status"][field] = value
    else:
        job[field] = value
    terminal, _ = failure(monkeypatch, capsys, lambda: operator.attest(store, tmp_path, key))
    assert terminal["stage"] == "provider_validation" and terminal["error_type"] == "AttributeError"
    assert terminal["frames"][-1]["file"] == "research_context.py"
    assert not writes and not (tmp_path / "provider-context.json").exists()


def test_uncertain_context_publication_keeps_cause_and_never_retries(monkeypatch, tmp_path, capsys):
    key, fixture_store, _ = fixture(monkeypatch)
    s3 = S3()
    s3.head_object = lambda **kwargs: {"LastModified": datetime.now(UTC)}
    store = Store(s3, fixture_store.request)
    store.claim()
    put, attempts = s3.put_object, []
    def uncertain_put(**kwargs):
        attempts.append(kwargs["Key"])
        put(**kwargs)
        raise TimeoutError("PRIVATE_VALUE")
    s3.put_object = uncertain_put
    terminal, progress = failure(monkeypatch, capsys, lambda: operator.attest(store, tmp_path, key))
    assert terminal["stage"] == "context_publish"
    assert terminal["error_type"] == "PublicationUncertain" and terminal["cause_type"] == "TimeoutError"
    assert terminal["cause_frames"][-1]["function"] == "uncertain_put"
    assert len(attempts) == 1 and attempts[0] in s3.objects
    assert progress[-1]["event"] == "context_publication_started"
    assert not (tmp_path / "provider-context.json").exists()


def test_receipt_failure_distinguishes_already_published_context(monkeypatch, tmp_path, capsys):
    key, store, writes = fixture(monkeypatch)
    def fail_write(*args):
        raise PermissionError("PRIVATE_VALUE")
    monkeypatch.setattr(operator, "write", fail_write)
    terminal, progress = failure(monkeypatch, capsys, lambda: operator.attest(store, tmp_path, key))
    assert terminal["stage"] == "context_receipt" and terminal["error_type"] == "PermissionError"
    assert progress[-1]["event"] == "context_published" and len(writes) == 1


def test_authentication_failure_reports_origin_before_ready(monkeypatch, tmp_path, capsys):
    directory = tmp_path / "smoke"
    directory.mkdir()
    (directory / "request.json").write_text("{}")
    monkeypatch.setattr(operator.sys, "argv", ["operator", "attest", "--evidence", str(tmp_path), "--slot", "smoke"])
    def fail_authentication():
        raise AttributeError("PRIVATE_VALUE")
    monkeypatch.setattr(operator, "authenticated_client", fail_authentication)
    terminal, progress = failure(monkeypatch, capsys, operator.main)
    assert terminal["stage"] == "authentication" and terminal["error_type"] == "AttributeError"
    assert terminal["frames"][-1]["function"] == "fail_authentication" and not progress


def test_absent_job_cannot_extend_attestation_deadline(monkeypatch, tmp_path, capsys):
    key, store, writes = fixture(monkeypatch)
    store.request["resources"]["timeout_seconds"] = 5
    monkeypatch.setattr(operator, "cli", lambda *args: None)
    elapsed = clock(monkeypatch)
    terminal, _ = failure(monkeypatch, capsys, lambda: operator.attest(store, tmp_path, key))
    assert terminal["stage"] == "attestation_timeout" and terminal["error_type"] == "TimeoutError"
    assert elapsed[0] == 5 and not writes
