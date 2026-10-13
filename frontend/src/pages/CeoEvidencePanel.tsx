import type { AnomalySnapshot, DemoExplanation, EvidenceRecord, EvidenceSummary } from "@/types/ceoJourney";

interface Props {
  snapshot: AnomalySnapshot | null; explanation: DemoExplanation | null; saved: EvidenceRecord | null;
  records: EvidenceSummary[]; busy: boolean; onExplain: () => void; onSave: () => void;
  onReopen: (id: string) => void; onDownload: () => void;
}
export function CeoEvidencePanel(p: Props) {
  return <section className="nebius-result-block investigation-team-report" aria-label="Captured evidence">
    <header className="arena-column-header"><h2>Incidents / Investigations</h2></header>
    <h2>{p.snapshot ? `${p.snapshot.row.symbol} · captured anomaly` : "Capture an alert to continue"}</h2>
    {p.snapshot ? <>
      <p>Original row {p.snapshot.row.ordinal} · {p.snapshot.detector} · synthetic label {p.snapshot.row.synthetic_label}</p>
      <p>This snapshot stays fixed when playback or detector selection changes.</p>
      <section className="detector-confidence-panel" aria-label="Captured paired detector scores"><h3>Saved detector probabilities</h3>
      <div className="detector-meter-list">{(["transformer", "lightgbm"] as const).map(name => {
        const score = p.snapshot!.paired_scores[name];
        return <div className={`detector-meter ${score.alert ? "highlighted" : ""}`} key={name}>
          <div className="detector-meter-header"><span>{name === "transformer" ? "Transformer" : "LightGBM"}</span><strong>{score.probability.toFixed(6)}</strong></div>
          <div className="detector-meter-track" aria-label={`${name} saved probability ${score.probability.toFixed(6)}`}><div style={{ width: `${score.probability * 100}%` }} /></div>
          <span>Threshold {String(score.threshold)} · {score.alert ? "Threshold alert" : "Below threshold"}</span></div>;
      })}</div></section>
      <section className="evidence-panel"><h3>Captured original evidence</h3><dl className="incident-replay-meta">
        <div><dt>Target</dt><dd>{p.snapshot.row.target_id}</dd></div>
        <div><dt>Source row</dt><dd>{p.snapshot.row.source_ordinal}</dd></div>
        <div><dt>Timestamp (ns)</dt><dd>{p.snapshot.row.timestamp_ns}</dd></div>
        <div><dt>Family</dt><dd>{p.snapshot.row.family}</dd></div>
        <div><dt>Snapshot SHA-256</dt><dd>{p.snapshot.snapshot_sha256}</dd></div>
      </dl></section>
      <p>{p.snapshot.context.length} preceding saved rows retained.</p>
      <button className="primary-button" type="button" disabled={p.busy || !!p.explanation} onClick={p.onExplain}>Explain captured evidence</button>
      {p.explanation ? <section className="nebius-investigator-panel"><div className="structured-ai-output"><article><h4>Deterministic fallback · no LLM call</h4><p>{p.explanation.text}</p></article></div></section> : null}
      <div className="nebius-button-row"><button className="primary-button" type="button" disabled={p.busy || !p.explanation || !!p.saved} onClick={p.onSave}>Save verified evidence</button>
        <button className="secondary-button" type="button" disabled={p.busy || !p.saved} onClick={p.onDownload}>Download evidence JSON</button></div>
      {p.saved ? <p role="status">Evidence saved and verified. Reopen it below to check the retained result.</p> : null}
    </> : <p>The backend captures original scores and provenance before an explanation can be requested.</p>}
    <h3>Saved evidence</h3>
    {p.records.length ? <div className="incident-evidence-summary"><ul>{p.records.map(r => <li key={r.id}>
      <span>{r.symbol} · {r.detector} · {new Date(r.saved_at).toLocaleString()}</span>
      <button className="secondary-button" type="button" disabled={p.busy} onClick={() => p.onReopen(r.id)}>Reopen {r.id.slice(0, 8)}</button>
    </li>)}</ul></div> : <p>No saved records in this account yet.</p>}
  </section>;
}
