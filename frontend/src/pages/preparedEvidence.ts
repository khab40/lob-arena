import { createContext, useContext } from "react";
import type { SavedDetectorId } from "@/types/savedScores";
import type { AnomalySnapshot, DemoExplanation, EvidenceRecord, EvidenceSummary, PreparedCampaign, PreparedPage } from "@/types/ceoJourney";

export interface PreparedEvidence {
  campaign: PreparedCampaign | null; page: PreparedPage | null; detector: SavedDetectorId;
  cursor: number; playing: boolean; speed: number; selected: string;
  snapshot: AnomalySnapshot | null; explanation: DemoExplanation | null; saved: EvidenceRecord | null;
  records: EvidenceSummary[]; busy: boolean; error: string;
  activate: () => void; retry: () => void; chooseDetector: (value: SavedDetectorId) => void;
  setPlaying: (value: boolean) => void; setSpeed: (value: number) => void;
  setCursor: (value: number) => void; setSelected: (value: string) => void;
  capture: () => void; explain: () => void; save: () => void;
  reopen: (id: string) => void; download: () => void;
}
export const PreparedEvidenceContext = createContext<PreparedEvidence | null>(null);
export const usePreparedEvidence = () => useContext(PreparedEvidenceContext);
