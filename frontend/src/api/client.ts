import type { BenchmarkResult, Incident, ScenarioConfig } from "@/types/arena";
import { API_BASE_URL } from "@/config/runtime";
import type {
  AttackScenario,
  AttackScenarioInput,
  ExperimentArtifact,
  GeneratedScenario,
  ScenarioGridConfig
} from "@/features/nebius/types";

export { API_BASE_URL };

export type LobsterCandidate = {
  candidate_id: string;
  symbol: string;
  trade_date: string;
  start_time_ms: number;
  end_time_ms: number;
  start_time: string;
  end_time: string;
  depth: number;
  message_file: string | null;
  orderbook_file: string | null;
  message_file_size: number | null;
  orderbook_file_size: number | null;
  status: "ready" | "invalid" | "importing" | "failed" | "imported";
  errors: string[];
  dataset_id: string | null;
};

export type ImportedDataset = {
  dataset_id: string;
  source_type: string;
  symbol: string;
  trade_date: string;
  start_time_ms: number;
  end_time_ms: number;
  start_time: string;
  end_time: string;
  depth: number;
  row_count: number;
  event_counts: Record<string, number>;
  imported_at: string;
  path: string;
};

export type HistoricalReplayDataset = {
  dataset_id: string;
  source_type: string;
  symbol: string;
  trade_date: string;
  start_time: string;
  end_time: string;
  depth: number;
  row_count: number;
  events_sha256?: string;
};

export async function listLobsterCandidates(): Promise<LobsterCandidate[]> {
  const response = await fetch(`${API_BASE_URL}/api/data-ingestion/lobster/candidates`);
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "LOBSTER discovery failed"));
  }
  return response.json();
}

export async function importLobsterCandidate(
  candidateId: string,
  importWindow: { start_time_ms?: number; end_time_ms?: number } = {}
): Promise<{
  candidate_id: string;
  dataset_id: string | null;
  status: "importing" | "imported";
}> {
  const response = await fetch(
    `${API_BASE_URL}/api/data-ingestion/lobster/candidates/${encodeURIComponent(candidateId)}/import`,
    {
      body: JSON.stringify(importWindow),
      headers: { "Content-Type": "application/json" },
      method: "POST"
    }
  );
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "LOBSTER import failed"));
  }
  return response.json();
}

export async function listImportedDatasets(): Promise<ImportedDataset[]> {
  const response = await fetch(`${API_BASE_URL}/api/data-ingestion/datasets`);
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Dataset registry request failed"));
  }
  return response.json();
}

export async function deleteImportedDataset(datasetId: string): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/data-ingestion/datasets/${encodeURIComponent(datasetId)}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Dataset deletion failed"));
  }
}

export async function listHistoricalReplayDatasets(): Promise<HistoricalReplayDataset[]> {
  const response = await fetch(`${API_BASE_URL}/api/arena/historical-datasets`);
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Historical replay registry request failed"));
  }
  return response.json();
}

export async function getHealth(): Promise<{ status: string }> {
  const response = await fetch(`${API_BASE_URL}/health`);
  return response.json();
}

export async function launchScenario(name: string): Promise<unknown> {
  const response = await fetch(`${API_BASE_URL}/api/scenarios/${name}`, {
    method: "POST"
  });
  return response.json();
}

export async function getBenchmarkSummary(): Promise<BenchmarkResult[]> {
  const response = await fetch(`${API_BASE_URL}/benchmark/summary`);
  return response.json();
}

export type IncidentExplanation = {
  mode: "nebius" | "mock";
  endpoint: string;
  incident_id: string;
  explanation_id?: string | null;
  created_at?: string | null;
  stored_artifact?: string | null;
  risk_level: string;
  plain_english_summary: string;
  evidence: string[];
  recommended_action: string;
  fallback_reason?: string | null;
};

export async function explainIncident(incidentId: string): Promise<IncidentExplanation> {
  const response = await fetch(`${API_BASE_URL}/api/incidents/${incidentId}/explain`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Incident explanation failed: ${response.status}`);
  }
  return response.json();
}

export async function explainIncidentPayload(incident: Incident): Promise<IncidentExplanation> {
  const response = await fetch(`${API_BASE_URL}/api/incidents/explain`, {
    body: JSON.stringify({ incident }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Incident explanation failed: ${response.status}`);
  }
  return response.json();
}

export type RedTeamScenarioGenerateRequest = {
  scenario_family: string;
  market_regime: "calm" | "volatile" | "thin_liquidity";
  goal: "obvious" | "stealth" | "hard_to_detect";
  constraints: Record<string, unknown>;
};

export type AttackExperimentRequest = {
  scenario_type: string;
  wall_size_multiplier: number;
  lifetime_seconds: number;
  distance_from_mid_bps: number;
  cancel_style: "instant" | "gradual" | "partial";
  noise_cover: "none" | "low" | "high";
  predicted_detection_risk: number;
};

export type SavedExperiment = {
  id: string;
  kind: "attack_builder";
  created_at: string;
  config: AttackExperimentRequest;
};

export type LabLaunchResponse = {
  experiment_id: string;
  launch_endpoint: string;
  attack: unknown;
};

