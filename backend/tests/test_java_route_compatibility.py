"""CEO-BACKEND-FULL-I1-01: actual main order, invented typed/raw upstreams only."""

import json

import pytest
from fastapi.testclient import TestClient

from app.api import routes_arena, routes_scenarios, routes_simulation
from app.arena.java_client import JavaArenaClient
from app.arena.java_transport import JavaResponse
from app.schemas.arena import ArenaState, AttackTrackerState, ExchangeEventReplay
from test_ceo_auth import ORIGIN, configured as auth_fixture, sign_in
from test_java_arena_client import _state
from test_runtime_roots import execute_startup

configured = auth_fixture
OWNED = [
    ("GET", "/api/arena/state", routes_arena.get_arena_state),
    ("GET", "/api/arena/exchange-events", routes_arena.get_exchange_events),
    ("POST", "/api/simulation/start", routes_simulation.start_simulation),
    ("POST", "/api/simulation/pause", routes_simulation.pause_simulation),
    ("POST", "/api/simulation/reset", routes_simulation.reset_simulation),
    ("POST", "/api/scenarios/spoofing-like", routes_scenarios.start_spoofing_like),
    ("POST", "/api/scenarios/layering-like", routes_scenarios.start_layering_like),
    ("POST", "/api/scenarios/quote-stuffing", routes_scenarios.start_quote_stuffing),
    ("POST", "/api/scenarios/liquidity-evaporation", routes_scenarios.start_liquidity_evaporation),
]


def replay():
    return {"events": [], "after_sequence": 123, "next_after_sequence": 125,
            "latest_sequence": 130, "has_more": True, "stream_id": "invented-stream"}


def tracker():
    return {"scenario_id": "SCN-invented", "scenario_name": "Invented", "scenario_family": "layering_like",
            "agent_id": "invented", "current_stage": "armed", "start_tick": 1, "status": "armed"}


@pytest.fixture(params=[False, True], ids=["ordinary", "authenticated"])
def integrated(configured, monkeypatch, request):
    auth, claims, *_ = configured
    enabled = request.param
    auth.settings.ceo_demo_enabled = enabled
    if not enabled:
        auth.settings.research_saved_scores_dir = None
    monkeypatch.setattr("app.ceo_auth.CEOAuth", lambda _settings: auth)
    spec, module, _ = execute_startup(monkeypatch, auth.settings)
    spec.loader.exec_module(module)
    upstream = JavaArenaClient("http://invented-java", 0.2)
    module.app.state.simulation = upstream
    client = TestClient(module.app, base_url=ORIGIN, client=("127.0.0.1", 12345))
    if enabled:
        assert sign_in(client, claims).status_code == 200
    calls = []

    def typed(method, path, *_args):
        calls.append(("typed", method, path))
        if "/exchange-events" in path:
            payload = replay()
        elif path.startswith("/api/scenarios/"):
            payload = tracker()
        else:
            payload = _state(tick=9, running=True)
        return JavaResponse(200, json.dumps(payload).encode(), "application/json")

    class Raw:
        status, content_type = 206, "application/x-protobuf"
        def chunks(self):
            yield b"invented-exact-raw-result"
        def close(self):
            pass

    def raw(method, path, body, content_type, *, timeout):
        calls.append(("raw", method, path, body, content_type, timeout))
        return Raw()

    monkeypatch.setattr(upstream.transport, "request", typed)
    monkeypatch.setattr(upstream.transport, "open", raw)
    return client, module.app, upstream, calls


@pytest.mark.parametrize("method,path,_endpoint", OWNED)
def test_original_collision_paths_keep_typed_adapter_and_normal_response(integrated, method, path, _endpoint):
    client, _, _, calls = integrated
    response = client.request(method, path, headers={"Origin": ORIGIN})
    model = (ExchangeEventReplay if path.endswith("exchange-events") else
             AttackTrackerState if "/scenarios/" in path else ArenaState)
    expected = replay() if model is ExchangeEventReplay else tracker() if model is AttackTrackerState else _state(tick=9, running=True)
    assert response.status_code == 200 and response.json() == model.model_validate(expected).model_dump(mode="json")
    target = "/api/arena/exchange-events?afterSequence=0&limit=100" if path.endswith("exchange-events") else path
    assert calls == [("typed", method, target)]


