import { expect, test } from "@playwright/test";

const session = { user: { id: "test-user", email: "reviewer@example.com", name: "Reviewer" },
  workspace_id: "ceo-demo", expires_at: "2030-01-01T12:00:00Z" };
const config = { configured: true, client_id: "example.apps.googleusercontent.com", nonce: "a".repeat(43) };
const google = `window.google={accounts:{id:{initialize(options){this.options=options},renderButton(element){
  const button=document.createElement('button');button.textContent='Sign in with Google';
  button.onclick=()=>this.options.callback({credential:'example'});element.appendChild(button);
}}}};`;

test("Google callback enters the workspace and logout removes its contents", async ({ page }) => {
  let active = false;
  await page.route("**/api/auth/session", (route) => route.fulfill({ status: active ? 200 : 401, json: active ? session : {} }));
  await page.route("**/api/auth/config", (route) => route.fulfill({ json: config }));
  await page.route("https://accounts.google.com/gsi/client", (route) => route.fulfill({ contentType: "text/javascript", body: google }));
  await page.route("**/api/auth/google", (route) => {
    expect(route.request().postDataJSON()).toEqual({ credential: "example" });
    active = true;
    return route.fulfill({ json: session });
  });
  await page.route("**/api/auth/logout", (route) => { active = false; return route.fulfill({ status: 204 }); });
  await page.goto("/ceo-demo");
  await page.getByRole("button", { name: "Sign in with Google" }).click();
  await expect(page.getByRole("heading", { name: "Prepared research campaign" })).toBeVisible();
  expect(await page.evaluate(() => Object.keys(localStorage).filter((key) => /token|session|credential/i.test(key)))).toEqual([]);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page.getByRole("heading", { name: "Follow an anomaly from result to evidence" })).toBeVisible();
});

test("unconfigured sign-in cannot grant a demo workspace", async ({ page }) => {
  await page.route("**/api/auth/session", (route) => route.fulfill({ status: 401, json: {} }));
  await page.route("**/api/auth/config", (route) => route.fulfill({ json: { configured: false, client_id: null, nonce: null } }));
  await page.goto("/ceo-demo");
  await expect(page.getByRole("status")).toContainText("Sign-in is not configured");
  await expect(page.getByRole("heading", { name: "Prepared research campaign" })).toHaveCount(0);
});

test("retry after unavailable configuration mounts a working Google button", async ({ page }) => {
  let ready = false;
  await page.route("**/api/auth/session", (route) => route.fulfill({ status: 401, json: {} }));
  await page.route("**/api/auth/config", (route) => route.fulfill({ json: ready ? config
    : { configured: false, client_id: null, nonce: null } }));
  await page.route("https://accounts.google.com/gsi/client", (route) => route.fulfill({ contentType: "text/javascript", body: google }));
  await page.route("**/api/auth/google", (route) => route.fulfill({ json: session }));
  await page.goto("/ceo-demo");
  await expect(page.getByRole("status")).toContainText("Sign-in is not configured");
  ready = true;
  await page.getByRole("button", { name: "Try again" }).click();
  await page.getByRole("button", { name: "Sign in with Google" }).click();
  await expect(page.getByRole("heading", { name: "Prepared research campaign" })).toBeVisible();
});

test("denied identity stays on sign-in with a fresh challenge", async ({ page }) => {
  let challenges = 0;
  await page.route("**/api/auth/session", (route) => route.fulfill({ status: 401, json: {} }));
  await page.route("**/api/auth/config", (route) => { challenges++; return route.fulfill({ json: config }); });
  await page.route("https://accounts.google.com/gsi/client", (route) => route.fulfill({ contentType: "text/javascript", body: google }));
  await page.route("**/api/auth/google", (route) => route.fulfill({ status: 403, json: {} }));
  await page.goto("/ceo-demo");
  await page.getByRole("button", { name: "Sign in with Google" }).click();
  await expect(page.getByRole("alert")).toContainText("could not be completed");
  await expect.poll(() => challenges).toBeGreaterThan(1);
  await expect(page.getByRole("heading", { name: "Prepared research campaign" })).toHaveCount(0);
});

test("server expiration clears the workspace without a browser session fallback", async ({ page }) => {
  let active = true;
  await page.clock.install();
  await page.route("**/api/auth/session", (route) => route.fulfill({ status: active ? 200 : 401, json: active ? session : {} }));
  await page.route("**/api/auth/config", (route) => route.fulfill({ json: { configured: false, client_id: null, nonce: null } }));
  await page.goto("/ceo-demo");
  await expect(page.getByRole("heading", { name: "Prepared research campaign" })).toBeVisible();
  active = false;
  await page.clock.fastForward(60000);
  await expect(page.getByRole("heading", { name: "Prepared research campaign" })).toHaveCount(0);
  await expect(page.getByRole("alert")).toContainText("session ended");
});
