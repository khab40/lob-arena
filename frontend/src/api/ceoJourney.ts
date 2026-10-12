import { validateEvidence, validateEvidenceList, validateExplanation, validatePreparedCampaign, validatePreparedPage, validateSnapshot } from "./ceoJourneyContract";
import type { SavedDetectorId } from "../types/savedScores";
import type { AnomalySnapshot, PreparedCampaign } from "../types/ceoJourney";

export class DemoAccessEnded extends Error {}
async function request(path: string, signal: AbortSignal, body?: unknown): Promise<unknown> {
  const response = await fetch(`/api/ceo-demo/${path}`, { method: body === undefined ? "GET" : "POST",
    credentials: "same-origin", cache: "no-store", redirect: "error", signal,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  if (response.status === 401) throw new DemoAccessEnded("Your session ended. Sign in to continue.");
  if (!response.ok) throw new Error(response.status === 503
    ? "Verified campaign evidence is unavailable. Ask the operator to check the prepared evidence store."
    : "The operation could not be verified. Please retry.");
  return response.json();
}
const safeId = (id: string) => {
  if (!/^[a-f0-9]{32}$/.test(id)) throw new Error("Invalid evidence identifier.");
  return id;
};
export const getPreparedCampaign = async (signal: AbortSignal) => validatePreparedCampaign(await request("campaign", signal));
export const getPreparedRows = async (campaign: PreparedCampaign, detector: SavedDetectorId, signal: AbortSignal) =>
  validatePreparedPage(await request(`rows?detector=${detector}`, signal), campaign, detector);
export const captureAnomaly = async (detector: SavedDetectorId, target_id: string, signal: AbortSignal) =>
  validateSnapshot(await request("anomalies", signal, { detector, target_id }));
export const explainAnomaly = async (snapshot: AnomalySnapshot, signal: AbortSignal) =>
  validateExplanation(await request(`anomalies/${safeId(snapshot.id)}/explanation`, signal, {}), snapshot);
export const saveEvidence = async (snapshot: AnomalySnapshot, signal: AbortSignal) => {
  const record = validateEvidence(await request(`anomalies/${safeId(snapshot.id)}/save`, signal, {}));
  if (record.id !== snapshot.id || record.snapshot.snapshot_sha256 !== snapshot.snapshot_sha256) throw new Error("The saved evidence did not match the captured anomaly.");
  return record;
};
export const getEvidenceList = async (signal: AbortSignal) => validateEvidenceList(await request("evidence", signal));
export const reopenEvidence = async (id: string, signal: AbortSignal) => {
  const record = validateEvidence(await request(`evidence/${safeId(id)}`, signal));
  if (record.id !== id) throw new Error("The reopened evidence identifier did not match.");
  return record;
};

export async function downloadEvidence(id: string, signal: AbortSignal) {
  const record = validateEvidence(await request(`evidence/${safeId(id)}/export`, signal));
  if (record.id !== id) throw new Error("The exported evidence identifier did not match.");
  const url = URL.createObjectURL(new Blob([JSON.stringify(record, null, 2) + "\n"], { type: "application/json" }));
  const link = document.createElement("a");
  link.href = url; link.download = `lob-arena-evidence-${record.id}.json`; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
