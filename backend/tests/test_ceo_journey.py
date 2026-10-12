"""CEO-AC-03..08: fictional saved scores and identities; no private/model calls."""
import os
import secrets

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.routes_ceo_auth import router as auth_router
from app.api.routes_ceo_journey import router
from app.ceo_auth import CEOAuth
from app.ceo_auth_boundary import CEOAccessBoundary
from app.ceo_journey import CEOJourney
from app.ceo_journey_evidence import factual_text, verify_hash
from app.ceo_journey_store import ArtifactUnavailable, JourneyStore
from app.config import Settings
from app.research.saved_score_io import canonical, sha256
from app.research.saved_scores import load_campaign, SavedCampaign, THRESHOLDS

ORIGIN = "http://localhost:5173"


@pytest.fixture
def journey(tmp_path):
    state = tmp_path / "state"
    settings = Settings(_env_file=None, CEO_DEMO_ENABLED=True, CEO_DEMO_LOCAL=True,
        CEO_DEMO_ORIGIN=ORIGIN, GOOGLE_CLIENT_ID="example.apps.googleusercontent.com",
        CEO_DEMO_ALLOWED_EMAILS="reviewer@example.com,other@example.com", CEO_DEMO_STATE_DIR=state,
        ARENA_OUTPUT_DIR=tmp_path / "generic", RESEARCH_SAVED_SCORES_DIR=tmp_path / "custody")
    clock = [1000.0]
    claims = {"sub": "example-subject", "email": "reviewer@example.com", "name": "Reviewer",
        "iss": "accounts.google.com", "aud": settings.google_client_id, "email_verified": True,
        "exp": 10000, "nonce": ""}
    auth = CEOAuth(settings, lambda *_: dict(claims), lambda: clock[0])
    original_rows = [{"target_id": f"{i + 1:064x}", "label": int(i == 40), "run_id": "example-shard",
        "base_session_id": "example-base", "campaign_id": "example-campaign",
        "prediction_timestamp_ns": 1000000000000 + i, "logit": 0.0,
        "probability": 0.997 if i in {40, 70, 95} else 0.1,
        "baseline_probability": 0.7 if i == 35 else 0.4, "family": "layering_like" if i == 40 else "control",
        "symbol": "AAPL"} for i in range(110)]
    original = SavedCampaign(original_rows, {"verification_sha256": "a" * 64, "settings_sha256": "b" * 64,
        "job_id": "example-job", "request_sha256": "c" * 64,
        "predictions": {"sha256": "d" * 64, "size_bytes": 100, "version_id": "1"},
        "model_checkpoint_sha256": "e" * 64})
    reads = []
    def loader(path, roots):
        assert path == settings.research_saved_scores_dir
        reads.append((path, roots))
        return original
    service = CEOJourney(settings, (settings.arena_output_dir, settings.ceo_demo_state_dir),
                         loader=loader, clock=lambda: clock[0])
    app = FastAPI()
    app.state.ceo_auth, app.state.ceo_journey = auth, service
    app.include_router(auth_router)
    app.include_router(router)
    app.add_middleware(CEOAccessBoundary, auth=auth)
    @app.exception_handler(RequestValidationError)
    async def invalid(_request, _error):
        return JSONResponse({"detail": "Invalid request"}, status_code=400, headers={"Cache-Control": "no-store"})
    client = TestClient(app, base_url=ORIGIN, client=("127.0.0.1", 50000))
    def login(subject="example-subject", email="reviewer@example.com", selected_client=client):
        response = selected_client.get("/api/auth/config")
        claims.update(nonce=response.json()["nonce"], sub=subject, email=email)
        assert selected_client.post("/api/auth/google", json={"credential": "example"},
                                    headers={"Origin": ORIGIN}).status_code == 200
    login()
    return type("Fixture", (), {"service": service, "client": client, "auth": auth, "original": original,
        "reads": reads, "clock": clock, "login": staticmethod(login), "app": app})()


def post(journey, path, body=None, client=None):
    return (client or journey.client).post("/api/ceo-demo/" + path, json={} if body is None else body,
                                          headers={"Origin": ORIGIN})


def capture(journey, *, detector="transformer", index=40):
    response = post(journey, "anomalies", {"detector": detector, "target_id": journey.original.rows[index]["target_id"]})
    assert response.status_code == 200, response.text
    return response.json()


def complete(journey):
    snapshot = capture(journey)
    explanation = post(journey, f"anomalies/{snapshot['id']}/explanation")
    assert explanation.status_code == 200
    saved = post(journey, f"anomalies/{snapshot['id']}/save")
    assert saved.status_code == 200
    return snapshot, explanation.json(), saved.json()


def test_fixed_original_window_preserves_ordinals_targets_timestamps_and_both_scores(journey):
    catalog = journey.client.get("/api/ceo-demo/campaign")
    assert catalog.status_code == 200 and catalog.headers["cache-control"] == "no-store"
    window = catalog.json()["prepared_window"]
    assert window == {"session_id": sha256(b"example-shard")[:16], "offset": 24, "limit": 64}
    assert catalog.json()["kind"] == "saved_research_predictions"
    assert catalog.json()["label_context"] == "synthetic_research_labels"
    for detector in THRESHOLDS:
        response = journey.client.get("/api/ceo-demo/rows", params={"detector": detector})
        assert response.json() == journey.original.page(window["session_id"], detector, 24, 64)
        assert response.json()["rows"][16]["timestamp_ns"] == "1000000000040"
    assert len(journey.reads) == 3


