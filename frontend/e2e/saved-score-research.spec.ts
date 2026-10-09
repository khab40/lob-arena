import { expect, test, type Page, type Route } from "@playwright/test";

// Small, invented API responses. Never copy private retained row evidence here.
const sessionId = "0123456789abcdef";
const secondSessionId = "fedcba9876543210";
const provenance = {
  verification_sha256: "a".repeat(64), settings_sha256: "b".repeat(64), job_id: "TEST-JOB",
  request_sha256: "c".repeat(64), model_checkpoint_sha256: "d".repeat(64),
  predictions: { sha256: "e".repeat(64), size_bytes: 123, version_id: "1" }
};
function catalog(total = 3, mixed = false) {
  return {
    kind: "saved_research_predictions", campaign_id: "december-holdout-20261007",
    label_context: "synthetic_research_labels", limitations: ["Invented test evidence; no production qualification."],
    provenance, detectors: [{ id: "transformer", threshold: 0.7, mode: "balanced" }, { id: "lightgbm", threshold: 0.6, mode: "balanced" }],
    sessions: [sessionId, secondSessionId].map((id) => ({
      id, rows: total, symbol: "TEST", family: mixed ? "mixed" : "test_family",
      families: mixed ? ["control", "test_attack"] : ["test_family"]
    }))
  };
}
function rows(url: URL, total = 3, mixed = false) {
  const offset = Number(url.searchParams.get("offset"));
  const detector = url.searchParams.get("detector");
  const session = url.searchParams.get("session_id");
  const threshold = detector === "transformer" ? 0.7 : 0.6;
  const count = Math.min(100, total - offset);
  return {
    campaign_id: "december-holdout-20261007", session_id: session, detector, threshold, mode: "balanced",
    total, offset, next_offset: offset + count < total ? offset + count : null, provenance,
    rows: Array.from({ length: count }, (_, index) => {
      const ordinal = offset + index;
      const probability = mixed ? ordinal >= 100 ? 0.9 : 0.2 : ordinal % 2 ? 0.9 : detector === "lightgbm" ? 0.3 : 0.2;
      return { ordinal, source_ordinal: ordinal + 50, target_id: `test-${session}-${ordinal}`,
        timestamp_ns: "9007199254740993123", symbol: "TEST", family: mixed ? ordinal < 100 ? "control" : "test_attack" : "test_family",
        synthetic_label: mixed ? ordinal >= 100 ? 1 : 0 : ordinal % 2, probability, alert: probability >= threshold };
    })
  };
}
async function mockSaved(page: Page, options: {
  total?: number; missing?: boolean; corrupt?: boolean; unavailableDetector?: boolean; mixed?: boolean;
  pageResponse?: (route: Route, url: URL) => Promise<void>;
} = {}) {
  const requests: URL[] = [];
  const sockets: string[] = [];
  page.on("websocket", (socket) => sockets.push(socket.url()));
  await page.route(/^https?:\/\/[^/]+\/api\//, async (route) => {
    const url = new URL(route.request().url()); requests.push(url);
    const json = (body: unknown, status = 200) => route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
    if (url.pathname === "/api/research/saved-scores/campaigns") {
      if (options.missing) return json({ detail: "Disabled" }, 404);
      const value = catalog(options.total, options.mixed);
      if (options.unavailableDetector) value.detectors = value.detectors.filter((item) => item.id !== "lightgbm");
      return json(value);
    }
    if (url.pathname === "/api/research/saved-scores/campaigns/december-holdout-20261007/rows") {
      if (options.pageResponse) return options.pageResponse(route, url);
      const value = rows(url, options.total, options.mixed);
      if (options.corrupt) value.provenance = { ...provenance, verification_sha256: "f".repeat(64) };
      return json(value);
    }
    return json({ detail: "Unexpected test request" }, 500);
  });
  return { requests, sockets };
}

