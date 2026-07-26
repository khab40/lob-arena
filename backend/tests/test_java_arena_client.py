import asyncio
import json
from io import BytesIO

from app.arena.java_client import JavaArenaClient


class Response(BytesIO):
    def __enter__(self) -> "Response":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


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

    def urlopen(req, timeout: float):
        calls.append((req.method, req.full_url))
        return Response(json.dumps(_state(tick=2, running=True)).encode())

    monkeypatch.setattr("app.arena.java_client.request.urlopen", urlopen)
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
    def urlopen(req, timeout: float):
        assert req.full_url == "http://java:8080/api/arena/metrics-state"
        return Response(b'{"tick":7,"running":false,"incidents_count":3}')

    monkeypatch.setattr("app.arena.java_client.request.urlopen", urlopen)

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

    def urlopen(req, timeout: float):
        assert req.full_url == "http://java:8080/api/scenarios/spoofing-like"
        return Response(json.dumps(scenario).encode())

    monkeypatch.setattr("app.arena.java_client.request.urlopen", urlopen)
    tracker = asyncio.run(JavaArenaClient("http://java:8080").start_scenario("spoofing_like_wall"))

    assert tracker.scenario_id == "SCN-000001"
    assert tracker.scenario_family == "spoofing_like_wall"
