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

The Transformer implementation, replacement GPU smoke and all four fixed-grid
trials have passed independent verification. The [grid results](../ml/transformer-training-grid-results.md)
select width 128, learning rate 0.0003, seed 42, epoch 4: selection log loss
0.002437833 and F1 1.0 on 1,250 rows, including 45 positives. This is the tuning
fold, not evidence of superiority over LightGBM. Both replacement confirmations
are [independently verified](../ml/transformer-confirmation-results-20261004.md);
three-seed stability passed with selection-loss range 0.002395075568322679 and
F1 range 0.0. Seed 42 / epoch 4 remains the candidate. The earlier failed attempt
is preserved, and the full $25 confirmation commitment remains held pending billing.
The [checkpoint compatibility package](../ml/transformer-comparison-20261004.md)
was approved and PR #311 merged, but its one-hour Job was cancelled when the
observer rejected IMAGE_PULLING. That attempt's output prefix is empty.
[Bug #312](https://github.com/khab40/lob-arena/issues/312) repairs the
state mismatch and startup timer; PR #313 merged with all 25 checks passed.
The [fresh r2 package](../ml/transformer-comparison-r2-20261004.md) passes
252 inert tests (one expected skip), image/request inspection and exact dry-run.
PR #315 merged and its exactly approved one-hour L40S Job completed in 324.59 s.
The [comparison report](../ml/experiments/transformer-comparison-r2-20261004/report.md)
records independently reconciled temperature/operating points and all 244 artifacts.
[Bug #317](https://github.com/khab40/lob-arena/issues/317) resolves a single-ULP
aggregate mismatch without rerunning the model. O development F1/AP are 1.00/1.00
for Transformer versus 0.545/0.436 for frozen LightGBM. Recommendation is
**continue_research**, accepted by the operator after PR #318 merged with green CI.
The approved next study uses the same prepared December Nasdaq data with candidate
choices locked before access. [Settings #314](../ml/transformer-settings-release.md)
and the [prospective protocol](../ml/transformer-holdout-protocol-20261005.md) are
merged in PR #319. The [separate consumer](../ml/transformer-holdout-consumer.md)
is merged in PR #321 with authorization/parity, exact inputs/pairing and verified
measurement/publication readback. The [sealed execution image/startup chunk](../ml/transformer-holdout-execution-package.md)
preserves 13 numerical files and 48 installed packages; 403 inert regressions pass.
P1 Bug #325 binds the copied overlay to a clean matching Git commit and verifies
all 20 context files in the rebuilt image; PR #323 and review-policy PR #326 are
merged with green CI. [Admission preparation](../ml/transformer-holdout-admission.md)
authenticates a saved 64-row reference. PR #328 merged with all 25 checks passed;
P1 #329 is closed. The approved three-JSON/62-HEAD metadata audit completed and
[passed independent verification](../ml/transformer-holdout-metadata-results-20261006.md):
30 December runs / 15,160 aligned rows, all versions `1`. Both grants are removed
and original policies verified at final version 10 / results version 11.
At that metadata stage, no December rows were read; HEAD checks did not verify
fresh payload hashes. The later authorized evaluation is recorded below.
PR #331 and both post-merge workflows passed. The reference is now published at
version `1`; the sealed image is published by immutable digest. The
[252-input execution package](../ml/transformer-holdout-run-20261006.md) binds exact
access/credential/request pins, bounded supervision and original-policy restoration.
Actual SDK/local-CLI preflight, 258 inert holdout tests and the exact provider dry-run pass.
PR #337 merged with green CI and the operator approved the exact package. Both
grants were verified at final11/results12, but the standalone watcher expired
before a separate creation tool call; the submission guard stopped before intent
or mutation. All 23 observations and fresh MCP reconciliation show Job absence;
no December payload read or model ran. [Bug #339](https://github.com/khab40/lob-arena/issues/339)
repairs this with [same-process admission](../operations/transformer-coordinated-admission.md),
durable intent and reserved observation time; 46 focused inert cases pass.
PR #340 and public-evidence prevention #342 are merged with green checks.
Original observer history and the prior access overrun remain disclosed. The
approved [first-Job recovery](../ml/transformer-holdout-first-run-recovery-20261007.md)
completed as aijob-e00gvk2fdn6cmjxvkg, passed CUDA reference parity and published
all seven outputs. Original verification aborted on cross-platform rounding;
reviewed offline replay now verifies all 15,160 rows against the original baseline.
The Job grants were removed after about 1,691 seconds within the three-hour window.
After an earlier before-credential recovery failure, the corrected approved
one-file recovery used one GET and restored the original results policy in
139.547514 seconds. Current complete policies match at final14/2 and results19/9.
[Bug #345](https://github.com/khab40/lob-arena/issues/345) repairs probability
equivalence and durable readback under [this recovery plan](../ml/transformer-holdout-verification-repair-20261007.md).
PR #346's repair and full verification are independently reviewed. Frozen balanced
F1 is 95.35% for Transformer versus 74.48% for LightGBM; Transformer has zero
false positives and 91.11% recall. LightGBM's high-recall point reaches 93.33%
recall with 851 false positives. The [verified report and plots](../ml/transformer-holdout-report-20261007.md)
and operator's 8 October continuation support bounded research/demo engineering.
Explicit retained-reference calibration/decision acceptance completes #314's scope.
Next: the [saved-score mock and fresh-inference sequence](../ml/transformer-research-disposition-20261008.md#next-medium-prs)
under #90/#91. One date and three sessions do not establish production quality.
The $6.25 holdout reservation remains held with billing unreconciled; no GPU
rerun is required. Full #24 acceptance remains open alongside the approved first
#90/#91 saved-score mock; fresh scoring follows separately reviewed packaging.
Historical LightGBM December exposure remains disclosed; online
MLflow follows research. Both $6.25 comparison commitments remain held pending
billing. This roadmap grants no execution or access authority. Consumed attempts
stay retained; no GPU rerun is needed. Future workloads need fresh exact approval.

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
- G9: [signed and closed September 27](../operations/g8/g9-closure-20260927.md)
  as `research_baseline_qualified`. Operator package/cost acceptance and delegated
  signature are verified. Billed cost remains unknown under operator-managed
  alerts; production/client qualification and registry promotion are not claimed.
- R4's four prior submissions, consumed approval and pre-scoring failure remain
  historical evidence. The approved replacement does not erase that history.

Remaining critical path:

The September 28 maintenance-first ordering is historical and was superseded by
the operator's October 2 [research-first decision](../ml/transformer-research-fork.md).
The Transformer/LightGBM comparison and authorized December evaluation are
independently verified, and the bounded continuation decision is recorded.
The #90/#91 saved-score mock is next; platform acceptance under #19–#21 remains
deferred. The [MLflow metadata recovery drill](../ml/mlflow-metadata-recovery.md)
passed; remaining recovery/registration, infrastructure and observability work
is deferred. Preserve durable research artifacts and reconcile MLflow afterward.
None requires reopening G8 or altering the signed G9 decision.

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
