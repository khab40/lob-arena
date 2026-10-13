import type { SavedDetectorId, SavedScoreRow } from "@/types/savedScores";
import type { PreparedCampaign, PreparedPage } from "@/types/ceoJourney";
import "./savedScoreResearch.css";
import { ScorePlot, Provenance } from "./SavedScoreView";

interface Props {
  campaign: PreparedCampaign; page: PreparedPage; detector: SavedDetectorId; cursor: number;
  playing: boolean; speed: number; busy: boolean; selected: string;
  onDetector: (id: SavedDetectorId) => void; onPlay: () => void; onSpeed: (speed: number) => void;
  onJump: () => void; onSelect: (row: SavedScoreRow) => void; onCapture: () => void;
}
export function CeoPlaybackPanel(p: Props) {
  const visible = p.page.rows.slice(0, p.cursor);
  const alerts = visible.filter(r => r.alert);
  return <div className="saved-score-page">
  <section className="saved-score-panel" aria-label="Verified saved playback">
    <header className="saved-score-heading"><h2>Research source</h2></header>
    <strong>One prepared window, two frozen detectors</strong>
    <p>Synthetic research labels · no fresh inference · no order-book replay</p>
    <div className="saved-score-controls">
      <label>Detector <select value={p.detector} disabled={p.busy} onChange={e => p.onDetector(e.target.value as SavedDetectorId)}>
        <option value="transformer">Transformer</option><option value="lightgbm">LightGBM</option>
      </select></label>
      <button className="secondary-button" type="button" disabled={p.busy} onClick={p.onPlay}>{p.playing ? "Pause" : p.cursor === p.page.rows.length ? "Replay window" : "Play saved rows"}</button>
      <label>Presentation speed <select value={p.speed} onChange={e => p.onSpeed(Number(e.target.value))}>
        <option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option>
      </select></label>
      <button className="secondary-button" type="button" disabled={p.busy || !p.page.rows.some(r => r.alert)} onClick={p.onJump}>Go to recorded alert</button>
    </div>
    <p role="status">{p.cursor} / {p.page.rows.length} saved rows shown · threshold {p.page.threshold.toPrecision(7)}</p>
    {alerts.length ? <label className="saved-score-controls">Recorded alert <select value={p.selected} disabled={p.busy} onChange={e => {
      const found = alerts.find(r => r.target_id === e.target.value); if (found) p.onSelect(found);
    }}><option value="">Choose an alert</option>{alerts.map(r => <option key={r.target_id} value={r.target_id}>{r.symbol} · original row {r.ordinal}</option>)}</select></label>
      : <p>No threshold alert is visible yet for this detector.</p>}
    <button className="primary-button" type="button" disabled={p.busy || !p.selected} onClick={p.onCapture}>Capture selected anomaly</button>
    <Provenance value={p.campaign.provenance} />
    <ul aria-label="Research limitations">{p.campaign.limitations.map(line => <li key={line}>{line}</li>)}</ul>
  </section>
  <section className="saved-score-panel" aria-label="Saved prediction history">
    <header className="saved-score-heading"><h2>Saved prediction playback</h2></header>
    <p>Order-book data is unavailable in this saved prediction package.</p>
    <ScorePlot rows={visible.slice(-20)} threshold={p.page.threshold} />
    <div className="saved-score-table-scroll"><table><caption>{p.detector === "transformer" ? "Transformer" : "LightGBM"} · original saved rows</caption>
      <thead><tr><th>Original row</th><th>Source row</th><th>Symbol</th><th>Timestamp (ns)</th><th>Probability</th><th>Decision</th><th>Synthetic label</th></tr></thead>
      <tbody>{visible.slice(-20).map(r => <tr key={r.target_id}><td>{r.ordinal}</td><td>{r.source_ordinal}</td><td>{r.symbol}</td><td>{r.timestamp_ns}</td><td>{r.probability.toFixed(6)}</td>
        <td>{r.alert ? "Threshold alert" : "Below threshold"}</td><td>{r.synthetic_label}</td></tr>)}</tbody></table></div>
  </section>
  </div>;
}