export type BenchmarkRunRequest = {
  runs: number;
  market_regime: string;
  scenarios: string[];
  detectors: string;
};

export type BenchmarkRunResponse = {
  id: string;
  mode: "local_serverless_job";
  status: "queued" | "running" | "generating_report" | "completed";
  created_at: string;
  command: string[];
  results: BenchmarkResult[];
  artifact_paths: Record<string, string>;
};

export type ManagedExperimentStatus =
  | "draft"
  | "manifest_generated"
  | "submitted"
  | "running"
  | "completed"
  | "failed"
  | "cloud_artifacts_pending";
export type ManagedExperimentMode = "mock" | "local_parallel_batch" | "real_nebius_pending";

export type ManagedExperimentCreateRequest = {
  name?: string;
  attack_count?: number;
  batch_size?: number;
  scenarios?: string[];
  seed?: number;
  nebius_mode?: ManagedExperimentMode;
};

export type ManagedExperiment = {
  id: string;
  name: string;
  status: ManagedExperimentStatus;
  attack_count: number;
  batch_size: number;
  scenarios: string[];
  seed: number;
  nebius_mode: ManagedExperimentMode;
  smart_batch_id?: string | null;
  artifact_dir: string;
  artifact_paths: Record<string, string>;
  metrics: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
};

export type ManagedExperimentDeleteResponse = {
  id: string;
  deleted: boolean;
};

export type AttackManifestResponse = {
  experiment_id: string;
  path: string;
  attack_count: number;
  scenarios: string[];
  status: ManagedExperimentStatus;
};

export type ExperimentLocalBatchRunResponse = {
  id: string;
  experiment_id: string;
  mode: "local_parallel_batch";
  status: "completed" | "failed";
  created_at: string;
  elapsed_seconds: number;
  runs: number;
  batch_size: number;
  scenarios: string[];
  artifact_paths: Record<string, string>;
  metrics: Record<string, unknown>[];
  error?: Record<string, unknown> | null;
};

export type ArtifactNormalizationResponse = {
  experiment_id: string;
  artifact_dir: string;
  artifact_paths: Record<string, string>;
  copied_count: number;
  missing: string[];
};

export type NebiusArtifactCollectionResponse = ArtifactNormalizationResponse & {
  status: "collected" | "cloud_artifacts_pending";
  source_dir?: string | null;
  source_uri?: string | null;
  evidence_path?: string | null;
  message: string;
};

export type NebiusJobConfigRenderResponse = {
  experiment_id: string;
  path: string;
  image: string;
  output_dir: string;
};

export type InvestigationRecord = {
  alert_id: string;
  experiment_id: string;
  source_alert_path: string;
  json_path: string;
  markdown_path: string;
  mode: string;
  latency_seconds: number;
  fallback_reason?: string | null;
  request: Record<string, unknown>;
  response: Record<string, unknown>;
};

export type InvestigationRunResponse = {
  experiment_id: string;
  selected_count: number;
  investigation_count: number;
  investigation_mode: string;
  endpoint_avg_latency_seconds: number;
  investigations: InvestigationRecord[];
};

export type ExperimentSummary = {
  experiment_id: string;
  total_attacks: number;
  total_alerts: number;
  scenarios: string[];
  precision_by_scenario: Record<string, number | null>;
  recall_by_scenario: Record<string, number | null>;
  f1_by_scenario: Record<string, number | null>;
  avg_detection_latency_ms?: number | null;
  investigation_count: number;
  failed_runs: number;
  artifact_paths: Record<string, string>;
};

export type ExperimentLeaderboardRow = {
  scenario: string;
  detector: string;
  model: string;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  specificity?: number | null;
  false_positive_rate?: number | null;
  avg_detection_latency_ms?: number | null;
  alert_count: number;
};

export type ExperimentAggregationResult = {
  summary: ExperimentSummary;
  leaderboard: ExperimentLeaderboardRow[];
  report_path: string;
};

export type ExperimentJobRecord = {
  job_id: string;
  experiment_id: string;
  backend: "local_parallel_batch" | "nebius_serverless_job";
  status: "queued" | "running" | "completed" | "failed" | "real_nebius_pending";
  batch_start: number;
  batch_end: number;
  attack_count: number;
  created_at: string;
  updated_at: string;
  message: string;
  artifact_paths: Record<string, string>;
};

export type ArtifactReadResponse = {
  path: string;
  name: string;
  content_type: string;
  content: string;
};

export type ArtifactExportResponse = {
  path: string;
  download_url: string;
  format: "markdown" | "pdf";
};

export type BenchmarkCompareResponse = {
  run_ids: string[];
  rows: Record<string, unknown>[];
};

export type IncidentReplayResponse = {
  incident_id: string;
  incident: Record<string, unknown> | null;
  events: Record<string, unknown>[];
  labels: Record<string, unknown>[];
  ticks: Record<string, unknown>[];
};

export type ScreenshotAttachmentResponse = {
  id: string;
  title: string;
  path: string;
  created_at: string;
};

export type PromoteEvidenceResponse = {
  run_id: string;
  path: string;
  download_url: string;
};

export type ClearReportsResponse = {
  deleted_files: string[];
  deleted_dirs: string[];
  message: string;
};

