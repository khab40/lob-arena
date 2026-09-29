import { Area, AreaChart, CartesianGrid, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { Frame } from '../data/replay';

export default function ReplayChart({ frames, index }: { frames: Frame[]; index: number }) {
  return <div className="chart" role="img" aria-label={`Synthetic midpoint at second ${index}: ${frames[index].price.toFixed(2)}. Full values are in the event table.`}>
    <ResponsiveContainer width="100%" height="100%" minWidth={0}>
      <AreaChart data={frames.slice(0, index + 1)} margin={{ top: 12, right: 12, left: 0, bottom: 4 }}>
        <defs><linearGradient id="price-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#8b5cf6" stopOpacity={0.35} /><stop offset="100%" stopColor="#8b5cf6" stopOpacity={0} /></linearGradient></defs>
        <CartesianGrid stroke="var(--chart-grid)" vertical={false} />
        <XAxis dataKey="second" type="number" domain={[0, frames.length - 1]} tick={{ fill: '#9aa8bd', fontSize: 11 }} tickFormatter={(v: number) => `${v}s`} />
        <YAxis domain={[99.92, 100.04]} tick={{ fill: '#9aa8bd', fontSize: 11 }} tickFormatter={(v: number) => v.toFixed(2)} width={58} />
        <Tooltip contentStyle={{ background: '#101827', border: '1px solid #3a4b6c', borderRadius: 8 }} formatter={(v) => [Number(v).toFixed(2), 'Synthetic midpoint']} labelFormatter={(v) => `Second ${v}`} />
        <ReferenceLine y={100} stroke="#3a4b6c" strokeDasharray="4 4" />
        <Area type="linear" dataKey="price" stroke="#a78bfa" strokeWidth={2} fill="url(#price-fill)" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  </div>;
}
