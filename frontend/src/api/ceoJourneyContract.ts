import { validateSavedCampaign } from "./savedScoreContract.ts";
import type { SavedDetectorId, SavedScoreRow } from "../types/savedScores";
import type { AnomalySnapshot, DemoExplanation, EvidenceRecord, EvidenceSummary, PreparedCampaign, PreparedPage } from "../types/ceoJourney";

const object = (v: unknown): v is Record<string, unknown> => Boolean(v && typeof v === "object" && !Array.isArray(v));
const hash = (v: unknown) => typeof v === "string" && /^[a-f0-9]{64}$/.test(v);
const id = (v: unknown) => typeof v === "string" && /^[a-f0-9]{32}$/.test(v);
const integer = (v: unknown) => typeof v === "number" && Number.isSafeInteger(v) && v >= 0;
const probability = (v: unknown) => typeof v === "number" && Number.isFinite(v) && v >= 0 && v <= 1;
const detector = (v: unknown): v is SavedDetectorId => v === "transformer" || v === "lightgbm";
const date = (v: unknown) => typeof v === "string" && v.length <= 40 && /^\d{4}-\d\d-\d\dT.*(?:Z|\+00:00)$/.test(v) && Number.isFinite(Date.parse(v));
function requireValid(condition: unknown): asserts condition {
  if (!condition) throw new Error("The demo response could not be verified. Please retry.");
}
const same = (a: unknown, b: unknown): boolean => {
  if (a === b) return true;
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((v, i) => same(v, b[i]));
  if (!object(a) || !object(b)) return false;
  return Object.keys(a).length === Object.keys(b).length && Object.keys(a).every(k => same(a[k], b[k]));
};

function row(value: unknown, threshold: number): value is SavedScoreRow {
  return object(value) && integer(value.ordinal) && integer(value.source_ordinal) && hash(value.target_id)
    && typeof value.timestamp_ns === "string" && /^\d{1,30}$/.test(value.timestamp_ns)
    && ["AAPL", "MSFT", "NVDA"].includes(String(value.symbol))
    && ["control", "layering_like", "quote_stuffing", "spoofing_like_wall"].includes(String(value.family))
    && (value.synthetic_label === 0 || value.synthetic_label === 1) && probability(value.probability)
    && value.alert === (Number(value.probability) >= threshold);
}

export function validatePreparedCampaign(value: unknown): PreparedCampaign {
  const campaign = validateSavedCampaign(value);
  requireValid(object(value) && object(value.prepared_window));
  const window = value.prepared_window;
  const session = campaign.sessions.find(s => s.id === window.session_id);
  requireValid(session && integer(window.offset) && integer(window.limit) && Number(window.limit) > 0
    && Number(window.limit) <= 64 && Number(window.offset) + Number(window.limit) <= session.rows
    && campaign.detectors.length === 2 && campaign.detectors.some(d => d.id === "transformer")
    && campaign.detectors.some(d => d.id === "lightgbm"));
  return value as unknown as PreparedCampaign;
}

export function validatePreparedPage(value: unknown, campaign: PreparedCampaign, selected: SavedDetectorId): PreparedPage {
  const window = campaign.prepared_window;
  const session = campaign.sessions.find(s => s.id === window.session_id)!;
  const point = campaign.detectors.find(d => d.id === selected)!;
  requireValid(object(value) && value.campaign_id === campaign.campaign_id && value.session_id === session.id
    && value.detector === selected && value.threshold === point.threshold && value.mode === "balanced"
    && value.total === session.rows && value.offset === window.offset && same(value.provenance, campaign.provenance)
    && Array.isArray(value.rows) && value.rows.length === window.limit);
  const page = value as unknown as PreparedPage;
  requireValid(page.next_offset === (window.offset + window.limit < session.rows ? window.offset + window.limit : null));
  page.rows.forEach((r, index) => requireValid(row(r, point.threshold) && r.ordinal === window.offset + index
    && r.symbol === session.symbol && session.families.includes(r.family)
    && (index === 0 || r.source_ordinal > page.rows[index - 1].source_ordinal)));
  requireValid(new Set(page.rows.map(r => r.target_id)).size === page.rows.length);
  return page;
}

export function validateSnapshot(value: unknown): AnomalySnapshot {
  requireValid(object(value) && id(value.id) && value.campaign_id === "december-holdout-20261007"
    && detector(value.detector) && probability(value.threshold) && row(value.row, Number(value.threshold))
    && value.row.alert && value.workspace_id === "ceo-demo" && date(value.created_at) && hash(value.snapshot_sha256)
    && object(value.provenance) && hash(value.provenance.verification_sha256) && hash(value.provenance.settings_sha256)
    && object(value.paired_scores) && Array.isArray(value.context) && value.context.length <= 16);
  const snapshot = value as unknown as AnomalySnapshot;
  for (const name of ["transformer", "lightgbm"] as const) {
    const p = snapshot.paired_scores[name];
    requireValid(object(p) && probability(p.probability) && probability(p.threshold) && p.alert === (p.probability >= p.threshold));
  }
  const chosen = snapshot.paired_scores[snapshot.detector];
  requireValid(chosen.probability === snapshot.row.probability && chosen.threshold === snapshot.threshold && chosen.alert);
  snapshot.context.forEach((r, index) => {
    requireValid(object(r) && object(r.paired_scores));
    for (const name of ["transformer", "lightgbm"] as const) {
      const p = r.paired_scores[name];
      requireValid(object(p) && probability(p.probability) && probability(p.threshold)
        && p.threshold === snapshot.paired_scores[name].threshold && p.alert === (p.probability >= p.threshold)
        && row({ ...r, probability: p.probability, alert: p.alert }, p.threshold));
    }
    requireValid(r.ordinal < snapshot.row.ordinal && r.source_ordinal < snapshot.row.source_ordinal
      && (index === 0 || r.source_ordinal > snapshot.context[index - 1].source_ordinal));
  });
  return snapshot;
}

export function validateExplanation(value: unknown, snapshot: AnomalySnapshot): DemoExplanation {
  requireValid(object(value) && value.mode === "deterministic_fallback" && value.input_sha256 === snapshot.snapshot_sha256
    && same(value.input, snapshot) && typeof value.text === "string" && value.text.length > 0 && value.text.length <= 8000
    && ![...value.text].some(c => c.charCodeAt(0) < 32 && ![9, 10, 13].includes(c.charCodeAt(0)))
    && date(value.created_at) && hash(value.explanation_sha256));
  return value as unknown as DemoExplanation;
}

export function validateEvidence(value: unknown): EvidenceRecord {
  requireValid(object(value) && id(value.id) && date(value.saved_at) && hash(value.record_sha256));
  const snapshot = validateSnapshot(value.snapshot);
  validateExplanation(value.explanation, snapshot);
  requireValid(value.id === snapshot.id);
  return value as unknown as EvidenceRecord;
}

export function validateEvidenceList(value: unknown): EvidenceSummary[] {
  requireValid(Array.isArray(value) && value.length <= 1000);
  value.forEach(v => requireValid(object(v) && id(v.id) && ["AAPL", "MSFT", "NVDA"].includes(String(v.symbol)) && detector(v.detector) && date(v.saved_at)));
  requireValid(new Set(value.map(v => v.id)).size === value.length);
  return value as EvidenceSummary[];
}
