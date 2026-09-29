import type { Frame } from '../data/replay';

export function OrderBook({ frame }: { frame: Frame }) {
  const max = Math.max(frame.bidSize, frame.askSize);
  return <div className="book">
    <div className="book-labels"><span>Bid size</span><span>Price</span><span>Ask size</span></div>
    {[3, 2, 1].map((level) => <div className="book-row ask" key={`a${level}`}>
      <span>—</span><span>{(frame.price + level * 0.01).toFixed(2)}</span>
      <span className="depth"><i style={{ width: `${frame.askSize / max * (1 - (level - 1) * 0.18) * 100}%` }} />{Math.round(frame.askSize * (1 - (level - 1) * 0.18))}</span>
    </div>)}
    <div className="midpoint"><strong>{frame.price.toFixed(2)}</strong><span>SYNTHETIC MIDPOINT</span></div>
    {[1, 2, 3].map((level) => <div className="book-row bid" key={`b${level}`}>
      <span className="depth"><i style={{ width: `${frame.bidSize / max * (1 - (level - 1) * 0.18) * 100}%` }} />{Math.round(frame.bidSize * (1 - (level - 1) * 0.18))}</span>
      <span>{(frame.price - level * 0.01).toFixed(2)}</span><span>—</span>
    </div>)}
    <p className="caption">Illustrative depth in arbitrary units</p>
  </div>;
}