test("saved playback starts paused, pauses, resumes and resets on detector selection", async ({ page }) => {
  await page.clock.install();
  await page.addInitScript(() => { window.localStorage.setItem("lob-arena.runtimeMode", "nebius-cloud"); });
  const observed = await mockSaved(page);
  await page.goto("/research-predictions");
  const play = page.getByRole("button", { name: "Play", exact: true });
  await expect(play).toBeEnabled();
  await expect(page.getByRole("status")).toContainText("Paused · 0 / 3 rows");
  await expect(page.getByRole("cell", { name: "9007199254740993123", exact: true })).toHaveCount(0);
  await play.click();
  await page.clock.runFor(1001);
  await expect(page.getByRole("status")).toContainText("1 / 3 rows");
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  await page.clock.runFor(5000);
  await expect(page.getByRole("status")).toContainText("Paused · 1 / 3 rows");
  await page.getByLabel("Playback speed").selectOption("20");
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  await page.clock.runFor(101);
  await expect(page.getByRole("status")).toContainText("Playback complete · 3 / 3 rows");
  await expect(page.getByRole("cell", { name: "9007199254740993123", exact: true })).toHaveCount(3);
  await expect(page.getByText("Transformer checkpoint SHA-256", { exact: true })).toBeVisible();
  await expect(page.getByLabel("Research limitations")).toContainText("no production qualification");
  await page.getByRole("combobox", { name: "Detector", exact: true }).selectOption("lightgbm");
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeEnabled();
  await expect(page.getByRole("status")).toContainText("Paused · 0 / 3 rows");
  await expect(page.getByRole("cell", { name: "9007199254740993123", exact: true })).toHaveCount(0);
  await page.locator(".runtime-status-pill").click();
  await expect(page.getByRole("dialog", { name: "Runtime mode selection" }).getByRole("button", { name: "Test", exact: true })).toBeDisabled();
  expect(observed.requests.every((url) => url.pathname.startsWith("/api/research/saved-scores/"))).toBe(true);
  // Vite's local HMR socket uses "/"; saved playback must not open Arena sockets.
  expect(observed.sockets.filter((url) => new URL(url).pathname !== "/")).toEqual([]);
});

test("mixed control and attack pages preserve order through completion with a 20-row table", async ({ page }) => {
  await page.clock.install();
  const observed = await mockSaved(page, { total: 102, mixed: true });
  await page.goto("/research-predictions");
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeEnabled();
  await page.getByLabel("Playback speed").selectOption("20");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(async () => {
    await page.clock.runFor(500);
    return page.getByRole("status").innerText();
  }, { timeout: 10000, intervals: [20] }).toContain("Playback complete · 102 / 102 rows");
  const pageRequests = observed.requests.filter((url) => url.pathname.endsWith("/rows"));
  expect(pageRequests.map((url) => url.searchParams.get("offset"))).toEqual(["0", "100"]);
  expect(pageRequests.every((url) => url.searchParams.get("limit") === "100")).toBe(true);
  await expect(page.locator("tbody tr")).toHaveCount(20);
  await expect(page.locator("tbody tr").first().getByRole("cell").first()).toHaveText("82");
  await expect(page.locator("tbody tr").last().getByRole("cell").first()).toHaveText("101");
  await expect(page.getByText("Session family context: mixed research families", { exact: false })).toContainText("control, test_attack");
  await expect(page.getByRole("columnheader", { name: "Family", exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: "control", exact: true })).toHaveCount(18);
  await expect(page.getByRole("cell", { name: "test_attack", exact: true })).toHaveCount(2);
});

test("a stale session response cannot replace a newly selected session", async ({ page }) => {
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const observed = await mockSaved(page, { pageResponse: async (route, url) => {
    if (url.searchParams.get("session_id") === sessionId) await gate;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(rows(url)) });
  } });
  await page.goto("/research-predictions");
  await expect.poll(() => observed.requests.some((url) => url.searchParams.get("session_id") === sessionId)).toBe(true);
  await page.getByRole("combobox", { name: "Session", exact: true }).selectOption(secondSessionId);
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeEnabled();
  release();
  await page.getByLabel("Playback speed").selectOption("20");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect(page.getByRole("cell", { name: `test-${secondSessionId}-0`, exact: true })).toBeVisible();
  await expect(page.getByRole("cell", { name: `test-${sessionId}-0`, exact: true })).toHaveCount(0);
});

