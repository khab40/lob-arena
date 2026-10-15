// Invented response shapes only. No retained research evidence or model execution.
const digest = "a".repeat(64);
export const session = { user: { id: "test-user", email: "reviewer@example.com", name: "Reviewer" },
  workspace_id: "ceo-demo", expires_at: "2030-01-01T12:00:00Z" };
export const provenance = { verification_sha256: digest, settings_sha256: digest, job_id: "fixture-job",
  request_sha256: digest, model_checkpoint_sha256: digest, predictions: { sha256: digest, size_bytes: 100, version_id: "1" } };
export const pairs = { transformer: { probability: 0.999, threshold: 0.996, alert: true },
  lightgbm: { probability: 0.4, threshold: 0.577, alert: false } };
export const campaign = { kind: "saved_research_predictions", campaign_id: "december-holdout-20261007",
  label_context: "synthetic_research_labels", limitations: ["Invented inert fixture; no model execution."], provenance,
  detectors: [{ id: "transformer", threshold: 0.996, mode: "balanced" }, { id: "lightgbm", threshold: 0.577, mode: "balanced" }],
  sessions: [{ id: "b".repeat(16), rows: 2, symbol: "AAPL", family: "control", families: ["control"] }],
  prepared_window: { session_id: "b".repeat(16), offset: 0, limit: 2 } };
export const row = { ordinal: 1, source_ordinal: 5, target_id: "c".repeat(64), timestamp_ns: "1234567890123456789",
  symbol: "AAPL", family: "control", synthetic_label: 1, probability: 0.999, alert: true };
export const previous = { ...row, ordinal: 0, source_ordinal: 4, target_id: "d".repeat(64), probability: 0.1, alert: false };
export function pageFor(detector: string) {
  return { campaign_id: campaign.campaign_id, session_id: campaign.prepared_window.session_id, detector,
    threshold: detector === "transformer" ? 0.996 : 0.577, mode: "balanced", total: 2, offset: 0, next_offset: null,
    provenance, rows: [previous, detector === "transformer" ? row : { ...row, probability: 0.4, alert: false }] };
}
const { probability: _p, alert: _a, ...original } = previous;
void _p; void _a;
export const snapshot = { id: "e".repeat(32), campaign_id: campaign.campaign_id, detector: "transformer", threshold: 0.996,
  row, paired_scores: pairs, context: [{ ...original, paired_scores: {
    transformer: { probability: 0.1, threshold: 0.996, alert: false }, lightgbm: { probability: 0.1, threshold: 0.577, alert: false }
  } }], provenance, workspace_id: "ceo-demo", created_at: "2026-10-12T10:00:00Z", snapshot_sha256: digest };
export const explanation = { mode: "deterministic_fallback", input_sha256: digest, input: snapshot,
  text: "Recorded threshold alert with synthetic research label. No fresh inference or adjudicated market abuse.",
  created_at: "2026-10-12T10:01:00Z", explanation_sha256: digest };
export const evidence = { id: snapshot.id, snapshot, explanation, saved_at: "2026-10-12T10:02:00Z", record_sha256: digest };
export const summary = { id: snapshot.id, symbol: "AAPL", detector: "transformer", saved_at: evidence.saved_at };
