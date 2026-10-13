import type { Page } from "@playwright/test";
import { campaign, pageFor } from "./ceo-journey.fixture";

// Every normal API and Arena socket is intercepted; no backend or workload runs.
export async function mockProductApi(page: Page) {
  const requests: string[] = [], commands: string[] = [];
  await page.routeWebSocket("**/ws/arena", socket => socket.onMessage(message => commands.push(String(message))));
  await page.route(/^https?:\/\/[^/]+\/api\//, route => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    if (path === "/api/nebius/status") return route.fulfill({ json: {
      endpoint_base_url_configured: false, endpoint_health: { status: "not_configured" },
      job_health: { status: "not_configured" }, storage_health: { status: "not_configured" },
      runner_health: { status: "not_configured" }, investigation_team_configured: false,
      incident_explainer_configured: false, model: "fixture deterministic mock"
    } });
    if (path === "/api/nebius/observatory") return route.fulfill({ json: {
      endpoint_mode: "mock", endpoint_health: { status: "not_configured" }, job_health: { status: "not_configured" },
      storage_health: { status: "not_configured" }, usage: {}, runtime_health: [], capabilities: []
    } });
    if (path === "/api/experiments/reports") return route.fulfill({ json: { nebius_batches: [] } });
    if (["/api/nebius/evidence", "/api/experiments", "/api/arena/historical-datasets", "/api/arena/market-profiles",
      "/api/data-ingestion/sources/lobster/candidates", "/api/data-ingestion/sources/nasdaq_itch/candidates",
      "/api/data-ingestion/datasets"].includes(path)) return route.fulfill({ json: [] });
    if (path === "/api/research/saved-scores/campaigns") return route.fulfill({ json: campaign });
    if (path.endsWith("/rows") && path.startsWith("/api/research/saved-scores/")) {
      return route.fulfill({ json: pageFor(new URL(route.request().url()).searchParams.get("detector")!) });
    }
    return route.fulfill({ status: 404, json: { detail: `Unhandled inert product route: ${path}` } });
  });
  return { requests, commands };
}
