# Transformer research week: 4–10 October 2026

Reconciled 4 October, Asia/Tbilisi, against verified grid/confirmation results and live
GitHub tracking. [Story #24](https://github.com/khab40/lob-arena/issues/24) →
[Feature #16](https://github.com/khab40/lob-arena/issues/16) →
[Epic #15](https://github.com/khab40/lob-arena/issues/15),
[Project #3](https://github.com/users/khab40/projects/3).

**Goal: decide whether Transformer adds enough value over frozen LightGBM to
justify further research.** Continue, stop and inconclusive are valid outcomes.
This refreshes the existing plan; it does not change the experiment protocol or
authorize execution, final-test access, promotion, merging or cleanup.
Verification: reconcile saved evidence, repository documentation and GitHub state.

## 4 October execution update

The two-seed package in PR #296 was merged and explicitly approved with a $25
additional cap excluding VAT. Seed 7 failed at context delivery before training;
the local attester returned AttributeError without diagnostic origin. Seed 2027
was not submitted. [Failure report](experiments/transformer-confirmation-20261004/seed-7.md).
[Bug #306](https://github.com/khab40/lob-arena/issues/306) repairs diagnostics and
startup-path coverage. The original error's exact cause remains unknown.

PR #307's diagnostic repair is merged. Both exactly approved replacement Jobs
reached COMPLETED and passed independent readback. [Three-seed stability passed](transformer-confirmation-results-20261004.md):
selection-loss range 0.002395075568322679 and F1-at-0.5 range 0.0, below the 0.05
limits. Seed 42 / epoch 4 remains the candidate. PR #308 remains open.
Keep the full $25 confirmation commitment, including the failed attempt's $12.50,
until billing reconciliation. Calibration and LightGBM comparison have not run;
subsequent dates remain conditional and separate exact run/spend approval is required.

## Completed on 3 October

- Startup/publication fixes and the replacement GPU smoke passed independent
  verification; consumed attempts remain preserved.
- All four fixed-grid trials completed sequentially and passed independent
  verification: 132 artifacts, 42 epoch checkpoints and 23m41s provider runtime.
- Selected width **128**, learning rate **0.0003**, seed **42**, checkpoint
  **epoch 4**, by selection log loss **0.00243783**. F1 at 0.5 is 1.0 on the
  tuning fold's 1,250 rows/45 positives; this does not establish Transformer
  superiority over LightGBM.
- Four Markdown reports and loss/F1/confusion-matrix plots are retained.
  Rich live epoch/selection logging is implemented for a future runtime package.
- [PR #291](https://github.com/khab40/lob-arena/pull/291) merged on 4 October as
  `25668a1`; all 25 checks passed on its implementation head `e3e1332`.
  [Bug #292](https://github.com/khab40/lob-arena/issues/292) is closed/Done.

## Ordered plan

Dates are working targets, conditional on review, exact approval, capacity and
verification. Proceed as soon as prerequisites pass; do not wait for a calendar
day or weaken checks to meet one. Keep related work in medium, reviewable PRs.

1. **4 October — confirm stability: complete.** Both replacement seeds **7 and
   2027** completed sequentially and passed independent verification. Both
   selection-loss and F1 ranges pass the existing ≤0.05 stability gates. Keep
   seed 42 / epoch 4 as candidate; do not select the luckiest seed.
2. **5 October — calibrate and compare.** Prepare one separately authorized
   calibration/inference Job, at most one hour, with explicit checkpoint-origin
   compatibility and an exact request/image, dry-run and spend approval.
   Fit temperature only on C (5,490 rows); choose declared operating points and
   compare on the identical O targets (2,470 rows). Reuse frozen LightGBM
   predictions/calibrator/thresholds; no refit, rescore or final-fold access.
3. **6 October — verify and decide.** Recompute prediction metrics, calibration,
   threshold and family results; verify hashes, lineage, seed spread and resources.
   Report actual quality deltas and limitations. Record `continue_research`,
   `stop_transformer` or `inconclusive`; a failed run is not an architectural loss.
4. **7 October — retain the decision package.** Bind selected weights, input
   contract, normalization, configuration, calibration, thresholds, predictions,
   plots, resource/cost disposition and independent receipts. Freeze a candidate
   only if existing stability/calibration/operating-point gates pass. Preserve
   failed gates and negative results without further search.
5. **8–9 October — reconcile MLflow after the research decision.** Index the same
   retained runs/artifacts without retraining. Keep online registration/alias and
   restoration acceptance separately visible under [#19](https://github.com/khab40/lob-arena/issues/19).
   Resume prioritized [#20](https://github.com/khab40/lob-arena/issues/20)/
   [#21](https://github.com/khab40/lob-arena/issues/21) work after research, without
   promising all platform acceptance within this week.
6. **10 October — review the outcome and reforecast.** Reserve this day for
   evidence/review delays and the next plan. Keep [#25](https://github.com/khab40/lob-arena/issues/25)
   Todo unless the decision justifies a separately approved cascade study.
   Reforecast #90/#91 around the selected detector approach. M3's 9 October
   date remains a baseline; a research decision alone does not close all of #24.

## Bounds and interpretation

Remaining planned model work is **one Job / one timeout GPU-hour**, requiring
separate exact authorization: one L40S, 8 vCPU, 32 GiB RAM, 100 GiB disk,
concurrency one and restart never.
The completed four-Job authorization is consumed. Its $50 reservation above the
operator-reported $300 baseline remains committed pending billing reconciliation;
the roughly $1 compute/disk estimate is not a bill or reusable authorization.
Exact next-stage monetary bounds must be approved before submission.
The $25 confirmation commitment also remains held; neither completed Jobs nor
estimated savings release it or authorize calibration.

The replacement package layers four execution modules onto the grid's original
digest image, preserving numerical source `87ce8a9` and all model/dependency bytes.
It admits only confirmation seeds and exact legacy smoke/grid references. Later
inference needs explicit checkpoint-origin compatibility; it cannot relabel the
seed-42 checkpoint's original bindings. New logging is not part of this image.
Existing epoch artifacts provide post-run curves; do not repeat training for logs.

O is also used for threshold selection, LightGBM calibration previously saw the
validation fold, and labels remain synthetic/research controls. Report these
limits; neither untouched holdout performance nor a LightGBM speedup is established.
G8/G9 remain closed. Platform work and cascade implementation do not precede the
research decision. Any later qualification protocol requires separate data/scope.

Evidence: [grid results](transformer-training-grid-results.md),
[per-run reports](experiments/transformer-grid-20261003/index.md),
[selection and decision protocol](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md),
[live logging handoff](transformer-training-progress.md).
