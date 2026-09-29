import { useEffect, useState } from 'react';
import { OrderBook } from '../components/OrderBook';
import ReplayChart from '../components/ReplayChart';
import { TeamMark } from '../components/TeamMark';
import { PageIntro, Panel } from '../components/UI';
import { nextFrame, replays } from '../data/replay';

export default function Demo() {
  const [scenario, setScenario] = useState(0);
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const replay = replays[scenario];
  const frame = replay.frames[index];
  const atEnd = index === replay.frames.length - 1;
  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setIndex((current) => {
        const next = nextFrame(current, replay.frames.length);
        return next;
      });
    }, 900);
    return () => window.clearInterval(timer);
  }, [playing, replay]);
  // Stop scheduling at the end without resetting the final evidence frame.
  useEffect(() => { if (atEnd) setPlaying(false); }, [atEnd]);
  const reset = () => { setPlaying(false); setIndex(0); };
  return <>
    <PageIntro eyebrow="02 / ARENA DEMO" title="Follow the sequence.">A small, synthetic market story. Move through the book and inspect what changes.</PageIntro>
    <div className="demo-disclosure"><span className="pill">ILLUSTRATIVE DATA</span><p>Hand-authored events and flags. No live market feed, model inference or measured detector scores.</p></div>
    <section className="replay-toolbar" aria-label="Replay controls">
      <label className="scenario-label">Scenario<select value={scenario} onChange={(e) => { setScenario(Number(e.target.value)); reset(); }}>{replays.map((item, i) => <option value={i} key={item.id}>{item.title}</option>)}</select></label>
      <div className="playback-buttons"><button className="button" onClick={() => { if (atEnd) setIndex(0); setPlaying(!playing); }}>{playing ? 'Pause' : atEnd ? 'Replay' : 'Play'}</button><button className="button secondary" disabled={atEnd || playing} onClick={() => setIndex(nextFrame(index, replay.frames.length))}>Step</button><button className="button secondary" onClick={reset}>Reset</button></div>
      <span className="playback-status" role="status">{playing ? 'Playing' : atEnd ? 'Complete' : 'Paused'} · {index + 1}/{replay.frames.length}</span>
    </section>
    <p className="scenario-description">{replay.description}</p>
    <div className="demo-grid">
      <Panel title="Synthetic order book"><OrderBook frame={frame} /></Panel>
      <Panel title="Midpoint over the replay"><div className="chart-label"><span className="mono">DEMO-01</span><span>Arbitrary price units</span></div><ReplayChart frames={replay.frames} index={index} /><label className="scrubber">Replay position: {index}s<input aria-label="Replay position" type="range" min="0" max={replay.frames.length - 1} value={index} onChange={(e) => { setPlaying(false); setIndex(Number(e.target.value)); }} /></label></Panel>
    </div>
    <div className="demo-grid evidence-grid">
      <Panel title="Evidence at this frame"><div className="evidence-state"><TeamMark team={frame.flag ? 'red' : 'blue'} /><div><span className={`pill ${frame.flag ? 'warning' : ''}`}>{frame.flag ? 'Illustrative flag' : 'No illustrative flag'}</span><h3>{frame.phase}</h3></div></div><p data-testid="current-event">{frame.event}</p><p className="caption">{frame.flag ? 'Placement → pressure → cancellation. The flag is part of the bundled story; it is not a detector verdict or proof of market abuse.' : 'Explore the next frame to follow the event sequence. Absence of a scripted flag is not evidence of detector performance.'}</p></Panel>
      <Panel title="Event tape"><div className="table-wrap"><table><caption className="sr-only">Synthetic events revealed so far</caption><thead><tr><th>Time</th><th>Midpoint</th><th>Event</th></tr></thead><tbody>{replay.frames.slice(0, index + 1).map((item) => <tr key={item.second}><td className="mono">+{item.second}s</td><td className="mono">{item.price.toFixed(2)}</td><td>{item.event}</td></tr>)}</tbody></table></div></Panel>
    </div>
  </>;
}
