import { expect, test, type Page, type Route } from "@playwright/test";

type ApiState = {
  candidates?: Record<string, unknown>[];
  datasets?: Record<string, unknown>[];
  deletedDatasets?: string[];
  experiment?: ReturnType<typeof experimentFixture> | null;
  importRequests?: Record<string, unknown>[];
  jobs?: Record<string, unknown>[];
  leaderboard?: Record<string, unknown>[];
  localRun?: (route: Route) => Promise<void>;
  scenarioRequests?: Record<string, unknown>[];
  submitCalls?: number;
  summary?: Record<string, unknown> | null;
};

function experimentFixture(overrides: Record<string, unknown> = {}) {
  return {
    artifact_dir: "/tmp/EXP-SEEDED",
    artifact_paths: {},
    attack_count: 24,
    batch_size: 6,
    created_at: "2026-07-16T10:00:00Z",
    id: "EXP-SEEDED",
    metrics: [],
    name: "Seeded surveillance run",
    nebius_mode: "local_parallel_batch",
    scenarios: ["spoofing_like_wall", "layering_like"],
    seed: 424242,
    status: "manifest_generated",
    updated_at: "2026-07-16T10:00:00Z",
    ...overrides
  };
}

function jobFixture(overrides: Record<string, unknown> = {}) {
  return {
    artifact_paths: {},
    attack_count: 24,
    backend: "local_parallel_batch",
    batch_end: 24,
    batch_start: 0,
    created_at: "2026-07-16T10:01:00Z",
    experiment_id: "EXP-SEEDED",
    job_id: "JOB-LOCAL-1",
    message: "Completed deterministic batch.",
    status: "completed",
    updated_at: "2026-07-16T10:02:00Z",
    ...overrides
  };
}

