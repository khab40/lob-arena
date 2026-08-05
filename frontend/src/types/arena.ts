export type PriceLevel = {
  agent_id?: string;
  owner?: "normal" | "abuser" | string;
  price: number;
  quantity: number;
  scenario_id?: string;
  scenario_name?: string;
};

export type OrderBookSnapshot = {
  bids: PriceLevel[];
  asks: PriceLevel[];
  best_bid: number | null;
  best_ask: number | null;
  mid: number | null;
  spread: number | null;
};

export type MarketFeatures = {
  spread_bps: number;
  depth_top_n: number;
  imbalance: number;
  order_book_imbalance?: number;
  top_n_bid_depth?: number;
  top_n_ask_depth?: number;
  message_rate: number;
  message_rate_per_sec?: number;
  cancel_to_trade_ratio: number;
  order_lifetime_ms: number;
  wall_size_ratio: number;
  large_level_count?: number;
  depth_change_pct: number;
};

export type DetectorScore = {
  name: string;
  confidence: number;
  alert: boolean;
  severity?: "low" | "medium" | "high" | "critical";
  evidence?: EvidenceItem[];
};

export type DetectorScores = {
  scores: DetectorScore[];
  alerts: DetectorScore[];
};

export type AgentEvent = {
  type: string;
  tick?: number;
  timestamp?: number;
  order_id?: string;
  aggressor_order_id?: string;
  resting_order_id?: string;
  agent_id?: string;
  aggressor_agent_id?: string;
  resting_agent_id?: string;
  side?: "buy" | "sell";
  price?: number;
  quantity?: number;
  scenario_id?: string | null;
  scenario_name?: string | null;
  scenario_family?: string | null;
  runtime_source?: "backend" | "agent_runner";
  [key: string]: unknown;
};

export type ExchangeEventType = "add" | "modify" | "cancel" | "execute" | "snapshot";
export type ExchangeEventSource = "simulation" | "historical";

type ExchangeEventBase = {
  schema_version: 1;
  event_type: ExchangeEventType;
  event_id: string;
  sequence: number;
  source: ExchangeEventSource;
  source_sequence: number | null;
  symbol: string;
  venue: string;
  tick: number | null;
  exchange_timestamp_ns: number | null;
  received_timestamp_ns: number | null;
  scenario_id: string | null;
  scenario_name: string | null;
  scenario_family: string | null;
};

type RestingOrderPayload = {
  order_id: string;
  agent_id: string;
  side: "buy" | "sell";
  price: number;
  quantity: number;
  owner: string;
};

export type AddExchangeEvent = ExchangeEventBase & RestingOrderPayload & {
  event_type: "add";
};

export type ModifyExchangeEvent = ExchangeEventBase & RestingOrderPayload & {
  event_type: "modify";
  previous_price: number;
  previous_quantity: number;
  priority_preserved: boolean;
};

export type CancelExchangeEvent = ExchangeEventBase & RestingOrderPayload & {
  event_type: "cancel";
};

export type ExecuteExchangeEvent = ExchangeEventBase & {
  event_type: "execute";
  execution_id: string;
  aggressor_order_id: string;
  resting_order_id: string;
  aggressor_agent_id: string;
  resting_agent_id: string;
  side: "buy" | "sell";
  price: number;
  quantity: number;
  aggressor_remaining_quantity: number;
  resting_remaining_quantity: number;
};

export type SnapshotExchangeEvent = ExchangeEventBase & {
  event_type: "snapshot";
  depth: number;
  book: OrderBookSnapshot;
};

export type ExchangeEvent =
  | AddExchangeEvent
  | ModifyExchangeEvent
  | CancelExchangeEvent
  | ExecuteExchangeEvent
  | SnapshotExchangeEvent;

export type EvidenceItem = {
  key: string;
  label: string;
  value: string | number | boolean;
  unit?: string;
  interpretation?: string;
};

