import { expect, test, type Page } from "@playwright/test";
import { campaign, evidence, explanation, pageFor, session, snapshot, summary } from "./ceo-journey.fixture";

async function prepare(page: Page, options: { unavailable?: boolean; saveFailure?: boolean } = {}) {
  let saved = false;
  let currentSession = session;
  await page.route("**/api/auth/session", route => route.fulfill({ json: currentSession }));
  await page.route("**/api/ceo-demo/**", route => {
    const url = new URL(route.request().url()), path = url.pathname.replace("/api/ceo-demo/", "");
    expect(route.request().headers().authorization).toBeUndefined();
    if (options.unavailable && path === "campaign") return route.fulfill({ status: 503, json: { detail: "/private/path" } });
    if (path === "campaign") return route.fulfill({ json: campaign });
    if (path === "rows") return route.fulfill({ json: pageFor(url.searchParams.get("detector")!) });
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
  await page.goto("/ceo-demo");
  return { replaceAccount: () => {
    currentSession = { ...session, user: { id: "second-user", email: "second@example.com", name: "Second reviewer" } };
    saved = false;
  } };
}
async function capture(page: Page) {
  await page.getByRole("button", { name: "Go to recorded alert" }).click();
  await page.getByRole("button", { name: "Capture selected anomaly" }).click();
  await expect(page.getByRole("heading", { name: "AAPL · captured anomaly" })).toBeVisible();
}
test("CEO-AC-03/05/06/07 play, capture, explain, save, reopen and export one fixed result", async ({ page }) => {
  await prepare(page);
  await page.getByRole("button", { name: "Play saved rows" }).click();
  await expect(page.getByText("2 / 2 saved rows shown", { exact: false })).toBeVisible();
  await capture(page);
  await page.getByRole("combobox", { name: "Detector", exact: true }).selectOption("lightgbm");
  await expect(page.getByText("Original row 1 · transformer · synthetic label 1")).toBeVisible();
  await page.getByRole("button", { name: "Explain captured evidence" }).click();
  await expect(page.getByText("Deterministic fallback · no LLM call")).toBeVisible();
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
  await page.getByRole("button", { name: "Explain captured evidence" }).click();
  await page.getByRole("button", { name: "Save verified evidence" }).click();
  await expect(page.getByRole("alert")).toContainText("could not be verified");
  await expect(page.getByRole("button", { name: "Download evidence JSON" })).toBeDisabled();
  await expect(page.getByText("Evidence saved and verified.", { exact: false })).toHaveCount(0);
});

test("CEO-AC-02/09 replacement account clears captured and saved evidence", async ({ page }) => {
  await page.clock.install();
  const control = await prepare(page); await capture(page);
  await page.getByRole("button", { name: "Explain captured evidence" }).click();
  await page.getByRole("button", { name: "Save verified evidence" }).click();
  await expect(page.getByRole("button", { name: "Reopen eeeeeeee" })).toBeVisible();
  control.replaceAccount(); await page.clock.fastForward(60000);
  await expect(page.getByText("Second reviewer · second@example.com")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Capture an alert to continue" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "AAPL · captured anomaly" })).toHaveCount(0);
  await expect(page.getByText("Deterministic fallback · no LLM call")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Reopen eeeeeeee" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Download evidence JSON" })).toHaveCount(0);
});

test("CEO-AC-05 same-account polling preserves its immutable captured snapshot", async ({ page }) => {
  await page.clock.install(); await prepare(page); await capture(page);
  await page.clock.fastForward(60000);
  await expect(page.getByRole("heading", { name: "AAPL · captured anomaly" })).toBeVisible();
  await expect(page.getByText("Original row 1 · transformer · synthetic label 1")).toBeVisible();
});
