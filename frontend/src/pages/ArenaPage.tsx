import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { AttackBuilder } from "@/components/AttackBuilder";
import { AttackTracker } from "@/components/AttackTracker";
import { AgentTimeline } from "@/components/AgentTimeline";
import { DetectorConfidence } from "@/components/DetectorConfidence";
import { EvidencePanel } from "@/components/EvidencePanel";
import { ExchangeEventTape } from "@/components/ExchangeEventTape";
import { IncidentDrawer } from "@/components/IncidentDrawer";
import { LiquidityHeatmap } from "@/components/LiquidityHeatmap";
import { MarketTimeline, type MarketTimelineFrame, type TimelineMarkerType } from "@/components/MarketTimeline";
import { OrderBookLadder } from "@/components/OrderBookLadder";
import { useArenaSource } from "@/hooks/useArenaSource";
import { getProductDemoConfig, type ProductDemoConfig } from "@/demoModes";
import { controlCenterIncidentPath, investigationContextFromArenaState, storeControlCenterIncident } from "@/controlCenterIncident";
import type { ArenaState, Incident, OrderBookSnapshot } from "@/types/arena";
import { arenaScenarioLabels } from "@/scenarios";
import {
  listHistoricalReplayDatasets,
  listImportedDatasets,
  listMarketProfiles,
  type HistoricalReplayDataset,
  type MarketProfileSummary
} from "@/api/client";

const WIDGET_TICK_WINDOW = 48;

type HeatmapSnapshotFrame = {
  book: OrderBookSnapshot;
  tick: number;
};

type DetectionSecondaryView = "evidence" | "exchange" | "timeline";
type MarketSecondaryView = "heatmap" | "timeline";
type MarketDataChoice = "synthetic" | "synthetic_profile" | "historical" | "hybrid";

function formatScenarioLabel(name?: string | null) {
  return name ? arenaScenarioLabels[name as keyof typeof arenaScenarioLabels] ?? name : "None";
}

function formatExchangeTime(timestampNs?: number) {
  if (timestampNs === undefined) return "not loaded";
  const totalMilliseconds = Math.floor(timestampNs / 1_000_000);
  const hours = Math.floor(totalMilliseconds / 3_600_000);
  const minutes = Math.floor((totalMilliseconds % 3_600_000) / 60_000);
  const seconds = Math.floor((totalMilliseconds % 60_000) / 1_000);
  const milliseconds = totalMilliseconds % 1_000;
  return `${hours.toString().padStart(2, "0")}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}.${milliseconds.toString().padStart(3, "0")}`;
}

function formatReplayProgress(progress = 0) {
  const percent = Math.max(0, Math.min(1, progress)) * 100;
  if (percent === 0) return "0%";
  if (percent < 0.01) return "<0.01%";
  if (percent < 1) return `${percent.toFixed(2)}%`;
  return `${Math.round(percent)}%`;
}

function formatDatasetOption(dataset: HistoricalReplayDataset) {
  const depth = dataset.depth > 0 ? `${dataset.depth} levels` : "event stream";
  return `${dataset.symbol} · ${dataset.trade_date} · ${dataset.start_time}–${dataset.end_time} · ${depth}`;
}

