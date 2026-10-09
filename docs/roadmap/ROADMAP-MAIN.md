# Main Roadmap

> **LightGBM G9 closed September 27 as `research_baseline_qualified`.**
> Wave 2 engineering is eligible; production qualification is not established.
> The September 23 exit target was missed; later dates remain baseline targets
> pending reforecast. See the [signed closure](../operations/g8/g9-closure-20260927.md).

Status date: 2026-10-08. See [current status and evidence](CURRENT_STATUS.md)
and the [4–10 October research plan](../ml/transformer-week-plan-20261004.md).
Tracking cleanup: [Bug #355](https://github.com/khab40/lob-arena/issues/355) /
[Project #3](https://github.com/users/khab40/projects/3).

Operator-approved priority: [Transformer versus LightGBM research](../ml/transformer-research-fork.md)
under [#24](https://github.com/khab40/lob-arena/issues/24), before platform maintenance
#19–#21. PR #283's reusable repairs are merged. The operator continues bounded
research after verified December results; see the [current disposition](../ml/transformer-research-disposition-20261008.md).
Next is #90/#91 saved-score mock integration, then fresh inference. Hybrid work
and broader quality claims still require a separately justified study.
Existing dates below remain baseline targets pending evidence-based reforecast.

The verified development comparison and December holdout support the recorded
`continue_research` decision and scoped #314 acceptance. Full #24 remains open
for MLflow lineage, dedicated serving and resource/cost acceptance. Coverage is
one December date and three sessions with research/synthetic labels; this does
not establish production quality. Current candidate identity, metrics, access
closure and unreconciled reservations are owned by [current status](CURRENT_STATUS.md)
and the [research disposition](../ml/transformer-research-disposition-20261008.md).

Consumed attempts and their immutable packages remain retained. The detailed
[pre-compaction campaign narrative](https://github.com/khab40/lob-arena/blob/1417a4e4bfb6803bc967b4469b85e4f379759e8e/docs/roadmap/ROADMAP-MAIN.md)
records the original Job, PR and recovery sequence. No rerun, final access,
promotion or new workload follows from this roadmap.

Baseline target for the current Nasdaq/LOBSTER learned-detector milestone:
**2026-11-20**.

Baseline feature-complete date: **2026-11-13**, followed by one week for
deployment, security verification, rehearsal, and final acceptance.

Critical path:

`Recorded continue_research -> saved-score mock -> causal inference integration -> integrated evidence -> secure CEO UI -> final demo`

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

**Complete 2026-09-07:** three sequential Jobs passed nine gates and matched
21 deterministic fields. Exact Job/MLflow identities remain in the
[historical campaign narrative](https://github.com/khab40/lob-arena/blob/1417a4e4bfb6803bc967b4469b85e4f379759e8e/docs/roadmap/ROADMAP-MAIN.md#g5---reproducibility).

### G6 - Bounded Development Campaign

Run the nine remaining experiments:

- two hyperparameter configurations;
- two feature-family ablations;
- two candidate seed-stability runs; and
- raw, Platt, and isotonic calibration comparisons.

The fixed matrix and validation-only ordering are encoded in
`configs/experiments/lightgbm-wave1/g6-campaign-20260907.json`. Search selection
feeds the two seed and three calibration Jobs mechanically; no test access or
result-dependent added trials are permitted. All nine run IDs, collection receipts,
input/image identities and metadata-only dataset lineage were verified.

**Complete 2026-09-10:** `ablate-state` selected; seeds 42, 7 and 2027 matched
exactly. Isotonic improved validation calibration without changing detection
metrics. All rejected candidates and the original fail-closed receipt are retained.
Development consumption is 20/20; this completed ceiling grants no new Jobs.
Detailed validation metrics and source-repair provenance remain in the
[historical G6 record](https://github.com/khab40/lob-arena/blob/1417a4e4bfb6803bc967b4469b85e4f379759e8e/docs/roadmap/ROADMAP-MAIN.md#g6---bounded-development-campaign).

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
- G9: [signed and closed September 27](../operations/g8/g9-closure-20260927.md)
  as `research_baseline_qualified`. Operator package/cost acceptance and delegated
  signature are verified. Billed cost remains unknown under operator-managed
  alerts; production/client qualification and registry promotion are not claimed.
- R4's four prior submissions, consumed approval and pre-scoring failure remain
  historical evidence. The approved replacement does not erase that history.

Remaining critical path:

1. Prepare #90/#91 private saved-score playback under the recorded continuation;
   then define and separately approve the fresh-inference adapter and causal event
   integration. Full #24 acceptance remains open.
2. Reconcile durable MLflow events/lineage and deferred platform work under #19–#21
   after research. None requires reopening signed G8/G9.
3. Reforecast downstream dates from remaining integration and acceptance work.
   October 9 is a baseline target, not a full-story completion forecast.

The [G8 closure PR #223](https://github.com/khab40/lob-arena/pull/223) is merged
at `118fde384f1c73d90390227085504e31a0319ae0`; post-merge CI passed. Its review
and merge are complete. Tracking reconciliation is [Bug #229](https://github.com/khab40/lob-arena/issues/229).

1. #24's [input-contract implementation](../ml/transformer-input-contract.md) is
   merged in #236. The [CPU development-input verification plan](../ml/transformer-development-verification-plan.md)
   is implemented. Its approved Job failed before input download due to late
   signed context; #238's repair is merged in #237 and the separately approved
   [r2 replacement passed independent verification](../ml/transformer-development-results-r2.md).
   PR #239 is merged. The [bounded GPU training/checkpoint, calibration and MLflow
   plan](../ml/transformer-gpu-campaign-plan.md) was approved and merged in #241.
   The first [readiness increment](../ml/transformer-campaign-readiness.md) merged
   in #248. The [provenance continuation](../ml/transformer-role-provenance.md)
   verified the 29-object metadata chain and 30 replay domains after the corrected
   temporary grant. Access cleanup is independently verified at bucket version 134.
   The verified metadata and train-only normalizer are now bound into a
   deterministic CPU evidence bundle, independently checked offline. #249/#254
   are merged. PR #258 and its compatibility repair are also merged with passing CI.
   PR #267 merged the [actual-runtime readiness repair](../ml/transformer-runtime-preflight.md)
   for Bugs #266/#268. The separately approved
   [r3 audit passed](../ml/transformer-lineage-r3-results.md): 115 metadata GETs,
   356,040 bytes and all 30 validation-run semantic bindings independently verified.
   Cleanup restored the original two rules and non-policy settings at bucket
   version 143. Earlier attempts remain preserved and consumed.
   PRs #271/#272 are merged. The [source separation proof](../ml/transformer-source-separation.md)
   now reauthenticates retained evidence and binds the three whole instrument
   domains, including warm-up ancestry and all synthetic labels, to the reviewed
   producer contract. It claims neither time separation nor statistical independence.
   The [CPU role-audit package](../ml/transformer-role-audit-package.md) now binds
   this proof to signed provider context, restricted row records and independent
   class-count readback; PR #275 is merged. The research fork moved these checks
   into each GPU Job, replacing the separate CPU-first prerequisite. The verified
   smoke and four grid Jobs checked per-role support and exact row alignment.
   [MLflow readiness](../ml/mlflow-readiness-design.md) and platform acceptance
   remain deferred; retained S3 artifacts and replayable events preserve results.
   Research-control negative labels remain assumptions and positive labels remain
   synthetic. The [grid result](../ml/transformer-training-grid-results.md) advances
   #24's research campaign; [confirmation stability passed](../ml/transformer-confirmation-results-20261004.md).
   Calibration, exact-row comparison and the authorized December holdout are
   independently verified. The [recorded continuation](../ml/transformer-research-disposition-20261008.md)
   completes scoped #314 acceptance; full #24 still needs MLflow lineage,
   dedicated serving-path and resource/cost acceptance.
2. Reforecast downstream dates. The gated September 24 start was missed;
   October 9 remains a baseline target, not a forecast. Preserve the frozen
   LightGBM result; future qualification claims need untouched held-out evaluation data.

See the [detailed G8 plan](PHASES.md#g8-recovery-and-completion-plan). Apply the
[validation execution policy](../ml/model-validation-execution-policy.md): model/runtime
work runs on Nebius Serverless; historical billing-freshness, submission-expiry and
fixed VM windows are not current prerequisites. Final-test approval remains separate.

Wave 2 eligibility is satisfied by the signed `research_baseline_qualified`
disposition. Its research-only limits remain binding; the fixed training grid is verified.

## Phase 3 - Standalone Transformer

Dates: **2026-09-24 through 2026-10-09**  
GitHub: [#24 Market-sequence Transformer](https://github.com/khab40/lob-arena/issues/24)

Classifier/training implementation is complete. Frozen C4 causal windows, masks,
train-only normalization, role support and exact baseline alignment have passed
governed-data runtime checks. The replacement smoke and
[four sequential grid trials](../ml/transformer-training-grid-results.md) are
independently verified. Width 128 / learning rate 0.0003 is the selection-fold
winner; both confirmation seeds are verified and three-seed stability passed.
Checkpoint compatibility, C-only temperature fitting, identical-row O comparison
and the locked December holdout are independently verified. The operator's bounded
`continue_research` decision is recorded, and #314 is closed after merged PR #354.
Next: #90/#91 private saved-score playback, then the research inference adapter
and causal event integration. Full #24 remains open for MLflow lineage,
dedicated serving-path and resource/cost acceptance.
Preserve prior development exposure, O threshold selection and the LightGBM
calibrator's prior validation exposure as comparison limitations.

The approved [research fork](../ml/transformer-research-fork.md) supersedes the
original CPU-first/MLflow-first ordering. The failed first smoke and approved
replacement remain consumed attempts; neither the original eight-slot plan nor
the completed four-trial authorization permits automatic replacements or later
slots. Reforecast against the remaining integration and acceptance work;
October 9 remains a baseline, not a verified full-story completion forecast.

Deliverables:

- causal sequence contract with cutoff, length, stride, masking, and row
  identity;
- CPU sequence materialization;
- smallest viable Transformer classifier;
- bounded GPU training matrix;
- seed stability, calibration, and threshold selection;
- any later final governed evaluation requires separate authorization and data;
- model bundle containing weights, preprocessing, schema, and checksums;
- comparison against LightGBM on identical rows; and
- GPU hours, cost, memory, throughput, and inference latency.

The Transformer may be approved as a feature producer even if it does not beat
LightGBM as a standalone model. The current continuation does not grant that
approval or authorize #25's separate hybrid study.

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

Research progress reconciled on **2026-10-08** for
[GitHub Project #3](https://github.com/users/khab40/projects/3):

- [#22](https://github.com/khab40/lob-arena/issues/22) records completed C0-C4,
  the frozen four-date forward corpus, and its governed release evidence.
- [#23](https://github.com/khab40/lob-arena/issues/23) is closed with G0–G9 complete.
  Merged #231 records the signed `research_baseline_qualified` disposition.
  Historical attempts and the frozen candidate remain preserved.
- [#24](https://github.com/khab40/lob-arena/issues/24) remains In Progress after
  verified GPU smoke, four-trial training, both seed confirmations, calibration,
  comparison and the authorized December holdout. Bounded `continue_research`
  is recorded; [#314](https://github.com/khab40/lob-arena/issues/314) is closed.
  MLflow lineage, dedicated serving-path and resource/cost acceptance remain.
  G9 permits no production promotion or G8 rerun.
- [#25](https://github.com/khab40/lob-arena/issues/25) remains Todo. A hybrid study
  needs separate justification and approval; continuation does not start it.
- [#90](https://github.com/khab40/lob-arena/issues/90) and
  [#91](https://github.com/khab40/lob-arena/issues/91) remain Todo. Their next
  approved chunk is local-only playback of verified saved scores, not fresh
  model execution or complete three-model/LOBSTER/secure-demo acceptance.
- [#28](https://github.com/khab40/lob-arena/issues/28) is Todo until #25 and #27
  complete.
- [#19](https://github.com/khab40/lob-arena/issues/19) is reopened/In Progress
  under [Bug #244](https://github.com/khab40/lob-arena/issues/244). Complete its
  recovery/registration evidence after research. Revalidate #20/#21 as well;
  completed foundations alone do not prove all platform exit criteria.
- Seven dated GitHub milestones now encode the targets in this document. The
  critical-path issues and supporting platform/Investigator issues are assigned
  to their expected exit milestone.
  All seven remain open under their existing acceptance scope and due baselines.
  [The project-wide reconciliation](project-tracking-reconciliation-20261008.md)
  records the assigned counts, unchanged backlog and closed-bug board correction.

The AI Investigator lane—[#26](https://github.com/khab40/lob-arena/issues/26),
[#27](https://github.com/khab40/lob-arena/issues/27), and
[#28](https://github.com/khab40/lob-arena/issues/28)—is supporting work, not
detector authority. It can be completed alongside the integrated evidence and
UI phases but must never change detector scores or labels.

## Schedule Assumptions And Risks

The **2026-11-20** baseline target assumes:

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
