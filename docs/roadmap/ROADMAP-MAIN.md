# Main Roadmap

Status date: 2026-09-21

Target completion for the current Nasdaq/LOBSTER learned-detector milestone:
**2026-11-20**.

Baseline feature-complete date: **2026-11-13**, followed by one week for
deployment, security verification, rehearsal, and final acceptance.

Critical path:

`G8-G9 LightGBM -> Transformer -> Transformer/LightGBM hybrid -> integrated evidence -> secure CEO UI -> final demo`

## Current Position

G0–G7 are complete; **G8 is open and G9 blocked**. The September 23 exit target
is at risk. Dates below remain the approved baseline, not a new completion forecast.
G8's goal is one separately authorized evaluation of the frozen LightGBM candidate,
with independently verified quality, rules comparison, lineage and runtime evidence.
G9 uses that evidence for the signed baseline/exit decision before Transformer work.

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
- G6 passed on 2026-09-10. All nine predeclared Jobs completed with distinct
  MLflow runs, all 12 completion gates passed, and the three seed results were
  identical on F1, minimum family recall, and validation log loss. Isotonic
  calibration was selected with candidate hash
  `5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff`.
- The G6 final comparison receipt is
  `outputs/lightgbm-wave1/nasdaq-g6-development-20260907/g6-comparison-final.json`
  (SHA-256
  `8baa904c5c8ccad4406d62b383999d0c294c9830869e1633aef71d3989b1aa40`).
  It records `test_fold_accessed=false`, the full rejection set, and total
  development consumption of 20/20. No additional development Job is allowed;
  the temporary publisher grant is removed and MLflow is `STOPPED` between
  experiment windows.
- G7 passed on 2026-09-12. The validation-selected isotonic candidate
  `5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff`
  was frozen without test access, and the operator supplied the exact-hash
  final-test authorization. Verification reports `authorized`,
  `signature_verified=true`, and `final_identity_available=true`.
- The G7 freeze receipt SHA-256 is
  `232f1a88e39caf2591df5ee135bb25b6ce2fb080688dc197cd96676840f8d7fc`.
  The outer authorization receipt SHA-256 is
  `b0b6cee7fce8db3618cdaeb905ec7588d57a94985ef3823215664da4ce8ceed6`;
  it binds signed-content SHA-256
  `dcf056eba18cd95169f3caade2f7d1c2285e1b49b94e2a9ab353bb74f1233db0`,
  signature SHA-256
  `a012abb5948b3cf058c77fd9336f5a81eaaa0b2c2782aab653d9ba3dbf3005ea`,
  and trusted public-key SHA-256
  `a433d622c153a47df472a703d549f180c43ab5d467ae35606667d29ef24e06ab`.
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
- G8: open. R4 (`aijob-e00vtamgkr07mwzt4t`) downloaded the final release
  and failed before scoring. Preserve four prior submissions and the consumed
  approval; candidate, calibration, features and thresholds remain frozen.
  Corrected C4 loading, comparison/report integration, pre-logging scored retention,
  same-run MLflow recovery and marker-last publication are implemented.
- Native recovery and authenticated remote rehearsal are complete for synthetic
  inputs: the [September 17 evidence](evidence/g8-native-recovery-20260917.json)
  records one scoring call, native reattachment and completed recovery, with
  independent readback of 24 MLflow metrics, 30 inputs and four artifact hashes.
  The subsequent [independent S3 verification](evidence/g8-independent-s3-readback-20260917.json)
  checked all 64 objects and resolves the earlier reader AccessDenied gap.
- Merged PR #201 prepares the [production native package](g8-production-package.md)
  for `nasdaq-g8-replacement-r5-20260917`; it remains unsigned and not executable.
  The changed production entrypoint still needs Nebius runtime verification;
  synthetic Java-comparison/lineage placeholders cannot qualify production inputs.

Completion evidence and remaining critical path:

1. Verify the original 27 Java/C3 checkpoints and genuine dataset registration;
   complete frozen projection, C4 profile, comparison inventory and input bindings.
   The approved [89-object metadata audit](evidence/g8-original-comparison-metadata-20260921.json)
   passed and all temporary access is removed. Live registration now verifies
   four metadata artifacts and 30 final-tabular inputs. [Payload verification](evidence/g8-original-payload-verification-20260921.json)
   is complete: 294 original objects staged; all 377 payload/metadata files rehashed.
   Temporary grants are removed and the VM stopped. Rows were not parsed; production
   comparison semantics still require verification on Nebius.
2. Verify the changed production bootstrap, mounts and context handoff on Nebius
   without final scoring. Record resources, finite timeout, Job count and identities.
3. Complete current credential/permission, image-alias, storage, MLflow and
   output/intent preflight; assemble the canonical request and complete v3 package.
   The approved [32 GiB expansion and live registration](evidence/g8-capacity-registration-20260921.json)
   are verified. The September 21 unsigned review now binds the original comparison,
   live registration and 32 GiB storage. Finish runtime/current preflight and recheck
   the 20 GiB free-space requirement immediately before execution.
4. Obtain replacement-specific final-test approval and sign the reviewed package;
   bind actual Job context separately after create. Never reuse R4 authorization.
5. Execute the one approved replacement, retain scored outputs before logging,
   recover tracking/publication without rescoring and verify S3/MLflow independently.
6. Close G8 with actual C4 quality and execution evidence, including failed gates.
   G9 then records quality, throughput, memory and operator-provided cost disposition
   and signs the go/no-go decision. Rehearsal success is not an exit decision.

See the [detailed G8 plan](PHASES.md#g8-recovery-and-completion-plan). Apply the
[validation execution policy](model-validation-execution-policy.md): model/runtime
work runs on Nebius Serverless; historical billing-freshness, submission-expiry and
fixed VM windows are not current prerequisites. Final-test approval remains separate.

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