export type ArenaRole = "attacker" | "defender" | "observer" | "judge";

export type ReportsSummary = {
  experiments: Record<string, unknown>[];
  benchmark_runs: Record<string, unknown>[];
  nebius_batches: Record<string, unknown>[];
  nebius_artifacts: Record<string, unknown>[];
  incidents: Record<string, unknown>[];
  explanations: Record<string, unknown>[];
  attacks: Record<string, unknown>[];
  significant_events: Record<string, unknown>[];
  evidence_screenshots: Record<string, unknown>[];
  promoted_runs: Record<string, unknown>[];
  nebius_detections: Record<string, unknown>[];
  nebius_investigation_reports: Record<string, unknown>[];
  history_artifacts: HistoryRecord[];
  history_ticks: HistoryRecord[];
};

export type HistoryRecord = {
  history_id: string;
  kind: string;
  created_at: string;
  run_id?: string | null;
  tick?: number | null;
  scenario_id?: string | null;
  incident_id?: string | null;
  source?: string | null;
  source_path?: string | null;
  summary: string;
  payload: Record<string, unknown>;
};

export type HistoryReplayResponse = {
  window_hours: number;
  generated_at: string;
  filters: Record<string, unknown>;
  tick_count: number;
  artifact_count: number;
  ticks: HistoryRecord[];
  artifacts: HistoryRecord[];
};

export type NebiusStatus = {
  tenant_id_configured: boolean;
  incident_explainer_configured: boolean;
  scenario_generator_configured: boolean;
  orderbook_alert_configured: boolean;
  investigation_report_configured: boolean;
  investigation_team_configured: boolean;
  market_abuse_scenario_configured?: boolean;
  endpoint_token_configured: boolean;
  api_key_configured?: boolean;
  endpoint_mode?: string;
  endpoint_base_url?: string | null;
  endpoint_base_url_configured?: boolean;
  endpoint_health?: Record<string, unknown> | null;
  runner_health?: Record<string, unknown>;
  job_health?: Record<string, unknown>;
  storage_health?: Record<string, unknown>;
  checked_at?: string;
  base_url_configured?: boolean;
  model_configured?: boolean;
  model?: string | null;
  job_image?: string;
  job_submit_template_configured?: boolean;
  job_resource_configured?: boolean;
  job_status_template_configured?: boolean;
  job_logs_template_configured?: boolean;
  job_artifacts_template_configured?: boolean;
  job_artifacts_collection_configured?: boolean;
  cli_installed: boolean;
  cli_path?: string | null;
  cli_version?: string | null;
};

export type NebiusEvidenceRecord = {
  evidence_id: string;
  kind: "endpoint_call" | "job";
  operation: string;
  status: string;
  created_at: string;
  latency_seconds?: number | null;
  prompt_tokens?: number;
  completion_tokens?: number;
  total_tokens?: number;
  estimated_cost_usd?: number | null;
  job_cost_usd?: number;
  duration_seconds?: number;
  job_runs?: number;
  workloads?: number;
  simulation_events?: number;
  artifact_count?: number;
  request_bytes?: number;
  response_bytes?: number;
  artifact_bytes?: number;
  run_id?: string | null;
  endpoint?: string | null;
  local_dir: string;
  source_uri?: string | null;
  s3_status: "uploaded" | "local_only" | "upload_failed";
  artifact_paths: Record<string, string>;
  error?: string | null;
};

export type NebiusEvidenceSyncResponse = {
  status: "synced" | "local_only" | "failed";
  source_uri?: string | null;
  local_dir: string;
  uploaded_pending: number;
  record_count: number;
  artifact_count: number;
  message: string;
};

export type SmartScenarioResponse = {
  mode: "nebius" | "mock";
  endpoint: string;
  scenario_type: string;
  title: string;
  description: string;
  parameters: Record<string, unknown>;
  expected_detector_risk: number;
  safety_note: string;
  fallback_reason?: string | null;
};

export type OrderBookAlertResponse = {
  mode: "nebius" | "mock";
  endpoint: string;
  suspicion_score: number;
  detected_pattern: string;
  confidence: number;
  reasons: string[];
  recommended_action: string;
  fallback_reason?: string | null;
};

export type InvestigationReportResponse = {
  mode: "nebius" | "mock";
  endpoint: string;
  title: string;
  summary: string;
  timeline: string[];
  detector_findings: string[];
  limitations: string[];
  recommended_next_steps: string[];
  fallback_reason?: string | null;
  raw_response?: Record<string, unknown> | null;
};

export type AIInvestigationEvidenceItem = {
  key: string;
  label: string;
  value: string | number | boolean;
  source?: string | null;
};

export type AIInvestigationEvidenceTimelineItem = {
  sequence: number;
  event: string;
  tick?: number | string | null;
  source?: string | null;
  significance?: string | null;
};

export type AIInvestigationAgentFinding = {
  name: string;
  role: string;
  finding: string;
  confidence: number;
  evidence: AIInvestigationEvidenceItem[];
};

export type AIInvestigationTeamRequest = {
  incident: Record<string, unknown>;
  detector_outputs: Record<string, unknown>[];
  order_book_context: Record<string, unknown>;
  trades: Record<string, unknown>[];
  market_metrics: Record<string, unknown>;
  episode_summary?: Record<string, unknown>;
};

