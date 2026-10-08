export type SavedDetectorId = "transformer" | "lightgbm";

export type SavedProvenance = {
  verification_sha256: string;
  settings_sha256: string;
  job_id: string;
  request_sha256: string;
  predictions: { sha256: string; size_bytes: number; version_id: string };
  model_checkpoint_sha256: string;
};

export type SavedCampaign = {
  kind: "saved_research_predictions";
  campaign_id: string;
  label_context: "synthetic_research_labels";
  limitations: string[];
  provenance: SavedProvenance;
  detectors: { id: SavedDetectorId; threshold: number; mode: "balanced" }[];
  sessions: { id: string; rows: number; symbol: string; family: string; families: string[] }[];
};

export type SavedScoreRow = {
  ordinal: number;
  source_ordinal: number;
  target_id: string;
  timestamp_ns: string;
  symbol: string;
  family: string;
  synthetic_label: 0 | 1;
  probability: number;
  alert: boolean;
};

export type SavedScorePage = {
  campaign_id: string;
  session_id: string;
  detector: SavedDetectorId;
  threshold: number;
  mode: "balanced";
  total: number;
  offset: number;
  next_offset: number | null;
  provenance: SavedProvenance;
  rows: SavedScoreRow[];
};
