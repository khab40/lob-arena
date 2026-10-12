import type { AnomalySnapshot, DemoExplanation, EvidenceRecord, EvidenceSummary } from "@/types/ceoJourney";

interface Props {
  snapshot: AnomalySnapshot | null; explanation: DemoExplanation | null; saved: EvidenceRecord | null;
  records: EvidenceSummary[]; busy: boolean; onExplain: () => void; onSave: () => void;
  onReopen: (id: string) => void; onDownload: () => void;
}
export function CeoEvidencePanel(p: Props) {
  return <section className="ceo-evidence" aria-label="Captured evidence">
    <div className="ceo-step-title"><span>2 · Review and retain the evidence</span></div>
    <h2>{p.snapshot ? `${p.snapshot.row.symbol} · captured anomaly` : "Capture an alert to continue"}</h2>
    {p.snapshot ? <>
      <p>Original row {p.snapshot.row.ordinal} · {p.snapshot.detector} · synthetic label {p.snapshot.row.synthetic_label}</p>
      <p>This snapshot stays fixed when playback or detector selection changes.</p>
      <div className="ceo-paired">{(["transformer", "lightgbm"] as const).map(name => {
        const score = p.snapshot!.paired_scores[name];
        return <div key={name}><b>{name === "transformer" ? "Transformer" : "LightGBM"}</b><strong>{score.probability.toFixed(6)}</strong>
          <span>Threshold {score.threshold.toPrecision(7)}</span><span>{score.alert ? "Threshold alert" : "Below threshold"}</span></div>;
      })}</div>
      <p>{p.snapshot.context.length} preceding saved rows retained.</p>
      <button type="button" disabled={p.busy || !!p.explanation} onClick={p.onExplain}>Explain captured evidence</button>
      {p.explanation ? <div className="ceo-explanation"><b>Deterministic fallback · no LLM call</b><p>{p.explanation.text}</p></div> : null}
      <div className="ceo-toolbar"><button type="button" disabled={p.busy || !p.explanation || !!p.saved} onClick={p.onSave}>Save verified evidence</button>
        <button type="button" disabled={p.busy || !p.saved} onClick={p.onDownload}>Download evidence JSON</button></div>
      {p.saved ? <p role="status">Evidence saved and verified. Reopen it below to check the retained result.</p> : null}
      <p className="ceo-digest">Snapshot SHA-256: {p.snapshot.snapshot_sha256}</p>
    </> : <p>The backend captures original scores and provenance before an explanation can be requested.</p>}
    <h3>Saved evidence</h3>
    {p.records.length ? <ul className="ceo-records">{p.records.map(r => <li key={r.id}>
      <span>{r.symbol} · {r.detector} · {new Date(r.saved_at).toLocaleString()}</span>
      <button type="button" disabled={p.busy} onClick={() => p.onReopen(r.id)}>Reopen {r.id.slice(0, 8)}</button>
    </li>)}</ul> : <p>No saved records in this account yet.</p>}
  </section>;
}
