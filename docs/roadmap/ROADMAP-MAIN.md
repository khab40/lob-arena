# Main Roadmap

> **Schedule risk:** September 23 LightGBM exit is at risk; later dates remain
> baseline targets, not a confirmed forecast. C0–C4 and G0–G8 are complete.
> G9 awaits operator cost disposition and a signed exit decision. See
> [current status](CURRENT_STATUS.md) for independently verified final results.

Status date: 2026-09-23. See [current status and evidence](CURRENT_STATUS.md).

Baseline target for the current Nasdaq/LOBSTER learned-detector milestone:
**2026-11-20**.

Baseline feature-complete date: **2026-11-13**, followed by one week for
deployment, security verification, rehearsal, and final acceptance.

Critical path:

`G8-G9 LightGBM -> Transformer -> Transformer/LightGBM hybrid -> integrated evidence -> secure CEO UI -> final demo`

## Current Position

Read [current status](CURRENT_STATUS.md) for gate outcomes, current blockers,
candidate identity and receipts. This roadmap owns baseline dates and forward
acceptance scope. A passed rehearsal or metadata check does not close a
model-quality gate; old final-test approval cannot be reused.

## Milestones And Dates

| Target | Milestone | Expected result |
| --- | --- | --- |
| **2026-09-03** | Train-date C3 complete | Both train dates have 27/27 comparisons, immutable output manifests, `SUCCESS`, runtime and checksum evidence |
| **2026-09-03** | Roadmap correction PR | Replace the stale seven-date/15-Job design with the approved four-date corpus and minimum 18 public-data Jobs |
| **2026-09-11** | C4 corpus freeze | Two train dates, one validation date, one test date; tabular and sequence projections; leakage and access-denial proof |
| **2026-09-07** | G5 complete | Three sequential identical LightGBM Jobs passed all nine gates and 21 deterministic comparisons |
| **2026-09-10** | G6 complete | Nine bounded development Jobs passed all gates; isotonic candidate selected |
| **2026-09-23** | G7-G9 complete | Candidate freeze, one authorized final evaluation, cost reconciliation, and signed Wave 1 decision |
| **2026-10-09** | Transformer complete | Verified causal standalone Transformer bundle, calibration, GPU/runtime/cost evidence |
| **2026-10-23** | Hybrid complete | `transformer_feature_release_v1`, exact join, cascade LightGBM, ablation, and champion/rollback decision |
| **2026-10-30** | Integrated E2E package complete | One campaign joining Nasdaq, LOBSTER, rules, LightGBM, Transformer, hybrid, and cost evidence |
| **2026-11-13** | CEO UI feature complete | Secure five-step guided UI backed only by verified campaign artifacts |
| **2026-11-20** | Final acceptance and CEO demonstration | Deployed rehearsal, security tests, evidence verification, demo script, and management report |

## Phase 1 - Finish The Governed Corpus

