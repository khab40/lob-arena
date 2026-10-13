import assert from "node:assert/strict";
import { test } from "node:test";
import { sessionFetch, startSessionRequests } from "../src/api/sessionRequests.ts";

const originalFetch = globalThis.fetch, originalWindow = globalThis.window;
test.after(() => { globalThis.fetch = originalFetch; globalThis.window = originalWindow; });
globalThis.window = { location: { origin: "http://localhost:5173" } };

test("ordinary requests preserve their existing transport before authenticated mode", async () => {
  const init = { credentials: "omit" };
  globalThis.fetch = async (input, value) => { assert.equal(input, "http://localhost:8000/api/example"); assert.equal(value, init); return new globalThis.Response("ok"); };
  assert.equal(await (await sessionFetch("http://localhost:8000/api/example", init)).text(), "ok");
});
test("confirmed session requests are same-origin, private and refuse redirects", async () => {
  const stop = startSessionRequests(() => assert.fail("Unexpected expiry"));
  let calls = 0;
  globalThis.fetch = async (_, init) => { calls++; assert.equal(init.credentials, "same-origin"); assert.equal(init.cache, "no-store"); assert.equal(init.redirect, "error"); return new globalThis.Response("ok"); };
  await sessionFetch("/api/example", { credentials: "omit" });
  for (const url of ["https://example.com/api/example", "http://user:example@localhost:5173/api/example"]) {
    await assert.rejects(sessionFetch(url), /same origin/);
  }
  assert.equal(calls, 1); stop();
  await assert.rejects(sessionFetch("/api/example"), /session required/);
});
test("logout aborts owned requests and refuses a late response", async () => {
  const stop = startSessionRequests(() => {});
  let finish, signal;
  globalThis.fetch = (_, init) => { signal = init.signal; return new Promise(resolve => { finish = resolve; }); };
  const request = sessionFetch("/api/example"); stop(); finish(new globalThis.Response("late"));
  assert.equal(signal.aborted, true); await assert.rejects(request, { name: "AbortError" });
});
test("account replacement aborts old requests and old cleanup cannot revoke the replacement", async () => {
  const oldStop = startSessionRequests(() => {});
  let finish;
  globalThis.fetch = () => new Promise(resolve => { finish = resolve; });
  const old = sessionFetch("/api/example"); const newStop = startSessionRequests(() => {}); oldStop();
  finish(new globalThis.Response("old")); await assert.rejects(old, { name: "AbortError" });
  globalThis.fetch = async () => new globalThis.Response("new");
  assert.equal(await (await sessionFetch("/api/example")).text(), "new"); newStop();
});
test("an unauthorized response ends the session once and prevents further requests", async () => {
  let ended = 0, calls = 0;
  const stop = startSessionRequests(() => ended++);
  globalThis.fetch = async () => { calls++; return new globalThis.Response("", { status: 401 }); };
  await assert.rejects(sessionFetch("/api/example"), /session ended/);
  await assert.rejects(sessionFetch("/api/example"), /session required/);
  assert.equal(ended, 1); assert.equal(calls, 1); stop();
});