def test_capture_keeps_exact_selected_row_paired_context_and_immutable_hash(journey):
    snapshot = capture(journey)
    verify_hash(snapshot, "snapshot_sha256")
    assert snapshot["row"]["ordinal"] == 40 and snapshot["row"]["synthetic_label"] == 1
    assert len(snapshot["context"]) == 16 and snapshot["context"][0]["ordinal"] == 24
    assert snapshot["paired_scores"]["transformer"]["alert"] is True
    assert snapshot["paired_scores"]["lightgbm"]["alert"] is False
    assert snapshot["context"][11]["paired_scores"]["lightgbm"]["alert"] is True
    original_bytes = canonical(snapshot)
    journey.client.get("/api/ceo-demo/rows?detector=lightgbm")
    journey.original.rows[40]["probability"] = 0.1
    assert canonical(journey.service.snapshot("example-subject", snapshot["id"])) == original_bytes
    explanation = post(journey, f"anomalies/{snapshot['id']}/explanation").json()
    assert canonical(explanation["input"]) == original_bytes


def test_explicit_factual_fallback_and_repeated_explain_save_reopen_export_are_durable(journey):
    snapshot, explanation, saved = complete(journey)
    assert explanation["mode"] == "deterministic_fallback"
    assert explanation["input_sha256"] == snapshot["snapshot_sha256"]
    assert explanation["text"] == factual_text(snapshot)
    assert "no LLM call or fresh inference" in explanation["text"]
    assert "do not establish adjudicated market abuse" in explanation["text"]
    verify_hash(explanation, "explanation_sha256")
    verify_hash(saved, "record_sha256")
    journey.clock[0] += 100
    assert post(journey, f"anomalies/{snapshot['id']}/explanation").json() == explanation
    assert post(journey, f"anomalies/{snapshot['id']}/save").json() == saved
    reopened = journey.client.get(f"/api/ceo-demo/evidence/{snapshot['id']}")
    exported = journey.client.get(f"/api/ceo-demo/evidence/{snapshot['id']}/export")
    assert reopened.json() == exported.json() == saved
    assert exported.content == canonical(saved) and "attachment" in exported.headers["content-disposition"]
    assert exported.headers["cache-control"] == "no-store"
    assert journey.client.get("/api/ceo-demo/evidence").json() == [{"id": snapshot["id"], "symbol": "AAPL",
        "detector": "transformer", "saved_at": saved["saved_at"]}]
    recovered = CEOJourney(journey.auth.settings, (), loader=lambda *_: None)
    assert recovered.record("example-subject", snapshot["id"]) == saved


@pytest.mark.parametrize("selection", ["nonalert", "outside", "unknown", "unsupported"])
def test_refuse_nonalert_outside_window_unknown_or_unsupported_selection(journey, selection):
    index = 39 if selection == "nonalert" else 95 if selection == "outside" else 40
    body = {"detector": "other" if selection == "unsupported" else "transformer",
            "target_id": "f" * 64 if selection == "unknown" else journey.original.rows[index]["target_id"]}
    response = post(journey, "anomalies", body)
    assert response.status_code in {400, 422}
    assert not list(journey.service.store.root.glob("*/*.snapshot.json"))


def test_lightgbm_alert_capture_uses_same_original_window(journey):
    snapshot = capture(journey, detector="lightgbm", index=35)
    assert snapshot["row"]["alert"] is True and snapshot["row"]["probability"] == 0.7
    assert snapshot["paired_scores"]["transformer"]["alert"] is False


@pytest.mark.parametrize("operation", ["campaign", "rows", "capture"])
def test_changed_custody_refuses_fresh_reads_and_capture_without_private_path_leak(journey, operation):
    def changed(*_):
        raise ValueError("/private/example/predictions changed")
    journey.service.loader = changed
    if operation == "capture":
        response = post(journey, "anomalies", {"detector": "transformer", "target_id": "a" * 64})
    else:
        response = journey.client.get("/api/ceo-demo/" + operation + ("?detector=transformer" if operation == "rows" else ""))
    assert response.status_code == 503 and "/private/" not in response.text


def test_no_original_transformer_alert_means_unavailable_campaign(journey):
    for row in journey.original.rows:
        row["probability"] = 0.1
    response = journey.client.get("/api/ceo-demo/campaign")
    assert response.status_code == 503


def test_existing_pinned_verifier_reads_only_invented_custody_and_refuses_later_change(journey, tmp_path):
    from tests.saved_score_fixtures import evidence
    directory, pin = evidence(tmp_path)
    journey.auth.settings.research_saved_scores_dir = directory
    journey.service.loader = lambda path, roots: load_campaign(path, roots, verification_sha=pin,
        expected_rows=3, expected_positives=1)
    campaign = journey.client.get("/api/ceo-demo/campaign")
    assert campaign.status_code == 200 and campaign.json()["prepared_window"]["limit"] == 3
    page = journey.client.get("/api/ceo-demo/rows?detector=transformer").json()
    threshold_row = page["rows"][1]
    snapshot = post(journey, "anomalies", {"detector": "transformer", "target_id": threshold_row["target_id"]})
    assert snapshot.status_code == 200 and snapshot.json()["row"] == threshold_row
    assert snapshot.json()["row"]["probability"] == THRESHOLDS["transformer"]
    (directory / "predictions.json").write_bytes(b"{}")
    response = post(journey, "anomalies", {"detector": "transformer", "target_id": threshold_row["target_id"]})
    assert response.status_code == 503 and str(directory) not in response.text
