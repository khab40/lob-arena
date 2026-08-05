import asyncio
import inspect
import json
from dataclasses import asdict, dataclass
from collections.abc import Awaitable, Callable
from concurrent.futures import Executor
from typing import Any, Literal, Protocol
from urllib import request

from app.exchange.schemas import BookSide, Order, Side


IntentKind = Literal["set_level", "market", "limit", "cancel"]
AgentEventType = Literal["market_maker", "normal"]
AgentRuntimeSource = Literal["backend", "agent_runner"]


@dataclass(frozen=True)
class MarketSnapshot:
    tick: int
    bids: list[dict[str, object]]
    asks: list[dict[str, object]]
    best_bid: float | None
    best_ask: float | None
    mid: float | None
    spread: float | None
    market_profile: dict[str, object] | None = None


@dataclass(frozen=True)
class AgentIntent:
    tick: int
    agent_id: str
    kind: IntentKind
    sequence: int = 0
    latency_bucket: int = 0
    event_type: AgentEventType = "normal"
    runtime_source: AgentRuntimeSource = "backend"
    side: BookSide | Side | None = None
    price: float | None = None
    quantity: float = 0.0
    order_id: str | None = None
    message: str = ""

    @property
    def sort_key(self) -> tuple[int, int, str, int, str]:
        return (self.tick, self.latency_bucket, self.agent_id, self.sequence, self.kind)

    def to_order(self) -> Order:
        side: Side
        if self.side in {"bid", "buy"}:
            side = "buy"
        elif self.side in {"ask", "sell"}:
            side = "sell"
        else:
            raise ValueError(f"intent {self.kind} requires a side")

        order_type = "limit"
        if self.kind == "market":
            order_type = "market"
        elif self.kind == "cancel":
            order_type = "cancel"

        return Order(
            order_id=self.order_id or f"{self.agent_id}-{self.tick}-{self.sequence}",
            agent_id=self.agent_id,
            side=side,
            quantity=self.quantity,
            price=self.price,
            order_type=order_type,
            timestamp=self.tick,
        )


class RuntimeAgent(Protocol):
    agent_id: str

    def decide(self, snapshot: MarketSnapshot) -> list[AgentIntent] | Awaitable[list[AgentIntent]]:
        ...


class TopOfBookMarketMaker:
    def __init__(self, agent_id: str = "MM_01") -> None:
        self.agent_id = agent_id

    def decide(self, snapshot: MarketSnapshot) -> list[AgentIntent]:
        if snapshot.best_bid is None or snapshot.best_ask is None:
            return []
        bid_size = round(2.0 + (snapshot.tick % 5) * 0.25, 3)
        ask_size = round(2.1 + ((snapshot.tick + 2) % 5) * 0.25, 3)
        return [
            AgentIntent(
                tick=snapshot.tick,
                agent_id=self.agent_id,
                kind="set_level",
                sequence=0,
                event_type="market_maker",
                side="bid",
                price=snapshot.best_bid,
                quantity=bid_size,
                message="refreshed best bid depth",
            ),
            AgentIntent(
                tick=snapshot.tick,
                agent_id=self.agent_id,
                kind="set_level",
                sequence=1,
                event_type="market_maker",
                side="ask",
                price=snapshot.best_ask,
                quantity=ask_size,
                message="refreshed best ask depth",
            ),
        ]


class DeterministicNoiseTrader:
    def __init__(self, agent_id: str = "NOISE_01", offset: int = 0, cadence: int = 1) -> None:
        self.agent_id = agent_id
        self.offset = offset
        self.cadence = max(1, cadence)

    def decide(self, snapshot: MarketSnapshot) -> list[AgentIntent]:
        if (snapshot.tick + self.offset) % self.cadence != 0:
            return []
        side: BookSide = "bid" if (snapshot.tick + self.offset) % 2 else "ask"
        levels = snapshot.bids if side == "bid" else snapshot.asks
        if not levels:
            return []
        level_index = min((snapshot.tick + self.offset + 2) % 5, len(levels) - 1)
        level = levels[level_index]
        price = float(level["price"])
        next_size = round(0.35 + ((snapshot.tick + self.offset) % 5) * 0.075, 3)
        return [
            AgentIntent(
                tick=snapshot.tick,
                agent_id=self.agent_id,
                kind="set_level",
                sequence=0,
                latency_bucket=self.offset % 5,
                side=side,
                price=price,
                quantity=next_size,
                message="small visible depth changed",
            )
        ]


