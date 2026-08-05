import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE_URL, ARENA_MODE, ARENA_WS_URL, type ArenaMode } from "@/config/runtime";
import { useMockArena, type MockScenarioType } from "@/hooks/useMockArena";
import type { ArenaState, ArenaWebSocketMessage } from "@/types/arena";

export type { ArenaMode };
export type ArenaScenarioType = MockScenarioType;
export type ArenaSourceStatus = "demo" | "mock" | "connecting" | "connected" | "disconnected" | "error";

export function useArenaSource({ demo = false, demoScenario, symbol }: { demo?: boolean; demoScenario?: ArenaScenarioType; symbol?: string } = {}) {
  const mode = demo ? "demo" : getArenaMode();
  const mockArena = useMockArena({ demo: mode === "demo", initialScenario: demoScenario, symbol });
  const wsUrl = ARENA_WS_URL;
  const apiBaseUrl = API_BASE_URL;
  const socketRef = useRef<WebSocket | null>(null);
  const [sourceStatus, setSourceStatus] = useState<ArenaSourceStatus>(mode === "websocket" ? "connecting" : mode);
  const [websocketState, setWebsocketState] = useState<ArenaState>(() => mockArena.state);

  useEffect(() => {
    if (mode !== "websocket") {
      setSourceStatus(mode);
      return undefined;
    }

    setSourceStatus("connecting");
    const socket = new WebSocket(wsUrl);
    socketRef.current = socket;

    socket.onopen = () => setSourceStatus("connected");
    socket.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data) as ArenaWebSocketMessage | ArenaState;
        const nextState = "payload" in message ? message.payload : message;
        if (isArenaState(nextState)) {
          setWebsocketState(nextState);
        }
      } catch {
        setSourceStatus("error");
      }
    };
    socket.onerror = () => setSourceStatus("error");
    socket.onclose = () => {
      if (socketRef.current === socket) {
        setSourceStatus("disconnected");
        socketRef.current = null;
      }
    };

    return () => {
      if (socketRef.current === socket) {
        socketRef.current = null;
      }
      socket.close();
    };
  }, [mode, wsUrl]);

  const sendWebSocketCommand = useCallback((message: Record<string, unknown>) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      setSourceStatus("error");
      return false;
    }
    socket.send(JSON.stringify(message));
    return true;
  }, []);

  const start = useCallback(() => {
    if (mode === "mock") {
      mockArena.start();
      return;
    }
    if (mode === "demo") {
      mockArena.start();
      return;
    }
    sendWebSocketCommand({ action: "start", type: "arena_control" });
  }, [mockArena, mode, sendWebSocketCommand]);

  const pause = useCallback(() => {
    if (mode === "mock") {
      mockArena.pause();
      return;
    }
    if (mode === "demo") {
      mockArena.pause();
      return;
    }
    sendWebSocketCommand({ action: "pause", type: "arena_control" });
  }, [mockArena, mode, sendWebSocketCommand]);

  const reset = useCallback(() => {
    if (mode === "mock") {
      mockArena.reset();
      return;
    }
    if (mode === "demo") {
      mockArena.reset();
      return;
    }
    sendWebSocketCommand({ action: "reset", type: "arena_control" });
  }, [mockArena, mode, sendWebSocketCommand]);

  const launchScenario = useCallback((scenario: ArenaScenarioType) => {
    if (mode === "mock") {
      mockArena.launchScenario(scenario);
      return;
    }
    if (mode === "demo") {
      mockArena.launchScenario(scenario);
      return;
    }
    sendWebSocketCommand({ scenario: scenarioToBackendName(scenario), type: "launch_scenario" });
  }, [mockArena, mode, sendWebSocketCommand]);

  const loadMarketDataSource = useCallback((sourceType: "synthetic" | "synthetic_profile" | "historical" | "hybrid", datasetId = "") => {
    if (mode !== "websocket") {
      return false;
    }
    return sendWebSocketCommand({
      dataset_id: datasetId,
      source_type: sourceType,
      type: "load_market_data_source"
    });
  }, [mode, sendWebSocketCommand]);

  const state = mode === "websocket" ? websocketState : mockArena.state;

  return useMemo(
    () => ({
      launchScenario,
      loadMarketDataSource,
      mode,
      pause,
      reset,
      running: state.running,
      sourceStatus,
      start,
      state,
      symbol: getSymbol(state),
      tick: state.tick,
      apiBaseUrl,
      wsUrl
    }),
    [apiBaseUrl, launchScenario, loadMarketDataSource, mode, pause, reset, sourceStatus, start, state, wsUrl]
  );
}

function getArenaMode(): ArenaMode {
  return ARENA_MODE;
}

function scenarioToBackendName(scenario: ArenaScenarioType) {
  return scenario;
}

function isArenaState(value: unknown): value is ArenaState {
  return Boolean(
    value &&
    typeof value === "object" &&
    "book" in value &&
    "tick" in value &&
    "running" in value
  );
}

function getSymbol(state: ArenaState) {
  const eventSymbol = state.events.find((event) => typeof event.symbol === "string")?.symbol;
  return typeof eventSymbol === "string" ? eventSymbol : "BTCUSDT";
}