export type AIInvestigationTeamResponse = {
  mode: "nebius" | "mock";
  endpoint: string;
  investigation_id: string;
  manipulation_type: string;
  risk_score: number;
  confidence: number;
  agents: AIInvestigationAgentFinding[];
  consensus: string;
  evidence_timeline: AIInvestigationEvidenceTimelineItem[];
  recommended_action: string;
  executive_summary: string;
  fallback_reason?: string | null;
  raw_response?: Record<string, unknown> | null;
  structured_assessment?: Record<string, unknown> | null;
};

export type MarketAbuseScenarioGenerationRequest = {
  manipulation_type: "spoofing_like_wall" | "layering_like" | "quote_stuffing" | "liquidity_evaporation";
  difficulty: "easy" | "medium" | "hard" | "adversarial";
  symbol: string;
  duration_ticks: number;
  liquidity_regime: "thin" | "normal" | "deep";
  volatility_regime: "low" | "medium" | "high";
  seed?: number | null;
};

export type MarketAbuseScenarioEvent = {
  event_id: string;
  tick: number;
  event_type: "place_order" | "cancel_order" | "trade" | "quote_update";
  type: string;
  agent_id: string;
  symbol: string;
  scenario_id: string;
  scenario_name: string;
  scenario_family: string;
  stage: string;
  message: string;
  side?: "buy" | "sell" | null;
  price?: number | null;
  quantity?: number | null;
  order_id?: string | null;
  metadata?: Record<string, unknown>;
};

export type MarketAbuseScenarioResponse = {
  mode: "nebius" | "mock";
  endpoint: string;
  scenario_id: string;
  title: string;
  description: string;
  manipulation_type: MarketAbuseScenarioGenerationRequest["manipulation_type"];
  difficulty: MarketAbuseScenarioGenerationRequest["difficulty"];
  symbol: string;
  duration_ticks: number;
  liquidity_regime: MarketAbuseScenarioGenerationRequest["liquidity_regime"];
  volatility_regime: MarketAbuseScenarioGenerationRequest["volatility_regime"];
  ground_truth: {
    label: string;
    manipulation_windows: { start_tick: number; end_tick: number }[];
    manipulator_agent_ids: string[];
    expected_detector_targets: string[];
    positive_event_ids: string[];
  };
  events: MarketAbuseScenarioEvent[];
  expected_detector_behavior: {
    primary_signals: string[];
    expected_risk_score: number;
    false_positive_risk: "low" | "medium" | "high";
  };
  explanation: string;
  replay: Record<string, unknown>;
  source: Record<string, unknown>;
  fallback_reason?: string | null;
  raw_response?: Record<string, unknown> | null;
};

export type DetectorTournamentStartRequest = {
  number_of_scenarios: number;
  manipulation_types: ("spoofing_like_wall" | "layering_like" | "quote_stuffing" | "liquidity_evaporation")[];
  difficulty_mix: Record<string, number>;
  detector_set: ("spoofing_like" | "layering_like" | "quote_stuffing" | "liquidity_shock")[];
  random_seed: number;
  execution_mode: "local" | "local_mock" | "nebius";
};

export type DetectorTournamentLeaderboardRow = {
  detector: string;
  scenario: string;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  specificity?: number | null;
  false_positive_rate?: number | null;
  false_positives: number;
  false_negatives: number;
  avg_detection_latency_ms?: number | null;
  runs?: number;
  temporal_overlap?: number | null;
  event_precision?: number | null;
  event_recall?: number | null;
  participant_precision?: number | null;
  participant_recall?: number | null;
  order_precision?: number | null;
  order_recall?: number | null;
};

export type DetectorTournamentResponse = {
  tournament_id: string;
  status: "queued" | "running" | "completed" | "failed" | "real_nebius_pending";
  execution_mode: "local_mock" | "local" | "nebius_serverless_job";
  started_at: string;
  completed_at?: string | null;
  detectors: string[];
  leaderboard: DetectorTournamentLeaderboardRow[];
  metrics: Record<string, unknown>;
  artifacts: Record<string, string>;
  summary: string;
  fallback_reason?: string | null;
};

export type ServerlessSmokeArtifact = {
  name: string;
  path: string;
  download_url: string;
};

export type ServerlessSmokeResponse = {
  mode: "local" | "real_nebius_pending" | "real_nebius" | "error";
  summary: string;
  scenario_id: string;
  incident_id?: string | null;
  detector_alerts: Record<string, unknown>[];
  explanation?: IncidentExplanation | null;
  investigation?: AIInvestigationTeamResponse | null;
  tournament: DetectorTournamentResponse;
  cloud_tournament?: DetectorTournamentResponse | null;
  serverless_job: Record<string, unknown>;
  artifacts: ServerlessSmokeArtifact[];
  benefits: string[];
  experiment_id: string;
  evidence_id: string;
  evidence_s3_status: "uploaded" | "local_only" | "upload_failed";
  evidence_source_uri?: string | null;
  usage: {
    duration_seconds: number;
    endpoint_calls: number;
    endpoint_avg_latency_seconds: number;
    prompt_tokens: number;
    completion_tokens: number;
    total_tokens: number;
    job_runs: number;
    workloads: number;
    simulation_events: number;
    artifact_count: number;
    artifact_bytes: number;
    endpoint_cost_usd: number;
    job_cost_usd: number;
    estimated_cost_usd: number;
    cost_basis: string;
  };
};

