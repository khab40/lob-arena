import type { SavedProvenance, SavedScoreRow } from "@/types/savedScores";

export function ScorePlot({ rows, threshold }: { rows: SavedScoreRow[]; threshold?: number }) {
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

export function Provenance({ value }: { value: SavedProvenance }) {
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
