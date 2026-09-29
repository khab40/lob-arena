export const repository = 'https://github.com/khab40/lob-arena';
// Immutable evidence snapshot; refresh deliberately after reviewing the sources.
export const sourceCommit = 'b3724b88fb4e5d4d29a453c4f1d58758a2e5a2ef';
export const snapshotDate = '29 September 2026';
export const source = (path: string) => `${repository}/blob/${sourceCommit}/${path}`;
export const research = {
  lightgbm: 'research_baseline_qualified',
  transformer: 'Readiness / input verification',
  direction: 'Near-real-time detection is a target, not a production capability.',
  precision: 85.58, recall: 65.93, f1: 74.48,
  observations: 15160, falsePositives: 15, missedPositives: 46,
};
export const evidence = {
  results: source('docs/operations/g8/g8-final-results-20260923.md'),
  disposition: source('docs/operations/g8/g9-closure-20260927.md'),
  status: source('docs/roadmap/CURRENT_STATUS.md'),
  roadmap: source('docs/roadmap/ROADMAP-MAIN.md'),
  methodology: source('docs/ml/benchmark-methodology.md'),
  architecture: source('docs/architecture.md'),
  transformer: source('docs/ml/transformer-role-provenance.md'),
};