export type InvestigationContext = {
  simulation_metadata?: Record<string, unknown>;
  market_regime?: Record<string, unknown>;
  instrument?: Record<string, unknown>;
  episode_duration?: Record<string, unknown>;
  suspected_agent?: Record<string, unknown>;
  order_book_context?: Record<string, unknown>;
  trades?: Record<string, unknown>[];
  event_timeline?: Record<string, unknown>[];
  market_metrics?: Record<string, unknown>;
  cancellation_metrics?: Record<string, unknown>;
  execution_metrics?: Record<string, unknown>;
  price_movement?: Record<string, unknown>;
  ground_truth?: Record<string, unknown> | null;
  previous_agent_behaviour?: Record<string, unknown>[];
};

export type Incident = {
  id: string;
  title: string;
  type: string;
  agent: string;
  confidence: number;
  severity: "Low" | "Medium" | "High" | "Critical";
  evidence: EvidenceItem[];
  explanation: string;
  scenario_id?: string;
  scenario_family?: string;
  tick?: number;
  investigation_context?: InvestigationContext;
};

export type AttackStage =
  | "armed"
  | "wall_placed"
  | "pressure_phase"
  | "wall_cancelled"
  | "cancelled"
  | "incident_confirmed"
  | "done";

export type AttackStageStatus = "pending" | "active" | "completed";

export type AttackStageSnapshot = {
  detector_confidence?: number;
  label: string;
  stage: AttackStage;
  status: AttackStageStatus;
  tick?: number;
  timestamp?: number;
};

export type AttackTrackerState = {
  scenario_id: string;
  scenario_name: string;
  scenario_family: string;
  agent_id: string;
  current_stage?: AttackStage;
  start_tick: number;
  stages?: AttackStageSnapshot[];
  status: AttackStage | string;
  evidence?: EvidenceItem[];
};

export type ArenaState = {
  tick: number;
  running: boolean;
  events: AgentEvent[];
  exchange_events: ExchangeEvent[];
  book: OrderBookSnapshot;
  best_bid: number | null;
  best_ask: number | null;
  mid: number | null;
  spread: number | null;
  active_agents: string[];
  active_scenario: AttackTrackerState | null;
  detectors: DetectorScores;
  incidents?: Incident[];
  features?: Partial<MarketFeatures>;
  historical_events?: Array<HistoricalMarketEvent | ExchangeEvent>;
  market_data?: MarketDataContext;
};

export type HistoricalMarketEvent = {
  type: string;
  event_kind: string;
  source_event_code: number;
  source_sequence: number;
  timestamp_ns_since_midnight: number;
  order_id: string;
  source_order_id: number;
  quantity: number;
  price_x10000: number;
  price?: number;
  side?: "buy" | "sell" | null;
  symbol: string;
  source: "historical";
};

export type MarketDataContext = {
  source_type: "historical" | "hybrid" | "synthetic_profile";
  dataset_id: string;
  format?: string;
  symbol: string;
  venue?: string;
  trade_date: string;
  depth: number;
  source_sequence: number;
  replay_position: number;
  exchange_timestamp_ns: number;
  row_count: number;
  progress: number;
  eof: boolean;
  events_sha256?: string;
  profile_id?: string;
  profile_sha256?: string;
  training_dataset_id?: string;
  current_reference_price_ticks?: number;
  run_binding_sha256?: string;
};

export type ArenaWebSocketMessage = {
  type: "arena_state";
  version: number;
  timestamp: string;
  payload: ArenaState;
};

export type ScenarioConfig = {
  label: string;
  slug: string;
  scenario_family: string;
  agent_id: string;
  description: string;
  launch_endpoint?: string;
  parameters?: Record<string, unknown>;
  market_regime?: "calm" | "volatile" | "thin_liquidity";
  goal?: "obvious" | "stealth" | "hard_to_detect";
  source?: "nebius" | "mock";
  expected_detector_risk?: number;
  safety_note?: string;
};

export type BenchmarkResult = {
  avg_detection_latency_ms?: number;
  scenario: string;
  precision: number;
  recall: number;
  f1: number;
};