class PeriodicLiquidityTaker:
    def __init__(self, agent_id: str = "TAKER_01", offset: int = 0, cadence: int = 4, quantity: float = 0.5) -> None:
        self.agent_id = agent_id
        self.offset = offset
        self.cadence = max(1, cadence)
        self.quantity = quantity

    def decide(self, snapshot: MarketSnapshot) -> list[AgentIntent]:
        if (snapshot.tick + self.offset) % self.cadence != 0:
            return []
        side: Side = "buy" if ((snapshot.tick + self.offset) // self.cadence) % 2 else "sell"
        return [
            AgentIntent(
                tick=snapshot.tick,
                agent_id=self.agent_id,
                kind="market",
                sequence=0,
                latency_bucket=self.offset % 7,
                side=side,
                quantity=self.quantity,
                message="consumed small top-of-book quantity",
            )
        ]


class HeavyAnalysisAgent:
    def __init__(
        self,
        agent_id: str,
        *,
        offset: int = 0,
        complexity: int = 20_000,
        executor: Executor | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.offset = offset
        self.complexity = max(100, complexity)
        self.executor = executor

    async def decide(self, snapshot: MarketSnapshot) -> list[AgentIntent]:
        loop = asyncio.get_running_loop()
        raw_intents = await loop.run_in_executor(
            self.executor,
            _heavy_agent_decision,
            self.agent_id,
            self.offset,
            self.complexity,
            asdict(snapshot),
        )
        return [AgentIntent(**item) for item in raw_intents]


def _heavy_agent_decision(
    agent_id: str,
    offset: int,
    complexity: int,
    snapshot: dict[str, Any],
) -> list[dict[str, Any]]:
    tick = int(snapshot["tick"])
    bids = snapshot.get("bids") or []
    asks = snapshot.get("asks") or []
    if not bids or not asks:
        return []

    checksum = 0
    seed = tick + offset + len(agent_id)
    for index in range(complexity):
        checksum = (checksum * 1103515245 + seed + index) & 0x7FFFFFFF

    side = "bid" if checksum % 2 else "ask"
    levels = bids if side == "bid" else asks
    level = levels[(checksum + offset) % min(len(levels), 5)]
    price = float(level["price"])
    quantity = round(0.3 + (checksum % 9) * 0.05, 3)

    return [
        {
            "tick": tick,
            "agent_id": agent_id,
            "kind": "set_level",
            "sequence": 0,
            "latency_bucket": 10 + (offset % 13),
            "event_type": "normal",
            "side": side,
            "price": price,
            "quantity": quantity,
            "message": "heavy agent worker-pool decision",
        }
    ]


def build_heavy_agents(
    count: int,
    prefix: str,
    *,
    complexity: int = 20_000,
    executor: Executor | None = None,
) -> list[RuntimeAgent]:
    normalized = prefix.strip().upper() or "HEAVY"
    return [
        HeavyAnalysisAgent(
            agent_id=f"{normalized}_HEAVY_{index:03d}",
            offset=index,
            complexity=complexity,
            executor=executor,
        )
        for index in range(1, max(0, count) + 1)
    ]


def build_normal_agents(count: int) -> list[RuntimeAgent]:
    if count < 1:
        return []

    agents: list[RuntimeAgent] = [TopOfBookMarketMaker()]
    if count >= 2:
        agents.append(DeterministicNoiseTrader())
    if count >= 3:
        agents.append(PeriodicLiquidityTaker())

    for index in range(4, count + 1):
        if index % 8 == 0:
            agents.append(
                PeriodicLiquidityTaker(
                    agent_id=f"TAKER_{index:03d}",
                    offset=index,
                    cadence=8 + (index % 5),
                    quantity=round(0.05 + (index % 4) * 0.025, 3),
                )
            )
        else:
            agents.append(
                DeterministicNoiseTrader(
                    agent_id=f"NOISE_{index:03d}",
                    offset=index,
                    cadence=2 + (index % 6),
                )
            )
    return agents


def build_prefixed_normal_agents(count: int, prefix: str) -> list[RuntimeAgent]:
    if count < 1:
        return []

    normalized = prefix.strip().upper() or "REMOTE"
    agents: list[RuntimeAgent] = [TopOfBookMarketMaker(f"{normalized}_MM_001")]
    if count >= 2:
        agents.append(DeterministicNoiseTrader(f"{normalized}_NOISE_001", offset=1))
    if count >= 3:
        agents.append(PeriodicLiquidityTaker(f"{normalized}_TAKER_001", offset=1, cadence=2, quantity=0.65))

    for index in range(4, count + 1):
        if index % 4 == 0:
            agents.append(
                PeriodicLiquidityTaker(
                    agent_id=f"{normalized}_TAKER_{index:03d}",
                    offset=index,
                    cadence=2 + (index % 3),
                    quantity=round(0.2 + (index % 4) * 0.05, 3),
                )
            )
        else:
            agents.append(
                DeterministicNoiseTrader(
                    agent_id=f"{normalized}_NOISE_{index:03d}",
                    offset=index,
                    cadence=2 + (index % 6),
                )
            )
    return agents


RemotePost = Callable[[str, dict[str, Any], float], dict[str, Any]]


class RemoteAgentClient:
    def __init__(
        self,
        base_url: str,
        *,
        runner_id: str,
        timeout_seconds: float = 0.05,
        post_json: RemotePost | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.agent_id = f"remote_runner:{runner_id}"
        self.timeout_seconds = timeout_seconds
        self._post_json = post_json or _post_json

    async def decide(self, snapshot: MarketSnapshot) -> list[AgentIntent]:
        payload = {"snapshot": asdict(snapshot)}
        response = await asyncio.to_thread(
            self._post_json,
            f"{self.base_url}/decide",
            payload,
            self.timeout_seconds,
        )
        intents = response.get("intents", [])
        if not isinstance(intents, list):
            return []
        parsed: list[AgentIntent] = []
        for item in intents:
            if not isinstance(item, dict):
                continue
            try:
                parsed.append(AgentIntent(**{**item, "runtime_source": "agent_runner"}))
            except (TypeError, ValueError):
                continue
        return parsed


def build_agent_manager(
    *,
    local_agent_count: int,
    remote_agent_urls: list[str] | None = None,
    decision_timeout_seconds: float = 0.05,
    remote_timeout_seconds: float | None = None,
) -> "AgentManager":
    agents = build_normal_agents(local_agent_count)
    timeout = remote_timeout_seconds if remote_timeout_seconds is not None else decision_timeout_seconds
    for index, url in enumerate(remote_agent_urls or [], start=1):
        if url.strip():
            agents.append(RemoteAgentClient(url.strip(), runner_id=f"{index:02d}", timeout_seconds=timeout))
    return AgentManager(agents, decision_timeout_seconds=decision_timeout_seconds)


def _post_json(url: str, payload: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    with request.urlopen(req, timeout=timeout_seconds) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        return {}
    return decoded


class AgentManager:
    def __init__(self, agents: list[RuntimeAgent], decision_timeout_seconds: float = 0.05) -> None:
        self.agents = sorted(agents, key=lambda agent: agent.agent_id)
        self.decision_timeout_seconds = decision_timeout_seconds

    @property
    def agent_ids(self) -> list[str]:
        ids: list[str] = []
        for agent in self.agents:
            nested = getattr(agent, "agent_ids", None)
            if isinstance(nested, list):
                ids.extend(str(item) for item in nested)
            else:
                ids.append(agent.agent_id)
        return ids

    async def collect_intents(self, snapshot: MarketSnapshot) -> list[AgentIntent]:
        tasks = [asyncio.create_task(_decide_agent(agent, snapshot)) for agent in self.agents]
        if not tasks:
            return []
        done, pending = await asyncio.wait(tasks, timeout=self.decision_timeout_seconds)
        for task in pending:
            task.cancel()

        intents: list[AgentIntent] = []
        for task in done:
            if task.cancelled() or task.exception() is not None:
                continue
            intents.extend(task.result())
        return sorted(intents, key=lambda intent: intent.sort_key)

    def collect_intents_sync(self, snapshot: MarketSnapshot) -> list[AgentIntent]:
        intents: list[AgentIntent] = []
        for agent in self.agents:
            result = agent.decide(snapshot)
            if inspect.isawaitable(result):
                result = _run_immediate(result)
            intents.extend(result)
        return sorted(intents, key=lambda intent: intent.sort_key)


async def _decide_agent(agent: RuntimeAgent, snapshot: MarketSnapshot) -> list[AgentIntent]:
    result = agent.decide(snapshot)
    if inspect.isawaitable(result):
        return await result
    return result


def _run_immediate(awaitable: Awaitable[list[AgentIntent]]) -> list[AgentIntent]:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)
    raise RuntimeError("collect_intents_sync cannot run while an event loop is active")