export type ServerlessSmokeFinalizeResponse = {
  experiment: ManagedExperiment;
  evidence: NebiusEvidenceRecord;
  usage: ServerlessSmokeResponse["usage"];
};

export type ScenarioActionResponse = {
  message: string;
  scenario?: AttackScenario | null;
  artifact?: ExperimentArtifact | null;
};

export type SmartBatchRunResponse = {
  id: string;
  mode: "local_parallel_batch";
  status: "completed";
  created_at: string;
  elapsed_seconds: number;
  runs: number;
  batch_size: number;
  scenarios: string[];
  artifact_paths: Record<string, string>;
  metrics: Record<string, string>[];
  job_image: string;
  deployment_target: string;
};

export type NebiusObservatory = {
  adapter: {
    name: string;
    mode: string;
    replacement_target: string;
  };
  capabilities: {
    name: string;
    surface: string;
    status: string;
    detail: string;
  }[];
  runtime_health: {
    name: string;
    status: string;
    detail: string;
    checked_at: string;
  }[];
  usage: {
    endpoint_requests: number;
    endpoint_avg_latency_seconds: number;
    endpoint_purpose: string;
    job_simulations: number;
    job_runtime: string;
    job_output_files: number;
    job_artifacts: string[];
    evidence_status: "mock" | "local" | "nebius_needed";
  };
  endpoint_base_url_configured: boolean;
  orderbook_alert_configured: boolean;
  investigation_report_configured: boolean;
  endpoint_health?: Record<string, unknown> | null;
  job_health: Record<string, unknown>;
  storage_health: Record<string, unknown>;
  checked_at: string;
  endpoint_mode: string;
  screenshots: { title: string; status: string; path: string }[];
  benchmark_artifacts: Record<string, string>;
  latest_batch?: Record<string, unknown> | null;
  experiment_jobs?: Record<string, unknown> | null;
};

export async function generateRedTeamScenario(
  request: RedTeamScenarioGenerateRequest
): Promise<ScenarioConfig> {
  const response = await fetch(`${API_BASE_URL}/api/red-team/generate-scenario`, {
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Red-team scenario generation failed: ${response.status}`);
  }
  return response.json();
}

export async function saveAttackExperiment(request: AttackExperimentRequest): Promise<SavedExperiment> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/attacks`, {
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Save experiment failed: ${response.status}`);
  }
  return response.json();
}

export async function launchAttackExperiment(request: AttackExperimentRequest): Promise<LabLaunchResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/attacks/launch`, {
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Launch experiment failed: ${response.status}`);
  }
  return response.json();
}

export async function runBenchmarkExperiment(request: BenchmarkRunRequest): Promise<BenchmarkRunResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/benchmark-runs`, {
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Benchmark run failed: ${response.status}`);
  }
  return response.json();
}

export async function createManagedExperiment(request: ManagedExperimentCreateRequest): Promise<ManagedExperiment> {
  const response = await fetch(`${API_BASE_URL}/api/experiments`, {
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Create experiment failed: ${response.status}`);
  }
  return response.json();
}

export async function listManagedExperiments(): Promise<ManagedExperiment[]> {
  const response = await fetch(`${API_BASE_URL}/api/experiments`);
  if (!response.ok) {
    throw new Error(`List experiments failed: ${response.status}`);
  }
  return response.json();
}

export async function getManagedExperiment(experimentId: string): Promise<ManagedExperiment> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}`);
  if (!response.ok) {
    throw new Error(`Get experiment failed: ${response.status}`);
  }
  return response.json();
}

export async function generateManagedExperimentManifest(experimentId: string): Promise<AttackManifestResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/generate-manifest`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(`Generate experiment manifest failed: ${response.status}`);
  }
  return response.json();
}

export async function runManagedExperimentLocalBatch(experimentId: string): Promise<ExperimentLocalBatchRunResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/run-local-batch`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(`Run experiment local batch failed: ${response.status}`);
  }
  return response.json();
}

export async function normalizeManagedExperimentArtifacts(experimentId: string): Promise<ArtifactNormalizationResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/normalize-artifacts`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(`Normalize experiment artifacts failed: ${response.status}`);
  }
  return response.json();
}

export async function runManagedExperimentInvestigations(
  experimentId: string,
  runtimeMode: "local-demo" | "nebius-cloud",
  topK = 7
): Promise<InvestigationRunResponse> {
  const params = new URLSearchParams({
    execution_mode: runtimeMode === "local-demo" ? "local" : "nebius",
    top_k: String(topK)
  });
  const response = await fetch(
    `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/run-investigations?${params.toString()}`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Run experiment investigations failed"));
  }
  return response.json();
}

