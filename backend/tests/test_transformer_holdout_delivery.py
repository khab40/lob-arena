from copy import deepcopy
import time

import pytest

pytest.importorskip("numpy")
pytest.importorskip("cryptography")
pytest.importorskip("pyarrow")

from app.ml.transformer.holdout_context import verify_context  # noqa: E402
from app.ml.transformer.holdout_delivery import context_for_job, deliver_context, provider_spec  # noqa: E402
from app.ml.transformer.holdout_entrypoint import wait_context  # noqa: E402
from app.ml.transformer.holdout_storage import HoldoutStore  # noqa: E402
from app.ml.transformer.role_execution_spec import PROJECT  # noqa: E402
from app.ml.transformer.role_execution_transport import PublicationUncertain  # noqa: E402
from app.ml.transformer.verification_spec import canonical, digest  # noqa: E402
from test_transformer_holdout_entrypoint import startup  # noqa: E402


def observed(tmp_path):
    req, envelope, _, s3, _ = startup(tmp_path)
    selectors = {name: {"secret_id": "mbsec-fixture", "version_id": "mbsecver-fixture"}
                 for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")}
    spec = provider_spec(req, selectors)
    req = req.model_copy(update={"provider_spec_sha256": digest(canonical(spec))})
    job = {"metadata": {"id": "aijob-fixture", "parent_id": PROJECT, "name": req.run_id},
           "spec": spec, "status": {"state": "IMAGE_PULLING"}}
    return req, selectors, job, envelope, s3


def attest(req, selectors, job):
    return context_for_job(job, req, selectors, approved_request_sha256=req.sha256(),
                           trusted_public_key=req.context_public_key)


def test_observed_provider_binding_is_acyclic_and_normalizes_ordinary_defaults(tmp_path):
    req, selectors, job, *_ = observed(tmp_path)
    assert attest(req, selectors, job)["provider_readback_sha256"] == digest(canonical(job))
    job["spec"].pop("public_ip")
    job["spec"]["disk"]["size_bytes"] = 100 * 1024**3
    job["spec"]["injected_files"].reverse()
    assert attest(req, selectors, job)["job_id"] == "aijob-fixture"
    changed = req.model_copy(update={"nonce": "9" * 32})
    assert digest(canonical(provider_spec(changed, selectors))) == req.provider_spec_sha256


@pytest.mark.parametrize("defect", ["image", "resource", "secret", "injection", "public", "replicas",
                                   "identity", "terminal", "extra", "provider_pin", "approval", "key"])
def test_attester_rejects_changed_job_or_missing_external_authority(tmp_path, defect):
    req, selectors, job, *_ = observed(tmp_path)
    pins = {"approved_request_sha256": req.sha256(), "trusted_public_key": req.context_public_key}
    if defect == "image":
        job["spec"]["image"] += "changed"
    elif defect == "resource":
        job["spec"]["timeout"] = "7200s"
    elif defect == "secret":
        job["spec"]["environment_variables"][0]["mysterybox_secret"]["version_id"] = "mbsecver-changed"
    elif defect == "injection":
        job["spec"]["injected_files"].pop()
    elif defect == "public":
        job["status"]["public_endpoints"] = ["unexpected"]
    elif defect == "replicas":
        job["status"]["instances"] = [{}, {}]
    elif defect == "identity":
        job["metadata"]["name"] += "changed"
    elif defect == "terminal":
        job["status"]["state"] = "COMPLETED"
    elif defect == "extra":
        job["spec"]["new_field"] = "unreviewed"
    elif defect == "provider_pin":
        req = req.model_copy(update={"provider_spec_sha256": "0" * 64})
        pins["approved_request_sha256"] = req.sha256()
    else:
        pins["approved_request_sha256" if defect == "approval" else "trusted_public_key"] = "0" * 64
    with pytest.raises(ValueError):
        context_for_job(job, req, selectors, **pins)


def test_signed_context_delivery_is_one_put_then_versioned_readback(tmp_path):
    req, envelope, _, s3, _ = startup(tmp_path)
    s3.objects.clear()
    store = HoldoutStore(s3, req, expires=time.monotonic() + req.timeout_seconds)
    pins = {"approved_request_sha256": req.sha256(), "trusted_public_key": req.context_public_key}
    receipt = deliver_context(store, envelope, **pins)
    assert receipt["sha256"] == digest(canonical(envelope)) and receipt["version_id"] == "1"
    assert wait_context(store) == envelope
    assert verify_context(req, envelope, **pins)["job_id"] == "aijob-fixture"
    assert [kind for kind, _ in s3.calls] == ["put", "get", "get"]
    assert s3.calls[0][1]["IfNoneMatch"] == "*" and s3.calls[1][1]["VersionId"] == "1"
    with pytest.raises(PublicationUncertain):
        deliver_context(store, envelope, **pins)  # No overwrite or mutation retry.


@pytest.mark.parametrize("defect", ["signature", "approval", "ambiguous"])
def test_context_failure_never_retries_mutation(tmp_path, defect):
    req, envelope, _, s3, _ = startup(tmp_path)
    s3.objects.clear()
    pins = {"approved_request_sha256": req.sha256(), "trusted_public_key": req.context_public_key}
    if defect == "signature":
        envelope = deepcopy(envelope)
        envelope["signature"] = "0" * 128
    elif defect == "approval":
        pins["approved_request_sha256"] = "0" * 64
    else:
        s3.fail_put = True
    store = HoldoutStore(s3, req, expires=time.monotonic() + req.timeout_seconds)
    with pytest.raises(Exception):
        deliver_context(store, envelope, **pins)
    assert len(s3.calls) == (1 if defect == "ambiguous" else 0)
