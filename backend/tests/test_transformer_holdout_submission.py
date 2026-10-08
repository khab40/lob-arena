import hashlib
import json
from types import SimpleNamespace

import pytest

from test_transformer_holdout_watch import CLI


@pytest.fixture
def creation(tmp_path, monkeypatch):
    command = ["nebius", "ai", "job", "create", "--timeout", "1h", "--retries", "1", "--async"]
    raw = json.dumps(command).encode()
    (tmp_path / "create-argv.json").write_bytes(raw)
    proposal = {"files": {"create-argv.json": hashlib.sha256(raw).hexdigest()},
        "submission": CLI.SUBMISSION, "create_to_terminal_seconds": 7200}
    monkeypatch.setattr(CLI, "sources", lambda *a, **kw: None)
    return tmp_path, proposal, command


def invoke(creation, remaining=120, expires=9000):
    output, proposal, _ = creation
    return CLI.create_once(output, proposal, "a" * 64, remaining, expires,
        now=lambda: 1000, monotonic=lambda: 0)


def test_intent_is_durable_before_exact_single_mutation(creation, monkeypatch):
    output, _, command = creation
    syncs, calls = [], []
    monkeypatch.setattr(CLI.os, "fsync", syncs.append)
    def create(argv, **kwargs):
        intent = json.loads((output / "creation-attempt.json").read_bytes())
        assert intent["attempt"] == 1 and intent["timeout_seconds"] == 90
        assert len(syncs) == 2  # File and parent directory flushed before mutation.
        assert argv == ["rtk", "proxy", *command] and kwargs["timeout"] == 90
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=b'{"id":"op-fixture"}', stderr=b"")
    monkeypatch.setattr(CLI.subprocess, "run", create)
    assert invoke(creation)["status"] == "async_returned"
    assert len(calls) == 1
    with pytest.raises(FileExistsError):
        invoke(creation)
    assert len(calls) == 1 and len(syncs) == 4


@pytest.mark.parametrize("kind", ["timeout", "spawn_error", "nonzero_exit", "uncertain_response"])
def test_uncertain_outcome_consumes_attempt_without_retry(creation, monkeypatch, kind):
    calls = []
    def create(argv, **kwargs):
        calls.append(argv)
        if kind == "timeout":
            raise CLI.subprocess.TimeoutExpired(argv, kwargs["timeout"])
        if kind == "spawn_error":
            raise OSError("fixture")
        return SimpleNamespace(returncode=1 if kind == "nonzero_exit" else 0,
            stdout=b"unparseable", stderr=b"fixture")
    monkeypatch.setattr(CLI.subprocess, "run", create)
    result = invoke(creation)
    assert result["status"] == kind and result["reconcile_required"] and not result["retry_allowed"]
    with pytest.raises(FileExistsError):
        invoke(creation)
    assert len(calls) == 1


@pytest.mark.parametrize("remaining,expires", [(30, 9000), (29, 9000), (120, 8499)])
def test_insufficient_creation_or_access_reserve_never_mutates(creation, monkeypatch, remaining, expires):
    monkeypatch.setattr(CLI.subprocess, "run", lambda *a, **kw: pytest.fail("mutation"))
    with pytest.raises(TimeoutError):
        invoke(creation, remaining, expires)
    assert not (creation[0] / "creation-attempt.json").exists()


def test_package_drift_never_mutates(creation, monkeypatch):
    (creation[0] / "create-argv.json").write_text('["changed"]')
    monkeypatch.setattr(CLI.subprocess, "run", lambda *a, **kw: pytest.fail("mutation"))
    with pytest.raises(ValueError, match="package differs"):
        invoke(creation)
    assert not (creation[0] / "creation-attempt.json").exists()