export async function listManagedExperimentInvestigations(experimentId: string): Promise<InvestigationRecord[]> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/investigations`);
  if (!response.ok) {
    throw new Error(`List experiment investigations failed: ${response.status}`);
  }
  return response.json();
}

export async function aggregateManagedExperiment(experimentId: string): Promise<ExperimentAggregationResult> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/aggregate`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Aggregate experiment failed: ${response.status}`);
  }
  return response.json();
}

export async function getManagedExperimentSummary(experimentId: string): Promise<ExperimentSummary> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/summary`);
  if (!response.ok) {
    throw new Error(`Get experiment summary failed: ${response.status}`);
  }
  return response.json();
}

export async function getManagedExperimentLeaderboard(experimentId: string): Promise<ExperimentLeaderboardRow[]> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/leaderboard`);
  if (!response.ok) {
    throw new Error(`Get experiment leaderboard failed: ${response.status}`);
  }
  return response.json();
}

export function getManagedExperimentReportUrl(experimentId: string): string {
  return `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/report`;
}

export async function getManagedExperimentReport(experimentId: string): Promise<string> {
  const response = await fetch(getManagedExperimentReportUrl(experimentId));
  if (!response.ok) {
    throw new Error(`Get experiment report failed: ${response.status}`);
  }
  return response.text();
}

export async function submitManagedExperimentNebius(experimentId: string): Promise<ExperimentJobRecord> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/submit-nebius`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Submit experiment to Nebius failed: ${response.status}`);
  }
  return response.json();
}

export async function renderManagedExperimentNebiusJobConfig(
  experimentId: string
): Promise<NebiusJobConfigRenderResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/render-nebius-job-config`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(`Render Nebius job config failed: ${response.status}`);
  }
  return response.json();
}

export async function listManagedExperimentJobs(experimentId: string): Promise<ExperimentJobRecord[]> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/jobs`);
  if (!response.ok) {
    throw new Error(`List experiment jobs failed: ${response.status}`);
  }
  return response.json();
}

export async function refreshManagedExperimentJobs(experimentId: string): Promise<ExperimentJobRecord[]> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/refresh-jobs`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Refresh experiment jobs failed: ${response.status}`);
  }
  return response.json();
}

export async function collectManagedExperimentNebiusArtifacts(
  experimentId: string
): Promise<NebiusArtifactCollectionResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}/collect-nebius-artifacts`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(`Collect Nebius experiment artifacts failed: ${response.status}`);
  }
  return response.json();
}

export async function deleteManagedExperiment(experimentId: string): Promise<ManagedExperimentDeleteResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/${encodeURIComponent(experimentId)}`, {
    method: "DELETE"
  });
  if (!response.ok) {
    throw new Error(`Delete experiment failed: ${response.status}`);
  }
  return response.json();
}

export async function getReportsSummary(): Promise<ReportsSummary> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/reports`);
  if (!response.ok) {
    throw new Error(`Reports summary failed: ${response.status}`);
  }
  return response.json();
}

export async function replayHistoryWindow(windowHours = 1, limit = 5000): Promise<HistoryReplayResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    window_hours: String(windowHours)
  });
  const response = await fetch(`${API_BASE_URL}/api/experiments/history/replay?${params.toString()}`);
  if (!response.ok) {
    throw new Error(`History replay failed: ${response.status}`);
  }
  return response.json();
}

export async function readArtifact(path: string): Promise<ArtifactReadResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/artifacts/read?path=${encodeURIComponent(path)}`);
  if (!response.ok) {
    throw new Error(`Artifact read failed: ${response.status}`);
  }
  return response.json();
}

export function artifactDownloadUrl(path: string) {
  return `${API_BASE_URL}/api/experiments/artifacts/download?path=${encodeURIComponent(path)}`;
}

export async function exportArtifact(path: string, format: "markdown" | "pdf"): Promise<ArtifactExportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/artifacts/export`, {
    body: JSON.stringify({ format, path }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Artifact export failed: ${response.status}`);
  }
  return response.json();
}

export async function compareBenchmarkRuns(runIds: string[]): Promise<BenchmarkCompareResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/benchmark-runs/compare`, {
    body: JSON.stringify({ run_ids: runIds }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Benchmark comparison failed: ${response.status}`);
  }
  return response.json();
}

export async function replayIncidentWindow(incidentId: string): Promise<IncidentReplayResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/incidents/${encodeURIComponent(incidentId)}/replay`);
  if (!response.ok) {
    throw new Error(`Incident replay failed: ${response.status}`);
  }
  return response.json();
}

export async function attachNebiusScreenshot(path = "assets/screenshots/nebius-logs-metrics.svg"): Promise<ScreenshotAttachmentResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/evidence/screenshots`, {
    body: JSON.stringify({ path, title: "Nebius logs and metrics" }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Screenshot attachment failed: ${response.status}`);
  }
  return response.json();
}

export async function promoteBenchmarkRun(runId: string): Promise<PromoteEvidenceResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/benchmark-runs/${encodeURIComponent(runId)}/promote`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Promote run failed: ${response.status}`);
  }
  return response.json();
}