test("pause remains available while the next saved page is pending", async ({ page }) => {
  await page.clock.install();
  let release: () => void = () => {};
  const gate = new Promise<void>((resolve) => { release = resolve; });
  const observed = await mockSaved(page, { total: 102, pageResponse: async (route, url) => {
    if (url.searchParams.get("offset") === "100") await gate;
    await route.fulfill({ contentType: "application/json", body: JSON.stringify(rows(url, 102)) });
  } });
  await page.goto("/research-predictions");
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeEnabled();
  await page.getByLabel("Playback speed").selectOption("20");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect.poll(async () => {
    await page.clock.runFor(500);
    return observed.requests.some((url) => url.searchParams.get("offset") === "100");
  }, { timeout: 10000, intervals: [20] }).toBe(true);
  await expect(page.getByRole("button", { name: "Pause", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "Pause", exact: true }).click();
  release();
  await expect(page.getByRole("button", { name: "Resume", exact: true })).toBeEnabled();
  await page.clock.runFor(1000);
  await expect(page.getByRole("status")).toContainText("Paused · 100 / 102 rows");
  await page.getByRole("button", { name: "Resume", exact: true }).click();
  await page.clock.runFor(101);
  await expect(page.getByRole("status")).toContainText("Playback complete · 102 / 102 rows");
});

for (const options of [{ missing: true }, { corrupt: true }]) {
  test(`saved evidence fails closed for ${options.missing ? "disabled configuration" : "corrupt provenance"}`, async ({ page }) => {
    const observed = await mockSaved(page, options);
    await page.goto("/research-predictions");
    await expect(page.getByRole("alert")).toContainText(options.missing ? "unavailable" : "Invalid saved");
    await expect(page.locator("tbody tr")).toHaveCount(0);
    expect(observed.requests.every((url) => url.pathname.startsWith("/api/research/saved-scores/"))).toBe(true);
  });
}

test("a remote API configuration is refused before any API request", async ({ page }) => {
  await page.route("**/runtime-config.js", (route) => route.fulfill({
    contentType: "application/javascript",
    body: 'window.__LOB_ARENA_CONFIG__ = { VITE_API_BASE_URL: "https://example.test" };'
  }));
  const observed = await mockSaved(page);
  await page.goto("/research-predictions");
  await expect(page.getByRole("alert")).toContainText("loopback browser and API");
  expect(observed.requests).toEqual([]);
});

test("an unavailable detector clears prior rows and makes no fallback request", async ({ page }) => {
  const observed = await mockSaved(page, { unavailableDetector: true });
  await page.goto("/research-predictions");
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeEnabled();
  const before = observed.requests.length;
  await page.getByRole("combobox", { name: "Detector", exact: true }).selectOption("lightgbm");
  await expect(page.getByRole("status").filter({ hasText: "LightGBM is unavailable" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeDisabled();
  await expect(page.locator("tbody tr")).toHaveCount(0);
  expect(observed.requests).toHaveLength(before);
});

for (const path of ["/research-predictions", "/research-predictions/", "/ReSeArCh-PrEdIcTiOnS", "/RESEARCH-PREDICTIONS/", "/%72esearch-predictions"]) {
  test(`research route ${path} suppresses cloud probes and Test controls`, async ({ page }) => {
    await page.addInitScript(() => { window.localStorage.setItem("lob-arena.runtimeMode", "nebius-cloud"); });
    const observed = await mockSaved(page);
    await page.goto(path);
    await expect(page.getByRole("button", { name: "Play", exact: true })).toBeEnabled();
    await page.locator(".runtime-status-pill").click();
    await expect(page.getByRole("dialog", { name: "Runtime mode selection" }).getByRole("button", { name: "Test", exact: true })).toBeDisabled();
    expect(observed.requests.every((url) => url.pathname.startsWith("/api/research/saved-scores/"))).toBe(true);
  });
}
