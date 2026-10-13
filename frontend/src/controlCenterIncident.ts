import type { AIInvestigationTeamRequest } from "@/api/client";
import type { Incident, InvestigationContext } from "@/types/arena";

const STORAGE_KEY = "lob-arena.control-center.incident";

export function clearControlCenterIncident() {
  window.sessionStorage.removeItem(STORAGE_KEY);
}

export function storeControlCenterIncident(incident: Incident) {
  window.sessionStorage.setItem(STORAGE_KEY, JSON.stringify(incident));
}

export function controlCenterIncidentPath(incident: Incident) {
  return `/nebius?step=3&incidentId=${encodeURIComponent(incident.id)}`;
}

export function loadControlCenterIncident(expectedId: string | null): Incident | null {
  if (!expectedId) return null;
  const serialized = window.sessionStorage.getItem(STORAGE_KEY);
  if (!serialized) return null;
  try {
    const incident = JSON.parse(serialized) as Incident;
    return incident.id === expectedId ? incident : null;
  } catch {
    window.sessionStorage.removeItem(STORAGE_KEY);
    return null;
  }
}

export function incidentInvestigationRequest(incident: Incident): AIInvestigationTeamRequest {
  const context = incident.investigation_context ?? {};
  const detectorEvidence = incident.evidence.map((item) => `${item.label}: ${String(item.value)}${item.unit ? ` ${item.unit}` : ""}`);
  const eventTimeline = context.event_timeline?.slice(-32) ?? [
    { sequence: 1, event: "Synthetic detector incident emitted.", source: "incident" },
    { sequence: 2, event: "Detector evidence supplied for investigation.", source: "detector_outputs" }
  ];
  const orderBookContext = {
    ...(context.order_book_context ?? {}),
    events: context.order_book_context?.events ?? eventTimeline
  };
  const marketMetrics = {
    ...(context.market_metrics ?? {}),
    ...Object.fromEntries(incident.evidence.map((item) => [item.key, item.value]))
  };
  const episodeSummary: Record<string, unknown> = {
    ...context,
    simulation_metadata: {
      ...(context.simulation_metadata ?? {}),
      episode_id: incident.id,
      scenario_id: incident.scenario_id,
      scenario_family: incident.scenario_family
    },
    suspected_agent: context.suspected_agent ?? { agent_id: incident.agent },
    order_book_context: orderBookContext,
    event_timeline: eventTimeline,
    market_metrics: marketMetrics,
    detector_scores: [{ detector: incident.title, score: incident.confidence, classification: incident.type, alert: true }]
  };
  return {
    incident: {
      agent: incident.agent,
      confidence: incident.confidence,
      explanation: incident.explanation,
      id: incident.id,
      scenario_family: incident.scenario_family,
      scenario_id: incident.scenario_id,
      severity: incident.severity,
      tick: incident.tick,
      title: incident.title,
      type: incident.type
    },
    detector_outputs: [{
      confidence: incident.confidence,
      detected_pattern: incident.type,
      detector: incident.title,
      evidence: detectorEvidence,
      suspicion_score: incident.confidence
    }],
    market_metrics: marketMetrics,
    order_book_context: orderBookContext,
    trades: context.trades?.slice(-20) ?? [],
    episode_summary: episodeSummary
  };
}

export function investigationContextFromArenaState(state: {
  tick: number;
  book: Record<string, unknown>;
  events: Record<string, unknown>[];
  features?: Record<string, unknown>;
  active_scenario?: Record<string, unknown> | null;
  mid?: number | null;
  spread?: number | null;
}): InvestigationContext {
  const events = state.events.slice(-32);
  const trades = events.filter((event) => event.type === "trade").slice(-20);
  const eventTimeline = events.map((event, index) => ({
    sequence: index + 1,
    time: event.timestamp ?? state.tick,
    event: String(event.type ?? "market_event"),
    agent: event.agent_id,
    side: event.side,
    price: event.price,
    quantity: event.quantity,
    stage: event.scenario_name ?? event.scenario_family
  }));
  const marketMetrics = { ...(state.features ?? {}) };
  return {
    simulation_metadata: { tick: state.tick, scenario_id: state.active_scenario?.scenario_id, scenario_family: state.active_scenario?.scenario_family },
    suspected_agent: state.active_scenario?.agent_id ? { agent_id: state.active_scenario.agent_id } : undefined,
    episode_duration: { end_tick: state.tick },
    order_book_context: { snapshot: state.book, events },
    trades,
    event_timeline: eventTimeline,
    market_metrics: marketMetrics,
    cancellation_metrics: {
      cancel_to_trade_ratio: state.features?.cancel_to_trade_ratio,
      order_lifetime_ms: state.features?.order_lifetime_ms
    },
    execution_metrics: { execution_ratio: state.features?.execution_ratio, trade_count: trades.length },
    price_movement: { mid: state.mid, spread: state.spread }
  };
}