export async function clearReportsData(confirmation: string): Promise<ClearReportsResponse> {
  const response = await fetch(`${API_BASE_URL}/api/experiments/reports/clear`, {
    body: JSON.stringify({ confirmation }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Clear reports failed: ${response.status}`);
  }
  return response.json();
}

export async function getNebiusStatus(): Promise<NebiusStatus> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/status`);
  if (!response.ok) {
    throw new Error(`Nebius status failed: ${response.status}`);
  }
  return response.json();
}

export async function listNebiusEvidence(): Promise<NebiusEvidenceRecord[]> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/evidence`);
  if (!response.ok) {
    throw new Error(`Nebius evidence listing failed: ${response.status}`);
  }
  return response.json();
}

export async function syncNebiusEvidence(): Promise<NebiusEvidenceSyncResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/evidence/sync`, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Nebius evidence sync failed: ${response.status}`);
  }
  return response.json();
}

export async function getNebiusObservatory(): Promise<NebiusObservatory> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/observatory`);
  if (!response.ok) {
    throw new Error(`Nebius observatory failed: ${response.status}`);
  }
  return response.json();
}

export async function createSmartScenario(): Promise<SmartScenarioResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/smart-scenario`, {
    body: JSON.stringify({
      goal: "hard_to_detect",
      market_regime: "volatile",
      scenario_family: "quote_stuffing"
    }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Smart scenario failed: ${response.status}`);
  }
  return response.json();
}

export async function runSmartDetection(): Promise<OrderBookAlertResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/smart-detection`, {
    body: JSON.stringify({
      bids: [{ owner: "abuser", price: 68120, quantity: 12.4 }],
      asks: [{ owner: "normal", price: 68130, quantity: 1.8 }],
      features: {
        cancel_to_trade_ratio: 5.4,
        depth_change_pct: 0.38,
        imbalance: 0.72,
        message_rate: 21,
        wall_size_ratio: 8.2
      },
      scenario_hint: "spoofing_like_wall",
      tick: 12
    }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Smart detection failed: ${response.status}`);
  }
  return response.json();
}

export async function runSmartBatches(runs = 100, batchSize = 100, scenarios = ["normal_market", "spoofing_like_wall", "layering_like", "quote_stuffing", "liquidity_evaporation"]): Promise<SmartBatchRunResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/smart-batches`, {
    body: JSON.stringify({
      batch_size: batchSize,
      runs,
      scenarios
    }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Smart batch run failed"));
  }
  return response.json();
}

export async function createInvestigationReport(): Promise<InvestigationReportResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/investigation-report`, {
    body: JSON.stringify({
      alerts: [
        {
          agent_id: "R-17",
          confidence: 0.91,
          detected_pattern: "spoofing",
          suspicion_score: 0.88
        }
      ],
      metrics: {
        cancel_to_trade_ratio: 5.4,
        precision: 0.82,
        wall_size_ratio: 8.2
      },
      scenario_trace: {
        active_window: "last 60 seconds",
        id: "Spoofing Attack #042",
        source: "Nebius AI"
      }
    }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Detection report failed: ${response.status}`);
  }
  return response.json();
}

export async function runAIInvestigationTeam(
  request: AIInvestigationTeamRequest = defaultAIInvestigationTeamRequest(),
  runtimeMode: "local-demo" | "nebius-cloud" = "local-demo"
): Promise<AIInvestigationTeamResponse> {
  const executionMode = runtimeMode === "local-demo" ? "local" : "nebius";
  const response = await fetch(`${API_BASE_URL}/api/nebius/investigation-team/analyze?execution_mode=${executionMode}`, {
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`AI investigation team failed: ${response.status}`);
  }
  return response.json();
}

export async function generateMarketAbuseScenario(
  request: MarketAbuseScenarioGenerationRequest,
  runtimeMode: "local-demo" | "nebius-cloud" = "local-demo"
): Promise<MarketAbuseScenarioResponse> {
  const executionMode = runtimeMode === "local-demo" ? "local" : "nebius";
  const response = await fetch(`${API_BASE_URL}/api/nebius/scenario-generator/generate?execution_mode=${executionMode}`, {
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`AI scenario generation failed: ${response.status}`);
  }
  return response.json();
}

export async function startDetectorTournament(
  request: DetectorTournamentStartRequest
): Promise<DetectorTournamentResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/tournament/start`, {
    body: JSON.stringify(request),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`AI detector tournament failed: ${response.status}`);
  }
  return response.json();
}

export async function getDetectorTournament(tournamentId: string): Promise<DetectorTournamentResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/tournament/${encodeURIComponent(tournamentId)}`);
  if (!response.ok) {
    throw new Error(`AI detector tournament status failed: ${response.status}`);
  }
  return response.json();
}

export async function refreshDetectorTournament(tournamentId: string): Promise<DetectorTournamentResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/nebius/tournament/${encodeURIComponent(tournamentId)}/refresh`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(`AI detector tournament refresh failed: ${response.status}`);
  }
  return response.json();
}

export async function runServerlessSmokeDemo(runtimeMode: "local-demo" | "nebius-cloud"): Promise<ServerlessSmokeResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/serverless-smoke/run`, {
    body: JSON.stringify({ execution_mode: runtimeMode === "local-demo" ? "local" : "nebius" }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Serverless smoke demo failed"));
  }
  return response.json();
}

export async function finalizeServerlessSmokeDemo(
  experimentId: string,
  tournamentId: string
): Promise<ServerlessSmokeFinalizeResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/nebius/serverless-smoke/${encodeURIComponent(experimentId)}/finalize/${encodeURIComponent(tournamentId)}`,
    { method: "POST" }
  );
  if (!response.ok) {
    throw new Error(await apiErrorMessage(response, "Serverless smoke finalization failed"));
  }
  return response.json();
}