Dates: **2026-09-01 through 2026-09-11**  
GitHub: [#22 Governed market-data corpus](https://github.com/khab40/lob-arena/issues/22)

Use the reduced chronological corpus:

- Train: `2019-01-30`, `2019-03-27`
- Validation: `2019-10-30`
- Final test: `2019-12-30`
- Symbols: AAPL, MSFT, NVDA
- Window: 10:00-10:30 ET
- Depth: 10

Execution:

1. ~~Finish and reconcile the `2019-01-30` preparation.~~ Complete.
2. ~~Prepare the already-acquired `2019-03-27` source.~~ Complete.
3. ~~Acquire and prepare `2019-10-30`.~~ Complete.
4. ~~Acquire and prepare `2019-12-30`.~~ Complete.
5. C4 corpus/split and both projections frozen. Complete.
6. Development-to-final access denial proved. Complete.

The completed public-data campaign used the amended **18-Job** planning envelope.
Earlier eleven-Job consumption and projected recovery headroom were intermediate
planning observations, not current execution authority.

## Phase 2 - G5 Through LightGBM Completion

Dates: **2026-09-14 through 2026-09-23**  
GitHub: [#23 LightGBM qualification](https://github.com/khab40/lob-arena/issues/23)

### G5 - Reproducibility

Run the identical development request three times sequentially.

The following must match exactly:

- model and prediction hashes;
- metrics and best iteration;
- calibration and thresholds;
- ordered features and feature importance; and
- corpus, split, projection, and configuration identities.

Different Job IDs, timestamps, runtime, and cost are permitted.

**Complete 2026-09-07.** Successful Jobs
`aijob-e00qe81x3p8td0sgmj`, `aijob-e00nq0t5p6j8jk88z3`, and
`aijob-e00aw1zyvs4nf931ef` map respectively to MLflow runs
`e3dd3db46d9741d89b3ed230df109c09`,
`36589c337eb343a6bfe826ac3fb347dd`, and
`ce34abdaf5014224b636f9a83354e67a`. The strict comparison receipt has status
`passed`, disposition `g5_reproducibility_passed`, nine passing gates, and 21
matching deterministic fields.

### G6 - Bounded Development Campaign

Run the nine remaining experiments:

- two hyperparameter configurations;
- two feature-family ablations;
- two candidate seed-stability runs; and
- raw, Platt, and isotonic calibration comparisons.

The fixed matrix, validation-only ordering, seed tolerances and calibration
gate are now encoded in
`configs/experiments/lightgbm-wave1/g6-campaign-20260907.json`. Four concrete
search Jobs run first. Their selected experiment is then mechanically reused
for the two seed and three calibration Jobs; no result-dependent trial is
added. The completion comparator requires all nine planned run IDs, matching
input/runtime-image identities, recorded source provenance, verified collection
receipts, no test access, and retention of every rejected candidate.
Each Job is also required to produce a distinct run in
`lob-arena/lightgbm-development` with metadata-only governed dataset inputs,
validation/detection/calibration metrics, artifacts and cloud resource
evidence; raw rows are not uploaded to MLflow.

The initial infrastructure-only G5 failure and three successful repeats raised
consumption from seven to 11 of the separate 20-Job LightGBM development
ceiling. In accordance with the predeclared failure rule, the unstarted G6
matrix drops one hyperparameter configuration and now consumes the nine
remaining slots. There is no failure reserve unless the matrix is reduced
again or the cap is formally amended before submission.

**Complete 2026-09-10.** The search selected `ablate-state`; seeds 42, 7, and
2027 reproduced F1 `0.6931407942`, minimum family recall `0.5333333333`, and
validation binary log loss `0.3449773248` exactly. Isotonic retained those
detection metrics while improving calibrated Brier score to
`0.0068910983` and validation ECE to `1.4586e-18`, ahead of Platt
(`0.0080377169`, `0.0042177037`) and raw
(`0.0209358031`, `0.0816111663`). These are validation-only research metrics,
not final-test or production claims.

All nine collection receipts verified, all nine MLflow run IDs are distinct,
dataset lineage is metadata-only, and no test fold was accessed. The immutable
runtime image and dataset identity match across the campaign. Two recorded
control-plane Git SHAs reflect the receipt-reliability fix applied before the
last two packages; the runtime image, inputs, experiment specifications, model,
and raw calibration predictions did not change. The original fail-closed
diagnostic is retained separately from the passing final receipt.

### G7-G9

- G7: complete. The validation-selected candidate is checksum-frozen, the
  exact-hash operator statement is signed, and independent verification exposes
  the final identity without reading the test fold.
- G8: complete. The separately approved replacement Job
  `aijob-e00kd6g7vaqtngwv9r` scored the frozen candidate once and completed within
  three hours. Independent readers verified 176 S3 objects, four final MLflow
  artifacts, 30 full dataset identities and 24 metrics recorded once each.
  Final key INACTIVE, temporary SSH rule absent, worker released and VM STOPPED.
- Final retained-row precision is 85.58%, recall 65.93% and F1 74.48%, with
  15 false positives and 46 missed positive observations. Coverage is one date,
  three symbols and research labels; this does not establish production acceptance.
- G9: pending operator cost disposition and signed exit. The
  [results and unsigned handoff](../operations/g8/g8-final-results-20260923.md)
  bind measured quality and resource limits. The selected model remains frozen.
- R4's four prior submissions, consumed approval and pre-scoring failure remain
  historical evidence. The approved replacement does not erase that history.

Remaining critical path:

1. Review the [G8 closure evidence in PR #223](https://github.com/khab40/lob-arena/pull/223).
2. Record G9's quality, resource and operator-provided cost disposition, then
   obtain the signed Wave 1 exit decision. Do not infer it from Job success.
3. Replan downstream dates if required by that decision. Any new model campaign
   preserves this result and uses fresh untouched held-out evaluation data.

See the [detailed G8 plan](PHASES.md#g8-recovery-and-completion-plan). Apply the
[validation execution policy](../ml/model-validation-execution-policy.md): model/runtime
work runs on Nebius Serverless; historical billing-freshness, submission-expiry and
fixed VM windows are not current prerequisites. Final-test approval remains separate.

Wave 2 starts only if the disposition is `qualified_for_wave2` or
`research_baseline_qualified`.

## Phase 3 - Standalone Transformer

Dates: **2026-09-24 through 2026-10-09**  
GitHub: [#24 Market-sequence Transformer](https://github.com/khab40/lob-arena/issues/24)

Classifier/training implementation has not started. C4 sequence projection
materialization is already implemented and frozen; Wave 2 must validate its
consumer, causal sampling and cross-model row alignment.

Deliverables:

- causal sequence contract with cutoff, length, stride, masking, and row
  identity;
- CPU sequence materialization;
- smallest viable Transformer classifier;
- bounded GPU training matrix;
- seed stability, calibration, and threshold selection;
- one final governed evaluation;
- model bundle containing weights, preprocessing, schema, and checksums;
- comparison against LightGBM on identical rows; and
- GPU hours, cost, memory, throughput, and inference latency.

The Transformer may be approved as a feature producer even if it does not beat
LightGBM as a standalone model.

## Phase 4 - Transformer-To-LightGBM Hybrid

Dates: **2026-10-12 through 2026-10-23**  
GitHub: [#25 Transformer to LightGBM cascade](https://github.com/khab40/lob-arena/issues/25)

Deliverables:

- immutable `transformer_feature_release_v1`;
- causal Transformer scores or embeddings for every governed row;
- exact identity-based join with `lob_features_v2`;
- separate hybrid LightGBM family;
- comparison of rules, tabular LightGBM, Transformer, hybrid, and optional late
  fusion;
- staleness, missing-feature, and failure-path tests;
- visible fallback to verified tabular LightGBM; and
- signed champion/candidate/rollback decision.

A negative result is valid: the hybrid must not be promoted merely because it
was built.

## Phase 5 - Integrated Evidence Flow

Dates: **2026-10-26 through 2026-10-30**  
GitHub: [#90 Three-model E2E evidence flow](https://github.com/khab40/lob-arena/issues/90)

Produce one campaign identity that binds:

- Nasdaq and LOBSTER source manifests;
- corpus, split, tabular, and sequence projections;
- rules, LightGBM, Transformer, and hybrid models;
- identical-row Nasdaq comparison;
- separate no-retuning LOBSTER robustness results;
- MLflow references, resource use, and cost; and
- limitations and the research-only claim boundary.

Support both a full evidence mode and a deterministic rehearsal using retained
artifacts without triggering new cloud spending.

## Phase 6 - Improved CEO UI

Dates: **2026-11-02 through 2026-11-13**  
GitHub: [#91 Secure CEO-facing UI](https://github.com/khab40/lob-arena/issues/91)

Guided flow:

**Sign in -> Data -> Replay -> Experiments -> Management Summary**

Key improvements:

- backend-enforced Google authentication and workspace authorization;
- Nasdaq/LOBSTER provenance, lifecycle, split, and projection status;
- asynchronous replay loading with clear progress and failure states;
- side-by-side rules, LightGBM, Transformer, and hybrid results;
- quality, calibration, detection delay, throughput, and CPU/GPU cost;
- clear champion and rollback decision;
- separate Nasdaq final-test and LOBSTER robustness results;
- one-page CEO report with value, limitations, and commercial next step; and
- deterministic rehearsal that cannot launch unbounded Jobs.

Final acceptance requires a non-technical reviewer to understand what was
tested, which model won, whether the extra Transformer complexity was
justified, and why the evidence is research-only.

## GitHub Project Reconciliation

Reconciled on **2026-09-13**:

- [#22](https://github.com/khab40/lob-arena/issues/22) records completed C0-C4,
  the frozen four-date forward corpus, and its governed release evidence.
- [#23](https://github.com/khab40/lob-arena/issues/23) records the completed
  G5-G7 evidence, the 20/20 consumed-slot reconciliation, the selected and
  authorized validation-only isotonic candidate, all three fail-closed
  pre-test G8 attempts, the corrected least-privilege G6 campaign policy, the
  exact-image runtime compatibility gate, and the G8-G9 remainder.
- [#28](https://github.com/khab40/lob-arena/issues/28) is Todo until #25 and #27
  complete.
- [#19](https://github.com/khab40/lob-arena/issues/19),
  [#20](https://github.com/khab40/lob-arena/issues/20), and
  [#21](https://github.com/khab40/lob-arena/issues/21) remain In Progress with
  completed foundations and outstanding exit evidence distinguished explicitly.
- Seven dated GitHub milestones now encode the targets in this document. The
  critical-path issues and supporting platform/Investigator issues are assigned
  to their expected exit milestone.

The AI Investigator lane—[#26](https://github.com/khab40/lob-arena/issues/26),
[#27](https://github.com/khab40/lob-arena/issues/27), and
[#28](https://github.com/khab40/lob-arena/issues/28)—is supporting work, not
detector authority. It can be completed alongside the integrated evidence and
UI phases but must never change detector scores or labels.

## Schedule Assumptions And Risks

The **2026-11-20** forecast assumes:

- same-day approval of reviewed cloud packages and submissions;
- no additional C3 root-cause-analysis cycle;
- bounded GPU capacity is available for the Transformer campaign;
- Google OAuth and deployment configuration are available before shared UI
  testing; and
- each code change starts from refreshed `origin/main` and is delivered through
  a dedicated PR.

A further cloud failure or delayed OAuth configuration should move the final
date by approximately one week rather than compressing verification.

After this milestone exits, the parked commercial continuation is governed BYO
data and BYO detector adapters. It is intentionally outside the 2026-11-20
completion target.
