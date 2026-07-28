import { useEffect, useState, type ReactNode } from "react";
import { useNavigate, useSearchParams } from "react-router";
import {
  aggregateManagedExperiment,
  artifactDownloadUrl,
  createManagedExperiment,
  finalizeServerlessSmokeDemo,
  generateMarketAbuseScenario,
  generateManagedExperimentManifest,
  getManagedExperiment,
  getManagedExperimentLeaderboard,
  getManagedExperimentSummary,
  getManagedExperimentReportUrl,
  getNebiusObservatory,
  getNebiusStatus,
  getReportsSummary,
  injectNebiusAttackScenario,
  listManagedExperimentJobs,
  listManagedExperimentInvestigations,
  listManagedExperiments,
  listNebiusEvidence,
  collectManagedExperimentNebiusArtifacts,
  refreshManagedExperimentJobs,
  refreshDetectorTournament,
  renderManagedExperimentNebiusJobConfig,
  runAIInvestigationTeam,
  runManagedExperimentInvestigations,
  runServerlessSmokeDemo,
  runManagedExperimentLocalBatch,
  submitManagedExperimentNebius,
  syncNebiusEvidence,
  type AIInvestigationTeamResponse,
  type DetectorTournamentResponse,
  type ExperimentJobRecord,
  type InvestigationRecord,
  type ExperimentLeaderboardRow,
  type ExperimentSummary,
  type MarketAbuseScenarioGenerationRequest,
  type MarketAbuseScenarioResponse,
  type ManagedExperiment,
  type ManagedExperimentCreateRequest,
  type NebiusArtifactCollectionResponse,
  type NebiusEvidenceRecord,
  type NebiusObservatory,
  type NebiusStatus,
  type ReportsSummary,
  type ServerlessSmokeResponse
} from "@/api/client";
import { incidentInvestigationRequest, loadControlCenterIncident } from "@/controlCenterIncident";
import type { Incident } from "@/types/arena";
import { arenaScenarioLabels, arenaScenarioTypes } from "@/scenarios";
import { RuntimeStatusCard } from "@/features/nebius/components/RuntimeStatusCard";
import { UsageCostMonitor } from "@/features/nebius/components/UsageCostMonitor";
import type {
  NebiusRuntimeStatus,
  NebiusUsageMetrics
} from "@/features/nebius/types";
import {
  getStoredRuntimeMode,
  RUNTIME_MODE_EVENT,
  storeRuntimeMode,
  visibleRuntimeOptions,
  type RuntimeMode
} from "@/runtimeModes";

const fallbackRuntimeStatus: NebiusRuntimeStatus = {
  activeSimulation: "No execution recorded",
  aiEndpointStatus: "checking",
  cloudStatus: "checking",
  eventsPerSecond: 0,
  mode: "local",
  region: "not reported",
  runningAgents: 0,
  serverlessStatus: "checking",
  storageStatus: "checking",
  ticksProcessed: 0,
  websocketStatus: "disconnected"
};

const fallbackUsageMetrics: NebiusUsageMetrics = {
  aiEndpointCallsSession: 0,
  averageLlmLatencySec: 0,
  artifactCount: 0,
  costBasis: "No session execution recorded.",
  estimatedCostUsd: 0,
  jobRuntimeSec: 0,
  replayStorageMb: 0,
  serverlessJobsRun: 0,
  sessionDurationSec: 0,
  simulationEventsGenerated: 0,
  tokensUsed: 0
};

type ExperimentFormState = Required<Pick<ManagedExperimentCreateRequest, "name" | "attack_count" | "batch_size" | "scenarios" | "seed">>;
type DemoScenario = {
  attackKey: string;
  cta?: string;
  demonstrates: string[];
  duration?: string;
  id: string;
  purpose?: string;
  runtime: RuntimeMode;
  title: string;
};
type ExperimentAction =
  | "create-experiment"
  | "generate-ai-scenario"
  | "generate-manifest"
  | "run-local-batch"
  | "submit-nebius"
  | "refresh-job-status"
  | "collect-cloud-artifacts"
  | "run-serverless-smoke"
  | "render-job-config"
  | "aggregate"
  | "run-investigations"
  | "run-investigation-team"
  | "sync-evidence"
  | "replay-ai-scenario";

const TOURNAMENT_POLL_INTERVAL_MS = 2000;
const TOURNAMENT_POLL_ATTEMPTS = 180;
const CLOUD_JOB_POLL_INTERVAL_MS = 5000;

