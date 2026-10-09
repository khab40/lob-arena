import type { SavedScoreRow } from "../types/savedScores";

export const SAVED_SPEEDS = [1, 5, 20] as const;
export const RECENT_SAVED_ROWS = 20;

export function savedPlaybackDelay(speed: number) {
  if (!SAVED_SPEEDS.some((value) => value === speed)) throw new Error("Unsupported saved playback speed.");
  return 1000 / speed;
}

export function appendSavedRow(recent: SavedScoreRow[], row: SavedScoreRow): SavedScoreRow[] {
  const previous = recent.at(-1);
  if (previous && (row.ordinal !== previous.ordinal + 1 || row.source_ordinal <= previous.source_ordinal)) {
    throw new Error("Saved playback row order changed.");
  }
  return [...recent, row].slice(-RECENT_SAVED_ROWS);
}
