import { PageIntro, Panel, SourceLink } from '../components/UI';
import { evidence } from '../data/research';

const steps = [
  ['01', 'Governed inputs', 'Historical data and synthetic scenarios, with explicit source and label roles.'],
  ['02', 'Deterministic replay', 'The Java kernel owns exchange semantics and replay state.'],
  ['03', 'Detection & evaluation', 'Rules and learned detectors produce evidence for controlled comparison.'],
  ['04', 'Inspectable artifacts', 'Versioned features, model identities, metrics and verification receipts.'],
];
export default function Architecture() {
  return <>
    <PageIntro eyebrow="04 / ARCHITECTURE" title="A traceable path through the arena.">Separate market execution, detection and explanation so every result has a clear owner.</PageIntro>
    <section className="pipeline" aria-label="Research platform data flow">{steps.map(([number, title, description]) => <article key={number}><span className="step-number">{number}</span><h2>{title}</h2><p>{description}</p></article>)}</section>
    <p className="caption">Research platform architecture. This public website does not execute this pipeline.</p>
    <div className="two-grid section-block"><Panel title="The platform"><dl className="architecture-list"><div><dt>Java kernel & control plane</dt><dd>Authoritative deterministic exchange and live arena orchestration.</dd></div><div><dt>Python research tooling</dt><dd>Governed feature preparation, learned-detector training and evaluation.</dd></div><div><dt>React operator frontend</dt><dd>Replay inspection, evidence views and operational workflows.</dd></div><div><dt>Governed cloud experiments</dt><dd>Nebius Jobs, object storage and MLflow within explicit execution and evidence boundaries.</dd></div></dl></Panel>
      <Panel title="This public website"><div className="static-diagram"><span>Bundled synthetic events</span><b aria-hidden="true">↓</b><span>Browser replay & local state</span><b aria-hidden="true">↓</b><span>Book · chart · event tape</span></div><p>Everything in the demo is packaged with the site. It does not need a backend, account, API key or Nebius connection.</p><p className="caption">Documentation links open published repository pages. They do not connect the replay to the research infrastructure.</p></Panel></div>
    <Panel title="Explanation is not detector authority" className="boundary-panel"><p>AI investigation can help summarize evidence in the wider platform. It does not establish ground truth, replace deterministic evidence or certify an incident. No AI investigator runs on this website.</p></Panel>
    <div className="link-row"><SourceLink href={evidence.architecture}>System architecture</SourceLink><SourceLink href={evidence.methodology}>Evaluation methodology</SourceLink></div>
  </>;
}
