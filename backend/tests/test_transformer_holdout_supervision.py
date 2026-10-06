from datetime import datetime, timezone

import pytest

from app.ml.transformer.holdout_delivery import provider_spec
from app.ml.transformer.holdout_supervision import supervise
from app.ml.transformer.verification_spec import canonical, digest
from test_transformer_holdout_runtime import fixture_request


def setup():
    req = fixture_request()
    selectors = {name: {"secret_id": "mbsec-fixture", "version_id": "mbsecver-fixture"}
                 for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY")}
    req = req.model_copy(update={"provider_spec_sha256": digest(canonical(provider_spec(req, selectors)))})
    pins = {"approved_request_sha256": req.sha256(), "trusted_public_key": req.context_public_key}
    def job(state="RUNNING", identity="aijob-fixture"):
        return {"metadata": {"id": identity, "name": req.run_id,
            "parent_id": "project-e00g6zvxpr00waz8t3y51k",
            "created_at": datetime.fromtimestamp(1000, timezone.utc).isoformat()},
            "spec": provider_spec(req, selectors), "status": {"state": state}}
    return req, selectors, pins, job


def test_context_delivered_once_and_terminal_result_observed():
    req, selectors, pins, job = setup()
    observations = iter([None, job(), job(), job("COMPLETED")])
    contexts, canceled, emitted = [], [], []
    result = supervise(req, selectors, pins, read=lambda: next(observations), deliver=contexts.append,
        cancel=canceled.append, emit=emitted.append, now=lambda: 1000, pause=lambda _: None)
    assert result == {"state": "COMPLETED", "job_id": "aijob-fixture", "context_delivered": True}
    assert len(contexts) == 1 and not canceled and emitted[0]["admission_ready"]


def test_failed_context_cancels_once_without_delivery_retry():
    req, selectors, pins, job = setup()
    calls, canceled = [], []
    def deliver(context):
        calls.append(context)
        raise TimeoutError("ambiguous PUT")
    with pytest.raises(TimeoutError):
        supervise(req, selectors, pins, read=job, deliver=deliver, cancel=canceled.append,
                  emit=lambda _: None, now=lambda: 1000, pause=lambda _: None)
    assert len(calls) == 1 and canceled == ["aijob-fixture"]


def test_accounting_watchdog_reserves_cancellation_time():
    req, selectors, pins, job = setup()
    observations = iter([job(), job("CANCELED")])
    canceled, contexts = [], []
    result = supervise(req, selectors, pins, read=lambda: next(observations), deliver=contexts.append,
        cancel=canceled.append, emit=lambda _: None, now=lambda: 8081, pause=lambda _: None)
    assert canceled == ["aijob-fixture"] and not contexts and result["state"] == "CANCELED"


def test_changed_identity_never_receives_context_or_cancellation():
    req, selectors, pins, job = setup()
    bad = job()
    bad["spec"]["image"] = "mutable:tag"
    actions = []
    with pytest.raises(ValueError):
        supervise(req, selectors, pins, read=lambda: bad, deliver=actions.append, cancel=actions.append,
                  emit=lambda _: None, now=lambda: 1000, pause=lambda _: None)
    assert actions == []


@pytest.mark.parametrize("state", ["RUNNING", "COMPLETED"])
def test_overdue_first_observation_cancels_only_owned_live_job(state):
    req, selectors, pins, job = setup()
    canceled, delivered = [], []
    with pytest.raises(ValueError, match="outside bound"):
        supervise(req, selectors, pins, read=lambda: job(state), deliver=delivered.append,
            cancel=canceled.append, emit=lambda _: None, now=lambda: 8201, pause=lambda _: None)
    assert canceled == (["aijob-fixture"] if state == "RUNNING" else [])
    assert delivered == []


def test_future_accounting_timestamp_never_claims_ownership():
    req, selectors, pins, job = setup()
    actions = []
    with pytest.raises(ValueError, match="outside bound"):
        supervise(req, selectors, pins, read=job, deliver=actions.append,
            cancel=actions.append, emit=lambda _: None, now=lambda: 900, pause=lambda _: None)
    assert actions == []
