import type { SavedCampaign, SavedDetectorId, SavedScorePage, SavedScoreRow, SavedProvenance } from "./savedScores";

export type PreparedCampaign = SavedCampaign & {
  prepared_window: { session_id: string; offset: number; limit: number };
};
export type PairedScores = Record<SavedDetectorId, { probability: number; threshold: number; alert: boolean }>;
export type ContextRow = Omit<SavedScoreRow, "probability" | "alert"> & { paired_scores: PairedScores };
export interface AnomalySnapshot {
  id: string;
  campaign_id: string;
  detector: SavedDetectorId;
  threshold: number;
  row: SavedScoreRow;
  paired_scores: PairedScores;
  context: ContextRow[];
  provenance: SavedProvenance;
  workspace_id: string;
  created_at: string;
  snapshot_sha256: string;
}
export interface DemoExplanation {
  mode: "deterministic_fallback";
  input_sha256: string;
  input: AnomalySnapshot;
  text: string;
  created_at: string;
  explanation_sha256: string;
}
export interface EvidenceRecord {
  id: string;
  snapshot: AnomalySnapshot;
  explanation: DemoExplanation;
  saved_at: string;
  record_sha256: string;
}
export interface EvidenceSummary { id: string; symbol: string; detector: SavedDetectorId; saved_at: string }
export type PreparedPage = SavedScorePage;
