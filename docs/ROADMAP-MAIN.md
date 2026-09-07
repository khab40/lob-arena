# Main Roadmap

Status date: 2026-09-07

Target completion for the current Nasdaq/LOBSTER learned-detector milestone:
**2026-11-20**.

Expected feature-complete date: **2026-11-13**, followed by one week for
deployment, security verification, rehearsal, and final acceptance.

Critical path:

`G6-G9 LightGBM -> Transformer -> Transformer/LightGBM hybrid -> integrated evidence -> secure CEO UI -> final demo`

## Current Position

- C0-C4 are complete. The C4 MLflow dataset-release receipt binds the release
  hashes to run `dc119d708cc4464e8fe1b82ba976bf3e`
  (`c5818eb6c836cc7693d025422553c36ed0c2981fd0c39af03f1f483cada8af7b`);
  G5 execution evidence verifies 240 metadata-only inputs and no raw-row upload.
- G5 passed on 2026-09-07. Three sequential successful Jobs produced the same
  reproducibility hash, best iteration, validation loss, governed identities,
  model outputs, predictions, calibration, thresholds, and feature evidence.
  All nine comparison gates and all 21 deterministic fields passed.
- The G5 execution and comparison receipts are recorded under
  `outputs/lightgbm-wave1/nasdaq-g5-repro-20260906/` with SHA-256 digests
  `ac51f8d3a40210e40ab66c0bb5b766c7807176a5a497b2f1992c4a27f5b0bd38`
  and `d6209d45027f376ac67d55fd8f1cdf7428b0e635d6f5fc011e45600051aedcb1`.
- One infrastructure-only G5 result-publication failure consumed a slot before
  the three successful repeats. Eleven of 20 development slots are consumed;
  the fixed G6 matrix is reduced to nine Jobs. MLflow is stopped between
  authorized experiment windows.
- GitHub Project #3 contains 74 items. Seven dated repository milestones now
  cover the active critical path from the corpus freeze through final CEO-demo
  acceptance.
- All new repository changes use dedicated branches and PRs created from a
  refreshed `origin/main` baseline.

## Milestones And Dates

| Target | Milestone | Expected result |
| --- | --- | --- |
| **2026-09-03** | Train-date C3 complete | Both train dates have 27/27 comparisons, immutable output manifests, `SUCCESS`, runtime and checksum evidence |
| **2026-09-03** | Roadmap correction PR | Replace the stale seven-date/15-Job design with the approved four-date corpus and minimum 18 public-data Jobs |
| **2026-09-11** | C4 corpus freeze | Two train dates, one validation date, one test date; tabular and sequence projections; leakage and access-denial proof |
| **2026-09-07** | G5 complete | Three sequential identical LightGBM Jobs passed all nine gates and 21 deterministic comparisons |
| **2026-09-18** | G6 complete | Nine bounded development Jobs: tuning, ablations, seed stability, and calibration |
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
3. Acquire and prepare `2019-10-30`.
4. Acquire and prepare `2019-12-30`.
5. Run C4 to freeze the corpus, split, `tabular_projection_v1`, and
   `sequence_projection_v1`.
6. Prove that development credentials cannot read final projections.

The public-data plan has an **18-Job cap**. Given the eleven Jobs already
consumed, the reduced design should finish C4 around public-data Job 16,
leaving two recovery slots.

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

The initial infrastructure-only G5 failure and three successful repeats raised
consumption from seven to 11 of the separate 20-Job LightGBM development
ceiling. In accordance with the predeclared failure rule, the unstarted G6
matrix drops one hyperparameter configuration and now consumes the nine
remaining slots. There is no failure reserve unless the matrix is reduced
again or the cap is formally amended before submission.

### G7-G9

- G7: freeze the validation-selected candidate and obtain exact-hash final-test
  authorization.
- G8: run the final test exactly once.
- G9: reconcile quality, throughput, memory, and cost; sign the go/no-go
  record.

Wave 2 starts only if the disposition is `qualified_for_wave2` or
`research_baseline_qualified`.

## Phase 3 - Standalone Transformer

Dates: **2026-09-24 through 2026-10-09**  
GitHub: [#24 Market-sequence Transformer](https://github.com/khab40/lob-arena/issues/24)

This implementation has not started yet.

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

Reconciled on **2026-09-07**:

- [#22](https://github.com/khab40/lob-arena/issues/22) records completed C0-C4,
  the frozen four-date forward corpus, and its governed release evidence.
- [#23](https://github.com/khab40/lob-arena/issues/23) records the completed G5
  comparison and execution receipts, the consumed-slot reconciliation, and the
  amended nine-Job G6 matrix.
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
