import asyncio
import json

from app.arena.java_client import JavaArenaClient
from app.arena.java_transport import JavaResponse


def _state(*, tick: int = 0, running: bool = False) -> dict[str, object]:
    return {
        "tick": tick,
        "running": running,
        "events": [],
        "exchange_events": [],
        "book": {
            "bids": [{"price": 99.0, "quantity": 1.0}],
            "asks": [{"price": 101.0, "quantity": 1.0}],
            "best_bid": 99.0,
            "best_ask": 101.0,
            "mid": 100.0,
            "spread": 2.0,
        },
        "best_bid": 99.0,
        "best_ask": 101.0,
        "mid": 100.0,
        "spread": 2.0,
        "active_agents": [],
        "active_scenario": None,
        "detectors": {"scores": [], "alerts": []},
        "incidents": [],
        "features": {},
    }


def test_java_arena_client_controls_and_reads_state(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def request(_self, method, path):
        calls.append((method, "http://java:8080" + path))
        return JavaResponse(200, json.dumps(_state(tick=2, running=True)).encode(), "application/json")

    monkeypatch.setattr("app.arena.java_transport.JavaTransport.request", request)
    client = JavaArenaClient("http://java:8080", timeout_seconds=0.5)

    async def run() -> None:
        state = await client.start()
        assert state.tick == 2
        assert state.running is True
        assert (await client.get_state()).book.best_bid == 99.0

    asyncio.run(run())
    assert calls == [
        ("POST", "http://java:8080/api/simulation/start"),
        ("GET", "http://java:8080/api/arena/state"),
    ]


def test_java_arena_client_reads_lightweight_metrics_snapshot(monkeypatch) -> None:
    def request(_self, method, path):
        assert path == "/api/arena/metrics-state"
        return JavaResponse(200, b'{"tick":7,"running":false,"incidents_count":3}', "application/json")

    monkeypatch.setattr("app.arena.java_transport.JavaTransport.request", request)

    snapshot = asyncio.run(JavaArenaClient("http://java:8080").get_metrics_snapshot())

    assert snapshot.tick == 7
    assert snapshot.running is False
    assert snapshot.incidents_count == 3


def test_java_arena_client_maps_scenario_slug(monkeypatch) -> None:
    scenario = {
        "scenario_id": "SCN-000001",
        "scenario_name": "Spoofing-like Wall",
        "scenario_family": "spoofing_like_wall",
        "agent_id": "ABUSER_01",
        "current_stage": "armed",
        "start_tick": 1,
        "status": "armed",
        "stages": [],
        "evidence": [],
    }

    def request(_self, method, path):
        assert path == "/api/scenarios/spoofing-like"
        return JavaResponse(200, json.dumps(scenario).encode(), "application/json")

    monkeypatch.setattr("app.arena.java_transport.JavaTransport.request", request)
    tracker = asyncio.run(JavaArenaClient("http://java:8080").start_scenario("spoofing_like_wall"))

    assert tracker.scenario_id == "SCN-000001"
    assert tracker.scenario_family == "spoofing_like_wall"
