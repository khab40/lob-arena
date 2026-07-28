import type { CSSProperties, PointerEvent as ReactPointerEvent } from "react";
import { useEffect, useRef, useState } from "react";
import { BrowserRouter, Navigate, NavLink, Route, Routes, useLocation } from "react-router";
import "./App.css";
import { AboutPage } from "@/pages/AboutPage";
import { getNebiusStatus } from "@/api/client";
import { ArenaPage } from "@/pages/ArenaPage";
import { AttackScenarioGeneratorPage } from "@/pages/AttackScenarioGeneratorPage";
import { DataIngestionPage } from "@/pages/DataIngestionPage";
import { NebiusControlPanelPage } from "@/pages/NebiusControlPanelPage";
import {
  getStoredRuntimeMode,
  runtimeComponents,
  storeRuntimeMode,
  visibleRuntimeOptions,
  type RuntimeComponent,
  type RuntimeMode,
  type RuntimeStatus
} from "@/runtimeModes";

const disclaimer =
  "This project is an educational simulation. It does not detect real market manipulation, does not provide trading signals, and should not be used for compliance decisions. The scenarios are synthetic “abuse-like” patterns designed to demonstrate order-book anomaly detection and AI Investigator explanations.";

type ThemePreference = "system" | "light" | "dark";
type ResolvedTheme = "light" | "dark";

const THEME_PREFERENCE_KEY = "lob-arena.themePreference";
const SIDEBAR_WIDTH_KEY = "lob-arena.sidebarWidth";
const SIDEBAR_MIN_WIDTH = 220;
const SIDEBAR_MAX_WIDTH = 420;
const SIDEBAR_DEFAULT_WIDTH = 292;
const SIDEBAR_COLLAPSED_WIDTH = 78;

export function App() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [sidebarWidth, setSidebarWidth] = useState(() => getStoredSidebarWidth());
  const resizingRef = useRef(false);
  const [themePreference, setThemePreference] = useState<ThemePreference>(() => getStoredThemePreference());
  const [systemTheme, setSystemTheme] = useState<ResolvedTheme>(() => getSystemTheme());
  const resolvedTheme = themePreference === "system" ? systemTheme : themePreference;

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    function handleChange() {
      setSystemTheme(media.matches ? "dark" : "light");
    }
    handleChange();
    media.addEventListener("change", handleChange);
    return () => media.removeEventListener("change", handleChange);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(THEME_PREFERENCE_KEY, themePreference);
  }, [themePreference]);

  useEffect(() => {
    if (!sidebarCollapsed) {
      window.localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth));
    }
  }, [sidebarCollapsed, sidebarWidth]);

  useEffect(() => {
    document.documentElement.dataset.theme = resolvedTheme;
    document.documentElement.dataset.themePreference = themePreference;
    document.documentElement.style.colorScheme = resolvedTheme;
  }, [resolvedTheme, themePreference]);

  function startSidebarResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (sidebarCollapsed) {
      return;
    }
    resizingRef.current = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    document.body.dataset.sidebarResizing = "true";
  }

  function resizeSidebar(event: ReactPointerEvent<HTMLDivElement>) {
    if (!resizingRef.current) {
      return;
    }
    setSidebarWidth(clampSidebarWidth(event.clientX));
  }

  function stopSidebarResize(event: ReactPointerEvent<HTMLDivElement>) {
    if (!resizingRef.current) {
      return;
    }
    resizingRef.current = false;
    event.currentTarget.releasePointerCapture(event.pointerId);
    delete document.body.dataset.sidebarResizing;
  }

  const shellStyle = {
    "--sidebar-width": `${sidebarCollapsed ? SIDEBAR_COLLAPSED_WIDTH : sidebarWidth}px`
  } as CSSProperties;

  return (
    <BrowserRouter>
      <main className={`app-shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`} style={shellStyle}>
        <aside className="app-sidebar" aria-label="Application navigation">
          <div className="sidebar-brand">
            <div className="sidebar-wordmark">
              <strong>LOB Arena</strong>
            </div>
            <button
              aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
              className="sidebar-toggle"
              onClick={() => setSidebarCollapsed((collapsed) => !collapsed)}
              type="button"
            >
              <SidebarToggleIcon direction={sidebarCollapsed ? "right" : "left"} />
            </button>
          </div>

          <nav className="side-nav" aria-label="Main screens">
            {sidebarItems.map((item) => (
              <SidebarLink
                icon={item.icon}
                key={item.to}
                label={item.label}
                shortLabel={item.shortLabel}
                to={item.to}
              />
            ))}
          </nav>
          <div className="sidebar-controls" aria-label="Runtime and safety controls">
            <RuntimePanel />
            <DisclaimerPopover />
          </div>
          <div
            aria-hidden={sidebarCollapsed}
            className="sidebar-resize-handle"
            onDoubleClick={() => setSidebarWidth(SIDEBAR_DEFAULT_WIDTH)}
            onPointerCancel={stopSidebarResize}
            onPointerDown={startSidebarResize}
            onPointerMove={resizeSidebar}
            onPointerUp={stopSidebarResize}
            role="separator"
          />
        </aside>

        <section className="app-workspace">
          <header className="global-workspace-header" aria-label="Global account controls">
            <ConsoleTopbar />
            <ThemePanel
              collapsed={false}
              onPreferenceChange={setThemePreference}
              preference={themePreference}
              resolvedTheme={resolvedTheme}
            />
          </header>
          <WorkspaceBanner />

          <Routes>
            <Route path="/" element={<Navigate to="/nebius" replace />} />
            <Route path="/arena" element={<ArenaPage />} />
            <Route path="/data-ingestion" element={<DataIngestionPage />} />
            <Route path="/attack-scenarios" element={<AttackScenarioGeneratorPage />} />
            <Route path="/nebius" element={<NebiusControlPanelPage />} />
            <Route path="/about" element={<AboutPage />} />
          </Routes>
        </section>
      </main>
    </BrowserRouter>
  );
}