function defaultAIInvestigationTeamRequest(): AIInvestigationTeamRequest {
  return {
    detector_outputs: [
      {
        confidence: 0.91,
        detected_pattern: "spoofing_like_wall",
        detector: "SpoofingWallDetector",
        evidence: ["large visible wall", "rapid cancel before execution"],
        suspicion_score: 0.88
      }
    ],
    incident: {
      confidence: 0.91,
      incident_id: "INC-DEMO-042",
      scenario_family: "spoofing_like_wall",
      severity: "high",
      tick: 42,
      title: "Synthetic spoofing wall detected",
      type: "spoofing"
    },
    market_metrics: {
      cancel_to_trade_ratio: 5.4,
      depth_change_pct: 0.38,
      imbalance: 0.72,
      message_rate: 21,
      wall_size_ratio: 8.2
    },
    order_book_context: {
      asks: [{ owner: "normal", price: 68130, quantity: 1.8 }],
      bids: [{ owner: "abuser", price: 68120, quantity: 12.4 }],
      events: [
        { agent_id: "ABUSER_01", stage: "place_wall", tick: 40, type: "quote" },
        { agent_id: "ABUSER_01", stage: "cancel_wall", tick: 42, type: "cancel" }
      ]
    },
    trades: [
      { agent_id: "TAKER_01", price: 68125, quantity: 0.4, side: "buy", tick: 41 }
    ]
  };
}

export async function generateNebiusAttackScenario(input: AttackScenarioInput): Promise<AttackScenario> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/attack-scenario`, {
    body: JSON.stringify(input),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Attack scenario generation failed: ${response.status}`);
  }
  return response.json();
}

export async function listNebiusAttackScenarios(): Promise<AttackScenario[]> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/attack-scenarios`);
  if (!response.ok) {
    throw new Error(`Attack scenario list failed: ${response.status}`);
  }
  return response.json();
}

export async function generateNebiusAttackVariants(input: AttackScenarioInput, count = 10): Promise<AttackScenario[]> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/attack-scenario/variants`, {
    body: JSON.stringify({ count, input }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Attack variants generation failed: ${response.status}`);
  }
  return response.json();
}

export async function injectNebiusAttackScenario(scenarioId: string): Promise<ScenarioActionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/attack-scenario/${encodeURIComponent(scenarioId)}/inject`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Attack injection failed: ${response.status}`);
  }
  return response.json();
}

export async function saveNebiusAttackTemplate(scenarioId: string): Promise<ScenarioActionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/attack-scenario/${encodeURIComponent(scenarioId)}/template`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Scenario template save failed: ${response.status}`);
  }
  return response.json();
}

export async function generateNebiusScenarioGrid(config: ScenarioGridConfig, sourceAttackScenarioId?: string | null): Promise<GeneratedScenario[]> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/scenario-grid`, {
    body: JSON.stringify({ ...config, sourceAttackScenarioId }),
    headers: { "Content-Type": "application/json" },
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Scenario grid generation failed: ${response.status}`);
  }
  return response.json();
}

export async function saveNebiusEvidenceBundle(): Promise<ExperimentArtifact> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/evidence-bundle`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Evidence bundle save failed: ${response.status}`);
  }
  return response.json();
}

export async function exportNebiusDataset(): Promise<ExperimentArtifact> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/dataset-export`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Dataset export failed: ${response.status}`);
  }
  return response.json();
}

export async function generateNebiusTrainingData(): Promise<ExperimentArtifact> {
  const response = await fetch(`${API_BASE_URL}/api/nebius/training-data`, {
    method: "POST"
  });
  if (!response.ok) {
    throw new Error(`Training data generation failed: ${response.status}`);
  }
  return response.json();
}

async function apiErrorMessage(response: Response, prefix: string): Promise<string> {
  try {
    const payload = await response.json() as { detail?: unknown };
    const detail = formatApiErrorDetail(payload.detail);
    if (detail) {
      return `${prefix}: ${response.status} - ${detail}`;
    }
  } catch {
    // Fall back to status-only errors when the response is not JSON.
  }
  return `${prefix}: ${response.status}`;
}

function formatApiErrorDetail(detail: unknown): string | null {
  if (typeof detail === "string") {
    return detail.trim() || null;
  }
  if (Array.isArray(detail)) {
    const values = detail.map(formatApiErrorDetail).filter(Boolean);
    return values.length ? values.join("; ") : null;
  }
  if (detail && typeof detail === "object") {
    const record = detail as Record<string, unknown>;
    const message = formatApiErrorDetail(record.message);
    const stderr = formatApiErrorDetail(record.stderr);
    const stdout = formatApiErrorDetail(record.stdout);
    return [message, stderr && `stderr: ${stderr}`, stdout && `stdout: ${stdout}`].filter(Boolean).join(" - ") || null;
  }
  return null;
}
