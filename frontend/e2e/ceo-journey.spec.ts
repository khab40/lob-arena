import { expect, test, type Page } from "@playwright/test";
import { mockProductApi } from "./ceo-product.fixture";
import { campaign, evidence, explanation, pageFor, session, snapshot, summary } from "./ceo-journey.fixture";

async function prepare(page: Page, options: { unavailable?: boolean; saveFailure?: boolean; bounded?: boolean } = {}) {
  const product = await mockProductApi(page);
  let rowRequests = 0;
  let saved = false;
  let currentSession = session;
  await page.route("**/api/auth/session", route => route.fulfill({ json: currentSession }));
  await page.route("**/api/ceo-demo/**", route => {
    const url = new URL(route.request().url()), path = url.pathname.replace("/api/ceo-demo/", "");
    expect(route.request().headers().authorization).toBeUndefined();
    if (options.unavailable && path === "campaign") return route.fulfill({ status: 503, json: { detail: "/private/path" } });
    if (path === "campaign") return route.fulfill({ json: options.bounded ? { ...campaign, sessions: [{ ...campaign.sessions[0], rows: 20 }] } : campaign });
    if (path === "rows") { rowRequests++; const value = pageFor(url.searchParams.get("detector")!); return route.fulfill({ json: options.bounded ? { ...value, total: 20, next_offset: 2 } : value }); }
    if (path === "anomalies") {
      expect(route.request().postDataJSON()).toEqual({ detector: "transformer", target_id: snapshot.row.target_id });
      return route.fulfill({ json: snapshot });
    }
    if (path.endsWith("/explanation")) { expect(route.request().postDataJSON()).toEqual({}); return route.fulfill({ json: explanation }); }
    if (path.endsWith("/save")) {
      if (options.saveFailure) return route.fulfill({ status: 500, json: { detail: "/private/failed" } });
      saved = true; return route.fulfill({ json: evidence });
    }
    if (path === "evidence") return route.fulfill({ json: saved ? [summary] : [] });
    if (path.startsWith("evidence/")) return route.fulfill({ json: evidence });
    return route.fulfill({ status: 404, json: {} });
  });
  await page.goto("/research-predictions");
  return { product, rowRequests: () => rowRequests, replaceAccount: () => {
    currentSession = { ...session, user: { id: "second-user", email: "second@example.com", name: "Second reviewer" } };
    saved = false;
  } };
}
async function capture(page: Page) {
  await page.getByRole("button", { name: "Go to recorded alert" }).click();
  await page.getByRole("button", { name: "Capture selected anomaly" }).click();
  await expect(page.getByRole("heading", { name: "AAPL · captured anomaly" })).toBeVisible();
}
async function investigate(page: Page) {
  await page.getByRole("link", { name: "Investigate in Control Panel" }).click();
  await expect(page.getByRole("combobox", { name: "Investigation input" })).toHaveValue("saved");
}
test("CEO-AC-03/05/06/07 play, capture, explain, save, reopen and export one fixed result", async ({ page }) => {
  await prepare(page);
  await page.getByRole("button", { name: "Play saved rows" }).click();
  await expect(page.getByText("2 / 2 saved rows shown", { exact: false })).toBeVisible();
  await capture(page);
  await page.getByRole("combobox", { name: "Detector", exact: true }).selectOption("lightgbm");
  await expect(page.getByText("Original row 1 · transformer · synthetic label 1")).toBeVisible();
  await investigate(page);
  await page.getByRole("button", { name: "Explain captured evidence" }).click();
  await expect(page.getByRole("heading", { name: "Deterministic fallback · no LLM call", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Save verified evidence" }).click();
  await expect(page.getByText("Evidence saved and verified.", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Reopen eeeeeeee" }).click();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Download evidence JSON" }).click();
  expect((await download).suggestedFilename()).toBe(`lob-arena-evidence-${snapshot.id}.json`);
});
test("CEO-AC-04 unavailable custody shows a safe operator action", async ({ page }) => {
  await prepare(page, { unavailable: true });
  await expect(page.getByRole("alert")).toContainText("Ask the operator");
  await expect(page.getByText("/private/path", { exact: false })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Capture selected anomaly" })).toHaveCount(0);
});
test("CEO-AC-08 failed save cannot enable download or claim retained evidence", async ({ page }) => {
  await prepare(page, { saveFailure: true }); await capture(page);
  await investigate(page);
  await page.getByRole("button", { name: "Explain captured evidence" }).click();
  await page.getByRole("button", { name: "Save verified evidence" }).click();
  await expect(page.getByRole("alert")).toContainText("could not be verified");
  await expect(page.getByRole("button", { name: "Download evidence JSON" })).toBeDisabled();
  await expect(page.getByText("Evidence saved and verified.", { exact: false })).toHaveCount(0);
});

test("CEO-AC-02/09 replacement account clears captured and saved evidence", async ({ page }) => {
  await page.clock.install();
  const control = await prepare(page); await capture(page);
  await investigate(page);
  await page.getByRole("button", { name: "Explain captured evidence" }).click();
  await page.getByRole("button", { name: "Save verified evidence" }).click();
  await expect(page.getByRole("button", { name: "Reopen eeeeeeee" })).toBeVisible();
  await page.evaluate(() => { sessionStorage.setItem("lob-arena.control-center.incident", JSON.stringify({ id: "account-a-incident" }));
    sessionStorage.setItem("unrelated-example", "preserve"); });
  control.replaceAccount(); await page.clock.fastForward(60000);
  await expect(page.getByText("Second reviewer · second@example.com")).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("lob-arena.control-center.incident"))).toBeNull();
  expect(await page.evaluate(() => sessionStorage.getItem("unrelated-example"))).toBe("preserve");
  await expect(page.getByRole("heading", { name: "Capture an alert to continue" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "AAPL · captured anomaly" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Deterministic fallback · no LLM call", exact: true })).toHaveCount(0);
  await expect(page.getByText(explanation.text, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reopen eeeeeeee" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Download evidence JSON" })).toHaveCount(0);
});

test("CEO-AC-05 same-account polling preserves its immutable captured snapshot", async ({ page }) => {
  await page.clock.install(); await prepare(page); await capture(page);
  await page.evaluate(() => sessionStorage.setItem("lob-arena.control-center.incident", "account-a-example"));
  await page.clock.fastForward(60000);
  await expect(page.getByRole("heading", { name: "AAPL · captured anomaly" })).toBeVisible();
  expect(await page.evaluate(() => sessionStorage.getItem("lob-arena.control-center.incident"))).toBe("account-a-example");
  await expect(page.getByText("Original row 1 · transformer · synthetic label 1")).toBeVisible();
});


test("CEO-AC-11 authenticated full product keeps its controllers alongside saved evidence", async ({ page }) => {
  const control = await prepare(page); await capture(page); await investigate(page);
  await page.getByRole("button", { name: "Explain captured evidence" }).click();
  await page.getByRole("button", { name: "Save verified evidence" }).click();
  await expect(page.getByText("Evidence saved and verified.", { exact: false })).toBeVisible();
  await page.getByRole("combobox", { name: "Investigation input" }).selectOption("arena");
  await expect(page.getByRole("button", { name: "Run Nebius AI Investigation Team", exact: true })).toBeVisible();
  await expect(page.getByRole("tab", { name: /Detector Tournament/ })).toBeEnabled();
  await page.getByRole("navigation", { name: "Main screens" }).getByRole("link", { name: "Arena", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Attack Tracker" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Market workload generator" })).toBeVisible();
  await page.getByRole("button", { name: "Start", exact: true }).click();
  await expect.poll(() => control.product.commands.map(value => JSON.parse(value))).toContainEqual({ action: "start", type: "arena_control" });
  await page.getByRole("navigation", { name: "Main screens" }).getByRole("link", { name: "Data Ingestion", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Historical market-data import" })).toBeVisible();
  expect(control.product.requests).toContain("/api/data-ingestion/sources/lobster/candidates");
  expect(control.product.requests).toContain("/api/experiments");
  await page.getByRole("navigation", { name: "Main screens" }).getByRole("link", { name: "Saved Research", exact: true }).click();
  await expect(page.getByText("Original row 1 · transformer · synthetic label 1")).toBeVisible();
  await investigate(page);
  await expect(page.getByRole("button", { name: "Reopen eeeeeeee" })).toBeVisible();
});
test("CEO-AC-04/11 unavailable prepared custody leaves ordinary screens working", async ({ page }) => {
  await prepare(page, { unavailable: true });
  await expect(page.getByRole("alert")).toContainText("Ask the operator");
  await page.getByRole("navigation", { name: "Main screens" }).getByRole("link", { name: "Data Ingestion", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Historical market-data import" })).toBeVisible();
  await page.getByRole("navigation", { name: "Main screens" }).getByRole("link", { name: "Control Panel", exact: true }).click();
  await expect(page.getByRole("tab", { name: /Scenario Generator/ })).toBeEnabled();
  await expect(page.getByRole("tab", { name: /Detector Tournament/ })).toBeEnabled();
  await page.goto("/attack-scenarios");
  await expect(page.getByRole("button", { name: "Generate", exact: true })).toBeVisible();
});
test("CEO-AC-03 prepared source stops at its fixed window while ordinary paging remains available", async ({ page }) => {
  const control = await prepare(page, { bounded: true });
  await page.getByRole("combobox", { name: "Presentation speed" }).selectOption("4");
  await page.getByRole("button", { name: "Play saved rows" }).click();
  await expect(page.getByRole("button", { name: "Replay window" })).toBeVisible();
  expect(control.rowRequests()).toBe(1);
  await page.getByRole("combobox", { name: "Saved research source" }).selectOption("ordinary");
  await expect(page.getByRole("heading", { name: "Saved research predictions · local only" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Session", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeEnabled();
});
