import { Link } from 'react-router';
import { OrderBook } from '../components/OrderBook';
import { TeamMark } from '../components/TeamMark';
import { SourceLink, StatusNote } from '../components/UI';
import { replays } from '../data/replay';
import { evidence, research, snapshotDate } from '../data/research';

export default function Home() {
  return <>
    <section className="hero">
      <div className="hero-copy"><p className="eyebrow"><span className="short-rule" /> THE MARKET IS THE TEST.</p>
        <h1>Put detection<br />under <em>pressure.</em></h1>
        <p className="lede">Replay the market. Introduce controlled attacks. Find out what your detectors actually catch.</p>
        <p className="hero-description">LOB Arena is a research and validation platform for market-abuse detection, built around reproducible limit-order-book scenarios and inspectable evidence.</p>
        <div className="actions"><Link to="/demo" className="button">Explore the arena <span aria-hidden="true">↗</span></Link><Link to="/research" className="button secondary">Read the research</Link><Link to="/about#contact" className="text-link walkthrough-link">Request a walkthrough <span aria-hidden="true">→</span></Link></div>
        <div className="hero-footnote"><span className="status-dot" /> Bundled synthetic demo · no account required</div>
      </div>
      <div className="hero-terminal">
        <div className="terminal-header"><span><i className="terminal-dot" /> LOB / DEMO-01</span><span className="pill">SYNTHETIC</span></div>
        <div className="terminal-title"><div><span className="eyebrow">ORDER BOOK</span><h2>Pressure, then withdrawal.</h2></div><span className="mono">T+07s</span></div>
        <OrderBook frame={replays[0].frames[7]} />
        <div className="terminal-alert"><TeamMark team="red" /><div><strong>Layer cancellation</strong><small>A sequence worth investigating</small></div><span className="pill warning">DEMO FLAG</span></div>
        <Link className="terminal-link" to="/demo">Replay the full sequence <span>→</span></Link>
      </div>
    </section>
    <StatusNote />
    <section className="section-block"><div className="section-heading"><div><p className="eyebrow">ONE CONTROLLED LOOP</p><h2>From scenario to evidence.</h2></div><Link to="/architecture" className="text-link">Inside the architecture ↗</Link></div>
      <div className="three-grid process-grid">
        <article><TeamMark team="red" /><span className="step-number">01 / REPLAY</span><h3>Make the conditions repeatable.</h3><p>Replay a controlled market sequence. Separate historical observations from deliberately injected attack labels.</p></article>
        <article><TeamMark team="blue" /><span className="step-number">02 / DETECT</span><h3>Challenge the detector.</h3><p>Compare deterministic rules and learned approaches against explicit ground truth and frozen evaluation boundaries.</p></article>
        <article><span className="evidence-symbol" aria-hidden="true">≡</span><span className="step-number">03 / VERIFY</span><h3>Keep the result inspectable.</h3><p>Connect outcomes to their data, model and evaluation identities. Explain failures alongside successes.</p></article>
      </div>
    </section>
    <section className="research-strip"><div><p className="eyebrow">LIGHTGBM RESEARCH BASELINE</p><h2>Measured. With boundaries.</h2><p>One date · three symbols · research labels</p></div><div className="metric-inline"><strong>{research.f1.toFixed(2)}<small>%</small></strong><span>retained-row F1</span></div><div><span className="pill success">Research baseline qualified</span><p className="caption">Evidence snapshot: {snapshotDate}</p><SourceLink href={evidence.results}>Results & limitations</SourceLink></div></section>
  </>;
}