async function mockApi(page: Page, state: ApiState = {}) {
  state.candidates ??= [];
  state.datasets ??= [];
  state.deletedDatasets ??= [];
  state.importRequests ??= [];
  state.jobs ??= [];
  state.leaderboard ??= [];
  state.scenarioRequests ??= [];
  state.submitCalls ??= 0;

  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();
    const json = (body: unknown, status = 200) => route.fulfill({
      body: JSON.stringify(body),
      contentType: "application/json",
      status
    });

    if (path === "/api/data-ingestion/lobster/candidates" && method === "GET") {
      return json(state.candidates);
    }
    const candidateImport = path.match(/^\/api\/data-ingestion\/lobster\/candidates\/([^/]+)\/import$/);
    if (candidateImport && method === "POST") {
      state.importRequests?.push(request.postDataJSON() as Record<string, unknown>);
      return json({ candidate_id: candidateImport[1], dataset_id: null, status: "importing" }, 202);
    }
    if (path === "/api/data-ingestion/datasets" && method === "GET") {
      return json(state.datasets);
    }
    const datasetDelete = path.match(/^\/api\/data-ingestion\/datasets\/([^/]+)$/);
    if (datasetDelete && method === "DELETE") {
      const datasetId = decodeURIComponent(datasetDelete[1]);
      state.deletedDatasets?.push(datasetId);
      state.datasets = state.datasets?.filter((dataset) => dataset.dataset_id !== datasetId);
      return route.fulfill({ status: 204 });
    }

    if (path === "/api/nebius/status") {
      return json({
        api_key_configured: true,
        checked_at: "2026-07-16T10:00:00Z",
        cli_installed: true,
        endpoint_base_url: "https://mock.nebius.example",
        endpoint_base_url_configured: true,
        endpoint_health: { status: "healthy" },
        endpoint_token_configured: true,
        incident_explainer_configured: true,
        investigation_report_configured: true,
        investigation_team_configured: true,
        job_artifacts_collection_configured: true,
        job_health: { status: "healthy" },
        job_image: "registry.example/lob-arena:test",
        job_logs_template_configured: true,
        job_resource_configured: true,
        job_status_template_configured: true,
        job_submit_template_configured: true,
        market_abuse_scenario_configured: true,
        model: "mock-model",
        orderbook_alert_configured: true,
        runner_health: { status: "healthy" },
        scenario_generator_configured: true,
        storage_health: { status: "healthy" },
        tenant_id_configured: true
      });
    }
    if (path === "/api/nebius/observatory") {
      return json({
        adapter: { mode: "mock", name: "test", replacement_target: "none" },
        benchmark_artifacts: {},
        capabilities: [],
        checked_at: "2026-07-16T10:00:00Z",
        endpoint_base_url_configured: true,
        endpoint_health: { status: "healthy" },
        endpoint_mode: "mock",
        job_health: { status: "healthy" },
        orderbook_alert_configured: true,
        runtime_health: [],
        screenshots: [],
        storage_health: { status: "healthy" },
        usage: {
          endpoint_avg_latency_seconds: 0,
          endpoint_purpose: "test",
          endpoint_requests: 0,
          evidence_status: "mock",
          job_artifacts: [],
          job_output_files: 0,
          job_runtime: "0s",
          job_simulations: 0
        }
      });
    }
    if (path === "/api/nebius/evidence") return json([]);
    if (path === "/api/experiments/reports") return json({ nebius_batches: [] });

    if (path === "/api/nebius/scenario-generator/generate" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      state.scenarioRequests?.push(payload);
      const seed = Number(payload.seed);
      return json({
        description: `Deterministic scenario generated from seed ${seed}.`,
        difficulty: payload.difficulty,
        duration_ticks: payload.duration_ticks,
        endpoint: "mock",
        events: [{
          agent_id: "ABUSER_SEEDED",
          event_id: `event-${seed}`,
          event_type: "place_order",
          message: "Seeded wall placed",
          scenario_family: payload.manipulation_type,
          scenario_id: `SCN-${seed}`,
          scenario_name: payload.manipulation_type,
          stage: "wall_placed",
          symbol: payload.symbol,
          tick: 12,
          type: "limit_order"
        }],
        expected_detector_behavior: {
          expected_risk_score: 0.91,
          false_positive_risk: "low",
          primary_signals: ["wall_size_ratio"]
        },
        explanation: "Deterministic fixture",
        ground_truth: {
          expected_detector_targets: ["spoofing_like"],
          label: payload.manipulation_type,
          manipulation_windows: [{ end_tick: 30, start_tick: 10 }],
          manipulator_agent_ids: ["ABUSER_SEEDED"],
          positive_event_ids: [`event-${seed}`]
        },
        liquidity_regime: payload.liquidity_regime,
        manipulation_type: payload.manipulation_type,
        mode: "mock",
        replay: { route: "/arena", supported: true },
        scenario_id: `SCN-${seed}`,
        source: { seed },
        symbol: payload.symbol,
        title: `Seeded scenario ${seed}`,
        volatility_regime: payload.volatility_regime
      });
    }

    if (path === "/api/experiments" && method === "GET") {
      return json(state.experiment ? [state.experiment] : []);
    }
    if (path === "/api/experiments" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      state.experiment = experimentFixture({
        attack_count: payload.attack_count,
        batch_size: payload.batch_size,
        name: payload.name,
        scenarios: payload.scenarios,
        seed: payload.seed,
        status: "draft"
      });
      return json(state.experiment);
    }

    const experimentPath = path.match(/^\/api\/experiments\/([^/]+)(?:\/(.+))?$/);
    if (experimentPath) {
      const action = experimentPath[2];
      if (!action && method === "GET") return json(state.experiment ?? experimentFixture());
      if (action === "jobs" && method === "GET") return json(state.jobs);
      if (action === "summary" && method === "GET") {
        return state.summary ? json(state.summary) : json({ detail: "not aggregated" }, 404);
      }
      if (action === "leaderboard" && method === "GET") return json(state.leaderboard);
      if (action === "investigations" && method === "GET") return json([]);
      if (action === "run-local-batch" && method === "POST") {
        if (state.localRun) return state.localRun(route);
        return json({
          artifact_paths: {},
          batch_size: 6,
          created_at: "2026-07-16T10:02:00Z",
          elapsed_seconds: 1.2,
          experiment_id: "EXP-SEEDED",
          id: "BATCH-1",
          metrics: [],
          mode: "local_parallel_batch",
          runs: 24,
          scenarios: ["spoofing_like_wall"],
          status: "completed"
        });
      }
      if (action === "submit-nebius" && method === "POST") {
        state.submitCalls = (state.submitCalls ?? 0) + 1;
        const submitted = jobFixture({
          backend: "nebius_serverless_job",
          job_id: "JOB-CLOUD-1",
          message: "Submitted to Nebius Cloud.",
          status: "running"
        });
        state.jobs = [submitted];
        return json(submitted);
      }
    }

    return json({ detail: `Unhandled test route: ${method} ${path}` }, 404);
  });
}

