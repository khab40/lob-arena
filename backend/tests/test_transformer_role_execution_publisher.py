from copy import deepcopy
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from app.ml.transformer import role_execution_publisher as publisher
from app.ml.transformer.role_execution_context import verify_context
from app.ml.transformer.verification_spec import canonical
from transformer_role_execution_fixtures import MemoryStore, job_for, request_and_key


def intent_store(request):
    store = MemoryStore()
    store.objects[request["output_prefix"] + "INTENT"] = canonical(request)
    return store


def writes(store):
    return [args for action, args in store.calls if action == "put"]


def test_publisher_delivers_only_one_signed_matching_context():
    request, key = request_and_key()
    store = intent_store(request)
    job = job_for(request)
    calls = []
    def read_job():
        calls.append(True)
        return None if len(calls) == 1 else job
    pauses = []
    result = publisher.deliver(store, request, key, read_job, pause=pauses.append)
    assert result["provider_readback"] == job
    assert verify_context(result["envelope"], request)["job_id"] == "aijob-fixture"
    assert result["object"]["version_id"] == "1"
    assert len(writes(store)) == 1
    assert writes(store)[0]["Key"] == request["output_prefix"] + "execution-context.json"
    assert writes(store)[0]["IfNoneMatch"] == "*"
    assert pauses == [5]
    assert len(calls) >= 3  # Absent, discovered, independently refreshed before signing.


@pytest.mark.parametrize("absent", ["job", "intent"])
def test_missing_job_or_intent_has_finite_poll_budget(absent):
    request, key = request_and_key()
    store, calls, pauses = MemoryStore(), [], []
    def read_job():
        calls.append(True)
        return None if absent == "job" else job_for(request)
    with pytest.raises(TimeoutError):
        publisher.deliver(store, request, key, read_job, pause=pauses.append)
    assert len(calls) == 120
    assert pauses == [5] * 120
    assert writes(store) == []
    assert len([1 for action, _ in store.calls if action == "get"]) == (0 if absent == "job" else 120)


@pytest.mark.parametrize("fault", ["stale", "future", "bytes", "version", "denied", "FAILED", "SUCCESS"])
def test_unusable_intent_or_terminal_marker_never_gets_context(fault):
    request, key = request_and_key()
    store = intent_store(request)
    now = datetime.now(UTC)
    head = store.head_object
    def read_head(**args):
        if fault == "denied":
            raise PermissionError("access denied")
        value = head(**args)
        age = {"stale": 240, "future": -1}.get(fault, 1)
        value["LastModified"] = now - timedelta(seconds=age)
        if fault == "version":
            value["VersionId"] = "2"
        return value
    store.head_object = read_head
    if fault == "bytes":
        store.objects[request["output_prefix"] + "INTENT"] = b"{}"
    if fault in {"FAILED", "SUCCESS"}:
        store.objects[request["output_prefix"] + fault] = b"{}"
    with pytest.raises((ValueError, PermissionError)):
        publisher.deliver(store, request, key, lambda: job_for(request), now=lambda: now)
    assert writes(store) == []


@pytest.mark.parametrize("fault", ["key", "request", "job"])
def test_mismatched_authority_or_job_is_rejected_before_object_reads(fault):
    request, key = request_and_key()
    store = intent_store(request)
    job = job_for(request)
    if fault == "key":
        key = Ed25519PrivateKey.generate()
    elif fault == "request":
        request["execution_authorized"] = True  # Self-asserted authority is no schema field.
    else:
        job["metadata"]["name"] = "consumed-old-slot"
    with pytest.raises(ValueError):
        publisher.deliver(store, request, key, lambda: job)
    assert store.calls == []


@pytest.mark.parametrize("fault", ["terminated", "replaced", "missing", "spec"])
def test_changed_provider_after_intent_read_cannot_receive_signed_context(fault):
    request, key = request_and_key()
    store = intent_store(request)
    initial = job_for(request)
    changed = deepcopy(initial)
    if fault == "terminated":
        changed["status"]["state"] = "FAILED"
    elif fault == "replaced":
        changed["metadata"]["id"] = "aijob-replacement"
    elif fault == "missing":
        changed = None
    else:
        changed["spec"]["preemptible"] = True
    sequence = iter((initial, changed))
    with pytest.raises(ValueError):
        publisher.deliver(store, request, key, lambda: next(sequence))
    assert writes(store) == []


def test_cli_will_not_arm_over_existing_job(tmp_path, monkeypatch):
    request, key = request_and_key()
    request_path, key_path, evidence = (tmp_path / name for name in ("request.json", "private.key", "evidence.json"))
    request_path.write_bytes(canonical(request))
    key_path.write_bytes(key.private_bytes_raw())
    store = MemoryStore()
    monkeypatch.setattr(publisher.sys, "argv", ["publisher", str(request_path), str(key_path), str(evidence)])
    monkeypatch.setattr(publisher, "client", lambda: store)
    monkeypatch.setattr(publisher, "provider_job", lambda: job_for(request))
    with pytest.raises(ValueError, match="already exists"):
        publisher.main()
    assert not evidence.exists() and not evidence.with_suffix(".ready.json").exists()
    assert writes(store) == []
