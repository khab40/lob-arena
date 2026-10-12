import type { SavedDetectorId, SavedScoreRow } from "@/types/savedScores";
import type { PreparedCampaign, PreparedPage } from "@/types/ceoJourney";

interface Props {
  campaign: PreparedCampaign; page: PreparedPage; detector: SavedDetectorId; cursor: number;
  playing: boolean; speed: number; busy: boolean; selected: string;
  onDetector: (id: SavedDetectorId) => void; onPlay: () => void; onSpeed: (speed: number) => void;
  onJump: () => void; onSelect: (row: SavedScoreRow) => void; onCapture: () => void;
}
export function CeoPlaybackPanel(p: Props) {
  const visible = p.page.rows.slice(0, p.cursor);
  const alerts = visible.filter(r => r.alert);
  const points = visible.map((r, i) => `${10 + i * 600 / Math.max(1, p.page.rows.length - 1)},${110 - r.probability * 100}`).join(" ");
  return <section className="ceo-playback" aria-label="Verified saved playback">
    <div className="ceo-step-title"><span>1 · Inspect the recorded decisions</span><b>Saved research predictions</b></div>
    <h2>One prepared window, two frozen detectors</h2>
    <p>Synthetic research labels · no fresh inference · no order-book replay</p>
    <div className="ceo-toolbar">
      <label>Detector <select value={p.detector} disabled={p.busy} onChange={e => p.onDetector(e.target.value as SavedDetectorId)}>
        <option value="transformer">Transformer</option><option value="lightgbm">LightGBM</option>
      </select></label>
      <button type="button" disabled={p.busy} onClick={p.onPlay}>{p.playing ? "Pause" : p.cursor === p.page.rows.length ? "Replay window" : "Play saved rows"}</button>
      <label>Presentation speed <select value={p.speed} onChange={e => p.onSpeed(Number(e.target.value))}>
        <option value={1}>1×</option><option value={2}>2×</option><option value={4}>4×</option>
      </select></label>
      <button type="button" disabled={p.busy || !p.page.rows.some(r => r.alert)} onClick={p.onJump}>Go to recorded alert</button>
    </div>
    <p role="status">{p.cursor} / {p.page.rows.length} saved rows shown · threshold {p.page.threshold.toPrecision(7)}</p>
    <svg viewBox="0 0 620 130" role="img" aria-label={`${p.detector} recorded probabilities and frozen threshold`}>
      <line x1="10" y1={110 - p.page.threshold * 100} x2="610" y2={110 - p.page.threshold * 100} stroke="#d47a22" strokeDasharray="6 4" />
      <polyline points={points} fill="none" stroke="#176861" strokeWidth="3" />
      <text x="10" y="126" fontSize="10">Original row order · probability 0–1 · dashed line: frozen threshold</text>
    </svg>
    <div className="ceo-table-scroll"><table><thead><tr><th>Original row</th><th>Symbol</th><th>Probability</th><th>Decision</th><th>Synthetic label</th></tr></thead>
      <tbody>{visible.slice(-8).map(r => <tr key={r.target_id}><td>{r.ordinal}</td><td>{r.symbol}</td><td>{r.probability.toFixed(6)}</td>
        <td>{r.alert ? "Threshold alert" : "Below threshold"}</td><td>{r.synthetic_label}</td></tr>)}</tbody></table></div>
    {alerts.length ? <label className="ceo-alert-select">Recorded alert <select value={p.selected} disabled={p.busy} onChange={e => {
      const found = alerts.find(r => r.target_id === e.target.value); if (found) p.onSelect(found);
    }}><option value="">Choose an alert</option>{alerts.map(r => <option key={r.target_id} value={r.target_id}>{r.symbol} · original row {r.ordinal}</option>)}</select></label>
      : <p>No threshold alert is visible yet for this detector.</p>}
    <button type="button" disabled={p.busy || !p.selected} onClick={p.onCapture}>Capture selected anomaly</button>
    <details><summary>Source and limits</summary><p>{p.campaign.campaign_id}</p>
      {p.campaign.limitations.map(line => <p key={line}>{line}</p>)}
      <p className="ceo-digest">Verification SHA-256: {p.campaign.provenance.verification_sha256}</p></details>
  </section>;
}
