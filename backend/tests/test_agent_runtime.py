import asyncio

from app.agents.runtime import (
    AgentIntent,
    AgentManager,
    MarketSnapshot,
    RemoteAgentClient,
    build_agent_manager,
    build_heavy_agents,
    build_normal_agents,
    build_prefixed_normal_agents,
)
from app.arena.engine import SimulationEngine


def _snapshot(tick: int = 1) -> MarketSnapshot:
    return MarketSnapshot(
        tick=tick,
        bids=[{"price": 99.0, "quantity": 5.0}, {"price": 98.0, "quantity": 6.0}],
        asks=[{"price": 101.0, "quantity": 5.0}, {"price": 102.0, "quantity": 6.0}],
        best_bid=99.0,
        best_ask=101.0,
        mid=100.0,
        spread=2.0,
    )


def test_market_snapshot_accepts_profile_context_from_java_control_plane() -> None:
    snapshot = MarketSnapshot(
        **{
            **_snapshot().__dict__,
            "market_profile": {
                "profile_id": "fixture-profile",
                "simulation_parameters": {"agent_order_size_lots": 500_000},
            },
        }
    )

    assert snapshot.market_profile is not None
    assert snapshot.market_profile["profile_id"] == "fixture-profile"


class SlowAgent:
    agent_id = "SLOW_01"

    async def decide(self, snapshot: MarketSnapshot) -> list[AgentIntent]:
        await asyncio.sleep(0.05)
        return [
            AgentIntent(
                tick=snapshot.tick,
                agent_id=self.agent_id,
                kind="set_level",
                side="bid",
                price=99.0,
                quantity=1.0,
            )
        ]


def test_agent_manager_collects_hundreds_of_agents_with_deterministic_sorting() -> None:
    async def run() -> None:
        manager = AgentManager(build_normal_agents(250), decision_timeout_seconds=0.05)
        intents = await manager.collect_intents(_snapshot(tick=4))

        assert len(manager.agent_ids) == 250
        assert intents == sorted(intents, key=lambda intent: intent.sort_key)
        assert {intent.agent_id for intent in intents} >= {"MM_01", "NOISE_01", "TAKER_01"}

    asyncio.run(run())


def test_agent_manager_drops_agents_that_miss_tick_deadline() -> None:
    async def run() -> None:
        manager = AgentManager([SlowAgent()], decision_timeout_seconds=0.001)
        intents = await manager.collect_intents(_snapshot())

        assert intents == []

    asyncio.run(run())


def test_simulation_engine_runs_hundreds_of_registered_agents_single_writer() -> None:
    engine = SimulationEngine(normal_agent_count=250)
    state = engine.step()

    assert state["tick"] == 1
    assert len(state["active_agents"]) == 250
    assert state["book"]["bids"]
    assert state["book"]["asks"]
    assert state["events"]


def test_remote_agent_client_parses_runner_intents() -> None:
    def post_json(url: str, payload: dict[str, object], timeout_seconds: float) -> dict[str, object]:
        assert url == "http://runner.local/decide"
        assert timeout_seconds == 0.02
        assert payload["snapshot"]["tick"] == 7
        return {
            "intents": [
                {
                    "tick": 7,
                    "agent_id": "REMOTE_NOISE_001",
                    "kind": "set_level",
                    "side": "bid",
                    "price": 99.0,
                    "quantity": 4.5,
                    "message": "remote depth update",
                }
            ]
        }

    async def run() -> None:
        client = RemoteAgentClient(
            "http://runner.local",
            runner_id="01",
            timeout_seconds=0.02,
            post_json=post_json,
        )
        intents = await client.decide(_snapshot(tick=7))

        assert client.agent_id == "remote_runner:01"
        assert len(intents) == 1
        assert intents[0].agent_id == "REMOTE_NOISE_001"
        assert intents[0].kind == "set_level"
        assert intents[0].runtime_source == "agent_runner"

    asyncio.run(run())


