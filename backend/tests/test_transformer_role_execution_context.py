import copy
import io

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
import pytest

from app.ml.transformer import role_execution_context as context
from app.ml.transformer import role_execution_spec as spec


def request_and_key():
    key = Ed25519PrivateKey.generate()
    request = spec.request_template("1" * 40, "sha256:" + "2" * 64,
        key.public_key().public_bytes_raw().hex(), "4" * 32)
    return request, key


def provider_job(request):
    return {"metadata": {"id": "aijob-fixture", "name": spec.RUN_ID, "parent_id": spec.PROJECT},
        "spec": spec.provider_spec(request), "status": {"state": "RUNNING", "instances": []}}


def signed(request, key):
    value = context.context_for_job(provider_job(request), request)
    return {"context": value, "signature": key.sign(spec.canonical(value)).hex()}


def test_signed_actual_job_context_binds_complete_provider_envelope():
    request, key = request_and_key()
    envelope = signed(request, key)
    verified = context.verify_context(envelope, request)
    assert verified["job_id"] == "aijob-fixture"
    assert verified["provider_readback_sha256"] == spec.digest(spec.canonical(provider_job(request)))


@pytest.mark.parametrize("key", tuple(spec.provider_spec(request_and_key()[0])))
def test_every_provider_field_is_enforced(key):
    request, _ = request_and_key()
    job = provider_job(request)
    job["spec"][key] = None
    with pytest.raises(ValueError):
        context.context_for_job(job, request)


def test_ordinary_proto3_defaults_and_environment_order_are_normalized():
    request, _ = request_and_key()
    job = provider_job(request)
    for key in context.DEFAULTS:
        del job["spec"][key]
    job["spec"]["disk"]["size_bytes"] = 100 * 1024**3
    job["spec"]["environment_variables"].reverse()
    assert context.context_for_job(job, request)["provider_spec_sha256"] == spec.digest(
        spec.canonical(spec.provider_spec(request)))


@pytest.mark.parametrize("fault", ["unknown", "duplicate_env", "extra_file", "boolean_restart",
    "public_instance", "public_endpoint", "replicas", "terminal", "name", "parent", "job_id"])
def test_other_unreviewed_provider_configuration_is_rejected(fault):
    request, _ = request_and_key()
    job = provider_job(request)
    if fault == "unknown":
        job["spec"]["unreviewed"] = False
    elif fault == "duplicate_env":
        job["spec"]["environment_variables"].append(copy.deepcopy(job["spec"]["environment_variables"][0]))
    elif fault == "extra_file":
        job["spec"]["injected_files"].append({"container_path": "/extra"})
    elif fault == "boolean_restart":
        job["spec"]["restart_attempts"] = False
    elif fault == "public_instance":
        job["status"]["instances"] = [{"public_ip": "192.0.2.1"}]
    elif fault == "public_endpoint":
        job["status"]["public_endpoints"] = ["example.test"]
    elif fault == "replicas":
        job["status"]["instances"] = [{}, {}]
    elif fault == "terminal":
        job["status"]["state"] = "COMPLETED"
    else:
        job["metadata"][{"name": "name", "parent": "parent_id", "job_id": "id"}[fault]] = "other"
    with pytest.raises(ValueError):
        context.context_for_job(job, request)


@pytest.mark.parametrize("fault", ["signature", "resource", "nonce", "unknown", "old_schema"])
def test_signature_does_not_hide_mismatched_context(fault):
    request, key = request_and_key()
    envelope = signed(request, key)
    if fault == "signature":
        envelope["signature"] = "0" * 128
    else:
        field = {"resource": "provider_spec_sha256", "nonce": "nonce", "unknown": "other",
                 "old_schema": "schema_version"}[fault]
        envelope["context"][field] = "changed"
        envelope["signature"] = key.sign(spec.canonical(envelope["context"])).hex()
    with pytest.raises((ValueError, InvalidSignature)):
        context.verify_context(envelope, request)


class Absent(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


@pytest.mark.parametrize("fault", [None, "version", "null_version", "size", "encoding", "absent", "denied"])
def test_context_polling_is_bounded_and_rejects_invalid_publication(fault):
    request, key = request_and_key()
    payload = spec.canonical(signed(request, key)) + (b"\n" if fault == "encoding" else b"")
    calls, pauses, bodies = [], [], []
    class Store:
        def get_object(self, **kwargs):
            calls.append(kwargs)
            if fault == "absent":
                raise Absent()
            if fault == "denied":
                raise PermissionError("denied")
            body = io.BytesIO(payload)
            bodies.append(body)
            version = {"version": "", "null_version": "null"}.get(fault, "1")
            return {"Body": body, "VersionId": version,
                "ContentLength": len(payload) + (1 if fault == "size" else 0)}
    if fault:
        with pytest.raises((ValueError, TimeoutError, PermissionError)):
            context.wait_context(Store(), request, pause=pauses.append)
    else:
        assert context.wait_context(Store(), request)["job_id"] == "aijob-fixture"
    assert all(body.closed for body in bodies)
    assert len(calls) == (60 if fault == "absent" else 1)
    assert pauses == ([5] * 59 if fault == "absent" else [])
