// Hand-authored illustrative data. No licensed feed, model output or live prices.
export type Frame = {
  second: number; price: number; bidSize: number; askSize: number;
  event: string; phase: string; flag: boolean;
};
export type Replay = { id: string; title: string; description: string; frames: Frame[] };
const frame = (second: number, price: number, bidSize: number, askSize: number,
  event: string, phase: string, flag = false): Frame =>
  ({ second, price, bidSize, askSize, event, phase, flag });
export const replays: Replay[] = [
  {
    id: 'layering', title: 'Layering illustration',
    description: 'Large sell-side orders appear, the displayed balance shifts, then the orders are cancelled. A pre-authored flag connects the sequence to its evidence.',
    frames: [
      frame(0, 100.00, 240, 210, 'Balanced opening book', 'Baseline'),
      frame(1, 100.02, 260, 230, 'Small buy order added', 'Baseline'),
      frame(2, 100.01, 250, 780, 'Large sell layer appears', 'Placement'),
      frame(3, 99.99, 230, 1150, 'Additional sell layer appears', 'Placement'),
      frame(4, 99.97, 200, 1340, 'Displayed sell pressure increases', 'Pressure'),
      frame(5, 99.95, 190, 1420, 'Illustrative price moves lower', 'Pressure'),
      frame(6, 99.94, 300, 1300, 'Small opposite-side trade', 'Trade'),
      frame(7, 99.96, 290, 280, 'Large sell layers cancelled', 'Cancellation', true),
      frame(8, 99.99, 260, 240, 'Book returns toward balance', 'Recovery', true),
      frame(9, 100.01, 250, 220, 'Evidence window closes', 'Recovery', true),
    ],
  },
  {
    id: 'control', title: 'Quiet market control',
    description: 'Ordinary additions, trades and cancellations keep the displayed book balanced. This illustrative control has no pre-authored alert.',
    frames: [
      frame(0, 100.00, 240, 210, 'Balanced opening book', 'Baseline'),
      frame(1, 100.01, 260, 230, 'Small buy order added', 'Normal flow'),
      frame(2, 100.00, 240, 250, 'Small sell order added', 'Normal flow'),
      frame(3, 99.99, 220, 240, 'Trade at the bid', 'Normal flow'),
      frame(4, 100.00, 250, 230, 'Bid liquidity replenished', 'Normal flow'),
      frame(5, 100.01, 260, 220, 'Trade at the ask', 'Normal flow'),
      frame(6, 100.00, 230, 240, 'Small order cancelled', 'Normal flow'),
      frame(7, 100.02, 270, 230, 'Two-sided quoting continues', 'Normal flow'),
      frame(8, 100.01, 250, 250, 'Book remains balanced', 'Normal flow'),
      frame(9, 100.00, 240, 240, 'Control window closes', 'Normal flow'),
    ],
  },
];
export function nextFrame(index: number, length: number) {
  return Math.min(index + 1, Math.max(0, length - 1));
}
