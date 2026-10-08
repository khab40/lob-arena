import type { SavedCampaign, SavedDetectorId, SavedProvenance, SavedScorePage } from "../types/savedScores";

export const SAVED_PAGE_SIZE = 100;
export const SAVED_CAMPAIGN_ID = "december-holdout-20261007";
const failure = "Invalid saved research prediction response.";
const record = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === "object" && !Array.isArray(value));
const text = (value: unknown): value is string => typeof value === "string" && value.length > 0 && value.length <= 512;
const integer = (value: unknown): value is number => Number.isSafeInteger(value) && Number(value) >= 0;
const probability = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 1;
const hash = (value: unknown) => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);

function requireValid(condition: unknown): asserts condition {
  if (!condition) throw new Error(failure);
}

function provenance(value: unknown): value is SavedProvenance {
  return record(value) && hash(value.verification_sha256) && hash(value.settings_sha256)
    && text(value.job_id) && hash(value.request_sha256) && hash(value.model_checkpoint_sha256)
    && record(value.predictions) && hash(value.predictions.sha256)
    && integer(value.predictions.size_bytes) && value.predictions.size_bytes > 0
    && value.predictions.version_id === "1";
}

function sameProvenance(left: SavedProvenance, right: SavedProvenance) {
  return left.verification_sha256 === right.verification_sha256 && left.settings_sha256 === right.settings_sha256
    && left.job_id === right.job_id && left.request_sha256 === right.request_sha256
    && left.model_checkpoint_sha256 === right.model_checkpoint_sha256
    && left.predictions.sha256 === right.predictions.sha256
    && left.predictions.size_bytes === right.predictions.size_bytes
    && left.predictions.version_id === right.predictions.version_id;
}

export function assertSavedScoreLoopback(browserOrigin: string, apiBase: string) {
  const loopback = (value: string) => {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol)
      && ["localhost", "127.0.0.1", "[::1]"].includes(url.hostname)
      && !url.username && !url.password && url.pathname === "/" && !url.search && !url.hash;
  };
  try {
    if (loopback(browserOrigin) && loopback(apiBase)) return;
  } catch { /* Reject malformed configuration without making a request. */ }
  throw new Error("Saved research predictions require a loopback browser and API address.");
}

export function validateSavedCampaign(value: unknown): SavedCampaign {
  requireValid(record(value) && value.kind === "saved_research_predictions"
    && value.campaign_id === SAVED_CAMPAIGN_ID && value.label_context === "synthetic_research_labels"
    && Array.isArray(value.limitations) && value.limitations.length > 0 && value.limitations.every(text)
    && provenance(value.provenance) && Array.isArray(value.detectors) && Array.isArray(value.sessions));
  requireValid(value.detectors.every((item: unknown) => record(item)
    && ["transformer", "lightgbm"].includes(String(item.id)) && probability(item.threshold) && item.mode === "balanced"));
  requireValid(value.sessions.every((item: unknown) => record(item)
    && typeof item.id === "string" && /^[0-9a-f]{16}$/.test(item.id)
    && integer(item.rows) && item.rows > 0 && text(item.symbol) && text(item.family)
    && Array.isArray(item.families) && item.families.length > 0 && item.families.every(text)
    && item.families.every((family, index, families) => index === 0 || families[index - 1] < family)
    && item.family === (item.families.length > 1 ? "mixed" : item.families[0])));
  const campaign = value as unknown as SavedCampaign;
  requireValid(new Set(campaign.detectors.map((item) => item.id)).size === campaign.detectors.length
    && new Set(campaign.sessions.map((item) => item.id)).size === campaign.sessions.length);
  return campaign;
}

export function validateSavedScorePage(
  value: unknown, campaign: SavedCampaign, sessionId: string, detectorId: SavedDetectorId,
  offset: number, previousSourceOrdinal?: number
): SavedScorePage {
  const session = campaign.sessions.find((item) => item.id === sessionId);
  const detector = campaign.detectors.find((item) => item.id === detectorId);
  requireValid(session && detector && integer(offset) && offset < session.rows);
  requireValid(record(value) && value.campaign_id === campaign.campaign_id && value.session_id === sessionId
    && value.detector === detectorId && value.threshold === detector.threshold && value.mode === "balanced"
    && value.total === session.rows && value.offset === offset && provenance(value.provenance)
    && sameProvenance(value.provenance, campaign.provenance) && Array.isArray(value.rows)
    && value.rows.length === Math.min(SAVED_PAGE_SIZE, session.rows - offset));
  const page = value as unknown as SavedScorePage;
  requireValid(page.next_offset === (offset + page.rows.length < session.rows ? offset + page.rows.length : null));
  let previous = previousSourceOrdinal ?? -1;
  const targets = new Set<string>();
  page.rows.forEach((row, index) => {
    requireValid(record(row) && row.ordinal === offset + index && integer(row.source_ordinal)
      && row.source_ordinal > previous && text(row.target_id) && !targets.has(row.target_id)
      && typeof row.timestamp_ns === "string" && /^\d{1,30}$/.test(row.timestamp_ns)
      && row.symbol === session.symbol && session.families.includes(row.family)
      && (row.synthetic_label === 0 || row.synthetic_label === 1)
      && probability(row.probability) && typeof row.alert === "boolean"
      && row.alert === (row.probability >= detector.threshold));
    previous = row.source_ordinal;
    targets.add(row.target_id);
  });
  return page;
}