function ConsoleTopbar() {
  return (
    <section className="console-topbar" aria-label="AI command console">
      <span className="runtime-status active console-ai-button">Control Panel ready</span>
    </section>
  );
}

function WorkspaceBanner() {
  const { pathname } = useLocation();
  const content = workspaceBanners[pathname];
  if (!content) {
    return null;
  }
  return (
    <section className="workspace-banner" aria-label={`${content.title} overview`}>
      <div>
        <h1>{content.title}</h1>
        <p>{content.description}</p>
      </div>
    </section>
  );
}

function DisclaimerPopover() {
  const [open, setOpen] = useState(false);
  return (
    <div className="disclaimer-popover">
      <button
        aria-expanded={open}
        className="secondary-button disclaimer-popover-button"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        Disclaimer
      </button>
      {open ? (
        <div className="disclaimer-popover-panel" role="dialog" aria-label="Project disclaimer">
          <strong>Disclaimer</strong>
          <p>{disclaimer}</p>
        </div>
      ) : null}
    </div>
  );
}

function getStoredThemePreference(): ThemePreference {
  const stored = window.localStorage.getItem(THEME_PREFERENCE_KEY);
  return stored === "light" || stored === "dark" || stored === "system" ? stored : "system";
}

function getStoredSidebarWidth() {
  const storedValue = window.localStorage.getItem(SIDEBAR_WIDTH_KEY);
  if (storedValue === null) {
    return SIDEBAR_DEFAULT_WIDTH;
  }
  const stored = Number(storedValue);
  return clampSidebarWidth(Number.isFinite(stored) ? stored : SIDEBAR_DEFAULT_WIDTH);
}

function clampSidebarWidth(value: number) {
  return Math.min(SIDEBAR_MAX_WIDTH, Math.max(SIDEBAR_MIN_WIDTH, Math.round(value)));
}

function getSystemTheme(): ResolvedTheme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function SidebarToggleIcon({ direction }: { direction: "left" | "right" }) {
  const paths = direction === "left"
    ? ["M13 6l-5 6 5 6", "M18 6l-5 6 5 6"]
    : ["M11 6l5 6-5 6", "M6 6l5 6-5 6"];
  return (
    <svg aria-hidden="true" className="sidebar-toggle-icon" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
      {paths.map((path) => <path d={path} key={path} />)}
    </svg>
  );
}

function SidebarLink({
  label,
  shortLabel,
  icon,
  to
}: {
  label: string;
  shortLabel: string;
  icon: AppIconName;
  to: string;
}) {
  return (
    <NavLink title={label} to={to}>
      <span className="nav-short">{shortLabel}</span>
      <AppIcon name={icon} />
      <span className="nav-label">{label}</span>
    </NavLink>
  );
}

