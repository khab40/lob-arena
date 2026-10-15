import assert from "node:assert/strict";
import { test } from "node:test";
import { validateEvidence, validateExplanation, validatePreparedCampaign, validatePreparedPage, validateSnapshot } from "../src/api/ceoJourneyContract.ts";
import { campaign, evidence, explanation, pageFor, snapshot } from "../e2e/ceo-journey.fixture.ts";
// Network JSON has separate objects even when the fixture shares references.
const clone = value => JSON.parse(JSON.stringify(value));

test("prepared paired playback preserves the exact original window and decisions", () => {
  const c = validatePreparedCampaign(campaign);
  for (const name of ["transformer", "lightgbm"]) assert.equal(validatePreparedPage(pageFor(name), c, name).rows[1].source_ordinal, 5);
  for (const mutate of [v => { v.rows.reverse(); }, v => { v.rows[1].alert = false; },
    v => { v.provenance.predictions.sha256 = "f".repeat(64); }, v => { v.rows[1].probability = Infinity; },
    v => { v.rows[1].target_id = v.rows[0].target_id; }, v => { v.rows[1].timestamp_ns = 123; }]) {
    const p = clone(pageFor("transformer")); mutate(p); assert.throws(() => validatePreparedPage(p, c, "transformer"));
  }
});
test("prepared campaign refuses an unbounded window and another detector population", () => {
  for (const mutate of [v => { v.prepared_window.limit = 65; }, v => { v.prepared_window.offset = 2; },
    v => { v.detectors.pop(); }, v => { v.prepared_window.session_id = "f".repeat(16); }]) {
    const c = clone(campaign); mutate(c); assert.throws(() => validatePreparedCampaign(c));
  }
});
test("captured anomaly requires original alert and bounded preceding paired context", () => {
  assert.equal(validateSnapshot(snapshot), snapshot);
  for (const mutate of [v => { v.row.alert = false; }, v => { v.context = Array(17).fill(v.context[0]); },
    v => { v.context[0].source_ordinal = v.row.source_ordinal; }, v => { v.paired_scores.transformer.probability = 0.2; },
    v => { v.workspace_id = "other"; }, v => { v.id = "../../escape"; }]) {
    const s = clone(snapshot); mutate(s); assert.throws(() => validateSnapshot(s));
  }
});
test("explanation and reopened evidence keep exact snapshot binding and actual fallback mode", () => {
  assert.equal(validateExplanation(explanation, snapshot), explanation);
  assert.equal(validateEvidence(evidence), evidence);
  for (const mutate of [v => { v.explanation.mode = "nebius"; }, v => { v.explanation.input.row.target_id = "f".repeat(64); },
    v => { v.explanation.text = "\0secret"; }, v => { v.id = "f".repeat(32); }]) {
    const r = clone(evidence); mutate(r); assert.throws(() => validateEvidence(r));
  }
});
