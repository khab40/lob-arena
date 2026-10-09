import { useEffect, useRef, useState } from "react";
import { getSavedCampaign, getSavedScorePage } from "@/api/savedScores";
import type { SavedCampaign, SavedDetectorId, SavedProvenance, SavedScorePage, SavedScoreRow } from "@/types/savedScores";
import { appendSavedRow, savedPlaybackDelay, SAVED_SPEEDS } from "./savedScorePlayback";
import "./savedScoreResearch.css";

const detectorNames: Record<SavedDetectorId, string> = { transformer: "Transformer", lightgbm: "LightGBM" };
const errorMessage = (error: unknown) => error instanceof Error ? error.message : "Saved research predictions are unavailable.";

export function SavedScoreResearchPage() {
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

function ScorePlot({ rows, threshold }: { rows: SavedScoreRow[]; threshold?: number }) {
  const points = rows.map((row, index) => `${30 + index * (540 / 19)},${110 - row.probability * 90}`).join(" ");
  return <figure className="saved-score-plot">
    <figcaption>Last 20 saved probabilities · dashed line is the frozen threshold</figcaption>
    <svg aria-label="Recent saved probabilities and frozen threshold" role="img" viewBox="0 0 600 130">
      <text x="0" y="25">1</text><text x="0" y="115">0</text>
      <line x1="30" x2="570" y1="110" y2="110" className="saved-score-axis" />
      {threshold !== undefined ? <line x1="30" x2="570" y1={110 - threshold * 90} y2={110 - threshold * 90} className="saved-score-threshold" /> : null}
      <polyline fill="none" points={points} className="saved-score-line" />
    </svg>
  </figure>;
}

function Provenance({ value }: { value: SavedProvenance }) {
  return <details className="saved-score-provenance" open>
    <summary>Verified source identities</summary>
    <dl>
      <dt>Verification SHA-256</dt><dd>{value.verification_sha256}</dd>
      <dt>Selected Transformer settings SHA-256</dt><dd>{value.settings_sha256}</dd>
      <dt>Original Job</dt><dd>{value.job_id}</dd>
      <dt>Request SHA-256</dt><dd>{value.request_sha256}</dd>
      <dt>Paired prediction receipt</dt><dd>Version {value.predictions.version_id} · {value.predictions.size_bytes} bytes · {value.predictions.sha256}</dd>
      <dt>Transformer checkpoint SHA-256</dt><dd>{value.model_checkpoint_sha256}</dd>
    </dl>
    <p>LightGBM score lineage is bound to the verified paired predictions; the checkpoint above identifies the Transformer.</p>
  </details>;
}
