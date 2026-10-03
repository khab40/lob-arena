"""Operator handshake tests use fake provider/S3 objects, never cloud or models."""
from datetime import UTC, datetime, timedelta
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("numpy")
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402
from app.ml.transformer.research_execution_spec import PROJECT, provider_spec, template  # noqa: E402
from app.ml.transformer.verification_spec import canonical  # noqa: E402
from app.ml.transformer.research_context import observed, wait  # noqa: E402
from app.ml.transformer.research_storage import Store  # noqa: E402

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


def provider_replay(key):
    """Actual terminal spec, replayed as a live r2 identity; no generated spec."""
    path = Path(__file__).resolve().parents[2] / "docs/evidence/transformer-research-startup-diagnosis-20261003.json"
    actual = json.loads(path.read_bytes())["provider_spec_observed"]
    req = template("smoke", "a" * 40, actual["image"].split("@", 1)[1],
                   key.public_key().public_bytes_raw().hex(), "c" * 32, {})
    job = {"metadata": {"id": "aijob-replay", "name": req["run_id"], "parent_id": PROJECT},
           "status": {"state": "RUNNING"}, "spec": actual}
    return req, job


def test_actual_provider_spec_and_mixed_case_metadata_complete_startup(monkeypatch, tmp_path):
    from test_transformer_research_storage import S3
    key = Ed25519PrivateKey.generate()
    req, job = provider_replay(key)
    s3 = S3()
    s3.metadata_case = "Sha256"
    s3.head_object = lambda **kw: {"LastModified": datetime.now(UTC)}
    worker = Store(s3, req)
    worker.claim()
    reads = []
    def provider(*args):
        reads.append(args)
        return job
    monkeypatch.setattr(operator, "cli", provider)
    result = operator.attest(Store(s3, req), tmp_path, key)
    context = wait(worker)
    assert context["job_id"] == result["job_id"] == "aijob-replay"
    assert len(reads) == 2 and len(s3.objects) == 2
    assert set(worker.artifacts) == {"execution-context.json"}
    assert (tmp_path / "provider-context.json").exists()


@pytest.mark.parametrize("pricing", [None, {}, {"spot": {}}, {"on_demand": {}, "spot": {}}])
def test_provider_replay_rejects_missing_or_changed_pricing(pricing):
    req, job = provider_replay(Ed25519PrivateKey.generate())
    if pricing is None:
        job["spec"].pop("pricing_model")
    else:
        job["spec"]["pricing_model"] = pricing
    with pytest.raises(ValueError, match="resources, image or permissions"):
        observed(job, req)


def test_replacement_request_never_reuses_consumed_campaign():
    from app.ml.transformer.research_execution_spec import validate
    req, _ = provider_replay(Ed25519PrivateKey.generate())
    assert req["campaign"] == "transformer-research-c4-20261003-r2"
    old = "transformer-research-c4-20261002-r1"
    previous = json.loads(json.dumps(req).replace(req["campaign"], old))
    with pytest.raises(ValueError, match="fixed research bounds"):
        validate(previous)


def test_worker_reports_safe_failure_stage_and_cause_without_exception_text(monkeypatch, tmp_path, capsys):
    from app.ml.transformer import research_worker as worker
    from app.ml.transformer.role_execution_transport import PublicationUncertain
    request = tmp_path / "request.json"
    request.write_text("{}")
    monkeypatch.setattr(worker.sys, "argv", ["worker", str(request), str(tmp_path / "work")])
    monkeypatch.setattr(worker, "client", lambda: None)
    def fail(*args):
        error = PublicationUncertain("do not expose private details")
        error.research_stage = "claim"
        raise error from ValueError("sensitive exception context")
    monkeypatch.setattr(worker, "execute", fail)
    with pytest.raises(SystemExit):
        worker.main()
    assert json.loads(capsys.readouterr().out) == {"status": "failed", "stage": "claim",
        "error_type": "PublicationUncertain", "cause_type": "ValueError"}


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
def test_failed_claim_does_not_publish_into_existing_or_unverified_attempt(monkeypatch, tmp_path, error_type):
    from app.ml.transformer import research_worker as worker
    from app.ml.transformer.verification_spec import digest
    for name in ("source-commit", "bundle.json", "source-separation.json", "baseline.parquet", "baseline-calibration.json"):
        (tmp_path / name).write_bytes(b"fixture")
    monkeypatch.setattr(worker, "BUNDLE_SHA", digest(b"fixture"))
    monkeypatch.setattr(worker, "SOURCE_RECEIPT_SHA", digest(b"fixture"))
    monkeypatch.setattr(worker, "validate", lambda *a: None)
    monkeypatch.setattr(worker, "authenticate", lambda *a: ({},))
    monkeypatch.setattr(worker, "load_baseline", lambda *a: ({}, {}, {}))
    monkeypatch.setattr(worker, "load_inventory", lambda *a: [])
    def claim():
        raise error_type("occupied prefix or unavailable read")
    store = SimpleNamespace(claim=claim, put=lambda *a, **kw: pytest.fail("wrote after failed claim"))
    monkeypatch.setattr(worker, "Store", lambda *a: store)
    with pytest.raises(error_type) as caught:
        worker.execute(None, {"resources": {"timeout_seconds": 3600}}, tmp_path, tmp_path / "work")
    assert caught.value.research_stage == "claim"


