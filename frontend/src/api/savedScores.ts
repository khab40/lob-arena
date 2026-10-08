import { API_BASE_URL } from "@/config/runtime";
import { assertSavedScoreLoopback, SAVED_PAGE_SIZE, validateSavedCampaign, validateSavedScorePage } from "./savedScoreContract";
import type { SavedCampaign, SavedDetectorId } from "@/types/savedScores";

async function readSavedJson(path: string, signal: AbortSignal): Promise<unknown> {
  assertSavedScoreLoopback(window.location.origin, API_BASE_URL);
  const response = await fetch(`${API_BASE_URL.replace(/\/$/, "")}/api/research/saved-scores${path}`, {
    cache: "no-store", credentials: "omit", redirect: "error", signal
  });
  if (!response.ok) {
    throw new Error(response.status === 404
      ? "Saved research predictions are unavailable. Configure the approved private local evidence store."
      : `Saved research predictions are unavailable (HTTP ${response.status}).`);
  }
  return response.json();
}

export async function getSavedCampaign(signal: AbortSignal) {
  return validateSavedCampaign(await readSavedJson("/campaigns", signal));
}

export async function getSavedScorePage(
  campaign: SavedCampaign, sessionId: string, detector: SavedDetectorId,
  offset: number, signal: AbortSignal, previousSourceOrdinal?: number
) {
  const query = new URLSearchParams({ session_id: sessionId, detector, offset: String(offset), limit: String(SAVED_PAGE_SIZE) });
  const value = await readSavedJson(`/campaigns/${encodeURIComponent(campaign.campaign_id)}/rows?${query}`, signal);
  return validateSavedScorePage(value, campaign, sessionId, detector, offset, previousSourceOrdinal);
}
