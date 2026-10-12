export type ArenaMode = "demo" | "mock" | "websocket";

type RuntimeConfig = {
  VITE_API_BASE_URL?: string;
  VITE_ARENA_MODE?: ArenaMode;
  VITE_ARENA_WS_URL?: string;
  VITE_CEO_DEMO?: string;
};

declare global {
  interface Window {
    __LOB_ARENA_CONFIG__?: RuntimeConfig;
  }
}

const runtimeConfig = typeof window === "undefined" ? undefined : window.__LOB_ARENA_CONFIG__;
const browserOrigin = typeof window === "undefined" ? "http://localhost:5173" : window.location.origin;
const browserWebSocketOrigin = browserOrigin.replace(/^http/, "ws");

export const CEO_DEMO_ENABLED = configuredValue(runtimeConfig?.VITE_CEO_DEMO, import.meta.env.VITE_CEO_DEMO, "false") === "true";

function configuredValue(runtimeValue: string | undefined, buildValue: string | undefined, fallback: string): string {
  return runtimeValue?.trim() || buildValue?.trim() || fallback;
}

export const API_BASE_URL = configuredValue(
  runtimeConfig?.VITE_API_BASE_URL,
  import.meta.env.VITE_API_BASE_URL,
  browserOrigin
);

export const ARENA_WS_URL = configuredValue(
  runtimeConfig?.VITE_ARENA_WS_URL,
  import.meta.env.VITE_ARENA_WS_URL,
  `${browserWebSocketOrigin}/ws/arena`
);

const configuredMode = configuredValue(
  runtimeConfig?.VITE_ARENA_MODE,
  import.meta.env.VITE_ARENA_MODE,
  "websocket"
);

export const ARENA_MODE: ArenaMode = configuredMode === "demo" || configuredMode === "mock" ? configuredMode : "websocket";