def test_executed_bytes_must_match_pin_despite_later_path_restoration(creation, monkeypatch):
    path = creation[0] / "create-argv.json"
    original, reads = CLI.Path.read_bytes, []
    def interleaved(current):
        if current == path:
            reads.append(current)
            if len(reads) == 2:  # Package check saw approved bytes; captured argv does not.
                return b'["nebius","unapproved"]'
        return original(current)
    monkeypatch.setattr(CLI.Path, "read_bytes", interleaved)
    monkeypatch.setattr(CLI.subprocess, "run", lambda *a, **kw: pytest.fail("mutation"))
    with pytest.raises(ValueError, match="creation argv differs"):
        invoke(creation)
    assert not (creation[0] / "creation-attempt.json").exists()


@pytest.mark.parametrize("failure_at", [1, 2])
def test_intent_flush_failure_never_mutates_and_preserves_consumption(creation, monkeypatch, failure_at):
    calls = []
    def fail_sync(fd):
        calls.append(fd)
        if len(calls) == failure_at:
            raise OSError("fixture durability failure")
    monkeypatch.setattr(CLI.os, "fsync", fail_sync)
    monkeypatch.setattr(CLI.subprocess, "run", lambda *a, **kw: pytest.fail("mutation"))
    with pytest.raises(OSError):
        invoke(creation)
    assert (creation[0] / "creation-attempt.json").exists()


def test_interruption_after_intent_cannot_submit_again(creation, monkeypatch):
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(CLI.subprocess, "run", interrupt)
    with pytest.raises(KeyboardInterrupt):
        invoke(creation)
    monkeypatch.setattr(CLI.subprocess, "run", lambda *a, **kw: pytest.fail("second mutation"))
    with pytest.raises(FileExistsError):
        invoke(creation)


def test_slow_intent_durability_cannot_consume_observation_reserve(creation, monkeypatch):
    output, proposal, _ = creation
    clock = [0]
    original = CLI.durable_record
    def slow(path, record):
        original(path, record)
        clock[0] += 91
    monkeypatch.setattr(CLI, "durable_record", slow)
    monkeypatch.setattr(CLI.subprocess, "run", lambda *a, **kw: pytest.fail("mutation"))
    with pytest.raises(TimeoutError, match="after durable intent"):
        CLI.create_once(output, proposal, "a" * 64, 120, 9000,
            now=lambda: 1000, monotonic=lambda: clock[0])
    assert (output / "creation-attempt.json").exists()


@pytest.mark.parametrize("kind", ["accepted", "timeout"])
def test_outcome_receipt_failure_keeps_observation_and_context(creation, monkeypatch, kind):
    pytest.importorskip("numpy")
    pytest.importorskip("cryptography")
    from app.ml.transformer.holdout_supervision import supervise
    from test_transformer_holdout_supervision import setup
    output, proposal, _ = creation
    original, creates, contexts = CLI.durable_record, [], []
    def persist(path, record):
        if path.name == "creation-outcome.json":
            raise OSError("fixture outcome persistence failure")
        original(path, record)
    def create(argv, **kwargs):
        creates.append(argv)
        if kind == "timeout":
            raise CLI.subprocess.TimeoutExpired(argv, kwargs["timeout"])
        return SimpleNamespace(returncode=0, stdout=b'{"id":"op-fixture"}', stderr=b"")
    monkeypatch.setattr(CLI, "durable_record", persist)
    monkeypatch.setattr(CLI.subprocess, "run", create)
    req, selectors, pins, job = setup()
    observations = iter([None, job(), job("COMPLETED")])
    result = supervise(req, selectors, pins, read=lambda _: next(observations),
        deliver=lambda c, _: contexts.append(c), cancel=lambda _: pytest.fail("cancel"), emit=lambda _: None,
        now=lambda: 1000, pause=lambda _: None,
        admit=lambda remaining: CLI.create_once(output, proposal, "a" * 64, remaining, 9000,
            now=lambda: 1000, monotonic=lambda: 0))
    assert result["state"] == "COMPLETED" and len(creates) == len(contexts) == 1
    assert (output / "creation-attempt.json").exists()
    assert not (output / "creation-outcome.json").exists()


