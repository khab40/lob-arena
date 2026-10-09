# Transformer research week: 4–10 October 2026

Reconciled 8 October, Asia/Tbilisi. Tracking:
[Story #24](https://github.com/khab40/lob-arena/issues/24) →
[Feature #16](https://github.com/khab40/lob-arena/issues/16) →
[Epic #15](https://github.com/khab40/lob-arena/issues/15),
[Bug #357](https://github.com/khab40/lob-arena/issues/357),
[Project #3](https://github.com/users/khab40/projects/3).

Goal: decide whether Transformer justifies further research against frozen
LightGBM. The verified outcome supports **continue_research**, accepted by the
operator. [Current status](../roadmap/CURRENT_STATUS.md) owns remaining acceptance;
[this disposition](transformer-research-disposition-20261008.md) owns decision scope.
This plan changes neither experiment protocol nor execution/access/spend authority.

## Verified research milestones

| Completed | Evidence and bounded conclusion |
| --- | --- |
| Replacement smoke and four grid trials | [Grid reports](transformer-training-grid-results.md): 132 artifacts, 42 epoch checkpoints, 23m41s provider runtime. Width 128 / rate 0.0003 / seed 42 / epoch 4 selected by S log loss 0.00243783. |
| Replacement confirmations | [Three-seed results](transformer-confirmation-results-20261004.md): S loss range 0.002395075568322679, F1-at-0.5 range 0.0; both ≤0.05. Seed 42 retained. |
| C-only calibration and paired O comparison | [Report/plots](experiments/transformer-comparison-r2-20261004/report.md): temperature 0.998497; Transformer F1/AP 1.00/1.00 versus LightGBM 0.545/0.436 on identical O rows. Saved baseline reused, no refit. |
| Selected settings and strict holdout consumer | [Settings](transformer-settings-release.md), [package](transformer-holdout-execution-package.md), [metadata admission](transformer-holdout-metadata-results-20261006.md). Original checkpoint/preprocessing/thresholds preserved. |
| Authorized December holdout and independent verification | [Frozen report](transformer-holdout-report-20261007.md): 15,160 rows / 135 positives; balanced F1 95.35% versus 74.48%, zero Transformer false positives. No GPU rerun after arithmetic repair. |
| Settings/reference acceptance and research decision | [Disposition](transformer-research-disposition-20261008.md): #314 scoped acceptance met; full #24 and production qualification remain open. |

[ARD-0042](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md)
retains roles, selection/stability/calibration gates and comparison interpretation.
The independent verifier separates one-ULP calibrated-probability portability,
eight-ULP named float64 reductions and CUDA reference-logit parity. Reference
probability acceptance is separately derived arithmetic, not a fresh inference run.

## Ordered plan

Dates are working targets, conditional on design, review, exact approval and
capacity. Proceed when prerequisites pass; dates never weaken gates.

1. **First saved-score mock — #90/#91.** Authenticate an explicitly configured
   private verified campaign and expose bounded ordered playback, detector/source
   selection, pause/resume/speed, calibrated score, frozen threshold and alert
   provenance. Label saved research predictions. Use an allowlisted private store,
   opaque IDs and local-only access. No model run; public aggregates cannot replace
   private row evidence. Broader shared-deployment authentication stays separately gated.
2. **Dedicated inference adapter — #24/#90.** Bind selected architecture, weights,
   normalizer, temperature and thresholds in a research loader/adapter. Preserve
   original checkpoints and production denial; verify inert contracts first.
3. **Causal event integration — #90.** Reuse canonical 60-feature processing and
   per-stream sequence state. Resolve retained-row sampling, timestamp ties,
   warm-up, gaps/resets, bounded queues and incident consolidation before design
   acceptance. Python inference remains outside Java book mutation. Arena's nine
   display features cannot substitute for the trained inputs.
4. **Fresh bounded rehearsal.** Prepare exact data/resources/timeout/Job-count/spend
   bounds, reviewed packaging and dry-run; obtain separate execution/access approval
   before Nebius scoring. Measure parity, alert identity, lag and throughput. New
   holdout collections use `RetainingReadbackStore`; frozen collectors stay unchanged.
5. **Full acceptance reconciliation.** MLflow #19 indexes the same retained artifacts;
   costs and #24/#90/#91 acceptance stay open until verified. #20/#21 platform work
   follows research. #25 cascade and LOBSTER robustness need separate justified scope.

## Bounds and interpretation

Consumed smoke/grid/confirmation/comparison/holdout approvals are not reusable.
Historical commitments stay held pending billing: four-grid $50 above the
operator-reported $300 baseline, confirmation $25 including failed seed 7, both
comparison reservations $6.25 each, and the existing $6.25 holdout reservation.
The approximately $1 grid estimate is not a bill, released reservation or new
permission. Actual billing and online MLflow remain unreconciled; no billing queries.

The numerical source/checkpoint origin remains separate from later execution
assembly source and immutable images. Keep consumed attempts and original package
hashes intact; do not repeat training to obtain richer logs. Future studies require
fresh exact authorization and [retained readback](transformer-holdout-execution-package.md#future-readback-packages--8-october-2026).

Development O selected thresholds and LightGBM calibration already saw validation.
December was unseen by this Transformer but already used by LightGBM. One date,
three base sessions, synthetic labels/assumed controls and repeated variants limit
generalization. Batch timing is not event-to-alert latency or LightGBM speedup.
No automatic retraining/reselection, production promotion or cascade follows.

## Historical execution snapshots

[The immutable 4–7 October narrative](https://github.com/khab40/lob-arena/blob/d896efe8ca501c1ef8e6c63442f3433948a6405e/docs/ml/transformer-week-plan-20261004.md#4-october-execution-snapshot-before-replacement-approval)
retains failures, grant restoration timings, exact approval/CI milestones and
consumed package identities. Its pending-Job statements are historical. Detailed
[comparison incident](transformer-comparison-abort-20261004.md),
[first-run recovery](transformer-holdout-first-run-recovery-20261007.md),
[verification repair](transformer-holdout-verification-repair-20261007.md) and
[live-logging handoff](transformer-training-progress.md) remain linked evidence.
