import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { assertSavedScoreLoopback, SAVED_CAMPAIGN_ID, validateSavedCampaign, validateSavedScorePage } from "../src/api/savedScoreContract.ts";
import { appendSavedRow, savedPlaybackDelay } from "../src/pages/savedScorePlayback.ts";

// Invented in-memory objects only; no retained prediction payload is used.
const provenance = {
  verification_sha256: "a".repeat(64), settings_sha256: "b".repeat(64), job_id: "TEST-JOB",
  request_sha256: "c".repeat(64), model_checkpoint_sha256: "d".repeat(64),
  predictions: { sha256: "e".repeat(64), size_bytes: 123, version_id: "1" }
};
const campaign = {
  kind: "saved_research_predictions", campaign_id: SAVED_CAMPAIGN_ID,
  label_context: "synthetic_research_labels", limitations: ["Invented test evidence."], provenance,
  detectors: [{ id: "transformer", threshold: 0.7, mode: "balanced" }],
  sessions: [{ id: "0123456789abcdef", rows: 3, symbol: "TEST", family: "test_family", families: ["test_family"] }]
};
const makeRow = (ordinal) => ({
  ordinal, source_ordinal: ordinal + 50, target_id: `test-${ordinal}`,
  timestamp_ns: "9007199254740993123", symbol: "TEST", family: "test_family",
  synthetic_label: ordinal === 1 ? 1 : 0, probability: ordinal === 1 ? 0.9 : 0.2, alert: ordinal === 1
});
const makePage = () => ({
  campaign_id: SAVED_CAMPAIGN_ID, session_id: "0123456789abcdef", detector: "transformer",
  threshold: 0.7, mode: "balanced", total: 3, offset: 0, next_offset: null, provenance,
  rows: [0, 1, 2].map(makeRow)
});
const parsePage = (value, previous) => validateSavedScorePage(value, campaign, campaign.sessions[0].id, "transformer", 0, previous);

describe("saved research response boundaries", () => {
  it("accepts exact receipt identity and retains decimal timestamps and saved alerts", () => {
    assert.equal(validateSavedCampaign(campaign), campaign);
    const page = parsePage(makePage());
    assert.equal(page.rows[0].timestamp_ns, "9007199254740993123");
    assert.equal(page.rows[1].alert, true);
  });
  it("rejects invalid catalog identities, threshold values and duplicate selections", () => {
    for (const mutate of [
      (value) => { value.kind = "live"; },
      (value) => { value.provenance.predictions.version_id = 1; },
      (value) => { value.detectors[0].threshold = Number.NaN; },
      (value) => { value.detectors.push(value.detectors[0]); },
      (value) => { value.sessions[0].id = "../../private"; },
      (value) => { delete value.sessions[0].families; },
      (value) => { value.sessions[0].families = []; },
      (value) => { value.sessions[0].families = ["test_family", "test_family"]; },
      (value) => { value.sessions[0].families = ["test_family", "control"]; value.sessions[0].family = "mixed"; },
      (value) => { value.sessions[0].family = "mixed"; }
    ]) {
      const value = globalThis.structuredClone(campaign); mutate(value);
      assert.throws(() => validateSavedCampaign(value), /Invalid saved/);
    }
  });
  it("rejects mismatched provenance, pagination, source order and invalid scores", () => {
    for (const mutate of [
      (value) => { value.provenance.predictions.sha256 = "f".repeat(64); },
      (value) => { value.next_offset = 3; },
      (value) => { value.offset = 1; },
      (value) => { value.detector = "lightgbm"; },
      (value) => { value.threshold = 0.71; },
      (value) => { value.rows[1].ordinal = 2; },
      (value) => { value.rows[1].source_ordinal = 50; },
      (value) => { value.rows[1].target_id = value.rows[0].target_id; },
      (value) => { value.rows[0].timestamp_ns = 9007199254740992; },
      (value) => { value.rows[0].probability = Infinity; },
      (value) => { value.rows[0].alert = 1; },
      (value) => { value.rows[0].alert = true; }
    ]) {
      const value = globalThis.structuredClone(makePage()); mutate(value);
      assert.throws(() => parsePage(value), /Invalid saved/);
    }
    assert.throws(() => parsePage(makePage(), 51), /Invalid saved/);
  });
  it("allows only explicit loopback browser and API origins", () => {
    for (const origin of ["http://127.0.0.1:5173", "http://localhost:5173", "http://[::1]:5173"]) {
      assert.doesNotThrow(() => assertSavedScoreLoopback(origin, "http://127.0.0.1:8000"));
    }
    for (const bad of ["https://example.test", "http://localhost.example.test", "http://127.0.0.1/private", "ftp://localhost", "http://user@localhost", "malformed"]) {
      assert.throws(() => assertSavedScoreLoopback(bad, "http://localhost:8000"), /loopback/);
      assert.throws(() => assertSavedScoreLoopback("http://localhost:5173", bad), /loopback/);
    }
  });
  it("accepts control and attack families across pages while rejecting an unobserved family", () => {
    const mixed = globalThis.structuredClone(campaign);
    mixed.sessions[0] = { ...mixed.sessions[0], rows: 102, family: "mixed", families: ["control", "test_attack"] };
    validateSavedCampaign(mixed);
    const mixedPage = (offset) => ({
      ...makePage(), total: 102, offset, next_offset: offset === 0 ? 100 : null,
      rows: Array.from({ length: offset === 0 ? 100 : 2 }, (_, index) => {
        const ordinal = offset + index;
        return { ...makeRow(ordinal), family: ordinal < 100 ? "control" : "test_attack" };
      })
    });
    const first = validateSavedScorePage(mixedPage(0), mixed, mixed.sessions[0].id, "transformer", 0);
    const second = validateSavedScorePage(mixedPage(100), mixed, mixed.sessions[0].id, "transformer", 100, first.rows.at(-1).source_ordinal);
    assert.equal(first.rows[99].family, "control");
    assert.equal(second.rows[0].family, "test_attack");
    const invalid = mixedPage(100); invalid.rows[0].family = "unobserved";
    assert.throws(() => validateSavedScorePage(invalid, mixed, mixed.sessions[0].id, "transformer", 100), /Invalid saved/);
  });
});

describe("bounded saved playback", () => {
  it("supports exactly the documented row speeds", () => {
    assert.deepEqual([1, 5, 20].map(savedPlaybackDelay), [1000, 200, 50]);
    for (const speed of [0, -1, 2, Infinity]) assert.throws(() => savedPlaybackDelay(speed), /Unsupported/);
  });
  it("keeps only 20 recent rows and rejects a playback ordering change", () => {
    let recent = [];
    for (let ordinal = 0; ordinal < 30; ordinal++) recent = appendSavedRow(recent, makeRow(ordinal));
    assert.equal(recent.length, 20);
    assert.equal(recent[0].ordinal, 10);
    assert.throws(() => appendSavedRow(recent, makeRow(29)), /order changed/);
    assert.throws(() => appendSavedRow(recent, makeRow(31)), /order changed/);
  });
});