type AppIconName = "arena" | "cloud" | "database" | "about";

type SidebarItem = {
  icon: AppIconName;
  label: string;
  shortLabel: string;
  to: string;
};

const workspaceBanners: Record<string, { title: string; description: string }> = {
  "/nebius": {
    title: "Control Panel",
    description: "Generate suspicious workload, detect incidents with Nebius AI, and run detector tournaments on Nebius Serverless Jobs."
  },
  "/arena": {
    title: "Arena",
    description: "Generate synthetic market workloads, inspect order-book pressure, and review incident evidence in one live cockpit."
  },
  "/data-ingestion": {
    title: "Data Ingestion",
    description: "Validate and register local historical market datasets for replay in Arena."
  },
  "/about": {
    title: "About",
    description: "Understand the architecture, safety guardrails, benchmark flow, and research basis behind the synthetic market arena."
  }
};
const sidebarItems: SidebarItem[] = [
  { icon: "database", label: "Data Ingestion", shortLabel: "DI", to: "/data-ingestion" },
  { icon: "arena", label: "Arena", shortLabel: "AR", to: "/arena" },
  { icon: "cloud", label: "Control Panel", shortLabel: "CP", to: "/nebius" },
  { icon: "about", label: "About", shortLabel: "AB", to: "/about" }
];

function AppIcon({ name }: { name: AppIconName }) {
  const paths: Record<AppIconName, string[]> = {
    about: ["M12 17v-5", "M12 8h.01", "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z"],
    arena: ["M4 17h16", "M6 14l3-4 3 2 4-6 2 3", "M5 5v14h14"],
    cloud: ["M7 18h10a4 4 0 0 0 .8-7.9A6 6 0 0 0 6.4 8.4 4.5 4.5 0 0 0 7 18Z"],
    database: ["M4 6c0-2 16-2 16 0s-16 2-16 0Z", "M4 6v6c0 2 16 2 16 0V6", "M4 12v6c0 2 16 2 16 0v-6"]
  };
  return (
    <svg aria-hidden="true" className="app-icon" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24">
      {paths[name].map((path) => <path d={path} key={path} />)}
    </svg>
  );
}

const themeOptions: { label: string; mode: ThemePreference }[] = [
  { label: "System", mode: "system" },
  { label: "Light", mode: "light" },
  { label: "Dark", mode: "dark" }
];

function ThemePanel({
  collapsed,
  onPreferenceChange,
  preference,
  resolvedTheme
}: {
  collapsed: boolean;
  onPreferenceChange: (preference: ThemePreference) => void;
  preference: ThemePreference;
  resolvedTheme: ResolvedTheme;
}) {
  function cycleTheme() {
    const index = themeOptions.findIndex((option) => option.mode === preference);
    onPreferenceChange(themeOptions[(index + 1) % themeOptions.length].mode);
  }

  if (collapsed) {
    return (
      <section className="theme-panel collapsed" aria-label="Theme mode">
        <button
          aria-label={`Theme: ${preference}`}
          className="theme-cycle-button"
          onClick={cycleTheme}
          title={`Theme: ${preference}`}
          type="button"
        >
          <ThemeIcon mode={preference === "system" ? "system" : resolvedTheme} />
        </button>
      </section>
    );
  }

  return (
    <section className="theme-panel" aria-label="Theme mode">
      <span>Theme</span>
      <div className="theme-segmented-control" role="group" aria-label="Theme mode">
        {themeOptions.map((option) => (
          <button
            aria-pressed={preference === option.mode}
            className={preference === option.mode ? "active" : ""}
            key={option.mode}
            onClick={() => onPreferenceChange(option.mode)}
            title={option.label}
            type="button"
          >
            <ThemeIcon mode={option.mode} />
          </button>
        ))}
      </div>
    </section>
  );
}

function ThemeIcon({ mode }: { mode: ThemePreference | ResolvedTheme }) {
  const paths: Record<string, string[]> = {
    dark: ["M21 12.8A8.5 8.5 0 1 1 11.2 3a6.8 6.8 0 0 0 9.8 9.8Z"],
    light: ["M12 4V2", "M12 22v-2", "M4 12H2", "M22 12h-2", "M5.6 5.6 4.2 4.2", "M19.8 19.8l-1.4-1.4", "M18.4 5.6l1.4-1.4", "M4.2 19.8l1.4-1.4", "M12 16a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z"],
    system: ["M5 5h14v10H5z", "M9 19h6", "M12 15v4"]
  };
  return (
    <svg aria-hidden="true" className="theme-icon" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" viewBox="0 0 24 24">
      {paths[mode].map((path) => <path d={path} key={path} />)}
    </svg>
  );
}

function DrawerToggleIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg aria-hidden="true" className="auth-toggle-mark" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" viewBox="0 0 24 24">
      <path d={expanded ? "M6 15l6-6 6 6" : "M6 9l6 6 6-6"} />
    </svg>
  );
}

function RuntimePanel() {
  const [menuOpen, setMenuOpen] = useState(false);
  const panelRef = useRef<HTMLElement>(null);
  const [runtimeMode, setRuntimeMode] = useState<RuntimeMode>(() => getStoredRuntimeMode());
  const [cloudMessage, setCloudMessage] = useState("Checking live Nebius services...");
  const [runtimeOverrides, setRuntimeOverrides] = useState<Partial<Record<RuntimeMode, Partial<Record<RuntimeComponent, RuntimeStatus>>>>>({});
  const runtime = visibleRuntimeOptions.find((option) => option.value === runtimeMode) ?? visibleRuntimeOptions[0];
  const runtimeMessage = runtimeMode === "local-demo"
    ? "Local Demo is ready. Mock AI fallback is active."
    : cloudMessage;

  useEffect(() => {
    storeRuntimeMode(runtimeMode);
    void refreshNebiusRuntimeStatus();
  }, [runtimeMode]);

  useEffect(() => {
    if (!menuOpen) {
      return undefined;
    }
    function closeRuntimeMenu(event: KeyboardEvent | MouseEvent) {
      if (event instanceof KeyboardEvent && event.key === "Escape") {
        setMenuOpen(false);
        return;
      }
      if (event instanceof MouseEvent && !panelRef.current?.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("keydown", closeRuntimeMenu);
    document.addEventListener("mousedown", closeRuntimeMenu);
    return () => {
      document.removeEventListener("keydown", closeRuntimeMenu);
      document.removeEventListener("mousedown", closeRuntimeMenu);
    };
  }, [menuOpen]);

  function switchRuntime(mode: RuntimeMode) {
    setRuntimeMode(mode);
    if (mode === "nebius-cloud") {
      setCloudMessage("Checking live Nebius services...");
    }
  }

  async function refreshNebiusRuntimeStatus() {
    setRuntimeOverrides((current) => ({
      ...current,
      "nebius-cloud": {
        "AI Endpoint": "Checking",
        Backend: "Checking",
        Frontend: "Ready",
        Jobs: "Checking",
        Runner: "Checking",
        Storage: "Checking"
      }
    }));
    try {
      const status = await getNebiusStatus();
      const endpointReady = runtimeProbeStatus(status.endpoint_health ?? undefined) === "Connected";
      const endpointStatus: RuntimeStatus = endpointReady
        ? "Connected"
        : status.endpoint_base_url_configured
          ? "Endpoint unavailable"
          : "Not configured";
      const jobsStatus = runtimeProbeStatus(status.job_health);
      const storageStatus = runtimeProbeStatus(status.storage_health);
      const runnerProbeStatus = runtimeProbeStatus(status.runner_health);
      const runnerStatus: RuntimeStatus = runnerProbeStatus === "Connected"
        ? "Ready"
        : runnerProbeStatus === "Not configured"
          ? "Not configured"
          : runnerProbeStatus;
      setRuntimeOverrides((current) => ({
        ...current,
        "nebius-cloud": {
          "AI Endpoint": endpointStatus,
          Backend: "Ready",
          Frontend: "Ready",
          Jobs: jobsStatus,
          Runner: runnerStatus,
          Storage: storageStatus
        }
      }));
      const probeIssues = [
        endpointStatus === "Connected" ? null : `Endpoint: ${runtimeProbeDetail(status.endpoint_health ?? undefined)}`,
        runnerStatus === "Ready" ? null : `Runner: ${runtimeProbeDetail(status.runner_health)}`,
        jobsStatus === "Connected" ? null : `Jobs: ${runtimeProbeDetail(status.job_health)}`,
        storageStatus === "Connected" ? null : `Storage: ${runtimeProbeDetail(status.storage_health)}`
      ].filter((detail): detail is string => Boolean(detail));
      setCloudMessage(
        `Live check: Runner ${runtimeStatusText(runnerStatus)}; Endpoint ${runtimeStatusText(endpointStatus)}; Jobs ${runtimeStatusText(jobsStatus)}; Storage ${runtimeStatusText(storageStatus)}.${probeIssues.length ? ` ${probeIssues.join(" ")}` : ""}`
      );
    } catch (error) {
      setRuntimeOverrides((current) => ({
        ...current,
        "nebius-cloud": {
          "AI Endpoint": "Unavailable",
          Backend: "Unavailable",
          Frontend: "Ready",
          Jobs: "Unavailable",
          Runner: "Unavailable",
          Storage: "Unavailable"
        }
      }));
      setCloudMessage(error instanceof Error ? error.message : "Nebius live status check failed.");
    }
  }

  async function testNebiusConnection() {
    if (runtimeMode === "local-demo") {
      setCloudMessage("Switch to Nebius Cloud to view the live probe result.");
      return;
    }
    setCloudMessage("Checking live Nebius services...");
    await refreshNebiusRuntimeStatus();
  }

  return (
    <section className="runtime-control" aria-label="Runtime mode" ref={panelRef}>
      <button
        aria-controls="runtime-mode-dialog"
        aria-expanded={menuOpen}
        aria-haspopup="dialog"
        className="runtime-status-pill"
        onClick={() => setMenuOpen((value) => !value)}
        title="Runtime mode"
        type="button"
      >
        <span aria-hidden="true">{runtime.marker}</span>
        <strong>{runtime.label}</strong>
        <DrawerToggleIcon expanded={menuOpen} />
      </button>
      {menuOpen ? (
        <div aria-label="Runtime mode selection" className="runtime-drawer" id="runtime-mode-dialog" role="dialog">
          <div className="runtime-drawer-header">
            <div>
              <span>Execution environment</span>
              <strong>{runtime.label}</strong>
            </div>
            <button aria-label="Close runtime mode selection" className="runtime-drawer-close" onClick={() => setMenuOpen(false)} type="button">×</button>
          </div>
          <p>{runtime.description}</p>
          <table className="runtime-matrix">
            <thead>
              <tr>
                <th>Component</th>
                {visibleRuntimeOptions.map((option) => <th key={option.value}>{option.label}</th>)}
              </tr>
            </thead>
            <tbody>
              {runtimeComponents.map((component) => (
                <tr key={component}>
                  <th>{component}</th>
                  {visibleRuntimeOptions.map((option) => {
                    const optionMatrix = { ...option.matrix, ...runtimeOverrides[option.value] };
                    const status = optionMatrix[component];
                    return <td className={option.value === runtimeMode ? "current" : ""} key={option.value}><span className={`runtime-status ${status.toLowerCase().replace(/\s+/g, "-")}`}>{status}</span></td>;
                  })}
                </tr>
              ))}
            </tbody>
          </table>
          <div className="runtime-actions">
            <button
              aria-pressed={runtimeMode === "local-demo"}
              className={runtimeMode === "local-demo" ? "active" : ""}
              onClick={() => switchRuntime("local-demo")}
              type="button"
            >
              Local Demo
            </button>
            <button
              aria-pressed={runtimeMode === "nebius-cloud"}
              className={runtimeMode === "nebius-cloud" ? "active" : ""}
              onClick={() => switchRuntime("nebius-cloud")}
              type="button"
            >
              Nebius Cloud
            </button>
            <button onClick={testNebiusConnection} type="button">Test</button>
          </div>
          <p className="runtime-fallback-note">{runtimeMessage}</p>
        </div>
      ) : null}
    </section>
  );
}

function runtimeProbeStatus(probe: Record<string, unknown> | undefined): RuntimeStatus {
  const status = String(probe?.status ?? "unavailable").toLowerCase();
  if (["ok", "ready", "healthy", "connected"].includes(status)) return "Connected";
  if (status === "not_configured") return "Not configured";
  if (status === "degraded") return "Degraded";
  return "Unavailable";
}

function runtimeStatusText(status: RuntimeStatus): string {
  return status.toLowerCase();
}

function runtimeProbeDetail(probe: Record<string, unknown> | undefined): string {
  const detail = probe?.detail ?? probe?.fallback_reason;
  return typeof detail === "string" && detail.trim() ? detail : runtimeStatusText(runtimeProbeStatus(probe));
}
