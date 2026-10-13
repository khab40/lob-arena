import { useEffect, useRef, useState } from "react";
import { getSavedCampaign, getSavedScorePage } from "@/api/savedScores";
import type { SavedCampaign, SavedDetectorId, SavedScorePage, SavedScoreRow } from "@/types/savedScores";
import { appendSavedRow, savedPlaybackDelay, SAVED_SPEEDS } from "./savedScorePlayback";
import "./savedScoreResearch.css";
import { ScorePlot, Provenance } from "./SavedScoreView";
import { usePreparedEvidence } from "./preparedEvidence";
import { CeoPlaybackPanel } from "./CeoPlaybackPanel";
import { NavLink } from "react-router";


const detectorNames: Record<SavedDetectorId, string> = { transformer: "Transformer", lightgbm: "LightGBM" };
const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Saved research predictions are unavailable.";

export function SavedScoreResearchPage() {
  const prepared = usePreparedEvidence();
  const [source, setSource] = useState("prepared");
  if (!prepared) return <OrdinarySavedScoreResearchPage />;
  return <>
    <section className="saved-score-panel"><label>Saved research source <select value={source} onChange={e => setSource(e.target.value)}>
      <option value="prepared">Prepared verified window</option><option value="ordinary">Ordinary local research</option>
    </select></label></section>
    {source === "prepared" ? <PreparedSavedScoreResearch /> : <OrdinarySavedScoreResearchPage />}
  </>;
}

function PreparedSavedScoreResearch() {
  const prepared = usePreparedEvidence()!;
  const { activate } = prepared;
  useEffect(() => { activate(); }, [activate]);
  return <>
    {prepared.error ? <section className="saved-score-panel"><p role="alert">{prepared.error}</p>
      <button className="secondary-button" type="button" disabled={prepared.busy} onClick={prepared.retry}>Reload prepared campaign</button></section> : null}
    {!prepared.campaign || !prepared.page ? <p role="status">{prepared.busy ? "Opening the verified campaign…" : "The prepared campaign is unavailable."}</p>
      : <CeoPlaybackPanel campaign={prepared.campaign} page={prepared.page} detector={prepared.detector} cursor={prepared.cursor}
        playing={prepared.playing} speed={prepared.speed} busy={prepared.busy} selected={prepared.selected}
        onDetector={prepared.chooseDetector} onPlay={() => { if (prepared.cursor === prepared.page!.rows.length) prepared.setCursor(0); prepared.setPlaying(!prepared.playing); }}
        onSpeed={prepared.setSpeed} onJump={() => { prepared.setPlaying(false); const i = prepared.page!.rows.findIndex(r => r.alert);
          if (i >= 0) { prepared.setCursor(i + 1); prepared.setSelected(prepared.page!.rows[i].target_id); } }}
        onSelect={row => prepared.setSelected(row.target_id)} onCapture={prepared.capture} />}
    <section className="saved-score-panel" aria-label="Saved anomaly investigation">
      <h2>{prepared.snapshot ? `${prepared.snapshot.row.symbol} · captured anomaly` : "Capture an alert to continue"}</h2>
      {prepared.snapshot ? <p>Original row {prepared.snapshot.row.ordinal} · {prepared.snapshot.detector} · synthetic label {prepared.snapshot.row.synthetic_label}</p> : null}
      <p>Saved anomalies remain fixed when playback or detector selection changes.</p>
      <NavLink className="secondary-button" to="/nebius?step=3&input=saved">Investigate in Control Panel</NavLink>
    </section>
  </>;
}