async function openWorkflowStep(page: Page, name: string) {
  const tab = page.getByRole("tab", { name: new RegExp(name) });
  await expect(tab).toBeEnabled();
  await tab.click();
}

function contrastRatio(foreground: string, background: string) {
  const channelValues = (color: string) => (color.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
  const luminance = (color: string) => {
    const channels = channelValues(color).map((value) => {
      const normalized = value / 255;
      return normalized <= 0.03928 ? normalized / 12.92 : ((normalized + 0.055) / 1.055) ** 2.4;
    });
    return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
  };
  const first = luminance(foreground);
  const second = luminance(background);
  return (Math.max(first, second) + 0.05) / (Math.min(first, second) + 0.05);
}

test("sidebar curtain and Local/Cloud chooser stay usable when expanded and collapsed", async ({ page }) => {
  await mockApi(page);
  await page.setViewportSize({ height: 900, width: 1440 });
  await page.goto("/arena?demo=real");

  const sidebar = page.getByRole("complementary", { name: "Application navigation" });
  const workspace = page.locator(".app-workspace");
  const runtimeButton = page.locator(".runtime-status-pill");
  const expandedSidebar = await sidebar.boundingBox();
  const expandedWorkspace = await workspace.boundingBox();
  expect(expandedSidebar?.height).toBe(900);
  expect(expandedWorkspace!.x).toBeGreaterThanOrEqual(expandedSidebar!.x + expandedSidebar!.width);

  await runtimeButton.click();
  let dialog = page.getByRole("dialog", { name: "Runtime mode selection" });
  await expect(dialog).toBeVisible();
  let dialogBox = await dialog.boundingBox();
  expect(dialogBox!.x).toBeGreaterThanOrEqual(expandedSidebar!.x + expandedSidebar!.width - 1);
  expect(dialogBox!.x + dialogBox!.width).toBeLessThanOrEqual(1440);
  await expect(dialog.getByRole("button", { name: "Local Demo", exact: true })).toHaveAttribute("aria-pressed", "true");

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await page.getByRole("button", { name: "Collapse navigation" }).click();
  const collapsedSidebar = await sidebar.boundingBox();
  expect(collapsedSidebar!.width).toBeLessThanOrEqual(80);
  await expect(page.locator(".sidebar-wordmark")).toBeHidden();
  await expect(page.locator(".side-nav .nav-label").first()).toBeHidden();
  const collapsedWorkspace = await workspace.boundingBox();
  expect(collapsedWorkspace!.x).toBeGreaterThanOrEqual(collapsedSidebar!.x + collapsedSidebar!.width);

  await runtimeButton.click();
  dialog = page.getByRole("dialog", { name: "Runtime mode selection" });
  dialogBox = await dialog.boundingBox();
  expect(dialogBox!.width).toBeGreaterThan(500);
  expect(dialogBox!.x + dialogBox!.width).toBeLessThanOrEqual(1440);
  await dialog.getByRole("button", { name: "Nebius Cloud", exact: true }).click();
  await expect(runtimeButton).toContainText("Nebius Cloud");
  await expect.poll(() => page.evaluate(() => localStorage.getItem("lob-arena.runtimeMode"))).toBe("nebius-cloud");
  await dialog.getByRole("button", { name: "Close runtime mode selection" }).click();
  await page.getByRole("button", { name: "Expand navigation" }).click();
  await expect(page.locator(".sidebar-wordmark")).toBeVisible();
  await expect(page.locator(".side-nav .nav-label").first()).toBeVisible();
  const restoredSidebar = await sidebar.boundingBox();
  expect(restoredSidebar!.width).toBe(292);

  await page.setViewportSize({ height: 900, width: 900 });
  expect((await sidebar.boundingBox())!.width).toBe(292);
  await page.getByRole("button", { name: "Collapse navigation" }).click();
  expect((await sidebar.boundingBox())!.width).toBeLessThanOrEqual(80);
  await page.getByRole("button", { name: "Expand navigation" }).click();

  await page.setViewportSize({ height: 900, width: 620 });
  const mobileExpandedHeight = (await sidebar.boundingBox())!.height;
  await page.getByRole("button", { name: "Collapse navigation" }).click();
  await expect(page.getByRole("navigation", { name: "Main screens" })).toBeHidden();
  await expect(page.getByLabel("Runtime and safety controls")).toBeHidden();
  expect((await sidebar.boundingBox())!.height).toBeLessThan(mobileExpandedHeight);
  await page.getByRole("button", { name: "Expand navigation" }).click();
  await expect(page.getByRole("navigation", { name: "Main screens" })).toBeVisible();
});

test("day and night palettes keep sidebar text and buttons consistent", async ({ page }) => {
  await mockApi(page);
  await page.goto("/arena?demo=real");

  const sidebar = page.getByRole("complementary", { name: "Application navigation" });
  const wordmark = page.locator(".sidebar-wordmark strong");
  const primary = page.getByRole("button", { name: "Send to Nebius investigation" });
  const secondary = page.getByRole("button", { name: "Disclaimer" });

  await page.getByTitle("Light").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  const light = await page.evaluate(() => {
    const styles = (selector: string) => {
      const computed = getComputedStyle(document.querySelector(selector)!);
      return {
        backgroundColor: computed.backgroundColor,
        backgroundImage: computed.backgroundImage,
        color: computed.color
      };
    };
    return {
      primary: styles(".primary-link-button"),
      secondary: styles(".disclaimer-popover-button"),
      sidebar: styles(".app-sidebar"),
      wordmark: styles(".sidebar-wordmark strong")
    };
  });
  expect(light.sidebar.backgroundColor).toBe("rgb(248, 250, 252)");
  expect(light.wordmark.color).toBe("rgb(23, 32, 51)");
  expect(contrastRatio(light.wordmark.color, light.sidebar.backgroundColor)).toBeGreaterThanOrEqual(4.5);
  expect(light.primary.color).toBe("rgb(255, 255, 255)");
  expect(light.primary.backgroundImage).toContain("linear-gradient");
  await expect(primary).toBeVisible();
  await expect(secondary).toBeVisible();

  await page.getByTitle("Dark").click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const dark = await page.evaluate(() => {
    const styles = (selector: string) => {
      const computed = getComputedStyle(document.querySelector(selector)!);
      return {
        backgroundColor: computed.backgroundColor,
        backgroundImage: computed.backgroundImage,
        color: computed.color
      };
    };
    return {
      primary: styles(".primary-link-button"),
      secondary: styles(".disclaimer-popover-button"),
      sidebar: styles(".app-sidebar"),
      wordmark: styles(".sidebar-wordmark strong")
    };
  });
  expect(dark.sidebar.backgroundColor).toBe("rgb(7, 11, 22)");
  expect(dark.wordmark.color).toBe("rgb(248, 250, 252)");
  expect(contrastRatio(dark.wordmark.color, dark.sidebar.backgroundColor)).toBeGreaterThanOrEqual(4.5);
  expect(dark.primary.color).toBe("rgb(255, 255, 255)");
  expect(dark.primary.backgroundImage).toContain("linear-gradient");
  expect(dark.primary.backgroundImage).not.toBe(light.primary.backgroundImage);
  expect(dark.secondary.backgroundColor).not.toBe(light.secondary.backgroundColor);
  await expect(sidebar).toHaveCSS("background-color", "rgb(7, 11, 22)");
  await expect(wordmark).toHaveCSS("color", "rgb(248, 250, 252)");
});

test("simulation configuration sends the same deterministic request for a fixed seed", async ({ page }) => {
  const state: ApiState = { scenarioRequests: [] };
  await mockApi(page, state);
  await page.goto("/nebius");
  await openWorkflowStep(page, "Scenario Generator");

  await page.getByLabel("Manipulation type").selectOption("layering_like");
  await page.getByLabel("Difficulty").selectOption("hard");
  await page.getByLabel("Symbol").fill("seedx");
  await page.getByLabel("Duration (ticks)").fill("180");
  await page.getByRole("combobox", { name: "Liquidity", exact: true }).selectOption("deep");
  await page.getByRole("combobox", { name: "Volatility", exact: true }).selectOption("low");
  await page.getByLabel("Fixed seed").fill("8675309");

  const generate = page.getByRole("button", { name: "Generate AI Scenario" });
  await generate.click();
  await expect(page.getByRole("heading", { name: "Seeded scenario 8675309", exact: true })).toBeVisible();
  await expect(page.getByText("tick 12: Seeded wall placed")).toBeVisible();
  await generate.click();
  await expect.poll(() => state.scenarioRequests?.length).toBe(2);
  expect(state.scenarioRequests?.[0]).toEqual(state.scenarioRequests?.[1]);
  expect(state.scenarioRequests?.[0]).toMatchObject({
    difficulty: "hard",
    duration_ticks: 180,
    liquidity_regime: "deep",
    manipulation_type: "layering_like",
    seed: 8675309,
    symbol: "SEEDX",
    volatility_regime: "low"
  });
});

test("serverless run submission enters a visible in-progress state", async ({ page }) => {
  const state: ApiState = { experiment: experimentFixture() };
  await mockApi(page, state);
  await page.goto("/nebius");

  await page.locator(".runtime-status-pill").click();
  await page.getByRole("dialog", { name: "Runtime mode selection" })
    .getByRole("button", { name: "Nebius Cloud", exact: true })
    .click();
  await openWorkflowStep(page, "Detector Tournament");
  const submit = page.getByRole("button", { name: "Run serverless job", exact: true });
  await expect(submit).toBeEnabled();
  await submit.click();

  await expect.poll(() => state.submitCalls).toBe(1);
  await expect(page.getByText("pending cloud job execution: Submitted to Nebius Cloud.")).toBeVisible();
  await expect(page.getByRole("cell", { name: "JOB-CLOUD-1" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "running" })).toBeVisible();
  await expect(submit).toBeDisabled();
});

test("local run exposes progress and recovers from an API error", async ({ page }) => {
  let releaseRun: (() => void) | undefined;
  const state: ApiState = {
    experiment: experimentFixture(),
    localRun: async (route) => {
      await new Promise<void>((resolve) => {
        releaseRun = resolve;
      });
      await route.fulfill({
        body: JSON.stringify({ detail: "worker capacity exhausted" }),
        contentType: "application/json",
        status: 503
      });
    }
  };
  await mockApi(page, state);
  await page.goto("/nebius");
  await openWorkflowStep(page, "Detector Tournament");

  const run = page.getByRole("button", { name: "Run Local Demo tournament" });
  await run.click();
  await expect(page.getByText(/Running the tournament in an isolated/)).toBeVisible();
  await expect(run).toBeDisabled();
  await expect.poll(() => Boolean(releaseRun)).toBe(true);
  releaseRun?.();

  await expect(page.getByText("Run experiment local batch failed: 503")).toBeVisible();
  await expect(run).toBeEnabled();
});

test("completed results render status, alert, failure, and detector metrics", async ({ page }) => {
  const state: ApiState = {
    experiment: experimentFixture({
      artifact_paths: { alerts: "/tmp/alerts.json", detector_metrics: "/tmp/metrics.json" },
      status: "completed"
    }),
    jobs: [jobFixture()],
    leaderboard: [{
      alert_count: 37,
      avg_detection_latency_ms: 18,
      detector: "spoofing_like_detector",
      f1: 0.912,
      model: "rules_v2",
      precision: 0.934,
      recall: 0.891,
      scenario: "spoofing_like_wall"
    }],
    summary: {
      artifact_paths: { detector_metrics: "/tmp/metrics.json" },
      experiment_id: "EXP-SEEDED",
      f1_by_scenario: { spoofing_like_wall: 0.912 },
      failed_runs: 2,
      investigation_count: 4,
      precision_by_scenario: { spoofing_like_wall: 0.934 },
      recall_by_scenario: { spoofing_like_wall: 0.891 },
      scenarios: ["spoofing_like_wall"],
      total_alerts: 37,
      total_attacks: 24
    }
  };
  await mockApi(page, state);
  await page.goto("/nebius");
  await openWorkflowStep(page, "Detector Tournament");

  const lab = page.locator(".experiment-lab-panel");
  await expect(lab.locator(".runtime-metric").filter({ hasText: "Status" })).toContainText("completed");
  await expect(lab.locator(".runtime-metric").filter({ hasText: "Jobs" })).toContainText("1/1 done");
  await expect(lab.locator(".runtime-metric").filter({ hasText: "Alerts" })).toContainText("37");
  await expect(lab.locator(".runtime-metric").filter({ hasText: "Failed runs" })).toContainText("2");
  await expect(lab.locator(".runtime-metric").filter({ hasText: "Seed" })).toContainText("424242");
  await expect(page.getByRole("cell", { name: "spoofing like detector" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "0.912" })).toBeVisible();
  await expect(page.getByRole("cell", { name: "18 ms" })).toBeVisible();
});

test("attack tracker and market timeline visualize attack events", async ({ page }) => {
  await mockApi(page);
  await page.goto("/arena?demo=real");

  await expect(page.getByRole("heading", { name: "Attack Tracker" })).toBeVisible();
  await expect(page.locator(".attack-stage.active")).toContainText("Armed");
  await page.getByRole("button", { name: "Market Timeline" }).click();
  const markers = page.getByLabel("Timeline attack markers");
  await expect(markers).toContainText("attack started");
  await expect(markers).toContainText("detector warning");
  await expect(markers).toContainText("T0");
  await expect(page.getByRole("img", { name: "Mid price, spread bps, and imbalance timeline" })).toBeVisible();
  await expect(markers).toContainText("incident confirmed", { timeout: 7_000 });
});

test("liquidity heatmap dialog traps focus and restores it when closed", async ({ page }) => {
  await mockApi(page);
  await page.goto("/arena?demo=real");

  const expand = page.getByRole("button", { name: "Expand liquidity heatmap" });
  await expand.focus();
  await expand.click();

  const dialog = page.getByRole("dialog", { name: "Liquidity Heatmap" });
  const close = dialog.getByRole("button", { name: "Close expanded liquidity heatmap" });
  await expect(dialog).toBeVisible();
  await expect(page.locator("#root")).toHaveAttribute("inert", "");
  await expect(close).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(close).toBeFocused();

  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(page.locator("#root")).not.toHaveAttribute("inert", "");
  await expect(expand).toBeFocused();
});

test("data ingestion accepts custom minutes and deletes a confirmed dataset", async ({ page }) => {
  const state: ApiState = {
    candidates: [{
      candidate_id: "candidate-1",
      dataset_id: null,
      depth: 10,
      end_time: "10:30:00.000",
      end_time_ms: 37_800_000,
      errors: [],
      message_file: "message.csv",
      message_file_size: 100,
      orderbook_file: "orderbook.csv",
      orderbook_file_size: 200,
      start_time: "09:30:00.000",
      start_time_ms: 34_200_000,
      status: "ready",
      symbol: "SPY",
      trade_date: "2012-06-21"
    }],
    datasets: [{
      dataset_id: "dataset-stale",
      depth: 10,
      end_time: "09:35:00.000",
      end_time_ms: 34_500_000,
      event_counts: {},
      imported_at: "2026-07-27T13:00:00Z",
      path: "/data/processed/lobster/dataset-stale",
      row_count: 100,
      source_type: "lobster",
      start_time: "09:30:00.000",
      start_time_ms: 34_200_000,
      symbol: "SPY",
      trade_date: "2012-06-21"
    }]
  };
  await mockApi(page, state);
  await page.goto("/data-ingestion");

  await page.getByLabel("Import duration for SPY").selectOption("custom");
  await page.getByLabel("Import duration in minutes for SPY").fill("17");
  await expect(page.getByText("09:30:00–09:47:00")).toBeVisible();
  await page.getByRole("button", { name: "Import window" }).click();
  await expect.poll(() => state.importRequests?.length).toBe(1);
  expect(state.importRequests?.[0]).toEqual({
    end_time_ms: 35_220_000,
    start_time_ms: 34_200_000
  });

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete dataset" }).click();
  await expect.poll(() => state.deletedDatasets).toEqual(["dataset-stale"]);
  await expect(page.getByText("dataset-stale")).toBeHidden();
});
