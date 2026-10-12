import assert from "node:assert/strict";
import { it } from "node:test";
import { guardDemoProxy, ceoLoopbackProxy } from "../dev/ceoLoopbackProxy.ts";

function request(peer, url = "/api/auth/config", headers = {}) {
  let forwarded = false;
  const response = { statusCode: 200, headers: {}, body: null,
    setHeader(key, value) { this.headers[key] = value; }, end(body) { this.body = body; } };
  guardDemoProxy({ url, headers, socket: { remoteAddress: peer } }, response, () => { forwarded = true; });
  return { forwarded, response };
}

it("preserves direct loopback access for each demo proxy", () => {
  for (const peer of ["127.0.0.1", "127.2.3.4", "::1", "::ffff:127.0.0.1"]) {
    for (const path of ["/api/auth/config", "/api/auth/google?x=1", "/api/ceo-demo/campaign"]) {
      assert.equal(request(peer, path).forwarded, true);
    }
  }
});

it("denies remote or unknown original peers despite forged local headers", () => {
  for (const peer of ["192.0.2.1", "10.0.0.1", "::ffff:192.0.2.1", "2001:db8::1", undefined, "127.fake"]) {
    const result = request(peer, "/api/auth/google", { host: "localhost:5173", origin: "http://localhost:5173" });
    assert.equal(result.forwarded, false);
    assert.equal(result.response.statusCode, 403);
    assert.equal(result.response.headers["Cache-Control"], "no-store");
    assert.equal(result.response.body, '{"detail":"Local access required"}');
  }
});

it("denies forwarded identity headers from a local proxy peer", () => {
  for (const name of ["forwarded", "x-real-ip", "x-forwarded-for", "x-forwarded-host", "X-Forwarded-Proto"]) {
    assert.equal(request("127.0.0.1", "/api/ceo-demo/campaign", { [name]: "example" }).forwarded, false);
  }
});

it("keeps unrelated research routes available and registers the guard before proxying", () => {
  assert.equal(request("192.0.2.1", "/api/research/saved-scores", { forwarded: "example" }).forwarded, true);
  const registered = [];
  ceoLoopbackProxy().configureServer({ middlewares: { use(middleware) { registered.push(middleware); } } });
  assert.deepEqual(registered, [guardDemoProxy]);
});

it("guards the preview server before its inherited demo proxies", () => {
  const registered = [];
  ceoLoopbackProxy().configurePreviewServer({ middlewares: { use(middleware) { registered.push(middleware); } } });
  assert.deepEqual(registered, [guardDemoProxy]);
  assert.equal(request("192.0.2.1", "/api/ceo-demo/campaign").forwarded, false);
});
