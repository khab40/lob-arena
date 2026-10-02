from pathlib import Path

import pytest

pytest.importorskip("numpy")
pytest.importorskip("cryptography")
from app.ml.transformer import role_execution_runner as runner
from app.ml.transformer.verification_spec import canonical, digest
from transformer_role_execution_fixtures import MemoryStore, request_and_key


@pytest.fixture
def prepared(monkeypatch, tmp_path):
    request, _ = request_and_key()
    bundle, source = b"bound-bundle", b"bound-source"
    monkeypatch.setattr(runner, "BUNDLE_SHA", digest(bundle))
    monkeypatch.setattr(runner, "SOURCE_RECEIPT_SHA", digest(source))
    monkeypatch.setattr(runner, "verify", lambda raw: None)
    monkeypatch.setattr(runner, "load_inventory", lambda *args: [])
    monkeypatch.setattr(runner, "wait_context", lambda *args: {"job_id": "aijob-fixture"})
    monkeypatch.setattr(runner, "download", lambda *args: {"get_attempts": 0, "response_bytes": 0})
    monkeypatch.setattr(runner, "audit_package", lambda *args: {name: canonical({}) for name in (
        "role-audit.json", "target-ledger.jsonl", "input-contract.json", "normalization.json")})
    return MemoryStore(), request, Path("unused-inventory"), bundle, source, "a" * 40, tmp_path / "run"


def test_worker_publishes_eight_artifacts_success_last(prepared):
    s3, request, *_ = prepared
    result = runner.execute(*prepared)
    writes = [args["Key"] for kind, args in s3.calls if kind == "put"]
    assert writes[0].endswith("INTENT") and writes[-1].endswith("SUCCESS")
    assert len(writes) == 11  # intent + eight artifacts + checksums + SUCCESS
    assert result["version_id"] == "1"
    assert not any(key.endswith("FAILED") for key in writes)
    assert request["run_id"] in writes[-1]


def test_bad_evidence_rejected_before_cloud(prepared):
    args = list(prepared)
    args[3] = b"changed"
    with pytest.raises(ValueError, match="evidence"):
        runner.execute(*args)
    assert not args[0].calls


def test_audit_failure_retained_without_retry(prepared, monkeypatch):
    count = []
    def fail(*_):
        count.append(1)
        raise ValueError("SDK diagnostic must not leak")
    monkeypatch.setattr(runner, "audit_package", fail)
    with pytest.raises(ValueError):
        runner.execute(*prepared)
    writes = [args for kind, args in prepared[0].calls if kind == "put"]
    assert len(count) == 1 and writes[-1]["Key"].endswith("FAILED")
    assert b"must not leak" not in writes[-1]["Body"]
    assert not any(args["Key"].endswith("SUCCESS") for args in writes)


def test_ambiguous_publication_never_appends_failure(prepared, monkeypatch):
    def uncertain(*_):
        raise TimeoutError("unknown publication outcome")
    monkeypatch.setattr(runner, "publish", uncertain)
    with pytest.raises(TimeoutError):
        runner.execute(*prepared)
    assert not any(args["Key"].endswith("FAILED") for kind, args in prepared[0].calls if kind == "put")


def test_prefix_conflict_prevents_context_and_payload(prepared, monkeypatch):
    s3, request, *_ = prepared
    s3.objects[request["output_prefix"] + "old"] = b"old"
    monkeypatch.setattr(runner, "wait_context", lambda *_: pytest.fail("context accessed"))
    with pytest.raises(ValueError):
        runner.execute(*prepared)
    assert [kind for kind, _ in s3.calls] == ["list"]
