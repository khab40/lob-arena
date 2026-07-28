import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const productTagline = "Governed Historical + Synthetic Order-Book Validation for Market Surveillance";
const productDescription =
  "A research and validation platform that replays licensed historical order-book data, injects controlled synthetic attacks, and benchmarks surveillance detectors against reproducible ground truth.";

function read(relativePath) {
  return readFileSync(resolve(root, relativePath), "utf8");
}

function expectIncludes(source, values) {
  for (const value of values) {
    assert.match(source, new RegExp(escapeRegExp(value)), `missing ${value}`);
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

describe("LOB Arena branding contract", () => {
  const readme = read("../README.md");
  const app = read("src/App.tsx");
  const about = read("src/pages/AboutPage.tsx");
  const packageJson = read("package.json");
  const index = read("index.html");
  const manifest = read("public/site.webmanifest");

  it("keeps the project title, tagline, description, and repository URL aligned", () => {
    expectIncludes(readme, [
      "# LOB Arena",
      productTagline,
      "A research and validation platform that replays licensed historical order-book",
      "detectors against reproducible ground truth.",
      "github.com/khab40/lob-arena"
    ]);
    expectIncludes(app, ["<strong>LOB Arena</strong>"]);
    expectIncludes(about, [
      productTagline,
      "A research and validation platform that replays licensed historical order-book data, injects",
      "controlled synthetic attacks, and benchmarks surveillance detectors against reproducible ground",
      "truth."
    ]);
    expectIncludes(packageJson, [productDescription]);
    expectIncludes(index, ["<title>LOB Arena</title>", 'name="description"', productDescription]);
    expectIncludes(manifest, ['"name": "LOB Arena"', '"short_name": "LOB Arena"', productDescription]);
    assert.doesNotMatch(`${readme}\n${app}\n${about}\n${index}\n${manifest}`, /AI Market Abuse Detection Arena/);
  });

  it("presents the README in reviewer-first narrative order", () => {
    const sections = ["Problem", "Solution", "Architecture", "Screenshots", "Quick start", "Demo", "Evidence"];
    const offsets = sections.map((section) => readme.indexOf(`## ${section}`));

    assert.ok(offsets.every((offset) => offset >= 0), "README narrative section is missing");
    assert.deepEqual(offsets, [...offsets].sort((left, right) => left - right));
  });
});

describe("Core UI navigation and workflow contracts", () => {
  const app = read("src/App.tsx");
  const arena = read("src/pages/ArenaPage.tsx");
  const agentTimeline = read("src/components/AgentTimeline.tsx");
  const exchangeTape = read("src/components/ExchangeEventTape.tsx");
  const arenaTypes = read("src/types/arena.ts");
  const marketTimeline = read("src/components/MarketTimeline.tsx");
  const nebius = read("src/pages/NebiusControlPanelPage.tsx");
  const runtimeModes = read("src/runtimeModes.ts");
  const css = read("src/App.css");
  const trace = read("src/components/NebiusExecutionTrace.tsx");
  const incidentTransfer = read("src/controlCenterIncident.ts");
  const investigator = read("src/components/NebiusAIInvestigatorPanel.tsx");
  const apiClient = read("src/api/client.ts");
  const runtimeStatus = read("src/features/nebius/components/RuntimeStatusCard.tsx");
  const usageMonitor = read("src/features/nebius/components/UsageCostMonitor.tsx");
  const ingestion = read("src/pages/DataIngestionPage.tsx");

  it("keeps product navigation focused and removes implementation destinations", () => {
    expectIncludes(app, [
      "label: \"Data Ingestion\"",
      "label: \"Arena\"",
      "label: \"Control Panel\"",
      "label: \"About\"",
      "LOB Arena",
      "Control Panel ready",
      "<Route path=\"/\" element={<Navigate to=\"/nebius\" replace />} />",
      "<Route path=\"/nebius\" element={<NebiusControlPanelPage />} />",
      "<Route path=\"/arena\" element={<ArenaPage />} />",
      "<Route path=\"/about\" element={<AboutPage />} />"
    ]);
    const navigationOrder = [
      "label: \"Data Ingestion\"",
      "label: \"Arena\"",
      "label: \"Control Panel\"",
      "label: \"About\""
    ].map((label) => app.indexOf(label));
    assert.ok(navigationOrder.every((index) => index >= 0));
    assert.deepEqual(navigationOrder, [...navigationOrder].sort((left, right) => left - right));
    assert.doesNotMatch(app, /label: "Attack"/);
    assert.doesNotMatch(app, /label: "Demo"/);
    assert.doesNotMatch(app, /label: "Scenario Generator"/);
    assert.doesNotMatch(app, /label: "Detection"/);
    assert.doesNotMatch(app, /label: "Experiments"/);
    assert.doesNotMatch(app, /label: "Reports"/);
    assert.doesNotMatch(app, /label: "Blue Team"/);
    assert.doesNotMatch(app, /label: "Incidents \/ Investigations", primary: true/);
    assert.doesNotMatch(app, /label: "Detector Benchmark", primary: true/);
  });

  it("keeps Arena status, controls, tabs, and standard market visible", () => {
    expectIncludes(arena, [
      "Market Workload Generator",
      "Scenario Setup",
      "Incidents / Investigations",
      "MetricPill label=\"State\"",
      "MetricPill label=\"Tick\"",
      "MetricPill label=\"Scenario\"",
      "MetricPill label=\"Source\"",
      "className=\"arena-start-button\"",
      "className=\"arena-pause-button\"",
      "className=\"arena-reset-button\"",
      "aria-label=\"Keyboard shortcuts\"",
      "MetricPill label=\"Mid\"",
      "MetricPill label=\"Spread\"",
      "📄 Evidence",
      "Market Timeline",
      "🕒 Agent Events",
      "IncidentDrawer",
      "Live replay active:",
      "Exchange ticks, LOB updates, detectors, and incident evidence are streaming below."
    ]);
    expectIncludes(arena, ["storeControlCenterIncident", "controlCenterIncidentPath", "onSendToControlCenter"]);
    assert.doesNotMatch(arena, /aria-label="Market visualization"/);
    assert.doesNotMatch(arena, /MarketBattlefield3D|OrderBookTerrain|battlefieldFrames/);
  });

  it("keeps historical ingestion administrative and source selection explicit", () => {
    expectIncludes(app, [
      "label: \"Data Ingestion\"",
      "<Route path=\"/data-ingestion\" element={<DataIngestionPage />} />"
    ]);
    expectIncludes(ingestion, [
      "LOBSTER batch import",
      "Available source datasets",
      "Dataset registry",
      "importLobsterCandidate",
      "1 minute",
      "5 minutes",
      "Full range",
      "Import window"
    ]);
    expectIncludes(arena, [
      "Market data source",
      "Synthetic",
      "Historical control",
      "Hybrid + attacks",
      "marketDataChoiceTouchedRef",
      "chooseMarketDataSource",
      "Historical dataset",
      "Only canonical event streams support attack injection.",
      "Load Historical Control",
      "Load Hybrid Replay",
      "formatReplayProgress",
      "\"<0.01%\"",
      "no inferred benign or attack labels"
    ]);
    assert.doesNotMatch(ingestion, /type="file"/);
  });

  it("labels agent events as synthetic tick-based activity with runtime provenance", () => {
    expectIncludes(agentTimeline, [
      "Clock · simulation ticks",
      "Venue · synthetic LOB",
      "No orders are routed to a real exchange.",
      "Agent Runner",
      "formatSimulationTick"
    ]);
    assert.doesNotMatch(agentTimeline, /new Date\(timestamp\)/);
    expectIncludes(arena, ["activeAgents={state.active_agents}", "\"Agent Event Timeline\"", "source={historicalMode ? \"historical\" : \"synthetic\"}"]);
    expectIncludes(marketTimeline, [
      "Rolling simulation history",
      "mid price (cyan)",
      "spread in basis points (amber)",
      "order-book imbalance (violet)",
      "simulation tick, not wall-clock time"
    ]);
  });

  it("renders the canonical exchange stream as a typed compact tape", () => {
    expectIncludes(arena, ["⇄ Exchange Tape", "<ExchangeEventTape events={state.exchange_events ?? []}"]);
    expectIncludes(arenaTypes, [
      'ExchangeEventType = "add" | "modify" | "cancel" | "execute" | "snapshot"',
      "export type ExchangeEvent =",
      "exchange_events: ExchangeEvent[]"
    ]);
    expectIncludes(exchangeTape, [
      "Canonical exchange event tape",
      "Canonical simulation stream · newest first",
      "event.event_type === \"snapshot\"",
      "event.event_type === \"execute\"",
      "priority kept",
      "MAX_VISIBLE_EVENTS"
    ]);
  });

  it("transfers the selected Arena incident into the investigation workflow", () => {
    expectIncludes(incidentTransfer, [
      "lob-arena.control-center.incident",
      "incidentInvestigationRequest",
      "detector_outputs",
      "market_metrics"
    ]);
    expectIncludes(nebius, [
      "loadControlCenterIncident",
      "Selected Arena incident",
      "incidentInvestigationRequest(arenaIncident)",
      "Investigate selected Arena incident"
    ]);
    assert.doesNotMatch(nebius, /Switch runtime: Local Demo|Switch runtime: Cloud|Test connection/);
  });

  it("keeps shared Nebius execution trace and cost latency fields complete", () => {
    expectIncludes(trace, [
      "Execution type",
      "Run id",
      "Endpoint id",
      "Job id",
      "Model",
      "Runtime/GPU",
      "Status",
      "Latency",
      "Tokens in",
      "Tokens out",
      "Estimated cost",
      "Artifact link",
      "Last execution time",
      "Simulated / Local Demo",
      "AI Cost & Latency"
    ]);
  });

  it("uses the real endpoint for client-side incidents in Nebius Cloud mode", () => {
    expectIncludes(investigator, [
      "runtimeMode === \"nebius-cloud\"",
      "explainIncidentPayload(incident)",
      "Endpoint request failed",
      "Local Demo mode selected; no Nebius endpoint call was made."
    ]);
    expectIncludes(apiClient, ["/api/incidents/explain", "JSON.stringify({ incident })"]);
    assert.doesNotMatch(investigator, /incident\.id\.startsWith\("MOCK-"\)/);
    assert.doesNotMatch(investigator, /Simulated fallback\. Using cached demo explanation\./);
  });

  it("keeps the AI command center focused on runtime, investigation, benchmark, and trace", () => {
    expectIncludes(nebius, [
      "Command Center workflow",
      "title=\"Serverless Endpoint\"",
      "title=\"Investigation Team\"",
      "title=\"Scenario Generator\"",
      "title=\"Serverless Jobs\"",
      "title=\"Detector Tournament\"",
      "title=\"Runtime\"",
      "Demo Scenarios",
      "Local Lightweight Demo",
      "Local AI Pipeline Demo",
      "Endpoint Demo",
      "Full Platform Demo",
      "demoScenario",
      "navigate(`/attack-scenarios?",
      "title=\"Scenario Generator\"",
      "Generate AI Scenario",
      "AI Investigation unlocks after detector alerts are available",
      "experimentHasAlerts",
      "Replay in Arena",
      "Ground truth",
      "generateMarketAbuseScenario",
      "injectNebiusAttackScenario",
      "navigate(`/arena?replayScenario=",
      "The live Arena remains available and keeps ticking.",
      "title=\"Investigation Team\"",
      "title=\"Detector Tournament\"",
      "Nebius AI Detector Tournament",
      "Powered by Nebius Serverless Jobs",
      "Create benchmark",
      "Generate manifest",
      "Run local or serverless detector tournaments",
      "title=\"Execution Trace\"",
      "Run Nebius AI Investigation Team",
      "Final verdict",
      "Agent findings",
      "Evidence timeline",
      "Recommended action",
      "runAIInvestigationTeam",
      "Explain benchmark alerts",
      "Switch to Cloud to run this explanation on a real endpoint.",
      "Run Local Demo tournament",
      "Run serverless job",
      "Aggregate",
      "Latest execution",
      "Detectors compared",
      "Models compared",
      "<th>Detector</th>",
      "<th>Model</th>",
      "Execution graph",
      "Scenario",
      "Detector",
      "Endpoint",
      "Job",
      "Result",
      "real endpoint used",
      "fallback to deterministic mock",
      "refreshDetectorTournament",
      "mergeSmokeCloudTournament",
      "Sync evidence from S3",
      "listNebiusEvidence",
      "syncNebiusEvidence",
      "evidenceArtifactsFrom",
      "endpoint unavailable",
      "Model name",
      "Cost",
      "Artifacts",
      "Tokens",
      "Deployment Status",
      "Cloud artifact sync",
      "Execution artifacts",
      "CLOUD_JOB_POLL_INTERVAL_MS",
      "refreshManagedExperimentJobs",
      "collectManagedExperimentNebiusArtifacts",
      "cloud artifacts automatically",
      "Simulated / Local Demo",
      "mock fallback",
      "No credentials or deployment are required in Local Demo",
      "deterministic mock results"
    ]);
    assert.doesNotMatch(nebius, /Run Nebius AI Detector Tournament/);
    assert.equal((nebius.match(/<h2>Nebius AI Detector Tournament<\/h2>/g) ?? []).length, 1);
    assert.equal((nebius.match(/<InfrastructureSection/g) ?? []).length, 5);
    assert.doesNotMatch(nebius, /title="Models"/);
    assert.doesNotMatch(nebius, /title="Inference"/);
    assert.doesNotMatch(nebius, /title="Batch Jobs"/);
    assert.doesNotMatch(nebius, /title="GPU Runtime"/);
    assert.doesNotMatch(nebius, /title="Artifacts"/);
    assert.doesNotMatch(nebius, /title="Costs"/);
    assert.doesNotMatch(nebius, /Compare models|Run Jobs|Detector comparison|Model comparison/);
    assert.doesNotMatch(nebius, /Managed Experiment Lab/);
  });

  it("gates the five-step workflow and keeps session telemetry in Execution Trace", () => {
    expectIncludes(nebius, [
      "workflowStepReady",
      "workflowStepLockedReason",
      "controlsDisabled",
      "executionResultsReady",
      "mergeArtifactLinks",
      "ExperimentArtifactBrowser",
      "ExperimentInvestigationResults",
      "Benchmark alert explanations",
      "Showing Tab 3 · Benchmark alert explanations",
      "benchmark-alert-explanations",
      "scrollIntoView",
      "Explain alerts → Tab 3",
      "Open analyst report",
      "<UsageCostMonitor",
      "showE2ECompletion",
      "<E2ECompletionDialog",
      "finalizeServerlessSmokeDemo",
      "Nebius Serverless Job did not finish before the polling timeout."
    ]);
    expectIncludes(usageMonitor, [
      "Current Command Center browser session",
      "aiEndpointCallsSession",
      "sessionDurationSec",
      "estimatedCostUsd",
      "costBasis"
    ]);
    assert.equal((nebius.match(/<ExperimentArtifactBrowser/g) ?? []).length, 1);
    assert.equal((nebius.match(/<ExperimentArtifactLinks/g) ?? []).length, 0);
    assert.doesNotMatch(runtimeStatus, /Estimated cost|Tokens|GPU|Latency/);
  });

  it("persists Polished E2E results and selects Local Mock explicitly", () => {
    expectIncludes(apiClient, [
      "execution_mode: runtimeMode === \"local-demo\" ? \"local\" : \"nebius\"",
      "/api/nebius/serverless-smoke/",
      "/finalize/",
      "ServerlessSmokeFinalizeResponse"
    ]);
    expectIncludes(nebius, [
      "finalized.evidence.s3_status",
      "refreshExperimentDetails(result.experiment_id)",
      "Polished E2E demo saved as experiment"
    ]);
  });

  it("gates every Nebius-only control on live service probes", () => {
    expectIncludes(nebius, [
      "probeSucceeded(nebiusStatus?.endpoint_health)",
      "probeSucceeded(nebiusStatus?.job_health)",
      "probeSucceeded(nebiusStatus?.storage_health)",
      "Requires successful live Endpoint and Serverless Jobs probes",
      "configured submit command, and successful live Jobs probe",
      "Object Storage is ${storageHealthStatus",
      "Required Nebius services did not pass their live probes",
      "Usage measured",
      "not reported"
    ]);
  });

  it("keeps demo runtime as the default experience", () => {
    expectIncludes(app, [
      "className=\"global-workspace-header\"",
      "<RuntimePanel />",
      "Runtime mode",
      "Local Demo",
      "Nebius Cloud",
      "testNebiusConnection",
      "Checking live Nebius services",
      "runtimeProbeStatus",
      "status.runner_health",
      "Runner ${runtimeStatusText(runnerStatus)}",
      "status.job_health",
      "status.storage_health"
    ]);
    expectIncludes(runtimeModes, [
      "Local Demo",
      "Nebius Cloud",
      "Component",
      "Frontend",
      "Backend",
      "Runner",
      "AI Endpoint",
      "Jobs",
      "Storage",
      "Ready",
      "Mock",
      "Connected",
      "Not configured",
      "Endpoint unavailable",
      "Error"
    ]);
    assert.doesNotMatch(runtimeModes, /"AI Endpoint": "Connected"/);
    assert.doesNotMatch(runtimeModes, /Jobs: "Connected"/);
    assert.doesNotMatch(app, /Google|AuthProvider|IdentityPanel|useAuth/);
    assert.doesNotMatch(app, /Switch to Hybrid/);
  });

  it("keeps Nebius-inspired console design tokens available", () => {
    expectIncludes(css, [
      "--color-bg",
      "--color-bg-muted",
      "--color-surface",
      "--color-surface-elevated",
      "--color-border",
      "--color-border-strong",
      "--color-text",
      "--color-text-muted",
      "--color-text-soft",
      "--color-primary",
      "--color-primary-hover",
      "--color-primary-soft",
      "--color-success",
      "--color-warning",
      "--color-danger",
      "--color-sidebar-bg",
      "--color-sidebar-text",
      "--color-sidebar-muted",
      "--color-sidebar-active-bg",
      "--color-sidebar-active-text",
      "--shadow-card",
      "--radius-sm",
      "--radius-md",
      "--radius-lg",
      "--layout-sidebar-width",
      "--layout-topbar-height",
      ".console-topbar",
      ".command-center-service-grid",
      ".artifact-link-list",
      ".ai-scenario-generator-panel",
      ".experiment-form-grid"
    ]);
  });
});

describe("Retired feature boundaries", () => {
  const app = read("src/App.tsx");
  const arena = read("src/pages/ArenaPage.tsx");
  const client = read("src/api/client.ts");
  const attackBuilder = read("src/components/AttackBuilder.tsx");
  const attackPage = read("src/pages/AttackScenarioGeneratorPage.tsx");

  it("keeps retired features out of active frontend imports and routes", () => {
    expectIncludes(attackBuilder, ["Scenario Setup", "Manipulation type", "Difficulty", "Send to Nebius investigation", "storeControlCenterIncident", "controlCenterIncidentPath"]);
    expectIncludes(attackPage, ["AI Scenario Generator", "sendToInvestigation", "storeControlCenterIncident"]);
    assert.doesNotMatch(`${app}\n${arena}\n${client}`, /GoogleAuth|AuthProvider|IdentityPanel|MarketBattlefield3D|OrderBookTerrain/);
    assert.doesNotMatch(`${attackBuilder}\n${attackPage}`, /featureFlags|enableAdvancedAttackControls/);
    assert.doesNotMatch(attackBuilder, /to="\/investigations/);
    assert.doesNotMatch(attackPage, /to={`\/investigations/);
  });
});

describe("API error contract", () => {
  const client = read("src/api/client.ts");

  it("keeps structured smart-batch backend errors visible", () => {
    expectIncludes(client, [
      "formatApiErrorDetail",
      "record.message",
      "stderr:",
      "Smart batch run failed"
    ]);
  });
});
