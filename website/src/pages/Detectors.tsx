import { PageIntro, SourceLink, StatusNote } from '../components/UI';
import { evidence, research, snapshotDate } from '../data/research';

export default function Detectors() {
  return <>
    <PageIntro eyebrow="05 / DETECTORS & ML" title="A baseline. A challenger. A direction.">Each detector has its own evidence and readiness boundary. The roadmap does not stand in for a completed model.</PageIntro>
    <p className="caption">Status snapshot: {snapshotDate}. Follow the linked roadmap for subsequent changes.</p>
    <section className="detector-list">
      <article><div className="detector-index">01</div><div><div className="section-heading"><h2>Deterministic rules</h2><span className="pill">REFERENCE PATH</span></div><p>Explicit logic provides an inspectable comparison point for abuse-like patterns in controlled replay. Thresholds and context influence false-alert load.</p><SourceLink href={evidence.results}>Rules and LightGBM evaluation</SourceLink></div></article>
      <article className="highlight"><div className="detector-index">02</div><div><div className="section-heading"><h2>LightGBM</h2><span className="pill success">RESEARCH BASELINE</span></div><p className="mono status-code">{research.lightgbm}</p><p>The governed tabular baseline completed its frozen evaluation and signed G9 research disposition. Its scope remains one date, three symbols and research labels.</p><div className="small-metrics"><span><strong>85.58%</strong> Precision</span><span><strong>65.93%</strong> Recall</span><span><strong>74.48%</strong> F1</span></div><SourceLink href={evidence.disposition}>Qualification scope and decision</SourceLink></div></article>
      <article><div className="detector-index">03</div><div><div className="section-heading"><h2>Market-sequence Transformer</h2><span className="pill warning">READINESS WORK</span></div><p><strong>{research.transformer}, before GPU training.</strong> Source lineage, role support, the bounded audit package and MLflow readiness must be verified before the training campaign proceeds.</p><p>No trained Transformer quality result or completed GPU campaign is claimed here.</p><SourceLink href={evidence.transformer}>Input and provenance verification</SourceLink></div></article>
      <article><div className="detector-index">04</div><div><div className="section-heading"><h2>Transformer → LightGBM</h2><span className="pill">PLANNED / GATED</span></div><p>A later cascade would add causal sequence outputs to tabular features. It depends on a verified standalone Transformer and a fair comparison on identical evaluation rows.</p><SourceLink href={evidence.roadmap}>Detector roadmap and gates</SourceLink></div></article>
    </section>
    <div className="direction"><p className="eyebrow">WHERE THIS IS HEADING</p><h2>From offline evidence toward timely detection.</h2><p>{research.direction} Replay quality, inference latency, throughput, alert load and operational safeguards need separate evidence before live or shadow-mode claims.</p></div><StatusNote />
  </>;
}