@pytest.mark.parametrize("target,fault", [("result.json", "put"), ("result.json", "readback"),
    ("SUCCESS", "put"), ("SUCCESS", "readback"), (None, None)])
def test_terminal_publication_reports_stage_without_followup_writes(monkeypatch, tmp_path, capsys, target, fault):
    from app.ml.transformer import research_worker as worker
    from app.ml.transformer.verification_spec import digest
    from test_transformer_research_storage import S3, request

    writes, computations = [], []
    class FaultS3(S3):
        def put_object(self, **kwargs):
            name = kwargs["Key"].rsplit("/", 1)[-1]
            writes.append(name)
            response = super().put_object(**kwargs)
            if name == target and fault == "put":
                raise TimeoutError("sensitive acknowledgement detail")
            return response

        def get_object(self, **kwargs):
            if kwargs["Key"].rsplit("/", 1)[-1] == target and fault == "readback":
                raise OSError("sensitive readback detail")
            return super().get_object(**kwargs)

    req, s3 = request(), FaultS3()
    package = tmp_path / "package"
    package.mkdir()
    for name in ("bundle.json", "source-separation.json", "baseline.parquet", "baseline-calibration.json"):
        (package / name).write_bytes(b"fixture")
    (package / "source-commit").write_text(req["source_commit"])
    monkeypatch.setattr(worker, "BUNDLE_SHA", digest(b"fixture"))
    monkeypatch.setattr(worker, "SOURCE_RECEIPT_SHA", digest(b"fixture"))
    monkeypatch.setattr(worker, "authenticate", lambda *a: ({},))
    monkeypatch.setattr(worker, "load_baseline", lambda *a: ({}, {}, {}))
    monkeypatch.setattr(worker, "load_inventory", lambda *a: [])
    monkeypatch.setattr(worker, "wait", lambda *a: {"job_id": "aijob-fixture"})
    monkeypatch.setattr(worker, "download", lambda *a: {})
    monkeypatch.setattr(worker, "audit_package", lambda *a: {})
    monkeypatch.setattr(worker, "prepare", lambda *a: ({}, {}))
    def inert_computation(*args):
        computations.append(True)
        return {"inert_fixture": True}
    # Replace the GPU module before import: exercise orchestration, never a model.
    monkeypatch.setitem(worker.sys.modules, "app.ml.transformer.research_run",
                        SimpleNamespace(run=inert_computation))
    real_execute = worker.execute
    monkeypatch.setattr(worker, "execute", lambda client, request, unused, work:
                        real_execute(client, request, package, work))
    monkeypatch.setattr(worker, "client", lambda: s3)
    request_path = tmp_path / "request.json"
    request_path.write_bytes(canonical(req))
    monkeypatch.setattr(worker.sys, "argv", ["worker", str(request_path), str(tmp_path / "work")])
    if fault:
        with pytest.raises(SystemExit) as stopped:
            worker.main()
        assert stopped.value.code == 1
        assert json.loads(capsys.readouterr().out) == {"status": "failed", "stage": "publication",
            "error_type": "PublicationUncertain", "cause_type": "TimeoutError" if fault == "put" else "OSError"}
        assert writes[-1] == target and writes.count(target) == 1
        assert (req["output_prefix"] + target) in s3.objects  # Possibly committed: preserve for reconciliation.
    else:
        worker.main()
        output = json.loads(capsys.readouterr().out)
        success = s3.objects[req["output_prefix"] + "SUCCESS"][0]
        assert output == {"status": "published", "success_object": {
            "sha256": digest(success), "size_bytes": len(success), "version_id": "version-1"}}
    assert computations == [True]
    assert "FAILED" not in writes and len(writes) == len(set(writes))
