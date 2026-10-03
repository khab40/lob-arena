"""Operator handshake tests use fake provider/S3 objects, never cloud or models."""
from datetime import UTC, datetime, timedelta
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("numpy")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from app.ml.transformer.research_execution_spec import PROJECT, provider_spec, template  # noqa: E402
from app.ml.transformer.verification_spec import canonical  # noqa: E402

spec = importlib.util.spec_from_file_location("research_operator", Path(__file__).resolve().parents[2]
                                            / "scripts/transformer_research_operator.py")
operator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator)


def fixture(monkeypatch, age=0, state="RUNNING"):
    key = Ed25519PrivateKey.generate()
    req = template("smoke", "a" * 40, "sha256:" + "b" * 64,
                   key.public_key().public_bytes_raw().hex(), "c" * 32, {})
    job = {"metadata": {"id": "aijob-abc123", "name": req["run_id"], "parent_id": PROJECT},
           "status": {"state": state}, "spec": provider_spec(req)}
    writes = []
    store = SimpleNamespace(request=req,
        read=lambda *a, **k: (canonical(req), {"version_id": "one"}),
        s3=SimpleNamespace(head_object=lambda **k: {"LastModified": datetime.now(UTC) - timedelta(seconds=age)}),
        put=lambda *a, **k: writes.append(a))
    monkeypatch.setattr(operator, "cli", lambda *a: job)
    return key, store, writes


def test_current_live_provider_is_signed_and_published_once(monkeypatch, tmp_path):
    key, store, writes = fixture(monkeypatch)
    result = operator.attest(store, tmp_path, key)
    assert result == {"job_id": "aijob-abc123", "context_delivered": True}
    assert len(writes) == 1
    assert (tmp_path / "provider-context.json").exists()


@pytest.mark.parametrize("age,state", [(241, "RUNNING"), (-60, "RUNNING"), (0, "FAILED")])
def test_expired_or_terminal_worker_never_receives_authorization(monkeypatch, tmp_path, age, state):
    key, store, writes = fixture(monkeypatch, age, state)
    with pytest.raises(ValueError):
        operator.attest(store, tmp_path, key)
    assert not writes


def test_wrong_custody_fails_before_provider_read(monkeypatch, tmp_path):
    _, store, writes = fixture(monkeypatch)
    monkeypatch.setattr(operator, "cli", lambda *a: pytest.fail("provider touched"))
    with pytest.raises(ValueError, match="custody"):
        operator.attest(store, tmp_path, Ed25519PrivateKey.generate())
    assert not writes


def test_dependency_mismatch_fails_before_credentials(monkeypatch):
    pytest.importorskip("botocore")
    monkeypatch.setattr(operator.importlib.metadata, "version", lambda name: "wrong")
    monkeypatch.setattr(operator, "cli", lambda *a: pytest.fail("credentials touched"))
    with pytest.raises(RuntimeError, match="dependency"):
        operator.authenticated_client()


def test_transient_reads_use_three_increasing_retries(monkeypatch):
    calls = []
    def run(*args, **kwargs):
        calls.append(kwargs["timeout"])
        return SimpleNamespace(returncode=1, stderr=b"code = Unavailable", stdout=b"")
    monkeypatch.setattr(operator.subprocess, "run", run)
    with pytest.raises(RuntimeError):
        operator.cli("ai", "job", "get")
    assert calls == [30, 60, 90, 120]


def test_permission_failure_is_not_retried_or_echoed(monkeypatch):
    calls = []
    def run(*args, **kwargs):
        calls.append(1)
        return SimpleNamespace(returncode=1, stderr=b"code = PermissionDenied private-detail", stdout=b"")
    monkeypatch.setattr(operator.subprocess, "run", run)
    with pytest.raises(RuntimeError) as error:
        operator.cli("mysterybox", "payload", "get")
    assert calls == [1]
    assert "private-detail" not in str(error.value)
