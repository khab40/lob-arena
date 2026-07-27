from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field
from app.scenarios.catalog import ScenarioType


class SimulationStatus(StrEnum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"


class MarketRegime(StrEnum):
    CALM = "calm"
    VOLATILE = "volatile"
    THIN_LIQUIDITY = "thin_liquidity"


class RedTeamGoal(StrEnum):
    OBVIOUS = "obvious"
    STEALTH = "stealth"
    HARD_TO_DETECT = "hard_to_detect"


class RedTeamScenarioGenerateRequest(BaseModel):
    scenario_family: ScenarioType
    market_regime: MarketRegime
    goal: RedTeamGoal
    constraints: dict[str, Any] = Field(default_factory=dict)


class ScenarioConfig(BaseModel):
    label: str
    slug: ScenarioType
    scenario_family: str
    agent_id: str
    description: str
    launch_endpoint: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    market_regime: MarketRegime
    goal: RedTeamGoal
    source: Literal["nebius", "mock"]
    expected_detector_risk: float = Field(ge=0.0, le=1.0)
    safety_note: str


class BenchmarkResult(BaseModel):
    scenario: str
    precision: float
    recall: float
    f1: float
    avg_detection_latency_ms: float | None = None


class PriceLevel(BaseModel):
    price: float
    quantity: float
    agent_id: str | None = None
    owner: str | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None


class OrderBookSnapshot(BaseModel):
    bids: list[PriceLevel]
    asks: list[PriceLevel]
    best_bid: float | None
    best_ask: float | None
    mid: float | None
    spread: float | None


class MarketFeatures(BaseModel):
    spread_bps: float
    depth_top_n: float
    imbalance: float
    message_rate: float
    cancel_to_trade_ratio: float
    order_lifetime_ms: float
    wall_size_ratio: float
    depth_change_pct: float
    distance_from_touch_bps: float = 0.0
    cancel_probability: float = 0.0
    execution_ratio: float = 0.0
    replenishment_rate: float = 0.0
    side_switching_rate: float = 0.0
    participant_order_linkage: float = 0.0
    linked_participant_ids: str = ""
    linked_order_ids: str = ""
    linked_event_ids: str = ""
    large_level_count: float = 0.0


class DetectorScore(BaseModel):
    name: str
    confidence: float = Field(ge=0.0, le=1.0)
    alert: bool
    severity: Literal["low", "medium", "high", "critical"] | None = None
    evidence: list["EvidenceItem"] | None = None


class DetectorScores(BaseModel):
    scores: list[DetectorScore]
    alerts: list[DetectorScore]


class AgentEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    type: str
    event_id: str | None = None
    timestamp: float | None = None
    order_id: str | None = None
    aggressor_order_id: str | None = None
    resting_order_id: str | None = None
    agent_id: str | None = None
    aggressor_agent_id: str | None = None
    resting_agent_id: str | None = None
    side: Literal["buy", "sell"] | None = None
    price: float | None = None
    quantity: float | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None
    scenario_family: str | None = None


class EvidenceItem(BaseModel):
    key: str
    label: str
    value: str | int | float | bool
    unit: str | None = None
    interpretation: str | None = None


class Incident(BaseModel):
    id: str
    title: str
    type: str
    agent: str
    confidence: float = Field(ge=0.0, le=1.0)
    severity: Literal["Low", "Medium", "High", "Critical"]
    evidence: list[EvidenceItem]
    explanation: str
    scenario_id: str | None = None
    scenario_family: str | None = None


class AttackStage(StrEnum):
    ARMED = "armed"
    WALL_PLACED = "wall_placed"
    PRESSURE_PHASE = "pressure_phase"
    WALL_CANCELLED = "wall_cancelled"
    CANCELLED = "cancelled"
    INCIDENT_CONFIRMED = "incident_confirmed"
    DONE = "done"


class AttackStageSnapshot(BaseModel):
    detector_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    label: str
    stage: AttackStage
    status: Literal["pending", "active", "completed"]
    tick: int | None = None
    timestamp: float | None = None


class ScenarioLabel(BaseModel):
    label_id: str
    run_id: str
    scenario_id: str
    scenario_family: str
    scenario_name: str
    seed: int
    start_tick: int
    expected_end_tick: int | None = None
    actual_end_tick: int | None = None
    agent_ids: list[str]
    event_ids: list[str] = Field(default_factory=list)
    order_ids: list[str] = Field(default_factory=list)
    manipulation_windows: list[dict[str, int | None]] = Field(default_factory=list)
    phase_windows: dict[str, dict[str, int | None]] = Field(default_factory=dict)
    parameters: dict[str, Any] = Field(default_factory=dict)


class AttackTrackerState(BaseModel):
    scenario_id: str
    scenario_name: str
    scenario_family: str
    agent_id: str
    current_stage: AttackStage | None = None
    start_tick: int
    stages: list[AttackStageSnapshot] | None = None
    status: AttackStage | str
    evidence: list[EvidenceItem] | None = None
    label: ScenarioLabel | None = None


class ExchangeEventRecord(BaseModel):
    schema_version: int = 1
    event_type: Literal["add", "modify", "cancel", "execute", "snapshot"]
    event_id: str
    sequence: int = Field(ge=1)
    source: Literal["simulation", "historical"]
    source_sequence: int | None = None
    symbol: str
    venue: str
    tick: int | None = None
    exchange_timestamp_ns: int | None = None
    received_timestamp_ns: int | None = None
    scenario_id: str | None = None
    scenario_name: str | None = None
    scenario_family: str | None = None
    order_id: str | None = None
    agent_id: str | None = None
    side: Literal["buy", "sell"] | None = None
    price: float | None = None
    quantity: float | None = None
    owner: str | None = None
    previous_price: float | None = None
    previous_quantity: float | None = None
    priority_preserved: bool | None = None
    execution_id: str | None = None
    aggressor_order_id: str | None = None
    resting_order_id: str | None = None
    aggressor_agent_id: str | None = None
    resting_agent_id: str | None = None
    aggressor_remaining_quantity: float | None = None
    resting_remaining_quantity: float | None = None
    depth: int | None = None
    book: OrderBookSnapshot | None = None


class ExchangeEventReplay(BaseModel):
    events: list[ExchangeEventRecord]
    after_sequence: int = Field(ge=0)
    next_after_sequence: int = Field(ge=0)
    latest_sequence: int = Field(ge=0)
    stream_id: str | None = None
    first_available_sequence: int | None = Field(default=None, ge=0)
    retained_from_sequence: int | None = Field(default=None, ge=0)
    has_more: bool


class ArenaMetricsSnapshot(BaseModel):
    tick: int = Field(ge=0)
    running: bool
    incidents_count: int = Field(ge=0)


class ArenaState(BaseModel):
    tick: int
    running: bool
    events: list[AgentEvent]
    exchange_events: list[ExchangeEventRecord] = Field(default_factory=list)
    book: OrderBookSnapshot
    best_bid: float | None
    best_ask: float | None
    mid: float | None
    spread: float | None
    active_agents: list[str]
    active_scenario: AttackTrackerState | None
    detectors: DetectorScores
    incidents: list[Incident] | None = None
    features: dict[str, Any] | MarketFeatures | None = None
    historical_events: list[dict[str, Any]] = Field(default_factory=list)
    market_data: dict[str, Any] | None = None