function wait(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

const experimentScenarioOptions = [
  "normal_market",
  "spoofing_like_wall",
  "layering_like",
  "quote_stuffing",
  "liquidity_evaporation"
];

const initialExperimentForm: ExperimentFormState = {
  attack_count: 100,
  batch_size: 20,
    name: "LOB Arena detector tournament",
  scenarios: ["normal_market", "spoofing_like_wall", "layering_like", "quote_stuffing", "liquidity_evaporation"],
  seed: 42
};

const initialScenarioForm: MarketAbuseScenarioGenerationRequest = {
  difficulty: "medium",
  duration_ticks: 120,
  liquidity_regime: "thin",
  manipulation_type: "spoofing_like_wall",
  seed: 42,
  symbol: "AIMD",
  volatility_regime: "high"
};

const demoScenarios: DemoScenario[] = [
  {
    attackKey: "spoofing_like_wall",
    cta: "Start",
    demonstrates: ["attack generation", "detection", "mock AI investigation", "simulated execution trace"],
    duration: "30 seconds",
    id: "local-lightweight",
    runtime: "local-demo",
    title: "Local Lightweight Demo"
  },
  {
    attackKey: "layering_like",
    demonstrates: ["fast classifier", "reasoning model", "simulated latency", "simulated cost"],
    id: "local-ai-pipeline",
    purpose: "Show AI architecture even offline.",
    runtime: "local-demo",
    title: "Local AI Pipeline Demo"
  },
  {
    attackKey: "quote_stuffing",
    demonstrates: ["real endpoint", "streaming explanation", "latency", "tokens", "cost"],
    id: "nebius-endpoint",
    runtime: "nebius-cloud",
    title: "Endpoint Demo"
  },
  {
    attackKey: "liquidity_evaporation",
    demonstrates: ["complete platform", "endpoint", "jobs", "benchmark", "artifacts", "execution trace"],
    id: "nebius-platform",
    runtime: "nebius-cloud",
    title: "Full Platform Demo"
  }
];

export function NebiusControlPanelPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [arenaIncident] = useState<Incident | null>(() => loadControlCenterIncident(searchParams.get("incidentId")));
  const [runtimeStatus, setRuntimeStatus] = useState<NebiusRuntimeStatus>(fallbackRuntimeStatus);
  const [usageMetrics, setUsageMetrics] = useState<NebiusUsageMetrics>(fallbackUsageMetrics);
  const [experiment, setExperiment] = useState<ManagedExperiment | null>(null);
  const [experimentForm, setExperimentForm] = useState<ExperimentFormState>(initialExperimentForm);
  const [experimentJobs, setExperimentJobs] = useState<ExperimentJobRecord[]>([]);
  const [experimentLeaderboard, setExperimentLeaderboard] = useState<ExperimentLeaderboardRow[]>([]);
  const [experimentInvestigations, setExperimentInvestigations] = useState<InvestigationRecord[]>([]);
  const [experimentSummary, setExperimentSummary] = useState<ExperimentSummary | null>(null);
  const [scenarioForm, setScenarioForm] = useState<MarketAbuseScenarioGenerationRequest>(initialScenarioForm);
  const [generatedScenario, setGeneratedScenario] = useState<MarketAbuseScenarioResponse | null>(null);
  const [scenarioMessage, setScenarioMessage] = useState<string | null>(null);
  const [serverlessSmokeResult, setServerlessSmokeResult] = useState<ServerlessSmokeResponse | null>(null);
  const [investigationTeamReport, setInvestigationTeamReport] = useState<AIInvestigationTeamResponse | null>(null);
  const [experimentMessage, setExperimentMessage] = useState<string | null>(null);
  const [experimentBusyAction, setExperimentBusyAction] = useState<ExperimentAction | null>(null);
  const [nebiusStatus, setNebiusStatus] = useState<NebiusStatus | null>(null);
  const [nebiusObservatory, setNebiusObservatory] = useState<NebiusObservatory | null>(null);
  const [nebiusEvidence, setNebiusEvidence] = useState<NebiusEvidenceRecord[]>([]);
  const [deploymentPanelMessage, setDeploymentPanelMessage] = useState<string | null>(null);
  const [controlPlaneFailed, setControlPlaneFailed] = useState(false);
  const [cloudArtifactCollection, setCloudArtifactCollection] = useState<NebiusArtifactCollectionResponse | null>(null);
  const [runtimeMode, setRuntimeMode] = useState<RuntimeMode>(() => getStoredRuntimeMode());
  const [sessionStartedAt] = useState(() => new Date().toISOString());
  const [showE2ECompletion, setShowE2ECompletion] = useState(false);
  const [activeWorkflowStep, setActiveWorkflowStep] = useState(() => Number(searchParams.get("step")) === 3 ? 3 : 1);
  const experimentId = experiment?.id;
  const activeCloudJob = latestExperimentJob(experimentJobs);
  const activeCloudJobId = activeCloudJob?.job_id;
  const activeCloudJobStatus = activeCloudJob?.status;
  const experimentHasAlerts = Boolean(experiment?.artifact_paths.alerts);

  useEffect(() => {
    void refreshControlPlane();
    void refreshExperimentLab();
    // Initial control-plane hydration only; user-triggered refreshes keep this page current.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!experimentId || !activeCloudJobId || !activeCloudJobStatus || !["queued", "running"].includes(activeCloudJobStatus)) {
      return;
    }
    let refreshInFlight = false;
    const timer = window.setInterval(() => {
      if (refreshInFlight) return;
      refreshInFlight = true;
      void refreshManagedExperimentJobs(experimentId)
        .then(async (refreshed) => {
          setExperimentJobs(refreshed);
          const latest = latestExperimentJob(refreshed);
          if (latest?.status === "completed") {
            const [updatedExperiment, collection] = await Promise.all([
              getManagedExperiment(experimentId),
              collectManagedExperimentNebiusArtifacts(experimentId)
            ]);
            setExperiment(updatedExperiment);
            setCloudArtifactCollection(collection);
            setDeploymentPanelMessage(`Collected ${collection.copied_count} cloud artifacts automatically.`);
          } else if (latest?.status === "failed") {
            setDeploymentPanelMessage(latest.message);
          }
        })
        .catch((error) => {
          setDeploymentPanelMessage(error instanceof Error ? error.message : "Cloud job refresh failed.");
        })
        .finally(() => {
          refreshInFlight = false;
        });
    }, CLOUD_JOB_POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [activeCloudJobId, activeCloudJobStatus, experimentId]);

  useEffect(() => {
    function syncRuntimeMode(event: Event) {
      const next = event instanceof CustomEvent && typeof event.detail === "string"
        ? event.detail
        : getStoredRuntimeMode();
      if (next === "local-demo" || next === "nebius-cloud") {
        setRuntimeMode(next);
      }
    }
    window.addEventListener(RUNTIME_MODE_EVENT, syncRuntimeMode);
    window.addEventListener("storage", syncRuntimeMode);
    return () => {
      window.removeEventListener(RUNTIME_MODE_EVENT, syncRuntimeMode);
      window.removeEventListener("storage", syncRuntimeMode);
    };
  }, []);

  async function refreshControlPlane() {
    try {
      const [status, observatory, reports, evidence] = await Promise.all([
        getNebiusStatus(),
        getNebiusObservatory(),
        getReportsSummary(),
        listNebiusEvidence()
      ]);
      setNebiusStatus(status);
      setNebiusObservatory(observatory);
      setRuntimeStatus(runtimeFrom(status, observatory));
      setUsageMetrics(usageFrom(reports, evidence, sessionStartedAt));
      setNebiusEvidence(evidence);
      setControlPlaneFailed(false);
    } catch (error) {
      setControlPlaneFailed(true);
      setRuntimeStatus({
        ...fallbackRuntimeStatus,
        aiEndpointStatus: "offline",
        cloudStatus: "offline",
        serverlessStatus: "error",
        storageStatus: "error"
      });
      setDeploymentPanelMessage(error instanceof Error ? error.message : "Control plane refresh failed.");
    }
  }

  async function refreshExperimentLab(experimentId?: string) {
    try {
      const targetId = experimentId ?? experiment?.id;
      if (!targetId) {
        const experiments = await listManagedExperiments();
        const latest = latestExperiment(experiments);
        if (!latest) return;
        setExperiment(latest);
        await refreshExperimentDetails(latest.id);
        return;
      }
      await refreshExperimentDetails(targetId);
    } catch (error) {
      setExperimentMessage(error instanceof Error ? error.message : "Benchmark refresh failed.");
    }
  }

  async function syncEvidenceArchive() {
    await runExperimentAction("sync-evidence", async () => {
      const result = await syncNebiusEvidence();
      setNebiusEvidence(await listNebiusEvidence());
      setDeploymentPanelMessage(result.message);
    });
  }

  async function refreshExperimentDetails(experimentId: string) {
    const [latest, jobs] = await Promise.all([
      getManagedExperiment(experimentId),
      listManagedExperimentJobs(experimentId).catch(() => [])
    ]);
    setExperiment(latest);
    setExperimentJobs(jobs);

    const [summary, leaderboard, investigations] = await Promise.all([
      getManagedExperimentSummary(experimentId).catch(() => null),
      getManagedExperimentLeaderboard(experimentId).catch(() => []),
      listManagedExperimentInvestigations(experimentId).catch(() => [])
    ]);
    setExperimentSummary(summary);
    setExperimentLeaderboard(leaderboard);
    setExperimentInvestigations(investigations);
  }

  async function runExperimentAction(action: ExperimentAction, fn: () => Promise<void>, onError?: (message: string) => void) {
    setExperimentBusyAction(action);
    setExperimentMessage(null);
    try {
      await fn();
      await refreshControlPlane();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Benchmark action failed.";
      setExperimentMessage(message);
      onError?.(message);
    } finally {
      setExperimentBusyAction(null);
    }
  }

  function updateExperimentForm<K extends keyof ExperimentFormState>(key: K, value: ExperimentFormState[K]) {
    setExperimentForm((current) => ({
      ...current,
      [key]: value
    }));
  }

  function toggleExperimentScenario(scenario: string) {
    setExperimentForm((current) => {
      const next = current.scenarios.includes(scenario)
        ? current.scenarios.filter((item) => item !== scenario)
        : [...current.scenarios, scenario];
      return {
        ...current,
        scenarios: next.length ? next : [scenario]
      };
    });
  }

  function updateScenarioForm<K extends keyof MarketAbuseScenarioGenerationRequest>(
    key: K,
    value: MarketAbuseScenarioGenerationRequest[K]
  ) {
    setScenarioForm((current) => ({
      ...current,
      [key]: value
    }));
  }

  async function createExperimentFromForm() {
    await runExperimentAction("create-experiment", async () => {
      const created = await createManagedExperiment({
        attack_count: Math.max(1, experimentForm.attack_count),
        batch_size: Math.max(1, experimentForm.batch_size),
        name: experimentForm.name.trim() || "LOB Arena benchmark",
        scenarios: experimentForm.scenarios,
        seed: experimentForm.seed
      });
      setExperiment(created);
      setExperimentJobs([]);
      setExperimentLeaderboard([]);
      setExperimentInvestigations([]);
      setExperimentSummary(null);
      setExperimentMessage(`Created benchmark ${created.id}.`);
      await refreshExperimentDetails(created.id);
    });
  }

  async function generateExperimentManifest() {
    if (!experiment) return;
    await runExperimentAction("generate-manifest", async () => {
      const manifest = await generateManagedExperimentManifest(experiment.id);
      setExperimentMessage(`Generated ${manifest.attack_count} attack rows at ${manifest.path}.`);
      await refreshExperimentDetails(experiment.id);
    });
  }

  async function runExperimentLocalBatch() {
    if (!experiment) return;
    await runExperimentAction("run-local-batch", async () => {
      setExperimentMessage("Running the tournament in an isolated, resource-limited worker. The live Arena remains available and keeps ticking.");
      const batch = await runManagedExperimentLocalBatch(experiment.id);
      setExperimentMessage(`${batch.status === "completed" ? "Completed" : "Failed"} local batch in ${batch.elapsed_seconds.toFixed(1)}s.`);
      await refreshExperimentDetails(experiment.id);
    });
  }

  async function submitExperimentToNebius() {
    if (!experiment) return;
    await runExperimentAction("submit-nebius", async () => {
      const job = await submitManagedExperimentNebius(experiment.id);
      setExperimentMessage(job.status === "real_nebius_pending" ? "pending cloud job execution" : job.message);
      await refreshExperimentDetails(experiment.id);
    });
  }

  async function renderExperimentJobConfig() {
    if (!experiment) return;
    await runExperimentAction("render-job-config", async () => {
      const rendered = await renderManagedExperimentNebiusJobConfig(experiment.id);
      setDeploymentPanelMessage(`Rendered job config: ${rendered.path}`);
      await refreshExperimentDetails(experiment.id);
    });
  }

  async function refreshExperimentJobStatus() {
    if (!experiment) return;
    await runExperimentAction("refresh-job-status", async () => {
      const refreshed = await refreshManagedExperimentJobs(experiment.id);
      setExperimentJobs(refreshed);
      const latest = latestExperimentJob(refreshed);
      const evidencePath = latest?.artifact_paths.cloud_artifact_evidence;
      if (evidencePath) {
        setCloudArtifactCollection((current) => current ?? {
          artifact_dir: experiment.artifact_dir,
          artifact_paths: latest.artifact_paths,
          copied_count: 0,
          evidence_path: evidencePath,
          experiment_id: experiment.id,
          message: "Nebius cloud artifact evidence is available from the latest job refresh.",
          missing: [],
          source_dir: null,
          source_uri: null,
          status: "collected"
        });
      }
      setDeploymentPanelMessage(latest ? `Latest cloud job status: ${latest.status.replaceAll("_", " ")}` : "No job records yet.");
      await refreshExperimentDetails(experiment.id);
    });
  }

  async function collectExperimentCloudArtifacts() {
    if (!experiment) return;
    await runExperimentAction("collect-cloud-artifacts", async () => {
      const result = await collectManagedExperimentNebiusArtifacts(experiment.id);
      setCloudArtifactCollection(result);
      setDeploymentPanelMessage(result.status === "collected" ? `Collected ${result.copied_count} cloud artifacts.` : result.message);
      await refreshExperimentDetails(experiment.id);
    });
  }

  async function aggregateExperimentResults() {
    if (!experiment) return;
    await runExperimentAction("aggregate", async () => {
      const result = await aggregateManagedExperiment(experiment.id);
      setExperimentSummary(result.summary);
      setExperimentLeaderboard(result.leaderboard);
      setExperimentMessage(`Aggregated ${result.summary.total_alerts} alerts into ${result.leaderboard.length} leaderboard rows.`);
      await refreshExperimentDetails(experiment.id);
    });
  }

  async function runExperimentInvestigations() {
    if (!experiment) return;
    await runExperimentAction("run-investigations", async () => {
      const result = await runManagedExperimentInvestigations(experiment.id, runtimeMode);
      setExperimentInvestigations(result.investigations);
      setExperimentMessage(`Produced ${result.investigation_count} AI Investigation summaries in ${result.investigation_mode} mode. Showing Tab 3 · Benchmark alert explanations.`);
      await refreshExperimentDetails(experiment.id);
      setActiveWorkflowStep(3);
      window.requestAnimationFrame(() => {
        window.requestAnimationFrame(() => {
          const results = document.getElementById("benchmark-alert-explanations");
          results?.focus({ preventScroll: true });
          results?.scrollIntoView({ behavior: "smooth", block: "start" });
        });
      });
    });
  }

  async function runInvestigationTeam() {
    await runExperimentAction("run-investigation-team", async () => {
      const report = await runAIInvestigationTeam(
        arenaIncident ? incidentInvestigationRequest(arenaIncident) : undefined,
        runtimeMode
      );
      setInvestigationTeamReport(report);
      setExperimentMessage(`Nebius AI Investigation Team consensus: ${report.consensus}`);
    });
  }

  async function generateAiScenario() {
    await runExperimentAction("generate-ai-scenario", async () => {
      const scenario = await generateMarketAbuseScenario(scenarioForm, runtimeMode);
      setGeneratedScenario(scenario);
      setScenarioMessage(`Generated ${scenario.title} with ${scenario.events.length} simulator-compatible events.`);
    }, setScenarioMessage);
  }

  async function replayGeneratedScenario() {
    if (!generatedScenario) return;
    await runExperimentAction("replay-ai-scenario", async () => {
      await injectNebiusAttackScenario(generatedScenario.scenario_id);
      navigate(`/arena?replayScenario=${encodeURIComponent(generatedScenario.scenario_id)}`);
    }, setScenarioMessage);
  }

  async function runServerlessSmoke() {
    await runExperimentAction("run-serverless-smoke", async () => {
      const result = await runServerlessSmokeDemo(runtimeMode);
      let finalResult = result;
      let tournament = result.cloud_tournament ?? result.tournament;
      setServerlessSmokeResult(finalResult);
      setInvestigationTeamReport(result.investigation ?? null);
      if (result.cloud_tournament && (tournament.status === "queued" || tournament.status === "running")) {
        for (
          let attempt = 0;
          attempt < TOURNAMENT_POLL_ATTEMPTS && tournament.status !== "completed" && tournament.status !== "failed";
          attempt += 1
        ) {
          await wait(TOURNAMENT_POLL_INTERVAL_MS);
          tournament = await refreshDetectorTournament(tournament.tournament_id);
          finalResult = mergeSmokeCloudTournament(result, tournament);
          setServerlessSmokeResult(finalResult);
        }
      }
      if (result.cloud_tournament) {
        if (tournament.status !== "completed" && tournament.status !== "failed") {
          throw new Error("Nebius Serverless Job did not finish before the polling timeout.");
        }
        const finalized = await finalizeServerlessSmokeDemo(result.experiment_id, tournament.tournament_id);
        finalResult = {
          ...finalResult,
          evidence_id: finalized.evidence.evidence_id,
          evidence_s3_status: finalized.evidence.s3_status,
          evidence_source_uri: finalized.evidence.source_uri,
          usage: finalized.usage
        };
        setServerlessSmokeResult(finalResult);
      }
      setUsageMetrics(usageFromSmoke(finalResult, sessionStartedAt));
      await refreshExperimentDetails(result.experiment_id);
      setExperimentMessage(`Polished E2E demo saved as experiment ${result.experiment_id}.`);
      setShowE2ECompletion(true);
    }, setDeploymentPanelMessage);
  }

  function switchRuntimeMode(nextMode: RuntimeMode) {
    storeRuntimeMode(nextMode);
    setRuntimeMode(nextMode);
  }

  function startDemoScenario(scenario: DemoScenario) {
    switchRuntimeMode(scenario.runtime);
    const params = new URLSearchParams({
      attack: scenario.attackKey,
      demoScenario: scenario.id,
      runtime: scenario.runtime
    });
    navigate(`/attack-scenarios?${params.toString()}`);
  }

  const runtimeLabel = visibleRuntimeOptions.find((option) => option.value === runtimeMode)?.label ?? "Local Demo";
  const endpointConfigured = Boolean(
    nebiusStatus?.incident_explainer_configured
    || nebiusStatus?.scenario_generator_configured
    || nebiusStatus?.orderbook_alert_configured
    || nebiusStatus?.investigation_report_configured
    || nebiusStatus?.investigation_team_configured
    || nebiusStatus?.market_abuse_scenario_configured
  );
  const jobConfigured = Boolean(nebiusStatus?.job_submit_template_configured);
  const endpointHealthStatus = probeStatus(nebiusStatus?.endpoint_health);
  const jobHealthStatus = probeStatus(nebiusStatus?.job_health);
  const storageHealthStatus = probeStatus(nebiusStatus?.storage_health);
  const endpointHealthy = probeSucceeded(nebiusStatus?.endpoint_health);
  const jobHealthy = probeSucceeded(nebiusStatus?.job_health);
  const storageHealthy = probeSucceeded(nebiusStatus?.storage_health);
  const endpointWillUseNebius = runtimeMode !== "local-demo" && endpointConfigured && endpointHealthy;
  const jobWillUseNebius = runtimeMode !== "local-demo" && jobConfigured && jobHealthy;
  const fallbackStatus = endpointWillUseNebius || jobWillUseNebius ? "cloud path available" : runtimeMode === "local-demo" ? "Simulated / Local Demo" : "fallback to deterministic mock";
  const scenarioEndpointConfigured = Boolean(nebiusStatus?.market_abuse_scenario_configured || nebiusStatus?.scenario_generator_configured);
  const investigationEndpointConfigured = Boolean(nebiusStatus?.investigation_team_configured || nebiusStatus?.incident_explainer_configured);
  const investigationWillUseNebius = runtimeMode !== "local-demo" && investigationEndpointConfigured && endpointHealthy;
  const workflowSteps = [
    "Runtime",
    "Scenario Generator",
    "Investigation Team",
    "Detector Tournament",
    "Execution Trace"
  ];
  const controlPlaneReady = Boolean(nebiusStatus) && !controlPlaneFailed;
  const investigationInputReady = Boolean(arenaIncident || generatedScenario || experimentHasAlerts || serverlessSmokeResult);
  const executionResultsReady = Boolean(
    serverlessSmokeResult
    || experimentSummary
    || experimentJobs.length
    || (experiment && Object.keys(experiment.artifact_paths).length)
    || nebiusEvidence.some((record) => Date.parse(record.created_at) >= Date.parse(sessionStartedAt))
  );
  const workflowStepReady = [true, controlPlaneReady, controlPlaneReady && investigationInputReady, controlPlaneReady, controlPlaneReady && executionResultsReady];
  const activeWorkflowTitle = workflowSteps[activeWorkflowStep - 1] ?? workflowSteps[0];
  const goToPreviousWorkflowStep = () => setActiveWorkflowStep((step) => Math.max(1, step - 1));
  const goToNextWorkflowStep = () => setActiveWorkflowStep((step) => Math.min(workflowSteps.length, step + 1));

  return (
    <section className="nebius-control-page">
      <section className="command-center-service-grid" aria-label="AI command center capabilities">
        <CommandCenterServiceCard
          title="Serverless Endpoint"
          detail={nebiusStatus?.endpoint_base_url || "No endpoint base URL configured"}
          status={serviceProbeLabel(nebiusStatus, endpointHealthStatus, controlPlaneFailed)}
        />
        <CommandCenterServiceCard
          title="Investigation Team"
          detail={investigationEndpointConfigured ? nebiusStatus?.model || "Configured route" : "Investigation route not configured"}
          status={routeProbeLabel(nebiusStatus, investigationEndpointConfigured, endpointHealthy, controlPlaneFailed)}
        />
        <CommandCenterServiceCard
          title="Scenario Generator"
          detail={scenarioEndpointConfigured ? "Scenario route configured" : "Scenario route not configured"}
          status={routeProbeLabel(nebiusStatus, scenarioEndpointConfigured, endpointHealthy, controlPlaneFailed)}
        />
        <CommandCenterServiceCard
          title="Serverless Jobs"
          detail={jobConfigured ? nebiusStatus?.job_image || "Job image configured" : "Job submit template missing"}
          status={serviceProbeLabel(nebiusStatus, jobHealthStatus, controlPlaneFailed)}
        />
        <CommandCenterServiceCard
          title="Detector Tournament"
          detail={experiment ? `${experiment.attack_count} workloads · batch ${experiment.batch_size}` : "Create a detector tournament"}
          status={experiment ? experiment.status.replaceAll("_", " ") : "pending"}
        />
      </section>

      <ServerlessSmokeDemoPanel
        available={runtimeMode === "local-demo"
          ? controlPlaneReady
          : jobHealthy && endpointHealthy && scenarioEndpointConfigured && investigationEndpointConfigured}
        busy={experimentBusyAction !== null}
        result={serverlessSmokeResult}
        runtimeMode={runtimeMode}
        onRun={() => void runServerlessSmoke()}
      />

      <section className="command-center-wizard" aria-label="Command Center workflow">
        <div className="command-center-wizard-header">
          <button
            aria-label="Previous workflow step"
            className="secondary-button wizard-arrow-button"
            disabled={activeWorkflowStep === 1}
            onClick={goToPreviousWorkflowStep}
            type="button"
          >
            &lt;&lt;
          </button>
          <div>
            <span>Step {activeWorkflowStep} of {workflowSteps.length}</span>
            <strong>{activeWorkflowTitle}</strong>
          </div>
          <button
            aria-label="Next workflow step"
            className="secondary-button wizard-arrow-button"
            disabled={activeWorkflowStep === workflowSteps.length || !workflowStepReady[activeWorkflowStep]}
            onClick={goToNextWorkflowStep}
            type="button"
          >
            &gt;&gt;
          </button>
        </div>
        <div className="command-center-step-tabs" role="tablist" aria-label="Command Center steps">
          {workflowSteps.map((label, index) => {
            const step = index + 1;
            return (
              <button
                aria-selected={step === activeWorkflowStep}
                className={step === activeWorkflowStep ? "active" : ""}
                disabled={!workflowStepReady[index]}
                key={label}
                onClick={() => setActiveWorkflowStep(step)}
                role="tab"
                title={workflowStepReady[index] ? undefined : workflowStepLockedReason(step)}
                type="button"
              >
                <span>{step}</span>
                {label}
              </button>
            );
          })}
        </div>
      </section>

      <section className="nebius-infra-workflow">
        {activeWorkflowStep === 1 ? <InfrastructureSection
          step={1}
          title="Runtime"
          description="Current local demo, endpoint, job, artifact, and fallback status for the command-center workflow."
        >
          <RuntimeStatusCard status={runtimeStatus} />
          <InfrastructureMetricGrid>
            <MetricBlock label="Current mode" value={runtimeLabel} />
            <MetricBlock label="Endpoint" value={endpointWillUseNebius ? "connected" : runtimeMode === "local-demo" ? "Local Mock ready" : endpointHealthStatus.replaceAll("_", " ")} />
            <MetricBlock label="Jobs" value={jobWillUseNebius ? "connected" : runtimeMode === "local-demo" ? "Local Mock ready" : jobHealthStatus.replaceAll("_", " ")} />
            <MetricBlock label="Storage" value={storageHealthy ? "connected" : storageHealthStatus.replaceAll("_", " ")} />
            <MetricBlock label="Last checked" value={nebiusStatus?.checked_at ?? "checking"} />
          </InfrastructureMetricGrid>
          <RealNebiusDeploymentPanel
            busyAction={experimentBusyAction}
            experiment={experiment}
            jobs={experimentJobs}
            message={deploymentPanelMessage}
            observatory={nebiusObservatory}
            cloudArtifactCollection={cloudArtifactCollection}
            onCollectArtifacts={() => void collectExperimentCloudArtifacts()}
            onRefreshJobStatus={() => void refreshExperimentJobStatus()}
            onRenderJobConfig={() => void renderExperimentJobConfig()}
            onSubmitNebius={() => void submitExperimentToNebius()}
            runtimeMode={runtimeMode}
            status={nebiusStatus}
          />
        </InfrastructureSection> : null}

        {activeWorkflowStep === 2 ? <InfrastructureSection
          step={2}
          title="Scenario Generator"
          description="Generate synthetic market-abuse workloads with ground truth, then replay them through the existing Arena scenario path."
        >
          <DemoScenariosSection
            endpointAvailable={endpointHealthy}
            jobAvailable={jobHealthy}
            onStart={startDemoScenario}
          />
          <AIScenarioGeneratorPanel
            busyAction={experimentBusyAction}
            form={scenarioForm}
            generatedScenario={generatedScenario}
            message={scenarioMessage}
            onGenerate={() => void generateAiScenario()}
            onReplay={() => void replayGeneratedScenario()}
            onUpdate={updateScenarioForm}
            controlsDisabled={experimentBusyAction !== null}
            endpointAvailable={runtimeMode === "local-demo" || (scenarioEndpointConfigured && endpointHealthy)}
            endpointStatus={runtimeMode === "local-demo" ? "local mock" : routeProbeLabel(nebiusStatus, scenarioEndpointConfigured, endpointHealthy, controlPlaneFailed)}
          />
        </InfrastructureSection> : null}

        {activeWorkflowStep === 3 ? <InfrastructureSection
          step={3}
          title="Investigation Team"
          description="Send detector incidents for explanation, report generation, and analyst-ready findings."
        >
          {arenaIncident ? (
            <article className="control-center-incident">
              <span>Selected Arena incident</span>
              <strong>{arenaIncident.title}</strong>
              <p>{arenaIncident.id} · {arenaIncident.severity} · {Math.round(arenaIncident.confidence * 100)}% confidence</p>
            </article>
          ) : null}
          <InfrastructureMetricGrid>
            <MetricBlock label="Session endpoint calls" value={String(usageMetrics.aiEndpointCallsSession)} />
            <MetricBlock label="Average latency" value={`${usageMetrics.averageLlmLatencySec.toFixed(2)}s`} />
            <MetricBlock label="Current incident explanation" value={investigationWillUseNebius ? "real endpoint used" : "mock fallback"} />
            <MetricBlock label="Model name" value={nebiusStatus?.model || "mock deterministic model"} />
            <MetricBlock label="Fallback status" value={investigationWillUseNebius ? "real endpoint used" : fallbackStatus} />
            <MetricBlock label="Report reasoning" value={runtimeMode !== "local-demo" && endpointHealthy && nebiusStatus?.investigation_report_configured ? "real endpoint used" : "mock fallback"} />
          </InfrastructureMetricGrid>
          <p className="fallback-note">{runtimeMode === "nebius-cloud" ? "Cloud mode calls a real endpoint when configured. If it fails, the response falls back to deterministic mock AI and is labeled clearly." : "Local Demo uses a deterministic mock response. Switch to Cloud to run this explanation on a real endpoint."}</p>
          <div className="nebius-button-row">
            <button className="primary-button" disabled={Boolean(experimentBusyAction) || (runtimeMode === "nebius-cloud" && (!investigationEndpointConfigured || !endpointHealthy))} onClick={() => void runInvestigationTeam()} type="button">
              {experimentBusyAction === "run-investigation-team" ? "Running..." : arenaIncident ? "Investigate selected Arena incident" : "Run Nebius AI Investigation Team"}
            </button>
            <button className="secondary-button" disabled={Boolean(experimentBusyAction) || !experimentHasAlerts} onClick={() => void runExperimentInvestigations()} title={experimentHasAlerts ? undefined : "Available after detector alerts are collected and normalized."} type="button">Explain benchmark alerts</button>
          </div>
          {investigationTeamReport ? <InvestigationTeamReport report={investigationTeamReport} /> : null}
          {experimentMessage ? <p className="experiment-message">{experimentMessage}</p> : null}
          <ExperimentInvestigationResults investigations={experimentInvestigations} />
        </InfrastructureSection> : null}

        {activeWorkflowStep === 4 ? <InfrastructureSection
          step={4}
          title="Detector Tournament"
          description="Run local or serverless detector tournaments over generated market workloads and compare detector outcomes."
        >
          <ExperimentLab
            busyAction={experimentBusyAction}
            experiment={experiment}
            form={experimentForm}
            jobConfigured={jobConfigured && jobHealthy}
            jobs={experimentJobs}
            leaderboard={experimentLeaderboard}
            message={experimentMessage}
            onAggregate={() => void aggregateExperimentResults()}
            onCreate={() => void createExperimentFromForm()}
            onGenerateManifest={() => void generateExperimentManifest()}
            onRefresh={() => void refreshExperimentLab()}
            onRunInvestigations={() => void runExperimentInvestigations()}
            onRunLocalBatch={() => void runExperimentLocalBatch()}
            onSubmitNebius={() => void submitExperimentToNebius()}
            onToggleScenario={toggleExperimentScenario}
            onUpdateForm={updateExperimentForm}
            runtimeMode={runtimeMode}
            summary={experimentSummary}
          />
        </InfrastructureSection> : null}

        {activeWorkflowStep === 5 ? <InfrastructureSection
          step={5}
          title="Execution Trace"
          description="Compact execution graph plus endpoint, jobs, latency, tokens, cost, artifacts, and real versus simulated status."
        >
          <ExecutionGraph endpointActive={endpointWillUseNebius} jobActive={jobWillUseNebius} runtimeMode={runtimeMode} />
          <p className="fallback-note">No credentials or deployment are required in Local Demo. Benchmark results use deterministic mock data until Cloud mode is selected.</p>
          <UsageCostMonitor metrics={usageMetrics} />
          <div className="nebius-button-row">
            <button
              className="secondary-button"
              disabled={!storageHealthy || experimentBusyAction === "sync-evidence"}
              title={storageHealthy ? undefined : `Object Storage is ${storageHealthStatus.replaceAll("_", " ")}.`}
              onClick={() => void syncEvidenceArchive()}
              type="button"
            >
              {experimentBusyAction === "sync-evidence" ? "Syncing evidence..." : "Sync evidence from S3"}
            </button>
            <span className="fallback-note">{nebiusEvidence.length} endpoint and Job evidence records</span>
          </div>
          <ExperimentArtifactBrowser
            artifacts={mergeArtifactLinks(
              evidenceArtifactsFrom(nebiusEvidence),
              experiment ? experimentArtifactsFrom(experiment, experimentSummary) : []
            )}
            experimentId={experiment?.id}
          />
        </InfrastructureSection> : null}
      </section>

      {showE2ECompletion && serverlessSmokeResult ? (
        <E2ECompletionDialog
          onClose={() => setShowE2ECompletion(false)}
          onViewExperiment={() => {
            setShowE2ECompletion(false);
            setActiveWorkflowStep(4);
          }}
          onViewTrace={() => {
            setShowE2ECompletion(false);
            setActiveWorkflowStep(5);
          }}
          result={serverlessSmokeResult}
        />
      ) : null}

    </section>
  );
}

function CommandCenterServiceCard({
  detail,
  status,
  title
}: {
  detail: string;
  status: string;
  title: string;
}) {
  return (
    <article className="command-center-service-card">
      <div>
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
      <span className={`runtime-status ${status.toLowerCase().replace(/\s+/g, "-")}`}>{status}</span>
    </article>
  );
}

function ServerlessSmokeDemoPanel({
  available,
  busy,
  onRun,
  result,
  runtimeMode
}: {
  available: boolean;
  busy: boolean;
  onRun: () => void;
  result: ServerlessSmokeResponse | null;
  runtimeMode: RuntimeMode;
}) {
  const jobStatus = String(result?.serverless_job.status ?? "not run");
  const jobId = result?.serverless_job.job_id ? String(result.serverless_job.job_id) : "pending";
  const cloudOutputUri = result?.serverless_job.cloud_output_uri ? String(result.serverless_job.cloud_output_uri) : "not configured";
  return (
    <section className="panel serverless-smoke-panel" aria-label="Nebius Serverless E2E demo">
      <div className="nebius-card-heading">
        <div>
          <span>Polished E2E demo</span>
          <h2>Nebius Serverless Spoofing Incident</h2>
          <p className="nebius-card-purpose">
            AI-generated spoofing incident {"->"} LOB simulation {"->"} detector alert {"->"} LLM explanation {"->"} investigation report {"->"} detector tournament {"->"} artifacts.
          </p>
        </div>
        <span className={`runtime-status ${result?.mode ?? (available ? "available" : "unavailable")}`}>{result?.mode.replaceAll("_", " ") ?? (available ? "available" : "unavailable")}</span>
      </div>
      <div className="nebius-button-row">
        <button className="primary-button" disabled={!available || busy} onClick={onRun} title={available ? undefined : runtimeMode === "local-demo" ? "Backend control plane is not ready." : "Requires successful live Endpoint and Serverless Jobs probes plus configured scenario and investigation routes."} type="button">
          {busy ? "Running E2E demo..." : "Run Serverless E2E Demo"}
        </button>
        {result ? <span className="fallback-note">Saved as experiment {result.experiment_id} · evidence {result.evidence_s3_status.replaceAll("_", " ")}</span> : null}
      </div>
      {result ? (
        <>
          <InfrastructureMetricGrid>
            <MetricBlock label="Current mode" value={result.mode.replaceAll("_", " ")} />
            <MetricBlock label="Scenario" value={result.scenario_id} />
            <MetricBlock label="Incident" value={result.incident_id ?? "not created"} />
            <MetricBlock label="Detector alerts" value={String(result.detector_alerts.length)} />
            <MetricBlock label="Job status" value={jobStatus.replaceAll("_", " ")} />
            <MetricBlock label="Job id" value={jobId} />
            <MetricBlock label="Cloud artifacts" value={cloudOutputUri} />
            <MetricBlock label="Experiment" value={result.experiment_id} />
            <MetricBlock label="Duration" value={`${result.usage.duration_seconds.toFixed(2)}s`} />
            <MetricBlock label="Estimated cost" value={`$${result.usage.estimated_cost_usd.toFixed(6)}`} />
          </InfrastructureMetricGrid>
          <div className="experiment-output-grid">
            <div className="nebius-result-block">
              <span>Incident explanation</span>
              <p>{result.explanation?.plain_english_summary ?? "No incident explanation available."}</p>
              {result.explanation?.evidence?.length ? (
                <ul>
                  {result.explanation.evidence.slice(0, 4).map((item) => <li key={item}>{item}</li>)}
                </ul>
              ) : null}
            </div>
            <div className="nebius-result-block">
              <span>Detector evidence</span>
              <ul>
                {result.detector_alerts.slice(0, 5).map((alert, index) => (
                  <li key={`${String(alert.name ?? alert.detector ?? "detector")}-${index}`}>
                    {String(alert.name ?? alert.detector ?? "detector")}: {String(alert.confidence ?? alert.suspicion_score ?? "n/a")}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="experiment-output-grid">
            <div className="nebius-result-block">
              <span>Tournament leaderboard</span>
              <table className="leaderboard-table">
                <thead>
                  <tr>
                    <th>Detector</th>
                    <th>Scenario</th>
                    <th>F1</th>
                    <th>FP</th>
                    <th>FN</th>
                  </tr>
                </thead>
                <tbody>
                  {result.tournament.leaderboard.slice(0, 8).map((row) => (
                    <tr key={`${row.detector}-${row.scenario}`}>
                      <td>{row.detector}</td>
                      <td>{row.scenario}</td>
                      <td>{formatScore(row.f1)}</td>
                      <td>{row.false_positives}</td>
                      <td>{row.false_negatives}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="nebius-result-block">
              <span>Artifacts</span>
              <div className="artifact-link-list">
                {result.artifacts.map((artifact) => (
                  <a href={artifactDownloadUrl(artifact.path)} key={artifact.name}>
                    {artifact.name}
                  </a>
                ))}
              </div>
              <span>Serverless benefits</span>
              <ul>
                {result.benefits.map((benefit) => <li key={benefit}>{benefit}</li>)}
              </ul>
            </div>
          </div>
          {result.investigation ? <InvestigationTeamReport report={result.investigation} /> : null}
          {String(result.serverless_job.message ?? "") ? <p className="fallback-note">{String(result.serverless_job.message)}</p> : null}
        </>
      ) : null}
    </section>
  );
}

function E2ECompletionDialog({
  onClose,
  onViewExperiment,
  onViewTrace,
  result
}: {
  onClose: () => void;
  onViewExperiment: () => void;
  onViewTrace: () => void;
  result: ServerlessSmokeResponse;
}) {
  const tournament = result.cloud_tournament ?? result.tournament;
  const best = [...tournament.leaderboard]
    .filter((row) => typeof row.f1 === "number")
    .sort((left, right) => (right.f1 ?? 0) - (left.f1 ?? 0))[0];
  return (
    <div className="e2e-completion-backdrop" role="presentation">
      <section aria-labelledby="e2e-completion-title" aria-modal="true" className="e2e-completion-dialog" role="dialog">
        <div className="nebius-card-heading">
          <div>
            <span>Polished E2E demo complete</span>
            <h2 id="e2e-completion-title">{result.summary}</h2>
            <p className="nebius-card-purpose">Results are saved in the backend experiment grid and the evidence bundle is {result.evidence_s3_status.replaceAll("_", " ")}.</p>
          </div>
          <button aria-label="Close completion summary" className="secondary-button" onClick={onClose} type="button">Close</button>
        </div>
        <InfrastructureMetricGrid>
          <MetricBlock label="Experiment" value={result.experiment_id} />
          <MetricBlock label="Mode" value={result.mode.replaceAll("_", " ")} />
          <MetricBlock label="Incident" value={result.incident_id ?? "not created"} />
          <MetricBlock label="Detector alerts" value={String(result.detector_alerts.length)} />
          <MetricBlock label="Best F1" value={best?.f1 == null ? "n/a" : `${best.detector} · ${best.f1.toFixed(3)}`} />
          <MetricBlock label="Endpoint calls" value={String(result.usage.endpoint_calls)} />
          <MetricBlock label="Tokens" value={result.usage.total_tokens.toLocaleString()} />
          <MetricBlock label="Duration" value={`${result.usage.duration_seconds.toFixed(2)}s`} />
          <MetricBlock label="Artifacts" value={`${result.usage.artifact_count} · ${(result.usage.artifact_bytes / 1_048_576).toFixed(3)} MB`} />
          <MetricBlock label="Estimated cost" value={`$${result.usage.estimated_cost_usd.toFixed(6)}`} />
        </InfrastructureMetricGrid>
        <p className="fallback-note">{result.usage.cost_basis}</p>
        <div className="nebius-button-row">
          <button className="primary-button" onClick={onViewExperiment} type="button">View experiment</button>
          <button className="secondary-button" onClick={onViewTrace} type="button">View execution trace</button>
        </div>
      </section>
    </div>
  );
}

function InvestigationTeamReport({ report }: { report: AIInvestigationTeamResponse }) {
  return (
    <section className="nebius-result-block investigation-team-report" aria-label="AI Investigation Team result">
      <div className="nebius-card-heading">
        <div>
          <span>Final verdict</span>
          <h2>{report.manipulation_type.replaceAll("_", " ")}</h2>
          <p className="nebius-card-purpose">{report.executive_summary}</p>
        </div>
        <span className={`runtime-status ${report.mode}`}>{report.mode}</span>
      </div>
      <InfrastructureMetricGrid>
        <MetricBlock label="Investigation" value={report.investigation_id} />
        <MetricBlock label="Risk score" value={report.risk_score.toFixed(2)} />
        <MetricBlock label="Confidence" value={report.confidence.toFixed(2)} />
        <MetricBlock label="Consensus" value={report.consensus} />
      </InfrastructureMetricGrid>
      <div className="experiment-output-grid">
        <div className="nebius-result-block">
          <span>Agent findings</span>
          <div className="generated-scenario-list">
            {report.agents.map((agent) => (
              <article className="generated-scenario-card" key={agent.name}>
                <strong>{agent.name}</strong>
                <p>{agent.role}</p>
                <p>{agent.finding}</p>
                <span className="runtime-status configured">{agent.confidence.toFixed(2)}</span>
                <ul>
                  {agent.evidence.map((item) => (
                    <li key={`${agent.name}-${item.key}-${String(item.value)}`}>
                      {item.label}: {String(item.value)}
                    </li>
                  ))}
                </ul>
              </article>
            ))}
          </div>
        </div>
        <div className="nebius-result-block">
          <span>Evidence timeline</span>
          <ol>
            {report.evidence_timeline.map((item) => (
              <li key={`${item.sequence}-${item.event}`}>
                {item.event}
              </li>
            ))}
          </ol>
          <p><strong>Recommended action</strong> {report.recommended_action}</p>
          {report.fallback_reason ? <p className="fallback-note">{report.fallback_reason}</p> : null}
        </div>
      </div>
    </section>
  );
}

function AIScenarioGeneratorPanel({
  busyAction,
  controlsDisabled,
  endpointAvailable,
  endpointStatus,
  form,
  generatedScenario,
  message,
  onGenerate,
  onReplay,
  onUpdate
}: {
  busyAction: ExperimentAction | null;
  controlsDisabled: boolean;
  endpointAvailable: boolean;
  endpointStatus: string;
  form: MarketAbuseScenarioGenerationRequest;
  generatedScenario: MarketAbuseScenarioResponse | null;
  message: string | null;
  onGenerate: () => void;
  onReplay: () => void;
  onUpdate: <K extends keyof MarketAbuseScenarioGenerationRequest>(
    key: K,
    value: MarketAbuseScenarioGenerationRequest[K]
  ) => void;
}) {
  const replaySupported = Boolean(generatedScenario?.replay?.supported ?? generatedScenario);
  return (
    <div className="experiment-output-grid ai-scenario-generator-panel">
      <div className="nebius-result-block">
        <div className="ai-scenario-panel-heading">
          <div>
            <h3>Nebius AI Scenario Generator</h3>
            <p>Configure a bounded synthetic workload, generate it with the active endpoint, then replay it in Arena.</p>
          </div>
          <span className={`runtime-status ${endpointStatus.replaceAll(" ", "-")}`}>{endpointStatus}</span>
        </div>
        <div className="experiment-form-grid">
          <label>
            Manipulation type
            <select
              disabled={controlsDisabled}
              value={form.manipulation_type}
              onChange={(event) => onUpdate("manipulation_type", event.target.value as MarketAbuseScenarioGenerationRequest["manipulation_type"])}
            >
              {arenaScenarioTypes.map((scenario) => (
                <option key={scenario} value={scenario}>{arenaScenarioLabels[scenario]}</option>
              ))}
            </select>
          </label>
          <label>
            Difficulty
            <select
              disabled={controlsDisabled}
              value={form.difficulty}
              onChange={(event) => onUpdate("difficulty", event.target.value as MarketAbuseScenarioGenerationRequest["difficulty"])}
            >
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
              <option value="adversarial">Adversarial</option>
            </select>
          </label>
          <label>
            Symbol
            <input
              disabled={controlsDisabled}
              maxLength={16}
              value={form.symbol}
              onChange={(event) => onUpdate("symbol", event.target.value.toUpperCase())}
            />
          </label>
          <label>
            Duration (ticks)
            <input
              disabled={controlsDisabled}
              max={600}
              min={30}
              type="number"
              value={form.duration_ticks}
              onChange={(event) => onUpdate("duration_ticks", Number(event.target.value))}
            />
          </label>
          <label>
            Liquidity
            <select
              disabled={controlsDisabled}
              value={form.liquidity_regime}
              onChange={(event) => onUpdate("liquidity_regime", event.target.value as MarketAbuseScenarioGenerationRequest["liquidity_regime"])}
            >
              <option value="thin">Thin</option>
              <option value="normal">Normal</option>
              <option value="deep">Deep</option>
            </select>
          </label>
          <label>
            Volatility
            <select
              disabled={controlsDisabled}
              value={form.volatility_regime}
              onChange={(event) => onUpdate("volatility_regime", event.target.value as MarketAbuseScenarioGenerationRequest["volatility_regime"])}
            >
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </label>
          <label>
            Fixed seed
            <input
              disabled={controlsDisabled}
              onChange={(event) => onUpdate("seed", Number(event.target.value))}
              type="number"
              value={form.seed ?? 42}
            />
          </label>
        </div>
        <div className="nebius-button-row">
          <button className="primary-button" disabled={controlsDisabled || !endpointAvailable} onClick={onGenerate} title={endpointAvailable ? undefined : "The configured scenario route did not pass the live Endpoint probe."} type="button">
            {busyAction === "generate-ai-scenario" ? "Generating..." : "Generate AI Scenario"}
          </button>
          <button className="secondary-button" disabled={controlsDisabled || !generatedScenario || !replaySupported} onClick={onReplay} type="button">
            {busyAction === "replay-ai-scenario" ? "Replaying..." : "Replay in Arena"}
          </button>
        </div>
        {message ? <p className="experiment-message">{message}</p> : null}
      </div>

      <div className="nebius-result-block">
        <div className="ai-scenario-panel-heading">
          <div>
            <h3>Generated scenario preview</h3>
            <p>Ground truth and simulator events remain deterministic; AI provides bounded scenario explanation.</p>
          </div>
        </div>
        {generatedScenario ? (
          <div className="generated-scenario-card">
            <div className="nebius-card-heading">
              <div>
                <h3>{generatedScenario.title}</h3>
                <p className="nebius-card-purpose">{generatedScenario.description}</p>
              </div>
              <span className={`runtime-status ${generatedScenario.mode}`}>{generatedScenario.mode}</span>
            </div>
            <InfrastructureMetricGrid>
              <MetricBlock label="Scenario" value={generatedScenario.scenario_id} />
              <MetricBlock label="Risk" value={generatedScenario.expected_detector_behavior.expected_risk_score.toFixed(2)} />
              <MetricBlock label="Events" value={String(generatedScenario.events.length)} />
              <MetricBlock label="Replay route" value={String(generatedScenario.replay.route ?? "projection")} />
            </InfrastructureMetricGrid>
            <div>
              <strong>Ground truth</strong>
              <ul>
                <li>Label: {generatedScenario.ground_truth.label.replaceAll("_", " ")}</li>
                <li>Agents: {generatedScenario.ground_truth.manipulator_agent_ids.join(", ")}</li>
                <li>Signals: {generatedScenario.ground_truth.expected_detector_targets.join(", ")}</li>
              </ul>
            </div>
            <div>
              <strong>Timeline</strong>
              <ol>
                {generatedScenario.events.slice(0, 4).map((event) => (
                  <li key={event.event_id}>
                    tick {event.tick}: {event.message}
                  </li>
                ))}
              </ol>
            </div>
            {generatedScenario.fallback_reason ? <p className="fallback-note">{generatedScenario.fallback_reason}</p> : null}
          </div>
        ) : (
          <p className="fallback-note">Generate a scenario to preview ground truth, event timeline, and replay projection.</p>
        )}
      </div>
    </div>
  );
}

function DemoScenariosSection({
  endpointAvailable,
  jobAvailable,
  onStart
}: {
  endpointAvailable: boolean;
  jobAvailable: boolean;
  onStart: (scenario: DemoScenario) => void;
}) {
  return (
    <details className="demo-scenarios-section">
      <summary>
        <span>Demo Scenarios</span>
        <strong>Choose a guided path through Scenario Setup {"->"} Workload Generator {"->"} AI Investigation.</strong>
      </summary>
      <div className="demo-scenario-grid">
        {demoScenarios.map((scenario) => {
          const available = scenario.runtime === "local-demo"
            || (endpointAvailable && (scenario.id !== "nebius-platform" || jobAvailable));
          return (
            <article className="demo-scenario-card" key={scenario.id}>
              <div className="nebius-card-heading">
                <div>
                  <h3>{scenario.title}</h3>
                  <p className="nebius-card-purpose">Runtime: {scenario.runtime === "local-demo" ? "Local Demo" : "Cloud"}</p>
                </div>
              </div>
              <div>
                <span>Demonstrates</span>
                <ul>
                  {scenario.demonstrates.map((item) => <li key={item}>{item}</li>)}
                </ul>
              </div>
              {scenario.duration ? <p><strong>Duration</strong> {scenario.duration}</p> : null}
              {scenario.purpose ? <p><strong>Purpose</strong> {scenario.purpose}</p> : null}
              <button className="primary-button" disabled={!available} onClick={() => onStart(scenario)} title={available ? undefined : "Required Nebius services did not pass their live probes."} type="button">{scenario.cta ?? "Start"}</button>
            </article>
          );
        })}
      </div>
    </details>
  );
}

function InfrastructureSection({
  children,
  description,
  step,
  title
}: {
  children: ReactNode;
  description: string;
  step: number;
  title: string;
}) {
  return (
    <section className="panel nebius-infra-section">
      <div className="nebius-card-heading">
        <div>
          <div className="workflow-step-heading">
            <span>{step}</span>
            <h2>{title}</h2>
          </div>
          <p className="nebius-card-purpose">{description}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function InfrastructureMetricGrid({ children }: { children: ReactNode }) {
  return <div className="nebius-infra-metric-grid">{children}</div>;
}

function ExecutionGraph({
  endpointActive,
  jobActive,
  runtimeMode
}: {
  endpointActive: boolean;
  jobActive: boolean;
  runtimeMode: RuntimeMode;
}) {
  const endpointStatus = endpointActive ? "real endpoint" : runtimeMode === "nebius-cloud" ? "endpoint unavailable" : "mock endpoint";
  const jobStatus = jobActive ? "cloud job" : runtimeMode === "nebius-cloud" ? "cloud job not configured" : "mock job";
  const resultsStatus = endpointActive || jobActive ? "real results" : "deterministic results";
  const steps = [
    ["Scenario", "ready"],
    ["Detector", "ready"],
    ["Endpoint", endpointStatus],
    ["Job", jobStatus],
    ["Result", resultsStatus]
  ];
  return (
    <ol className="execution-graph" aria-label="Execution graph">
      {steps.map(([label, status]) => (
        <li key={label}>
          <span>{label}</span>
          <strong>{status}</strong>
        </li>
      ))}
    </ol>
  );
}

function runtimeFrom(status: NebiusStatus, observatory: NebiusObservatory): NebiusRuntimeStatus {
  const latest = observatory.latest_batch;
  const endpointHealthy = probeSucceeded(status.endpoint_health);
  const jobsHealthy = probeSucceeded(status.job_health);
  const storageHealthy = probeSucceeded(status.storage_health);
  const configuredProbeCount = [status.endpoint_health, status.job_health, status.storage_health]
    .filter((probe) => probeStatus(probe) !== "not_configured").length;
  const healthyProbeCount = [endpointHealthy, jobsHealthy, storageHealthy].filter(Boolean).length;
  const runs = latest ? Number(latest.runs ?? 0) : 0;
  return {
    activeSimulation: latest ? String(latest.id ?? latest.scenarios ?? "Recorded batch") : "No execution recorded",
    aiEndpointStatus: endpointHealthy ? "ready" : probeStatus(status.endpoint_health) === "not_configured" ? "not-configured" : "offline",
    cloudStatus: healthyProbeCount === 3 ? "online" : healthyProbeCount > 0 ? "degraded" : configuredProbeCount ? "offline" : "offline",
    eventsPerSecond: latest ? Number(latest.events_per_second ?? 0) : 0,
    mode: healthyProbeCount > 0 ? "nebius-cloud" : "local",
    region: String(status.endpoint_health?.region ?? "not reported"),
    runningAgents: latest ? Number(latest.running_agents ?? 0) : 0,
    serverlessStatus: jobsHealthy ? "idle" : probeStatus(status.job_health) === "not_configured" ? "not-configured" : "error",
    storageStatus: storageHealthy ? "synced" : probeStatus(status.storage_health) === "not_configured" ? "not-configured" : "error",
    ticksProcessed: latest ? Number(latest.ticks_processed ?? runs * 240) : 0,
    websocketStatus: "disconnected"
  };
}

function ExperimentLab({
  busyAction,
  experiment,
  form,
  jobConfigured,
  jobs,
  leaderboard,
  message,
  onAggregate,
  onCreate,
  onGenerateManifest,
  onRefresh,
  onRunInvestigations,
  onRunLocalBatch,
  onSubmitNebius,
  onToggleScenario,
  onUpdateForm,
  runtimeMode,
  summary
}: {
  busyAction: ExperimentAction | null;
  experiment: ManagedExperiment | null;
  form: ExperimentFormState;
  jobConfigured: boolean;
  jobs: ExperimentJobRecord[];
  leaderboard: ExperimentLeaderboardRow[];
  message: string | null;
  onAggregate: () => void;
  onCreate: () => void;
  onGenerateManifest: () => void;
  onRefresh: () => void;
  onRunInvestigations: () => void;
  onRunLocalBatch: () => void;
  onSubmitNebius: () => void;
  onToggleScenario: (scenario: string) => void;
  onUpdateForm: <K extends keyof ExperimentFormState>(key: K, value: ExperimentFormState[K]) => void;
  runtimeMode: RuntimeMode;
  summary: ExperimentSummary | null;
}) {
  const canRun = Boolean(experiment);
  const pendingNebiusJob = jobs.find((job) => ["queued", "running", "real_nebius_pending"].includes(job.status));
  const investigationReady = Boolean(experiment?.artifact_paths.alerts);
  const cloudJobInFlight = Boolean(pendingNebiusJob);
  const controlsDisabled = busyAction !== null;
  const aggregationReady = Boolean(
    experiment?.artifact_paths.detector_metrics
    || experiment?.artifact_paths.local_batch_detector_metrics
    || experiment?.artifact_paths.metrics
  );
  const latestJob = latestExperimentJob(jobs);
  const detectorCount = new Set(leaderboard.map((row) => row.detector)).size;
  const modelCount = new Set(leaderboard.map((row) => row.model)).size;

  return (
    <section className="experiment-lab-panel">
      <div className="nebius-card-heading">
        <div>
          <span>Powered by Nebius Serverless Jobs</span>
          <h2>Nebius AI Detector Tournament</h2>
          <p className="nebius-card-purpose">Create one benchmark, run it locally or on Nebius, aggregate its evidence, and compare detector and model results.</p>
        </div>
        <div className="nebius-button-row">
          <span className={`runtime-status ${experiment?.status ?? "missing"}`}>{experiment?.status.replaceAll("_", " ") ?? "no benchmark"}</span>
          <button className="secondary-button" disabled={controlsDisabled} onClick={onRefresh} type="button">Refresh</button>
        </div>
      </div>
      <div className="experiment-summary-grid benchmark-status-strip" aria-label="Benchmark status">
        <MetricBlock label="Workloads" value={String(experiment?.attack_count ?? 0)} />
        <MetricBlock label="Seed" value={experiment ? String(experiment.seed) : "not set"} />
        <MetricBlock label="Latest execution" value={latestJob ? `${latestJob.backend.replaceAll("_", " ")} · ${latestJob.status.replaceAll("_", " ")}` : "not run"} />
        <MetricBlock label="Detectors compared" value={leaderboard.length ? String(detectorCount) : "not aggregated"} />
        <MetricBlock label="Models compared" value={leaderboard.length ? String(modelCount) : "not aggregated"} />
      </div>

      <div className="experiment-lab-layout">
        <div className="experiment-form-card">
          <label>
            <span>Name</span>
            <input
              disabled={controlsDisabled}
              onChange={(event) => onUpdateForm("name", event.target.value)}
              value={form.name}
            />
          </label>
          <div className="experiment-number-grid">
            <label>
              <span>Workload count</span>
              <input
                disabled={controlsDisabled}
                min={1}
                onChange={(event) => onUpdateForm("attack_count", Number(event.target.value))}
                type="number"
                value={form.attack_count}
              />
            </label>
            <label>
              <span>Batch size</span>
              <input
                disabled={controlsDisabled}
                min={1}
                onChange={(event) => onUpdateForm("batch_size", Number(event.target.value))}
                type="number"
                value={form.batch_size}
              />
            </label>
            <label>
              <span>Seed</span>
              <input
                disabled={controlsDisabled}
                onChange={(event) => onUpdateForm("seed", Number(event.target.value))}
                type="number"
                value={form.seed}
              />
            </label>
          </div>
          <div className="experiment-scenario-picker" aria-label="Benchmark scenarios">
            {experimentScenarioOptions.map((scenario) => (
              <button
                className={form.scenarios.includes(scenario) ? "scenario-pill selected" : "scenario-pill"}
                disabled={controlsDisabled}
                key={scenario}
                onClick={() => onToggleScenario(scenario)}
                type="button"
              >
                {scenario.replaceAll("_", " ")}
              </button>
            ))}
          </div>
          <button
            className="primary-button"
            disabled={controlsDisabled || !form.name.trim() || form.attack_count < 1 || form.batch_size < 1 || !form.scenarios.length}
            onClick={onCreate}
            type="button"
          >
            {busyAction === "create-experiment" ? "Creating..." : "Create benchmark"}
          </button>
        </div>

        <div className="experiment-progress-card">
          <div className="experiment-active-summary">
            <span>Current Benchmark</span>
            <strong>{experiment?.name ?? "Create or refresh a detector tournament"}</strong>
            <p>{experiment ? `${experiment.id} · ${experiment.attack_count} workloads · batch ${experiment.batch_size} · seed ${experiment.seed}` : "Local Demo benchmark runs deterministic mock results locally, then Cloud mode can run the same benchmark as serverless jobs."}</p>
          </div>
          <div className="experiment-flow-actions">
            <button disabled={controlsDisabled || !canRun || cloudJobInFlight} onClick={onGenerateManifest} type="button">Generate manifest</button>
            <button disabled={controlsDisabled || !canRun || cloudJobInFlight} onClick={onRunLocalBatch} title="Runs in a resource-limited worker while the live Arena continues ticking." type="button">Run Local Demo tournament</button>
            <button disabled={controlsDisabled || runtimeMode !== "nebius-cloud" || !canRun || !jobConfigured || cloudJobInFlight} onClick={onSubmitNebius} title={runtimeMode !== "nebius-cloud" ? "Switch Runtime to Nebius Cloud before submitting a Serverless Job." : undefined} type="button">Run serverless job</button>
            <button disabled={controlsDisabled || !aggregationReady} onClick={onAggregate} title={aggregationReady ? undefined : "Run a tournament and collect normalized detector metrics first."} type="button">Aggregate</button>
            <button disabled={controlsDisabled || !investigationReady} onClick={onRunInvestigations} title={investigationReady ? "Results open on Tab 3 · Investigation Team." : "Wait for detector alerts, then collect and normalize the completed Job artifacts."} type="button">Explain alerts → Tab 3</button>
          </div>
          {message ? <p className="experiment-message">{message}</p> : null}
          {pendingNebiusJob ? <p className="experiment-pending-note">pending cloud job execution: {pendingNebiusJob.message}</p> : null}
          {!investigationReady ? <p className="experiment-pending-note">AI Investigation unlocks after detector alerts are available. Complete the local tournament, or wait for the Serverless Job and collect its artifacts.</p> : null}
          <ExperimentProgressSummary experiment={experiment} summary={summary} jobs={jobs} />
        </div>
      </div>

      <div className="experiment-output-grid tournament-output-grid">
        <ExperimentJobsTable jobs={jobs} />
        <ExperimentLeaderboardTable leaderboard={leaderboard} />
      </div>
    </section>
  );
}

function RealNebiusDeploymentPanel({
  busyAction,
  cloudArtifactCollection,
  experiment,
  jobs,
  message,
  observatory,
  onCollectArtifacts,
  onRefreshJobStatus,
  onRenderJobConfig,
  onSubmitNebius,
  runtimeMode,
  status
}: {
  busyAction: ExperimentAction | null;
  cloudArtifactCollection: NebiusArtifactCollectionResponse | null;
  experiment: ManagedExperiment | null;
  jobs: ExperimentJobRecord[];
  message: string | null;
  observatory: NebiusObservatory | null;
  onCollectArtifacts: () => void;
  onRefreshJobStatus: () => void;
  onRenderJobConfig: () => void;
  onSubmitNebius: () => void;
  runtimeMode: RuntimeMode;
  status: NebiusStatus | null;
}) {
  const cloudJob = latestExperimentJob(jobs.filter((job) => job.backend === "nebius_serverless_job"));
  const endpointHealth = status?.endpoint_health ?? observatory?.endpoint_health ?? null;
  const endpointMode = status?.endpoint_mode ?? observatory?.endpoint_mode ?? "mock";
  const hasExperiment = Boolean(experiment);
  const jobHealthy = probeSucceeded(status?.job_health ?? observatory?.job_health);
  const storageHealthy = probeSucceeded(status?.storage_health ?? observatory?.storage_health);
  const controlsDisabled = busyAction !== null;
  const cloudMode = runtimeMode === "nebius-cloud";
  const canSubmitJob = cloudMode && hasExperiment && Boolean(status?.job_submit_template_configured) && jobHealthy;
  const noJobLabel = !status ? "checking" : status.job_submit_template_configured ? (jobHealthy ? "available" : healthStatusLabel(status.job_health)) : "not configured";
  const evidencePath = cloudArtifactCollection?.evidence_path ?? experiment?.artifact_paths.cloud_artifact_evidence;
  const sourceLabel = cloudArtifactCollection?.source_uri ?? cloudArtifactCollection?.source_dir ?? "waiting for cloud output";

  return (
    <section className="experiment-lab-panel real-nebius-deployment-panel">
      <div className="nebius-card-heading">
        <div>
          <h2>Deployment Status</h2>
        </div>
        <span className={`runtime-status ${cloudJob?.status ?? (jobHealthy ? "available" : "unavailable")}`}>
          {cloudJob?.status.replaceAll("_", " ") ?? noJobLabel}
        </span>
      </div>

      <div className="experiment-summary-grid real-nebius-summary-grid">
        <MetricBlock label="Endpoint base URL" value={status?.endpoint_base_url || "not configured"} />
        <MetricBlock label="Endpoint health" value={healthStatusLabel(endpointHealth)} />
        <MetricBlock label="Jobs live probe" value={healthStatusLabel(status?.job_health ?? observatory?.job_health)} />
        <MetricBlock label="Storage live probe" value={healthStatusLabel(status?.storage_health ?? observatory?.storage_health)} />
        <MetricBlock label="Last checked" value={status?.checked_at ?? observatory?.checked_at ?? "checking"} />
        <MetricBlock label="Endpoint mode" value={endpointMode} />
        <MetricBlock label="Model" value={status?.model || "not configured"} />
        <MetricBlock label="Job image" value={status?.job_image || "not configured"} />
        <MetricBlock
          label="Rendered config"
          value={experiment?.artifact_paths.nebius_job_config ?? "not rendered"}
        />
        <MetricBlock
          label="Submit template"
          value={status?.job_submit_template_configured ? "yes" : "no"}
        />
        <MetricBlock
          label="Job resources"
          value={status?.job_resource_configured ? "configured" : "missing subnet"}
        />
        <MetricBlock
          label="Status/logs"
          value={`${status?.job_status_template_configured ? "status" : "no status"} / ${status?.job_logs_template_configured ? "logs" : "no logs"}`}
        />
        <MetricBlock
          label="Cloud artifact sync"
          value={status?.job_artifacts_collection_configured ? "configured" : "set output URI"}
        />
        <MetricBlock
          label="Latest cloud job"
          value={cloudJob ? `${cloudJob.status.replaceAll("_", " ")} · ${cloudJob.job_id}` : noJobLabel}
        />
        <MetricBlock label="Artifact collection" value={artifactCollectionStatus(experiment)} />
        <MetricBlock label="Artifact source" value={sourceLabel} />
      </div>

      <div className="nebius-button-row">
        <button
          className="secondary-button"
          disabled={controlsDisabled || !cloudMode || !hasExperiment}
          onClick={onRenderJobConfig}
          type="button"
        >
          Render job config
        </button>
        <button
          className="secondary-button"
          disabled={controlsDisabled || !canSubmitJob}
          onClick={onSubmitNebius}
          title={canSubmitJob ? undefined : "Requires a benchmark, configured submit command, and successful live Jobs probe."}
          type="button"
        >
          Submit serverless job
        </button>
        <button
          className="secondary-button"
          disabled={controlsDisabled || !cloudMode || !hasExperiment || !cloudJob || !jobHealthy}
          onClick={onRefreshJobStatus}
          title={hasExperiment && cloudJob && jobHealthy ? undefined : "Requires a submitted Job and successful live Jobs probe."}
          type="button"
        >
          Refresh job status
        </button>
        <button
          className="secondary-button"
          disabled={controlsDisabled || !cloudMode || !hasExperiment || !cloudJob || !storageHealthy}
          onClick={onCollectArtifacts}
          title={hasExperiment && cloudJob && storageHealthy ? undefined : "Requires a submitted Job and successful live Object Storage probe."}
          type="button"
        >
          Collect cloud artifacts
        </button>
      </div>

      {status?.job_submit_template_configured ? null : (
        <p className="experiment-pending-note">
          Job submit template is not configured. Submitting records pending cloud execution and keeps Local Demo fallback available.
        </p>
      )}
      {status?.job_submit_template_configured && !status?.job_resource_configured ? (
        <p className="experiment-pending-note">
          Job submit template is configured, but `NEBIUS_SUBNET_ID` is missing from the backend environment.
        </p>
      ) : null}
      {cloudJob?.message ? <p className="experiment-message">{cloudJob.message}</p> : null}
      {evidencePath ? (
        <p className="experiment-message">
          Cloud evidence: <a href={artifactDownloadUrl(evidencePath)} target="_blank" rel="noreferrer">cloud_artifact_evidence.json</a>
        </p>
      ) : null}
      {message ? <p className="experiment-message">{message}</p> : null}
    </section>
  );
}

function ExperimentProgressSummary({
  experiment,
  jobs,
  summary
}: {
  experiment: ManagedExperiment | null;
  jobs: ExperimentJobRecord[];
  summary: ExperimentSummary | null;
}) {
  const completedJobs = jobs.filter((job) => job.status === "completed").length;
  const failedJobs = jobs.filter((job) => job.status === "failed").length;
  return (
    <div className="experiment-summary-grid">
      <MetricBlock label="Status" value={experiment?.status.replaceAll("_", " ") ?? "draft"} />
      <MetricBlock label="Jobs" value={`${completedJobs}/${jobs.length} done`} />
      <MetricBlock label="Alerts" value={summary ? String(summary.total_alerts) : "not aggregated"} />
      <MetricBlock label="Failed runs" value={String(summary?.failed_runs ?? failedJobs)} />
      <MetricBlock label="AI Investigation" value={String(summary?.investigation_count ?? metricValue(experiment, "investigation_count") ?? 0)} />
    </div>
  );
}

function MetricBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="runtime-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function ExperimentJobsTable({ jobs }: { jobs: ExperimentJobRecord[] }) {
  return (
    <div className="nebius-result-block experiment-jobs-block">
      <span>Benchmark job runs</span>
      {jobs.length ? (
        <div className="benchmark-table-panel">
          <table className="benchmark-table compact-job-table">
            <thead>
              <tr>
                <th>Job</th>
                <th>Backend</th>
                <th>Status</th>
                <th>Attacks</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.job_id}>
                  <td>{job.job_id}</td>
                  <td>{job.backend.replaceAll("_", " ")}</td>
                  <td>{job.status.replaceAll("_", " ")}</td>
                  <td>{job.attack_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>No jobs recorded yet.</p>
      )}
    </div>
  );
}

function ExperimentInvestigationResults({ investigations }: { investigations: InvestigationRecord[] }) {
  return (
    <section
      className="benchmark-investigations"
      aria-label="Benchmark alert explanations"
      id="benchmark-alert-explanations"
      tabIndex={-1}
    >
      <div className="artifact-browser-heading">
        <div>
          <span>Benchmark alert explanations</span>
          <strong>{investigations.length ? `${investigations.length} analyst summaries` : "No summaries yet"}</strong>
        </div>
        <span className={`runtime-status ${investigations.length ? "active" : "not-configured"}`}>
          {investigations.length ? "Ready" : "Awaiting run"}
        </span>
      </div>
      {investigations.length ? (
        <div className="benchmark-investigation-grid">
          {investigations.map((investigation) => {
            const title = textField(investigation.response, "title") || `Alert ${investigation.alert_id}`;
            const summary = textField(investigation.response, "summary") || "Investigation report generated.";
            return (
              <article className="benchmark-investigation-card" key={`${investigation.alert_id}-${investigation.json_path}`}>
                <div className="investigation-card-heading">
                  <span>{investigation.alert_id}</span>
                  <span className={`runtime-status ${investigation.mode === "mock" ? "mock" : "connected"}`}>{investigation.mode}</span>
                </div>
                <h3>{title}</h3>
                <p>{summary}</p>
                <small>{investigation.latency_seconds.toFixed(3)}s · persisted with benchmark evidence</small>
                <div className="investigation-card-actions">
                  <a href={artifactDownloadUrl(investigation.markdown_path)} target="_blank" rel="noreferrer">Open analyst report</a>
                  <a href={artifactDownloadUrl(investigation.json_path)} target="_blank" rel="noreferrer">View JSON</a>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <p>Run “Explain benchmark alerts” after a tournament produces alerts. Mock and cloud summaries will appear here and remain available after refresh.</p>
      )}
    </section>
  );
}

function ExperimentArtifactBrowser({
  artifacts,
  experimentId
}: {
  artifacts: Array<[string, string]>;
  experimentId?: string;
}) {
  const entries = artifacts.map(([label, path]) => ({
    category: artifactCategory(label),
    format: artifactFormat(path),
    href: artifactDownloadUrl(path),
    label: label.replaceAll("_", " "),
    path
  }));
  if (experimentId && !entries.some((entry) => entry.label === "benchmark report")) {
    entries.push({
      category: "Report",
      format: "HTML",
      href: getManagedExperimentReportUrl(experimentId),
      label: "benchmark report",
      path: `Experiment ${experimentId}`
    });
  }
  return (
    <section className="nebius-result-block experiment-artifact-browser" aria-label="Execution artifacts">
      <div className="artifact-browser-heading">
        <div>
          <span>Execution artifacts</span>
          <strong>{entries.length ? `${entries.length} files and reports` : "No artifacts yet"}</strong>
        </div>
        {experimentId ? <code>{experimentId}</code> : null}
      </div>
      {entries.length ? (
        <div className="artifact-browser-table-wrap">
          <table className="artifact-browser-table">
            <thead>
              <tr>
                <th>Type</th>
                <th>Artifact</th>
                <th>Format</th>
                <th>Source</th>
                <th aria-label="Action" />
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={`${entry.label}-${entry.path}`}>
                  <td><span className={`artifact-category artifact-category-${entry.category.toLowerCase()}`}>{entry.category}</span></td>
                  <td><strong>{entry.label}</strong></td>
                  <td><code>{entry.format}</code></td>
                  <td className="artifact-source" title={entry.path}>{compactArtifactSource(entry.path)}</td>
                  <td><a className="artifact-open-action" href={entry.href} target="_blank" rel="noreferrer">Open</a></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>Artifacts appear after benchmark generation, local execution, cloud jobs, aggregation, or AI Investigation.</p>
      )}
    </section>
  );
}

function ExperimentLeaderboardTable({ leaderboard }: { leaderboard: ExperimentLeaderboardRow[] }) {
  return (
    <div className="nebius-result-block experiment-leaderboard-block">
      <span>Benchmark leaderboard</span>
      {leaderboard.length ? (
        <div className="benchmark-table-panel">
          <table className="benchmark-table compact-job-table">
            <thead>
              <tr>
                <th>Scenario</th>
                <th>Detector</th>
                <th>Model</th>
                <th>Precision</th>
                <th>Recall</th>
                <th>F1</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody>
              {leaderboard.map((row) => (
                <tr key={`${row.scenario}-${row.detector}-${row.model}`}>
                  <td>{row.scenario.replaceAll("_", " ")}</td>
                  <td>{row.detector.replaceAll("_", " ")}</td>
                  <td>{row.model.replaceAll("_", " ")}</td>
                  <td>{formatScore(row.precision)}</td>
                  <td>{formatScore(row.recall)}</td>
                  <td>{formatScore(row.f1)}</td>
                  <td>{row.avg_detection_latency_ms == null ? "n/a" : `${row.avg_detection_latency_ms.toFixed(0)} ms`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>Aggregate the benchmark to populate detector rankings.</p>
      )}
    </div>
  );
}

function experimentArtifactsFrom(experiment: ManagedExperiment, summary: ExperimentSummary | null): Array<[string, string]> {
  const entries = Object.entries({
    ...experiment.artifact_paths,
    ...(summary?.artifact_paths ?? {})
  }).filter(([, path]) => typeof path === "string" && path.includes("."));
  const seen = new Set<string>();
  return entries.filter(([, path]) => {
    if (seen.has(path)) return false;
    seen.add(path);
    return true;
  });
}

function evidenceArtifactsFrom(records: NebiusEvidenceRecord[]): Array<[string, string]> {
  const entries: Array<[string, string]> = [];
  const seen = new Set<string>();
  for (const record of records) {
    for (const [name, path] of Object.entries(record.artifact_paths)) {
      if (!path || seen.has(path)) continue;
      seen.add(path);
      entries.push([`${record.kind}_${record.operation}_${name}`, path]);
    }
  }
  return entries.slice(0, 100);
}

function mergeArtifactLinks(...groups: Array<Array<[string, string]>>): Array<[string, string]> {
  const seen = new Set<string>();
  return groups.flat().filter(([, path]) => {
    if (!path || seen.has(path)) return false;
    seen.add(path);
    return true;
  });
}

function textField(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value : "";
}

function artifactCategory(label: string): "Config" | "Data" | "Evidence" | "Metrics" | "Report" {
  const normalized = label.toLowerCase();
  if (/report|investigation|summary/.test(normalized)) return "Report";
  if (/metric|leaderboard|result|score/.test(normalized)) return "Metrics";
  if (/evidence|endpoint|job|log|stdout|response/.test(normalized)) return "Evidence";
  if (/manifest|request|config|attack/.test(normalized)) return "Config";
  return "Data";
}

function artifactFormat(path: string): string {
  const filename = path.split(/[/?#]/).filter(Boolean).at(-1) ?? "";
  const extension = filename.includes(".") ? filename.split(".").at(-1) : null;
  return extension ? extension.toUpperCase() : "FILE";
}

function compactArtifactSource(path: string): string {
  if (path.startsWith("Experiment ")) return path;
  const parts = path.split("/").filter(Boolean);
  return parts.slice(-2).join("/") || path;
}

function workflowStepLockedReason(step: number): string {
  if (step === 2 || step === 4) return "Wait for the backend control plane to finish loading.";
  if (step === 3) return "Generate a scenario, select an Arena incident, or produce benchmark alerts first.";
  if (step === 5) return "Run a demo or tournament before opening its execution trace.";
  return "This workflow step is not ready.";
}

function mergeSmokeCloudTournament(
  result: ServerlessSmokeResponse,
  tournament: DetectorTournamentResponse
): ServerlessSmokeResponse {
  const artifacts = [...result.artifacts];
  const knownPaths = new Set(artifacts.map((artifact) => artifact.path));
  for (const [name, path] of Object.entries(tournament.artifacts)) {
    if (!path || knownPaths.has(path)) continue;
    artifacts.push({ name: `cloud_${name}`, path, download_url: artifactDownloadUrl(path) });
    knownPaths.add(path);
  }
  return {
    ...result,
    cloud_tournament: tournament,
    serverless_job: {
      ...result.serverless_job,
      status: tournament.status,
      message: tournament.summary,
      artifacts: tournament.artifacts,
      cloud_output_uri: tournament.metrics.cloud_output_uri ?? result.serverless_job.cloud_output_uri
    },
    artifacts
  };
}

function metricValue(experiment: ManagedExperiment | null, key: string): number | null {
  if (!experiment) return null;
  for (const row of experiment.metrics) {
    const value = row[key];
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return null;
}

function formatScore(value: number | null | undefined) {
  return typeof value === "number" && Number.isFinite(value) ? value.toFixed(3) : "n/a";
}

function latestExperiment(experiments: ManagedExperiment[]) {
  return [...experiments].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))[0] ?? null;
}

function latestExperimentJob(jobs: ExperimentJobRecord[]) {
  return [...jobs].sort((left, right) => Date.parse(right.updated_at) - Date.parse(left.updated_at))[0] ?? null;
}

function healthStatusLabel(health: Record<string, unknown> | null | undefined) {
  if (!health) return "not checked";
  const status = health.status;
  if (typeof status === "string" && status.trim()) return status.replaceAll("_", " ");
  return "available";
}

function probeStatus(health: Record<string, unknown> | null | undefined): string {
  if (!health) return "not_configured";
  const status = health.status;
  return typeof status === "string" && status.trim() ? status.toLowerCase() : "unavailable";
}

function probeSucceeded(health: Record<string, unknown> | null | undefined): boolean {
  return ["healthy", "ok", "ready", "connected"].includes(probeStatus(health));
}

function serviceProbeLabel(status: NebiusStatus | null, probe: string, failed = false): string {
  if (failed) return "backend unavailable";
  if (!status) return "checking";
  return probeSucceeded({ status: probe }) ? "connected" : probe.replaceAll("_", " ");
}

function routeProbeLabel(status: NebiusStatus | null, configured: boolean, endpointHealthy: boolean, failed = false): string {
  if (failed) return "backend unavailable";
  if (!status) return "checking";
  if (!configured) return "not configured";
  return endpointHealthy ? "connected" : "unavailable";
}

function artifactCollectionStatus(experiment: ManagedExperiment | null) {
  if (!experiment) return "no benchmark";
  if (experiment.status === "cloud_artifacts_pending") return "cloud artifacts pending";
  if (experiment.artifact_paths.artifact_index) return "collected";
  return "not collected";
}

function usageFrom(
  reports: ReportsSummary,
  evidence: NebiusEvidenceRecord[],
  sessionStartedAt: string
): NebiusUsageMetrics {
  const startedAtMs = Date.parse(sessionStartedAt);
  const sessionEvidence = evidence.filter((record) => Date.parse(record.created_at) >= startedAtMs);
  const endpointEvidence = sessionEvidence.filter((record) => record.kind === "endpoint_call");
  const latestJobEvidenceByRun = new Map<string, NebiusEvidenceRecord>();
  for (const record of sessionEvidence.filter((item) => item.kind === "job")) {
    const key = record.run_id || record.evidence_id;
    const current = latestJobEvidenceByRun.get(key);
    if (!current || Date.parse(record.created_at) > Date.parse(current.created_at)) {
      latestJobEvidenceByRun.set(key, record);
    }
  }
  const jobEvidence = [...latestJobEvidenceByRun.values()];
  const batches = (reports.nebius_batches ?? []).filter((row) => {
    const createdAt = row.created_at;
    return typeof createdAt === "string" && Date.parse(createdAt) >= startedAtMs;
  });
  const endpointLatency = endpointEvidence.reduce((total, record) => total + (record.latency_seconds ?? 0), 0);
  const artifactPaths = new Set(sessionEvidence.flatMap((record) => Object.values(record.artifact_paths)));
  const estimatedCosts = endpointEvidence
    .map((record) => record.estimated_cost_usd)
    .filter((value): value is number => typeof value === "number" && Number.isFinite(value));
  const measuredJobRuns = jobEvidence.reduce((total, record) => total + (record.job_runs ?? 0), 0);
  const measuredJobRuntime = jobEvidence.reduce((total, record) => total + (record.duration_seconds ?? 0), 0);
  const measuredWorkloads = jobEvidence.reduce(
    (total, record) => total + (record.workloads ?? 0) + (record.simulation_events ?? 0),
    0
  );
  const jobCosts = jobEvidence.reduce((total, record) => total + (record.job_cost_usd ?? 0), 0);
  return {
    aiEndpointCallsSession: endpointEvidence.length,
    averageLlmLatencySec: endpointEvidence.length ? endpointLatency / endpointEvidence.length : 0,
    artifactCount: artifactPaths.size,
    costBasis: estimatedCosts.length || jobCosts > 0
      ? "Provider token counts and measured Job runtime with configured rates."
      : endpointEvidence.length
      ? "Usage measured; cloud pricing rates are not configured."
      : "No metered cloud resources used in this session.",
    estimatedCostUsd: estimatedCosts.reduce((total, value) => total + value, 0) + jobCosts,
    jobRuntimeSec: measuredJobRuntime || batches.reduce((total, row) => total + numericValue(row.elapsed_seconds), 0),
    replayStorageMb: sessionEvidence.reduce((total, record) => total + (record.artifact_bytes ?? 0), 0) / 1_048_576,
    serverlessJobsRun: measuredJobRuns || batches.length,
    sessionDurationSec: Math.max(0, (Date.now() - startedAtMs) / 1000),
    simulationEventsGenerated: measuredWorkloads || batches.reduce((total, row) => total + numericValue(row.runs), 0),
    tokensUsed: endpointEvidence.reduce((total, record) => total + (record.total_tokens ?? 0), 0)
  };
}

function usageFromSmoke(result: ServerlessSmokeResponse, sessionStartedAt: string): NebiusUsageMetrics {
  return {
    aiEndpointCallsSession: result.usage.endpoint_calls,
    averageLlmLatencySec: result.usage.endpoint_avg_latency_seconds,
    artifactCount: result.usage.artifact_count,
    costBasis: result.usage.cost_basis,
    estimatedCostUsd: result.usage.estimated_cost_usd,
    jobRuntimeSec: result.usage.duration_seconds,
    replayStorageMb: result.usage.artifact_bytes / 1_048_576,
    serverlessJobsRun: result.usage.job_runs,
    sessionDurationSec: Math.max(0, (Date.now() - Date.parse(sessionStartedAt)) / 1000),
    simulationEventsGenerated: result.usage.workloads + result.usage.simulation_events,
    tokensUsed: result.usage.total_tokens
  };
}

function numericValue(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}