def test_agent_events_expose_execution_runtime_and_simulation_tick() -> None:
    engine = SimulationEngine(normal_agent_count=0, baseline_liquidity_levels=0)
    intent = AgentIntent(
        tick=7,
        agent_id="REMOTE_NOISE_001",
        kind="set_level",
        runtime_source="agent_runner",
        side="bid",
        price=99.0,
        quantity=1.0,
    )

    event = engine._apply_agent_intent(intent)

    assert event is not None
    assert event.timestamp == 7
    assert event.runtime_source == "agent_runner"


def test_build_agent_manager_combines_local_and_remote_runners() -> None:
    manager = build_agent_manager(
        local_agent_count=3,
        remote_agent_urls=["http://runner-a:9100", "", "http://runner-b:9100"],
        decision_timeout_seconds=0.05,
    )

    assert manager.agent_ids == ["MM_01", "NOISE_01", "TAKER_01", "remote_runner:01", "remote_runner:03"]


def test_prefixed_remote_agents_emit_market_flow_in_demo_window() -> None:
    agents = build_prefixed_normal_agents(24, "REMOTE")
    market_intents = []

    for tick in range(1, 5):
        for agent in agents:
            market_intents.extend(intent for intent in agent.decide(_snapshot(tick=tick)) if intent.kind == "market")

    assert len(agents) == 24
    assert market_intents
    assert {intent.agent_id for intent in market_intents} >= {"REMOTE_TAKER_001", "REMOTE_TAKER_004"}


def test_heavy_agent_uses_async_worker_path() -> None:
    async def run() -> None:
        agents = build_heavy_agents(3, "TEST", complexity=250)
        manager = AgentManager(agents, decision_timeout_seconds=0.5)
        intents = await manager.collect_intents(_snapshot(tick=9))

        assert len(manager.agent_ids) == 3
        assert intents
        assert all(intent.agent_id.startswith("TEST_HEAVY_") for intent in intents)
        assert all(intent.message == "heavy agent worker-pool decision" for intent in intents)

    asyncio.run(run())


def test_simulation_reseeds_asks_when_market_orders_empty_side() -> None:
    engine = SimulationEngine(
        normal_agent_count=0,
        baseline_liquidity_levels=4,
        baseline_liquidity_base_size=1.0,
        baseline_liquidity_tick_size=1.0,
        baseline_liquidity_reference_price=100.0,
    )
    engine.order_book.apply_market_order("buy", 1_000.0)
    assert engine.order_book.get_l2_snapshot()["asks"] == []

    state = engine.step()

    assert state["book"]["asks"]
    assert len(state["book"]["asks"]) >= 4
    assert state["book"]["best_ask"] == 101.0


def test_agent_set_level_intents_do_not_overwrite_same_price_liquidity() -> None:
    engine = SimulationEngine(normal_agent_count=0, baseline_liquidity_levels=0)
    first = AgentIntent(tick=1, agent_id="AGENT_A", kind="set_level", side="ask", price=101.0, quantity=2.0)
    second = AgentIntent(tick=1, agent_id="AGENT_B", kind="set_level", side="ask", price=101.0, quantity=3.0)

    engine._apply_agent_intents([first, second])

    assert engine.order_book.get_l2_snapshot()["asks"] == [{"price": 101.0, "quantity": 5.0}]


def test_agent_set_level_quantity_is_clamped_before_book_update() -> None:
    engine = SimulationEngine(normal_agent_count=0, baseline_liquidity_levels=0, max_agent_quote_size=25.0)
    intent = AgentIntent(tick=1, agent_id="REMOTE_BAD", kind="set_level", side="ask", price=101.0, quantity=1_000_000.0)

    engine._apply_agent_intents([intent])

    assert engine.order_book.get_l2_snapshot()["asks"] == [{"price": 101.0, "quantity": 25.0}]


def test_simulation_keeps_bounded_two_sided_ladder_after_many_agent_ticks() -> None:
    engine = SimulationEngine(normal_agent_count=250)

    for _ in range(120):
        state = engine.step()

    assert len(state["book"]["bids"]) >= 12
    assert len(state["book"]["asks"]) >= 12
    assert state["book"]["best_bid"] is not None
    assert state["book"]["best_ask"] is not None
    assert max(level["quantity"] for level in state["book"]["bids"]) < 1_000
    assert max(level["quantity"] for level in state["book"]["asks"]) < 1_000
