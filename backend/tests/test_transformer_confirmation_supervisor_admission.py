"""Admission stays closed after observing a Job, despite transient NotFound."""
import json

import pytest

from test_transformer_confirmation_supervisor import (
    DELIVERED, PUBLISH, PUBLISHED, READY, WAIT, event, harness, supervisor,
)

OBSERVED = event("provider_observed", "provider_validation")
INTENT_WAIT = event("attester_waiting", "intent_read")


def test_observed_job_then_missing_intent_then_notfound_never_readmits(monkeypatch, tmp_path):
    h = harness(monkeypatch, tmp_path, [(0, READY), (.25, WAIT), (.5, OBSERVED),
        (.75, INTENT_WAIT), (1, WAIT), (1.25, READY), (1.5, WAIT),
        (1.75, PUBLISHED), (2, DELIVERED)], exit_at=2)
    assert h.run() == 0
    assert [r["admission_ready"] for r in h.observations] == [False, True] + [False] * 6
    assert all(r["admission_closed"] for r in h.observations[2:])
    assert all(r["state"] == "attesting" for r in h.observations[2:])
    assert json.loads((h.output / "status.json").read_bytes())["admission_closed"] is True
    assert len(h.commands) == 1 and not h.signals


@pytest.mark.parametrize("closing_event", [OBSERVED, INTENT_WAIT, PUBLISH, PUBLISHED])
@pytest.mark.parametrize("previously_ready", [False, True])
def test_all_job_observation_paths_irreversibly_close_admission(
        monkeypatch, tmp_path, closing_event, previously_ready):
    prefix = [(0, READY), (.25, WAIT)] if previously_ready else []
    h = harness(monkeypatch, tmp_path, prefix + [(.5, closing_event), (.75, READY),
        (1, WAIT), (1.25, READY), (1.5, WAIT), (1.75, PUBLISHED), (2, DELIVERED)], exit_at=2)
    assert h.run() == 0
    assert any(r["admission_ready"] for r in h.observations) is previously_ready
    assert all(not r["admission_ready"] and r["admission_closed"] for r in h.observations[2:])
    assert (h.output / "readiness.json").exists() is previously_ready


def test_inspection_cannot_admit_a_closed_record_with_ready_state(monkeypatch, tmp_path):
    h = harness(monkeypatch, tmp_path, [(0, READY), (.25, WAIT), (.5, PUBLISHED), (1, DELIVERED)])
    assert h.run() == 0
    ready = json.loads((h.output / "readiness.json").read_bytes())
    ready["admission_closed"] = True
    supervisor.save(h.output / "status.json", ready)
    status = supervisor.inspect(h.output, h.binding["proposal_sha256"], h.binding["request_sha256"],
        now=lambda: ready["updated_at"], identity=lambda pid: "same-start")
    assert status["admission_ready"] is False


def test_provider_observed_with_wrong_stage_fails_closed(monkeypatch, tmp_path):
    h = harness(monkeypatch, tmp_path, [(0, READY), (.25, WAIT),
        (.5, event("provider_observed", "provider_read"))])
    assert h.run() == 1
    status = json.loads((h.output / "status.json").read_bytes())
    assert status["state"] == "failed" and status["error_type"] == "ValueError"
