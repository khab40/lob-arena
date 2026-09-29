import { PageIntro, Panel, SourceLink } from '../components/UI';
import { WalkthroughContact } from '../components/WalkthroughContact';
import { evidence, repository, snapshotDate, source, sourceCommit } from '../data/research';

const docs = [
  ['Start with the project', 'Overview, setup and the research workspace.', `${repository}#readme`],
  ['Understand the architecture', 'Runtime ownership and component boundaries.', evidence.architecture],
  ['Inspect the benchmark', 'Metrics, data roles and evaluation contracts.', evidence.methodology],
  ['Read the LightGBM result', 'Final retained-row metrics and their limits.', evidence.results],
  ['Review the research disposition', 'Signed G9 closure and qualification scope.', evidence.disposition],
  ['Follow the next steps', 'Transformer readiness and later detector work.', evidence.roadmap],
];
export default function About() {
  return <>
    <PageIntro eyebrow="06 / ABOUT & DOCS" title="Built to make research inspectable.">LOB Arena explores how controlled market scenarios can help test and improve market-abuse detectors.</PageIntro>
    <div className="two-grid"><Panel title="About the project"><p>Created by Alexey Khabalov, LOB Arena brings limit-order-book replay, controlled red-team scenarios and blue-team detection into a reproducible research workflow.</p><p>This public site is an introduction to that work. Researchers and potential collaborators can explore a small synthetic story, inspect the published results and follow the underlying engineering.</p><SourceLink href={repository}>Source code on GitHub</SourceLink></Panel>
      <Panel title="Scope & responsible interpretation"><p>The project is a research and validation platform. It does not certify regulatory compliance or establish that historical trading activity constitutes market abuse.</p><p>The public demo contains only hand-authored synthetic values. No licensed market-data payloads, customer data, credentials or private experiment artifacts are bundled.</p><p>There is no analytics tracker, account system or cloud execution in this website.</p></Panel></div>
    <WalkthroughContact />
    <section className="section-block"><div className="section-heading"><div><p className="eyebrow">READ THE SOURCE</p><h2>Documentation, with a clear trail.</h2></div></div><div className="docs-grid">{docs.map(([title, description, href]) => <a href={href} key={title}><div><h3>{title}</h3><p>{description}</p></div><span aria-hidden="true">↗</span></a>)}</div></section>
    <aside className="provenance"><h2>A dated snapshot, not a live status feed.</h2><p>The research content was checked against repository revision <a href={`${repository}/tree/${sourceCommit}`} className="mono">{sourceCommit.slice(0, 7)}</a> on {snapshotDate}. Evidence links pin that revision so the claims remain inspectable.</p><div className="link-row"><SourceLink href={`${repository}/blob/main/docs/roadmap/CURRENT_STATUS.md`}>Latest project status</SourceLink><SourceLink href={source('docs/DOCUMENTATION_GUIDE.md')}>Documentation guide</SourceLink><SourceLink href={`${repository}/issues`}>Discuss the project</SourceLink></div></aside>
  </>;
}
