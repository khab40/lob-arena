import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { validateDemoAuthConfig, validateDemoSession } from "../src/api/ceoAuthContract.ts";

const session = () => ({ user: { id: "test-user", email: "reviewer@example.com", name: "Reviewer" },
  workspace_id: "ceo-demo", expires_at: "2026-10-12T12:00:00Z" });
const config = () => ({ configured: true, client_id: "example.apps.googleusercontent.com", nonce: "a".repeat(43) });

describe("CEO identity response boundaries", () => {
  it("admits only an explicit configured Google challenge", () => {
    assert.deepEqual(validateDemoAuthConfig(config()), config());
    assert.deepEqual(validateDemoAuthConfig({ configured: false, client_id: null, nonce: null }),
      { configured: false, client_id: null, nonce: null });
    for (const value of [null, [], {}, { configured: false, client_id: "example", nonce: null }]) {
      assert.throws(() => validateDemoAuthConfig(value), /Invalid sign-in/);
    }
  });
  it("rejects absent, malformed and unbounded client and nonce fields", () => {
    for (const mutate of [
      (value) => { value.configured = "true"; }, (value) => { value.client_id = null; },
      (value) => { value.client_id = "https://google.example"; }, (value) => { value.nonce = "short"; },
      (value) => { value.nonce = "x".repeat(129); }, (value) => { value.nonce = "../".repeat(15); }
    ]) {
      const value = config(); mutate(value);
      assert.throws(() => validateDemoAuthConfig(value), /Invalid sign-in/);
    }
  });
  it("preserves the backend workspace and expiration without inferring authorization", () => {
    const value = session();
    assert.equal(validateDemoSession(value), value);
  });
  it("rejects another workspace, malformed identity and non-UTC expiration", () => {
    for (const mutate of [
      (value) => { value.workspace_id = "another"; }, (value) => { value.user = null; },
      (value) => { value.user.id = ""; }, (value) => { value.user.email = "x".repeat(255); },
      (value) => { value.user.name = "bad\nname"; }, (value) => { value.expires_at = "yesterday"; },
      (value) => { value.expires_at = "2026-10-12T12:00:00+03:00"; }
    ]) {
      const value = session(); mutate(value);
      assert.throws(() => validateDemoSession(value), /Invalid sign-in/);
    }
  });
});