export function ArenaPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const demoConfig = getProductDemoConfig(searchParams.get("demo"));
  const replayScenario = searchParams.get("replayScenario");
  const { launchScenario, loadMarketDataSource, mode, pause, reset, running, sourceStatus, start, state, tick } = useArenaSource({
    demo: Boolean(demoConfig),
    demoScenario: demoConfig?.scenarioType,
    symbol: demoConfig?.marketSymbol
  });
  const [secondaryView, setSecondaryView] = useState<DetectionSecondaryView>("evidence");
  const [marketSecondaryView, setMarketSecondaryView] = useState<MarketSecondaryView>("heatmap");
  const [heatmapSnapshots, setHeatmapSnapshots] = useState<HeatmapSnapshotFrame[]>(() => [toHeatmapSnapshotFrame(state)]);
  const [timeline, setTimeline] = useState<MarketTimelineFrame[]>(() => [toTimelineFrame(state)]);
  const lastRecordedTickRef = useRef(state.tick);
  const [pendingControl, setPendingControl] = useState<"pause" | "reset" | "start" | null>(null);
  const [shortcutsOpen, setShortcutsOpen] = useState(false);
  const [marketDataChoice, setMarketDataChoice] = useState<MarketDataChoice>("synthetic");
  const marketDataChoiceTouchedRef = useRef(false);
  const [historicalDatasets, setHistoricalDatasets] = useState<HistoricalReplayDataset[]>([]);
  const [hybridDatasets, setHybridDatasets] = useState<HistoricalReplayDataset[]>([]);
  const [marketProfiles, setMarketProfiles] = useState<MarketProfileSummary[]>([]);
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [datasetError, setDatasetError] = useState<string | null>(null);
  const [incidentDetailsMode, setIncidentDetailsMode] = useState<"live" | "replay">("live");
  const incident = useMemo(() => createIncident(state), [state]);
  const [lastIncident, setLastIncident] = useState<Incident | null>(incident);
  const loading = mode === "websocket" && sourceStatus === "connecting";
  const connected = mode === "demo" || mode === "mock" || sourceStatus === "connected";
  const canReset = tick > 0 || running || state.events.length > 0 || Boolean(state.active_scenario) || Boolean(state.incidents?.length);
  const selectedIncident = incident ?? lastIncident;
  const historicalMode = state.market_data?.source_type === "historical" || state.market_data?.source_type === "hybrid";
  const hybridMode = state.market_data?.source_type === "hybrid";
  const historicalControlMode = state.market_data?.source_type === "historical";
  const profileMode = state.market_data?.source_type === "synthetic_profile";
  const loadedMarketDataSource = state.market_data?.source_type;
  const loadedDatasetId = state.market_data?.dataset_id;

  useEffect(() => {
    if (!marketDataChoiceTouchedRef.current && loadedMarketDataSource && loadedDatasetId) {
      setMarketDataChoice(loadedMarketDataSource);
      setSelectedDatasetId(loadedDatasetId);
    }
  }, [loadedDatasetId, loadedMarketDataSource]);

  useEffect(() => {
    if (mode !== "websocket" || !connected) {
      return;
    }
    let cancelled = false;
    void Promise.all([
      listImportedDatasets().catch(() => []),
      listHistoricalReplayDatasets(),
      listMarketProfiles().catch(() => [])
    ])
      .then(([imported, replayable, profiles]) => {
        if (cancelled) {
          return;
        }
        const importedDatasets: HistoricalReplayDataset[] = imported.map((dataset) => ({
          dataset_id: dataset.dataset_id,
          depth: dataset.depth,
          end_time: dataset.end_time,
          row_count: dataset.row_count,
          source_type: dataset.source_type,
          start_time: dataset.start_time,
          symbol: dataset.symbol,
          trade_date: dataset.trade_date
        }));
        const merged = new Map(importedDatasets.map((dataset) => [dataset.dataset_id, dataset]));
        replayable.forEach((dataset) => merged.set(dataset.dataset_id, dataset));
        setHistoricalDatasets([...merged.values()]);
        setHybridDatasets(replayable);
        setMarketProfiles(profiles);
        setDatasetError(null);
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setDatasetError(error instanceof Error ? error.message : "Dataset registry unavailable");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [connected, mode]);

  const selectableDatasets = useMemo(
    () => marketDataChoice === "hybrid" ? hybridDatasets : historicalDatasets,
    [historicalDatasets, hybridDatasets, marketDataChoice]
  );

  const selectableIds = useMemo(
    () => marketDataChoice === "synthetic_profile"
      ? marketProfiles.map((profile) => profile.profile_id)
      : selectableDatasets.map((dataset) => dataset.dataset_id),
    [marketDataChoice, marketProfiles, selectableDatasets]
  );

  useEffect(() => {
    if (marketDataChoice === "synthetic") {
      return;
    }
    setSelectedDatasetId((current) =>
      selectableIds.includes(current)
        ? current
        : selectableIds[0] ?? ""
    );
  }, [marketDataChoice, selectableIds]);

  const chooseMarketDataSource = useCallback((choice: MarketDataChoice) => {
    marketDataChoiceTouchedRef.current = true;
    setMarketDataChoice(choice);
    setDatasetError(null);
  }, []);

  const loadSelectedMarketData = useCallback(() => {
    if (marketDataChoice !== "synthetic" && !selectedDatasetId) {
      setDatasetError(marketDataChoice === "synthetic_profile"
        ? "Select a market profile first."
        : "Select an imported dataset first.");
      return;
    }
    setDatasetError(null);
    loadMarketDataSource(marketDataChoice, marketDataChoice === "synthetic" ? "" : selectedDatasetId);
  }, [loadMarketDataSource, marketDataChoice, selectedDatasetId]);

  const sendToControlCenter = useCallback((selected: Incident) => {
    const enriched = {
      ...selected,
      investigation_context: investigationContextFromArenaState(state)
    };
    storeControlCenterIncident(enriched);
    navigate(controlCenterIncidentPath(enriched));
  }, [navigate, state]);

  useEffect(() => {
    if (incident) {
      setLastIncident(incident);
    }
  }, [incident]);

  useEffect(() => {
    if (state.tick === lastRecordedTickRef.current) {
      return;
    }
    lastRecordedTickRef.current = state.tick;
    setHeatmapSnapshots((snapshots) => [...snapshots, toHeatmapSnapshotFrame(state)].slice(-WIDGET_TICK_WINDOW));
    setTimeline((points) => [...points, toTimelineFrame(state)].slice(-WIDGET_TICK_WINDOW));
  }, [state]);

  useEffect(() => {
    setPendingControl(null);
  }, [running, sourceStatus, tick]);

  const startArena = useCallback(() => {
    if (running || !connected) {
      return;
    }
    setPendingControl("start");
    start();
  }, [connected, running, start]);

  const pauseArena = useCallback(() => {
    if (!running || !connected) {
      return;
    }
    setPendingControl("pause");
    pause();
  }, [connected, pause, running]);

  const resetArena = useCallback(() => {
    if (!canReset || !connected) {
      return;
    }
    setPendingControl("reset");
    reset();
    lastRecordedTickRef.current = -1;
    setHeatmapSnapshots([]);
    setTimeline([]);
    setLastIncident(null);
  }, [canReset, connected, reset]);

  useEffect(() => {
    function handleKeyDown(event: KeyboardEvent) {
      const target = event.target;
      if (isEditableTarget(target)) {
        return;
      }

      const key = event.key.toLowerCase();
      if (key === " ") {
        event.preventDefault();
        if (running) {
          pauseArena();
        } else {
          startArena();
        }
      }
      if (key === "s") {
        startArena();
      }
      if (key === "q") {
        pauseArena();
      }
      if (key === "r") {
        resetArena();
      }
      if (key === "l") {
        setIncidentDetailsMode((value) => value === "live" ? "replay" : "live");
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pauseArena, resetArena, running, startArena]);

  return (
    <section className={`cockpit-page ${incident ? "incident-active" : ""}`} aria-label="Market workload generator">
      <TopStatusBar
        onPause={pauseArena}
        onReset={resetArena}
        onStart={startArena}
        canReset={canReset}
        connected={connected}
        pendingControl={pendingControl}
        running={running}
        selectedScenario={historicalControlMode ? "Control run (no labels)" : formatScenarioLabel(state.active_scenario?.scenario_name)}
        tick={tick}
        source={historicalMode
          ? `${state.market_data?.symbol} ${hybridMode ? "hybrid" : "historical"} · ${formatExchangeTime(state.market_data?.exchange_timestamp_ns)}`
          : profileMode
            ? `${state.market_data?.symbol} calibrated · ${state.market_data?.profile_id}`
            : mode === "websocket" ? `backend websocket:${sourceStatus}` : mode === "demo" ? demoConfig?.title ?? "demo mode" : `local mock:${sourceStatus}`}
      />

      <section className="panel market-data-source-panel" aria-label="Market data source">
        <fieldset className="market-data-source-options">
          <legend>Market data source</legend>
          <label className={marketDataChoice === "synthetic" ? "selected" : ""}>
            <input checked={marketDataChoice === "synthetic"} disabled={mode !== "websocket"} name="market-data-source" onChange={() => chooseMarketDataSource("synthetic")} type="radio" />
            <span><strong>Synthetic</strong><small>Generated market</small></span>
          </label>
          <label className={marketDataChoice === "synthetic_profile" ? "selected" : ""}>
            <input checked={marketDataChoice === "synthetic_profile"} disabled={mode !== "websocket"} name="market-data-source" onChange={() => chooseMarketDataSource("synthetic_profile")} type="radio" />
            <span><strong>Calibrated synthetic</strong><small>ITCH-derived profile</small></span>
          </label>
          <label className={marketDataChoice === "historical" ? "selected" : ""}>
            <input checked={marketDataChoice === "historical"} disabled={mode !== "websocket"} name="market-data-source" onChange={() => chooseMarketDataSource("historical")} type="radio" />
            <span><strong>Historical control</strong><small>Replay only</small></span>
          </label>
          <label className={marketDataChoice === "hybrid" ? "selected" : ""}>
            <input checked={marketDataChoice === "hybrid"} disabled={mode !== "websocket"} name="market-data-source" onChange={() => chooseMarketDataSource("hybrid")} type="radio" />
            <span><strong>Hybrid + attacks</strong><small>Replay with injection</small></span>
          </label>
        </fieldset>
        {marketDataChoice !== "synthetic" ? (
          <label className="market-data-dataset-field">
            <span>{marketDataChoice === "synthetic_profile" ? "Market profile" : "Historical dataset"}</span>
            <select aria-label={marketDataChoice === "synthetic_profile" ? "Market profile" : "Historical dataset"} onChange={(event) => setSelectedDatasetId(event.target.value)} value={selectedDatasetId}>
              <option value="">{marketDataChoice === "synthetic_profile" ? "Select a profile" : "Select a dataset"}</option>
              {marketDataChoice === "synthetic_profile"
                ? marketProfiles.map((profile) => (
                  <option key={profile.profile_id} value={profile.profile_id}>
                    {profile.symbol} · {profile.trade_date} · {profile.profile_id}
                  </option>
                ))
                : selectableDatasets.map((dataset) => (
                  <option key={dataset.dataset_id} value={dataset.dataset_id}>
                    {formatDatasetOption(dataset)}
                  </option>
                ))}
            </select>
            <small>{marketDataChoice === "synthetic_profile"
              ? "The profile SHA and master seed are bound to every run."
              : marketDataChoice === "hybrid" ? "Only canonical event streams support attack injection." : "Control replay does not create ground-truth labels."}</small>
          </label>
        ) : null}
        <button className="primary-button" disabled={mode !== "websocket" || !connected || (marketDataChoice !== "synthetic" && !selectedDatasetId)} onClick={loadSelectedMarketData} type="button">
          {marketDataChoice === "hybrid"
            ? "Load Hybrid Replay"
            : marketDataChoice === "historical"
              ? "Load Historical Control"
              : marketDataChoice === "synthetic_profile" ? "Load Calibrated Synthetic" : "Load Synthetic Data"}
        </button>
        {historicalMode ? (
          <span className="historical-progress">
            Loaded: {hybridMode ? "Hybrid" : "Historical control"} · {formatReplayProgress(state.market_data?.progress)} · {state.market_data?.replay_position.toLocaleString()}/{state.market_data?.row_count.toLocaleString()}
          </span>
        ) : null}
        {datasetError ? <span className="control-error">{datasetError}</span> : null}
      </section>

      <div className="shortcut-help">
        <button
          aria-expanded={shortcutsOpen}
          aria-label="Keyboard shortcuts"
          className="shortcut-help-button"
          onClick={() => setShortcutsOpen((value) => !value)}
          type="button"
        >
          ?
        </button>
        {shortcutsOpen ? (
          <div className="shortcut-popover" role="dialog" aria-label="Keyboard shortcuts">
            <span><kbd>Space</kbd> start/pause</span>
            <span><kbd>S</kbd> start</span>
            <span><kbd>Q</kbd> pause</span>
            <span><kbd>R</kbd> reset</span>
            <span><kbd>L</kbd> live/replay</span>
          </div>
        ) : null}
      </div>

      {loading ? (
        <div className="loading-banner" role="status">
          Connecting to arena WebSocket source...
        </div>
      ) : null}

      {mode === "websocket" && (sourceStatus === "disconnected" || sourceStatus === "error") ? (
        <div className="empty-state warning" role="status">
          WebSocket arena source is {sourceStatus}. Switch `VITE_ARENA_MODE=mock` or start the backend stream.
        </div>
      ) : null}

      {incident ? (
        <div className="incident-alert-banner" role="alert">
          Incident alert: {incident.title} | confidence {incident.confidence.toFixed(2)}
        </div>
      ) : null}

      {demoConfig ? <ArenaDemoBanner config={demoConfig} /> : null}
      {replayScenario ? (
        <div className="loading-banner replay-active-banner" role="status">
          Live replay active: {replayScenario}. Exchange ticks, LOB updates, detectors, and incident evidence are streaming below.
        </div>
      ) : null}

      <div className="cockpit-grid">
        <section className="panel cockpit-left arena-column">
          <header className="arena-column-header">
            <h2>Scenario Setup</h2>
          </header>
          {historicalControlMode ? (
            <div className="empty-state">
              Historical control replay is immutable and has no inferred benign or attack labels. Select Hybrid + attacks to inject a predefined synthetic scenario over the same window.
            </div>
          ) : (
            <>
              <AttackTracker attack={state.active_scenario} />
              <AttackBuilder onLaunchScenario={launchScenario} />
            </>
          )}
        </section>

        <section className="panel cockpit-center arena-column">
          <header className="arena-column-header market-visualization-header">
            <div>
              <h2>Market Workload Generator</h2>
              <div className="market-microstructure-strip" aria-label="Market microstructure metrics">
                <MetricPill label="Mid" value={formatNumber(state.mid)} />
                <MetricPill label="Spread" value={formatNumber(state.spread)} />
              </div>
            </div>
          </header>
          <div className="market-mode-panel">
            <OrderBookLadder snapshot={state.book} />
            <section className="market-secondary-view">
              <div className="widget-tab-row" role="tablist" aria-label="Secondary market views">
                <button className={marketSecondaryView === "heatmap" ? "active" : ""} onClick={() => setMarketSecondaryView("heatmap")} type="button">Heatmap</button>
                <button className={marketSecondaryView === "timeline" ? "active" : ""} onClick={() => setMarketSecondaryView("timeline")} type="button">Market Timeline</button>
              </div>
              <div className="tab-content-panel" key={marketSecondaryView}>
                {marketSecondaryView === "heatmap" ? (
                  <LiquidityHeatmap maxFrames={WIDGET_TICK_WINDOW} snapshots={heatmapSnapshots} visibleLevels={20} />
                ) : (
                  <MarketTimeline frames={timeline} />
                )}
              </div>
            </section>
          </div>
        </section>

        <section className="panel cockpit-right arena-column">
          <header className="arena-column-header">
            <h2>Incidents / Investigations</h2>
          </header>
          <DetectorConfidence detectors={state.detectors} />
          <section className="secondary-widget-drawer">
            <div className="widget-tab-row" role="tablist" aria-label="Secondary detection widgets">
              <button className={secondaryView === "evidence" ? "active" : ""} onClick={() => setSecondaryView("evidence")} type="button">📄 Evidence</button>
              <button className={secondaryView === "timeline" ? "active" : ""} onClick={() => setSecondaryView("timeline")} type="button">🕒 Agent Events</button>
              <button className={secondaryView === "exchange" ? "active" : ""} onClick={() => setSecondaryView("exchange")} type="button">⇄ Exchange Tape</button>
            </div>
            <div className="tab-content-panel" key={secondaryView}>
              {secondaryView === "evidence" ? (
                <EvidencePanel state={state} />
              ) : secondaryView === "exchange" ? (
                <ExchangeEventTape events={state.exchange_events ?? []} />
              ) : (
                <AgentTimeline
                  activeAgents={state.active_agents}
                  events={state.events}
                  layout="compact"
                  source={historicalMode ? "historical" : "synthetic"}
                  title={hybridMode ? "Hybrid Event Timeline" : historicalMode ? "Historical Event Timeline" : "Agent Event Timeline"}
                />
              )}
            </div>
          </section>
          <IncidentDrawer demoConfig={demoConfig} incident={selectedIncident} currentTick={tick} incidentTick={selectedIncident?.tick ?? tick} mode={incident ? incidentDetailsMode : "replay"} onSendToControlCenter={sendToControlCenter} />
        </section>
      </div>
    </section>
  );
}

function ArenaDemoBanner({ config }: { config: ProductDemoConfig }) {
  return (
    <section className="panel arena-demo-banner" aria-label="Selected demo mode">
      <div>
        <span>Demo mode</span>
        <strong>{config.title}</strong>
      </div>
      <div>
        <span>Symbol</span>
        <strong>{config.marketSymbol}</strong>
      </div>
      <div>
        <span>Attack</span>
        <strong>{config.attackPattern}</strong>
      </div>
      <div>
        <span>Detector</span>
        <strong>{config.detectorProfile}</strong>
      </div>
      <div>
        <span>AI investigation</span>
        <strong>{config.aiInvestigationMode}</strong>
      </div>
    </section>
  );
}

function isEditableTarget(target: EventTarget | null) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA", "BUTTON"].includes(target.tagName);
}

function TopStatusBar({
  canReset,
  connected,
  onPause,
  onReset,
  onStart,
  pendingControl,
  running,
  selectedScenario,
  tick,
  source
}: {
  canReset: boolean;
  connected: boolean;
  onPause: () => void;
  onReset: () => void;
  onStart: () => void;
  pendingControl: "pause" | "reset" | "start" | null;
  running: boolean;
  selectedScenario: string;
  source: string;
  tick: number;
}) {
  return (
    <header className="cockpit-status-bar">
      <MetricPill label="State" value={running ? "Running" : "Paused"} tone={running ? "good" : "warn"} />
      <MetricPill label="Tick" value={String(tick)} />
      <MetricPill label="Scenario" value={selectedScenario} />
      <MetricPill label="Source" value={source} />
      <div className="cockpit-controls">
        <button className="arena-start-button" type="button" disabled={!connected || running || pendingControl !== null} onClick={onStart}>{pendingControl === "start" ? "Starting..." : "Start"}</button>
        <button className="arena-pause-button" type="button" disabled={!connected || !running || pendingControl !== null} onClick={onPause}>{pendingControl === "pause" ? "Pausing..." : "Pause"}</button>
        <button className="arena-reset-button" type="button" disabled={!connected || !canReset || pendingControl !== null} onClick={onReset}>{pendingControl === "reset" ? "Resetting..." : "Reset"}</button>
      </div>
    </header>
  );
}

function MetricPill({ label, tone, value }: { label: string; tone?: "good" | "warn"; value: string }) {
  return (
    <div className={`cockpit-pill ${tone ?? ""}`}>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function createIncident(state: ArenaState): Incident | null {
  if (state.incidents?.length) {
    return state.incidents[state.incidents.length - 1];
  }

  const alert = state.detectors.alerts[state.detectors.alerts.length - 1];
  const scenario = state.active_scenario;
  if (!alert || !scenario || !state.features) {
    return null;
  }

  return {
    agent: scenario.agent_id,
    confidence: alert.confidence,
    evidence: [
      { key: "message_rate", label: "Message rate", value: state.features.message_rate ?? 0, unit: "updates/sec" },
      { key: "wall_size_ratio", label: "Wall size ratio", value: state.features.wall_size_ratio ?? 0 },
      { key: "spread_bps", label: "Spread", value: state.features.spread_bps ?? 0, unit: "bps" },
      { key: "depth_change_pct", label: "Depth change", value: state.features.depth_change_pct ?? 0, unit: "%" }
    ],
    explanation: `${arenaScenarioLabels[scenario.scenario_name as keyof typeof arenaScenarioLabels] ?? scenario.scenario_name} is active in the mock arena and has raised the ${alert.name} detector score.`,
    id: `MOCK-${scenario.scenario_id}-${alert.name}`,
    scenario_family: scenario.scenario_family,
    scenario_id: scenario.scenario_id,
    tick: state.tick,
    severity: alert.severity === "critical" ? "Critical" : alert.severity === "high" ? "High" : "Medium",
    title: `${alert.name} alert`,
    type: scenario.scenario_name
  };
}

function toHeatmapSnapshotFrame(state: ArenaState): HeatmapSnapshotFrame {
  return {
    book: state.book,
    tick: state.tick
  };
}

function toTimelineFrame(state: ArenaState): MarketTimelineFrame {
  return {
    detectorScores: state.detectors,
    features: state.features ?? {},
    markers: getTimelineMarkers(state),
    mid: state.mid ?? 0,
    tick: state.tick
  };
}

function getTimelineMarkers(state: ArenaState): TimelineMarkerType[] {
  const markers: TimelineMarkerType[] = [];
  const attack = state.active_scenario;
  if (attack && attack.start_tick === state.tick) {
    markers.push("attack_started");
  }
  if (state.detectors.alerts.some((alert) => alert.confidence > 0.75)) {
    markers.push("detector_warning");
  }
  if (attack?.current_stage === "incident_confirmed" || attack?.status === "incident_confirmed") {
    markers.push("incident_confirmed");
  }
  return markers;
}

function formatNumber(value: number | null | undefined) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  if (Math.abs(value) >= 1_000) {
    return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return value.toFixed(2);
}