def test_snake_cursor_uses_original_translation_and_typed_response(integrated):
    client, _, _, calls = integrated
    response = client.get("/api/arena/exchange-events?after_sequence=123&limit=2")
    assert response.status_code == 200
    assert response.json() == ExchangeEventReplay.model_validate(replay()).model_dump(mode="json")
    assert calls == [("typed", "GET", "/api/arena/exchange-events?afterSequence=123&limit=2")]


def test_typed_pagination_advances_from_previous_page_cursor(integrated, monkeypatch):
    from urllib.parse import parse_qs, urlsplit
    client, _, upstream, calls = integrated
    def page(method, path):
        calls.append((method, path))
        cursor = int(parse_qs(urlsplit(path).query)["afterSequence"][0])
        payload = {**replay(), "after_sequence": cursor, "next_after_sequence": cursor + 2}
        return JavaResponse(200, json.dumps(payload).encode(), "application/json")
    monkeypatch.setattr(upstream.transport, "request", page)
    first = client.get("/api/arena/exchange-events?after_sequence=123&limit=2").json()
    second = client.get(f"/api/arena/exchange-events?after_sequence={first['next_after_sequence']}&limit=2").json()
    assert first["next_after_sequence"] == second["after_sequence"] == 125
    assert second["next_after_sequence"] == 127
    assert calls == [("GET", "/api/arena/exchange-events?afterSequence=123&limit=2"),
                     ("GET", "/api/arena/exchange-events?afterSequence=125&limit=2")]


@pytest.mark.parametrize("query", ["afterSequence=123&limit=2", "streamId=invented%2Fstream&limit=2",
    "afterSequence=123&streamId=invented%2Fstream&limit=2"])
def test_java_cursor_and_stream_forms_keep_exact_raw_query_status_and_bytes(integrated, query):
    client, _, _, calls = integrated
    response = client.get("/api/arena/exchange-events?" + query)
    assert response.status_code == 206 and response.content == b"invented-exact-raw-result"
    assert response.headers["content-type"] == "application/x-protobuf"
    assert calls == [("raw", "GET", "/api/arena/exchange-events?" + query, None, "application/json", 60)]


def test_mixed_snake_cursor_and_java_stream_advances_with_same_stream_value(integrated):
    client, _, _, calls = integrated
    response = client.get("/api/arena/exchange-events?after_sequence=123&streamId=invented%2Fstream&limit=2")
    assert response.status_code == 206
    assert calls == [("raw", "GET", "/api/arena/exchange-events?afterSequence=123&streamId=invented%2Fstream&limit=2",
                      None, "application/json", 60)]


@pytest.mark.parametrize("query", ["after_sequence=-1", "afterSequence=-1", "limit=0", "limit=1001",
    "after_sequence=not-integer", "afterSequence=not-integer", "limit=not-integer",
    "after_sequence=1&afterSequence=2", "after_sequence=1&afterSequence=1",
    "after_sequence=1&after_sequence=2", "afterSequence=1&afterSequence=2",
    "streamId=one&streamId=two", "limit=1&limit=2",
    "after_sequence=-1&streamId=invented", "afterSequence=-1&streamId=invented"])
def test_original_query_bounds_and_ambiguous_parameters_rejected_before_upstream(integrated, query):
    client, _, _, calls = integrated
    response = client.get("/api/arena/exchange-events?" + query)
    assert response.status_code == 422 and calls == []


@pytest.mark.parametrize("path", ["/api/arena/runtime-limits", "/api/arena/historical-datasets",
                                   "/api/kernel/run", "/api/scenarios/not-original"])
def test_java_only_paths_still_reach_shared_raw_bridge(integrated, path):
    client, _, _, calls = integrated
    method = "POST" if "/kernel/" in path or "/scenarios/" in path else "GET"
    response = client.request(method, path, headers={"Origin": ORIGIN})
    assert response.status_code == 206 and calls[0][:3] == ("raw", method, path)


def test_original_scenario_error_adapter_remains_authoritative(integrated, monkeypatch):
    client, _, upstream, calls = integrated
    def rejected(method, path):
        calls.append(("typed", method, path))
        return JavaResponse(422, b"invented-owner-error", "text/plain")
    monkeypatch.setattr(upstream.transport, "request", rejected)
    response = client.post("/api/scenarios/spoofing-like", headers={"Origin": ORIGIN})
    assert response.status_code == 404 and response.json() == {"detail": "Java arena returned HTTP 422"}
    assert calls == [("typed", "POST", "/api/scenarios/spoofing-like")]