function OrdinarySavedScoreResearchPage() {
  const [campaign, setCampaign] = useState<SavedCampaign | null>(null);
  const [sessionId, setSessionId] = useState("");
  const [detector, setDetector] = useState<SavedDetectorId>("transformer");
  const [page, setPage] = useState<SavedScorePage | null>(null);
  const [offset, setOffset] = useState(0);
  const [position, setPosition] = useState(0);
  const [recent, setRecent] = useState<SavedScoreRow[]>([]);
  const [running, setRunning] = useState(false);
  const [speed, setSpeed] = useState<number>(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const previousSourceOrdinal = useRef<number | undefined>(undefined);
  const session = campaign?.sessions.find((item) => item.id === sessionId);
  const selectedDetector = campaign?.detectors.find((item) => item.id === detector);
  const current = recent.at(-1);
  const completed = Boolean(page && page.next_offset === null && position === page.rows.length);

  useEffect(() => {
    const controller = new AbortController();
    getSavedCampaign(controller.signal).then((value) => {
      if (controller.signal.aborted) return;
      setCampaign(value);
      setSessionId(value.sessions[0]?.id ?? "");
      setLoading(false);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) { setError(errorMessage(cause)); setLoading(false); }
    });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!campaign || !sessionId || !selectedDetector) return;
    const controller = new AbortController();
    setLoading(true);
    setPage(null);
    setPosition(0);
    getSavedScorePage(campaign, sessionId, detector, offset, controller.signal, previousSourceOrdinal.current).then((value) => {
      if (controller.signal.aborted) return;
      setPage(value);
      setLoading(false);
    }).catch((cause: unknown) => {
      if (!controller.signal.aborted) {
        setError(errorMessage(cause)); setRunning(false); setRecent([]); setLoading(false);
      }
    });
    return () => controller.abort();
  }, [campaign, sessionId, detector, offset, selectedDetector]);

  useEffect(() => {
    if (!running || !page) return;
    if (position === page.rows.length) {
      if (page.next_offset === null) setRunning(false);
      else {
        previousSourceOrdinal.current = page.rows.at(-1)?.source_ordinal;
        setOffset(page.next_offset);
      }
      return;
    }
    const timer = window.setTimeout(() => {
      setRecent((value) => appendSavedRow(value, page.rows[position]));
      setPosition(position + 1);
    }, savedPlaybackDelay(speed));
    return () => window.clearTimeout(timer);
  }, [running, page, position, speed]);

  function resetSelection() {
    setRunning(false); setPage(null); setRecent([]); setOffset(0); setPosition(0); setError(""); setLoading(false);
    previousSourceOrdinal.current = undefined;
  }

  return (
    <div className="saved-score-page">
      <section className="saved-score-panel" aria-label="Saved research prediction controls">
        <h2>Saved research predictions · local only</h2>
        <p>Replay verified calibrated scores and frozen threshold alerts. Labels are synthetic research labels.
          This view does not run a model or replay an order book.</p>
        {error ? <p role="alert">{error}</p> : null}
        {campaign ? <>
          <p><strong>Campaign:</strong> {campaign.campaign_id}</p>
          <div className="saved-score-controls">
            <label>Session<select value={sessionId} onChange={(event) => { resetSelection(); setSessionId(event.target.value); }}>
              {campaign.sessions.map((item) => <option key={item.id} value={item.id}>{item.symbol} · {item.family} · {item.id}</option>)}
            </select></label>
            <label>Detector<select value={detector} onChange={(event) => { resetSelection(); setDetector(event.target.value as SavedDetectorId); }}>
              {(Object.keys(detectorNames) as SavedDetectorId[]).map((id) => <option key={id} value={id}>
                {detectorNames[id]}{campaign.detectors.some((item) => item.id === id) ? "" : " · unavailable"}
              </option>)}
            </select></label>
            <label>Playback speed<select value={speed} onChange={(event) => setSpeed(Number(event.target.value))}>
              {SAVED_SPEEDS.map((value) => <option key={value} value={value}>{value} rows / second</option>)}
            </select></label>
            <button className="secondary-button" disabled={!running && (!page || loading || Boolean(error) || completed)}
              onClick={() => setRunning((value) => !value)} type="button">{running ? "Pause" : recent.length ? "Resume" : "Play"}</button>
          </div>
          {!selectedDetector ? <p role="status">{detectorNames[detector]} is unavailable for this verified campaign.</p> : null}
          {!session ? <p role="status">No saved sessions are available.</p> : null}
          {session ? <p>Session family context: {session.family === "mixed" ? "mixed research families" : session.family}
            {session.family === "mixed" ? ` · ${session.families.join(", ")}. Each saved row retains its own family.` : ""}</p> : null}
          <p role="status">{loading ? "Loading verified saved rows…" : completed ? "Playback complete" : running ? "Playing" : "Paused"}
            {session ? ` · ${page ? page.offset + position : offset} / ${session.rows} rows` : ""}</p>
          <ul aria-label="Research limitations">{campaign.limitations.map((item) => <li key={item}>{item}</li>)}</ul>
        </> : !error ? <p role="status">Loading verified campaign…</p> : null}
      </section>
      {campaign ? <section className="saved-score-panel" aria-label="Saved score and alert provenance">
        <h2>{detectorNames[detector]} saved score</h2>
        <div className="saved-score-metrics">
          <p>Calibrated probability<strong>{current ? current.probability.toFixed(6) : "—"}</strong></p>
          <p>Frozen balanced threshold<strong>{selectedDetector ? String(selectedDetector.threshold) : "Unavailable"}</strong></p>
          <p>Saved threshold alert<strong>{current ? current.alert ? "Alert" : "No alert" : "—"}</strong></p>
        </div>
        {current ? <p>Alert source: {current.target_id} · saved row {current.source_ordinal} · timestamp {current.timestamp_ns} ns</p> : null}
        <ScorePlot rows={recent} threshold={selectedDetector?.threshold} />
        <div className="saved-score-table-scroll"><table>
          <caption>Recent saved rows · synthetic research labels</caption>
          <thead><tr><th>Ordinal</th><th>Source row</th><th>Target</th><th>Family</th><th>Timestamp (ns)</th><th>Probability</th><th>Threshold alert</th><th>Synthetic label</th></tr></thead>
          <tbody>{recent.map((row) => <tr key={row.ordinal}><td>{row.ordinal}</td><td>{row.source_ordinal}</td><td>{row.target_id}</td>
            <td>{row.family}</td><td>{row.timestamp_ns}</td><td>{row.probability.toFixed(6)}</td><td>{row.alert ? "Alert" : "No alert"}</td><td>{row.synthetic_label}</td></tr>)}</tbody>
        </table></div>
        <Provenance value={campaign.provenance} />
      </section> : null}
    </div>
  );
}
