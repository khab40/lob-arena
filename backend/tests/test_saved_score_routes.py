from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import routes_saved_scores
from app.api.routes_experiments import _resolve_readable_artifact
from app.research.saved_scores import CAMPAIGN_ID, load_campaign
from tests.saved_score_fixtures import evidence


def client_for(tmp_path, monkeypatch, *, enabled=True, peer="127.0.0.1"):
    directory, pin = evidence(tmp_path)
    app = FastAPI()
    app.state.settings = SimpleNamespace(research_saved_scores_enabled=enabled, research_saved_scores_dir=directory)
    app.state.store = SimpleNamespace(output_dir=tmp_path / "public")
    app.include_router(routes_saved_scores.router)
    monkeypatch.setattr(routes_saved_scores, "load_campaign", lambda base, roots: load_campaign(
        base, roots, verification_sha=pin, expected_rows=3, expected_positives=1))
    return TestClient(app, base_url="http://127.0.0.1", client=(peer, 50000)), directory, app


def test_read_only_routes_return_bounded_saved_scores(tmp_path, monkeypatch):
    client, _directory, _app = client_for(tmp_path, monkeypatch)
    catalog = client.get("/api/research/saved-scores/campaigns")
    assert catalog.status_code == 200
    assert catalog.headers["cache-control"] == "no-store"
    session = catalog.json()["sessions"][0]["id"]
    path = f"/api/research/saved-scores/campaigns/{CAMPAIGN_ID}/rows"
    response = client.get(path, params={"session_id": session, "detector": "lightgbm", "limit": 2})
    assert response.status_code == 200
    assert len(response.json()["rows"]) == 2
    assert response.json()["next_offset"] == 2
    assert client.post(path).status_code == 405
    for params in ({"limit": 101}, {"offset": -1}, {"offset": 4}, {"detector": "hybrid"}, {"session_id": "../private"}):
        rejected = client.get(path, params={"session_id": session, "detector": "transformer", **params})
        assert rejected.status_code in (404, 422)
    assert client.get(path.replace(CAMPAIGN_ID, "other"), params={"session_id": session, "detector": "transformer"}).status_code == 404


def test_disabled_by_default_and_no_private_error_details(tmp_path, monkeypatch):
    client, directory, app = client_for(tmp_path, monkeypatch, enabled=False)
    assert client.get("/api/research/saved-scores/campaigns").status_code == 404
    app.state.settings.research_saved_scores_enabled = True
    (directory / "predictions.json").write_bytes(b"{}")
    response = client.get("/api/research/saved-scores/campaigns")
    assert response.status_code == 503
    assert str(directory) not in response.text
    assert "predictions.json" not in response.text


@pytest.mark.parametrize("headers", [
    {"Host": "example.org"}, {"Host": "localhost.example.org"},
    {"Origin": "https://remote.example"}, {"Origin": "http://localhost@remote.example"},
    {"Forwarded": "for=127.0.0.1"}, {"X-Forwarded-For": "127.0.0.1"},
    {"X-Forwarded-Host": "localhost"}, {"Sec-Fetch-Site": "cross-site"},
])
def test_nonlocal_or_proxied_access_denied(tmp_path, monkeypatch, headers):
    client, _directory, _app = client_for(tmp_path, monkeypatch)
    assert client.get("/api/research/saved-scores/campaigns", headers=headers).status_code == 403


def test_nonloopback_peer_denied_even_with_loopback_host(tmp_path, monkeypatch):
    client, _directory, _app = client_for(tmp_path, monkeypatch, peer="192.0.2.1")
    assert client.get("/api/research/saved-scores/campaigns").status_code == 403


def test_loopback_browser_origin_allowed(tmp_path, monkeypatch):
    client, _directory, _app = client_for(tmp_path, monkeypatch)
    assert client.get("/api/research/saved-scores/campaigns", headers={"Origin": "http://localhost:5173"}).status_code == 200


def test_private_evidence_outside_generic_artifact_routes(tmp_path, monkeypatch):
    client, directory, app = client_for(tmp_path, monkeypatch)
    from starlette.requests import Request
    from fastapi import HTTPException
    request = Request({"type": "http", "app": app})
    for name in ("predictions.json", "verification.json", "receipts/predictions.json.json"):
        with pytest.raises(HTTPException) as error:
            _resolve_readable_artifact(request, str(directory / name))
        assert error.value.status_code == 403
    app.state.store.output_dir = directory.parent
    assert client.get("/api/research/saved-scores/campaigns").status_code == 503


@pytest.mark.parametrize("enabled", [True, False])
def test_private_root_guard_precedes_startup_cleanup(tmp_path, monkeypatch, enabled):
    import importlib
    import sys
    from app import config
    from app.storage import local_store, retention
    directory, _pin = evidence(tmp_path)
    settings = config.Settings(_env_file=None, ARENA_OUTPUT_DIR=tmp_path,
                               RESEARCH_SAVED_SCORES_ENABLED=enabled, RESEARCH_SAVED_SCORES_DIR=directory)
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    def forbidden(*_args, **_kwargs):
        pytest.fail("startup reached artifact initialization before rejecting private overlap")
    monkeypatch.setattr(local_store, "LocalStore", forbidden)
    monkeypatch.setattr(retention, "cleanup_output_data", forbidden)
    monkeypatch.delitem(sys.modules, "app.main", raising=False)
    with pytest.raises(ValueError, match="overlaps"):
        importlib.import_module("app.main")
    assert (directory / "predictions.json").exists()
