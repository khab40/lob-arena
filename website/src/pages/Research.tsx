import { PageIntro, Panel, SourceLink, StatusNote } from '../components/UI';
import { evidence, research, snapshotDate } from '../data/research';

export default function Research() {
  return <>
    <PageIntro eyebrow="03 / RESEARCH" title="Evidence before claims.">Reproducible evaluation connects a result to its data, candidate and decision. A good score is only part of the story.</PageIntro>
    <div className="section-heading"><div><span className="pill success">{research.lightgbm}</span><p className="caption">LightGBM · evidence snapshot {snapshotDate}</p></div><SourceLink href={evidence.disposition}>Signed G9 disposition</SourceLink></div>
    <section className="three-grid metrics" aria-label="LightGBM retained-row metrics">{[['Precision', research.precision], ['Recall', research.recall], ['F1', research.f1]].map(([label, value]) => <article key={label}><span>{label}</span><strong>{Number(value).toFixed(2)}<small>%</small></strong><p>Frozen final evaluation</p></article>)}</section>
    <div className="two-grid section-block"><Panel title="What was measured"><p><strong>15,160 retained observations</strong> across three symbol sessions on one date. Labels are research labels.</p><dl className="facts"><div><dt>False positives</dt><dd>15</dd></div><div><dt>Missed positive observations</dt><dd>46</dd></div><div><dt>Evaluation scope</dt><dd>Retained-row metrics</dd></div></dl><SourceLink href={evidence.results}>Full results and evaluation scope</SourceLink></Panel>
      <Panel title="What this does not establish"><p>These results do not demonstrate production surveillance quality, generalization across market regimes or client readiness.</p><p>Row-level recall is not interchangeable with campaign-level coverage. Data breadth, research labels and false-alert trade-offs remain material limitations.</p><p>The website replay is illustrative and is not the dataset behind these scores.</p></Panel></div>
    <section className="section-block"><div className="section-heading"><div><p className="eyebrow">THE RESEARCH CONTRACT</p><h2>Freeze. Evaluate. Verify.</h2></div></div><div className="three-grid process-grid">
      <article><span className="step-number">01 / DATA</span><h3>Keep the roles separate.</h3><p>Training, validation and final-test roles have explicit boundaries. Historical observations and injected labels retain their provenance.</p></article>
      <article><span className="step-number">02 / CANDIDATE</span><h3>Choose before the final test.</h3><p>Bind the selected model and threshold to frozen identities. Final-test evidence does not feed back into candidate selection.</p></article>
      <article><span className="step-number">03 / EVIDENCE</span><h3>Make verification possible.</h3><p>Link results to their manifests and independent readback. Preserve negative decisions, limitations and the signed disposition.</p></article>
    </div></section>
    <div className="link-row"><SourceLink href={evidence.methodology}>Benchmark methodology</SourceLink><SourceLink href={evidence.roadmap}>Roadmap and remaining gates</SourceLink></div><StatusNote />
  </>;
}
