import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { captureAnomaly, DemoAccessEnded, downloadEvidence, explainAnomaly, getEvidenceList, getPreparedCampaign, getPreparedRows, reopenEvidence, saveEvidence } from "@/api/ceoJourney";
import type { SavedDetectorId } from "@/types/savedScores";
import type { AnomalySnapshot, DemoExplanation, EvidenceRecord, EvidenceSummary, PreparedCampaign, PreparedPage } from "@/types/ceoJourney";
import { PreparedEvidenceContext } from "./preparedEvidence";

export function CeoJourney({ children, onAccessEnded }: { children: ReactNode; onAccessEnded: () => void }) {
  const [campaign, setCampaign] = useState<PreparedCampaign | null>(null);
  const [page, setPage] = useState<PreparedPage | null>(null);
  const [detector, setDetector] = useState<SavedDetectorId>("transformer");
  const [cursor, setCursor] = useState(0), [playing, setPlaying] = useState(false), [speed, setSpeed] = useState(1);
  const [selected, setSelected] = useState("");
  const [snapshot, setSnapshot] = useState<AnomalySnapshot | null>(null);
  const [explanation, setExplanation] = useState<DemoExplanation | null>(null);
  const [saved, setSaved] = useState<EvidenceRecord | null>(null);
  const [records, setRecords] = useState<EvidenceSummary[]>([]);
  const [active, setActive] = useState(false);
  const activate = useCallback(() => setActive(true), []);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [attempt, setAttempt] = useState(0);
  const operation = useRef<AbortController | null>(null);
  const ended = useRef(onAccessEnded); ended.current = onAccessEnded;

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController(); operation.current = controller;
    setBusy(true); setError("");
    setCampaign(null); setPage(null); setPlaying(false);
    Promise.all([getPreparedCampaign(controller.signal), getEvidenceList(controller.signal)]).then(async ([value, items]) => {
      const rows = await getPreparedRows(value, "transformer", controller.signal);
      if (controller.signal.aborted) return;
      setCampaign(value); setPage(rows); setRecords(items); setDetector("transformer"); setCursor(0); setSelected("");
    }).catch(err => {
      if (!controller.signal.aborted) {
        if (err instanceof DemoAccessEnded) ended.current(); else setError("Verified campaign evidence is unavailable. Ask the operator to check the prepared evidence store.");
      }
    }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    return () => { controller.abort(); operation.current?.abort(); };
  }, [active, attempt]);

  useEffect(() => {
    if (!playing || !page) return;
    const timer = window.setInterval(() => setCursor(value => Math.min(value + 1, page.rows.length)), 1000 / speed);
    return () => window.clearInterval(timer);
  }, [playing, page, speed]);
  useEffect(() => { if (page && cursor === page.rows.length) setPlaying(false); }, [cursor, page]);

  async function run(action: (signal: AbortSignal) => Promise<void>) {
    if (busy) return;
    const controller = new AbortController(); operation.current?.abort(); operation.current = controller;
    setBusy(true); setPlaying(false); setError("");
    try { await action(controller.signal); } catch (err) {
      if (!controller.signal.aborted) {
        if (err instanceof DemoAccessEnded) ended.current(); else setError(err instanceof Error ? err.message : "The operation could not be verified. Please retry.");
      }
    } finally { if (!controller.signal.aborted) setBusy(false); }
  }
  function chooseDetector(value: SavedDetectorId) {
    if (!campaign) return;
    void run(async signal => {
      const rows = await getPreparedRows(campaign, value, signal);
      if (signal.aborted) return;
      setPage(rows); setDetector(value); setCursor(0); setSelected("");
    });
  }
  function capture() { void run(async signal => {
    const value = await captureAnomaly(detector, selected, signal);
    if (signal.aborted) return;
    if (value.detector !== detector || value.row.target_id !== selected
      || value.provenance.verification_sha256 !== campaign?.provenance.verification_sha256) {
      throw new Error("The captured evidence did not match the selected alert. Please retry.");
    }
    setSnapshot(value); setExplanation(null); setSaved(null);
  }); }
  function explain() { if (snapshot) void run(async signal => {
    const value = await explainAnomaly(snapshot, signal); if (!signal.aborted) setExplanation(value);
  }); }
  function save() { if (snapshot) void run(async signal => {
    const value = await saveEvidence(snapshot, signal);
    if (signal.aborted) return;
    setSaved(value);
    const items = await getEvidenceList(signal); if (!signal.aborted) setRecords(items);
  }); }
  function reopen(id: string) { void run(async signal => {
    const value = await reopenEvidence(id, signal);
    if (signal.aborted) return;
    setSnapshot(value.snapshot); setExplanation(value.explanation); setSaved(value);
  }); }
  function download() { if (saved) void run(signal => downloadEvidence(saved.id, signal)); }
  return <PreparedEvidenceContext.Provider value={{ campaign, page, detector, cursor, playing, speed, selected,
    snapshot, explanation, saved, records, busy, error, activate, retry: () => setAttempt(v => v + 1),
    chooseDetector, setPlaying, setSpeed, setCursor, setSelected, capture, explain, save, reopen, download }}>
    {children}
  </PreparedEvidenceContext.Provider>;
}
