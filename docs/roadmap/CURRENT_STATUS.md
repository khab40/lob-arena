# Roadmap status — 2026-09-28

## Transformer input verification implemented — 2026-09-28

[PR #236](https://github.com/khab40/lob-arena/pull/236) is reviewed and merged;
dependency PRs #203/#227/#228 are also merged. Story
[#24](https://github.com/khab40/lob-arena/issues/24) remains In Progress.

The operator approved the [bounded development-input plan](../ml/transformer-development-verification-plan.md):
one CPU Job to verify 33,450 training and 9,210 validation rows, preserve
normalization/configuration and compare batch sizes. CPU is for input preparation;
Transformer model training follows as a separately planned GPU chunk.

All 185 retained development files match publication checksums (30,034,660 bytes).
This establishes local artifact integrity, not governed runtime success. Live
preflight now passes for all 185 object versions; the output prefix is empty.
The runner, pinned image and exact execution request are implemented and bound;
provider dry-run passes. There are 77 passing input/C4 tests, plus 14 packaging
and grader checks. CI must pass before the approved Job. No Job or permission
change has been performed. See the [preflight receipt](../evidence/transformer-development-preflight-20260928.json).
The [proposal](../evidence/transformer-development-proposal-20260928.json) records
one Job, 4 vCPU/16 GiB, a one-hour timeout, no GPU and no final-test access.

## Transformer input-contract implementation — 2026-09-28

The operator approved the first [#24](https://github.com/khab40/lob-arena/issues/24)
implementation chunk. The story is **In Progress** in Project #3. The
[input contract](../ml/transformer-input-contract.md) now verifies exact C4
source windows, causal ordering, masks, missingness, train-only normalization
and baseline row alignment. Its [Gherkin scenarios](../ml/transformer-input-contract.feature)
map to inert automated tests. Relevant input/C4 checks pass: 53 tests.

Six local fixture measurements passed batch-invariance checks. The 8,192-window
cases took 25–26 seconds total and 116–170 MiB peak RSS; these are input-array
measurements, not training or production performance. Config/normalizer examples,
code hashes and resource results are retained in the
[receipt](../evidence/transformer-input-measurements-20260928.json).

Next: review this implementation, then prepare the exact Nebius development-input
verification proposal. Model architecture/training, calibration, MLflow checkpoint
registration and a future authorized evaluation protocol remain separate chunks.
G8/G9 stay closed. #19–#21 platform acceptance remains open; #227 is merged,
while #203/#228 were still open at this implementation snapshot. Older dated
Todo statements below are historical, superseded by this approved start.

## Maintenance and platform continuation — 2026-09-28

G8 and G9 remain closed; PR #231 is merged. The current operator priority is
platform maintenance under [#19](https://github.com/khab40/lob-arena/issues/19),
[#20](https://github.com/khab40/lob-arena/issues/20) and
[#21](https://github.com/khab40/lob-arena/issues/21).

1. Dependency repairs are pushed to existing PRs #203/#227/#228. All 22 checks
   passed on each repaired head; #203 also passed after its subsequent main merge.
   Bugs #233/#234 track these repairs. #225/#226 are merged and their dependency
   diffs have no blocking review findings. A merged pin does not deploy a service.
2. [Metadata restoration](../ml/mlflow-metadata-recovery.md) passed on Nebius:
   60 tables / 19,521 rows matched the backup snapshot. The private dump is
   retained and independently rehashed locally; the VM is STOPPED. Deployed
   MLflow is 3.13.0. This verifies database table recovery, not application writes.
3. Next #19 chunk: verify the candidate's seven artifacts and exact feature
   release/hash against the accepted package, register one research-only model
   version, and record/read back its alias change. Preserve frozen bytes and
   distinguish a registry record from a deployable MLflow model package.
4. #20 needs the consolidated infrastructure plan, clean repeat-application
   evidence, preservation-aware teardown and a complete service-account grant
   audit. Existing resource-specific idempotency evidence is retained.
5. #21 needs native telemetry ingestion, correlated dashboards, controlled alert
   delivery and FOCUS/charge-stop evidence. Cost automation remains a platform
   acceptance item; it does not reopen G8 or override the operator-managed
   model-validation billing policy. No billing query was performed.

These stories remain In Progress. Later-model tracking and the application-level
restore check remain under #19; no new model evaluation or production promotion
was performed. Historical dated entries below retain their original context.

## G9 signed and closed — 2026-09-27

**LightGBM exits as `research_baseline_qualified`.** The operator accepted the
verified S3/MLflow package, unknown-cost disposition under the existing policy,
and delegated signing. The [signed closure](../operations/g8/g9-closure-20260927.md)
binds the exact approved JSON and Markdown; public-key verification and mutation
rejection checks passed. Story [#23](https://github.com/khab40/lob-arena/issues/23)
is complete. [PR #231](https://github.com/khab40/lob-arena/pull/231) is merged.

Transformer [#24](https://github.com/khab40/lob-arena/issues/24) is eligible for
engineering and remains Todo, not started. Next: plan its sequence contract and
bounded implementation chunks, then reforecast downstream dates. No production
qualification, G8 rerun, new model Job or billing query follows this decision.
The dated proposal and historical snapshots below retain their original wording;
the signed decision supersedes their pending-G9 status.

## G9 exit package prepared — 2026-09-27

The [G9 exit record](../operations/g8/g9-exit-20260927.md) recommends
`research_baseline_qualified`: Wave 2 engineering only, with no production claim.
Its [exact proposal](../evidence/g9-exit-proposal-20260927.json) binds the verified
G8 results, frozen package/configuration, lineage, quality limitations and resource
measurements. All 176 retained objects and seven development artifacts were
rechecked locally. No G8 evaluation or cloud workload was run.

Cost disposition proposed: accept unknown billed cost under the existing
operator-managed policy; no cost-efficiency claim. Operator acceptance of the
package interpretation, cost disposition and exact signed exit is still required.
[#23](https://github.com/khab40/lob-arena/issues/23) remains In Progress and
[#24](https://github.com/khab40/lob-arena/issues/24) remains Todo until that decision.
The entries below are historical snapshots; no review of merged #223 remains.

## Post-merge tracking reconciliation — 2026-09-27

**G8 is complete; G9 is the remaining LightGBM exit gate.**
[PR #223](https://github.com/khab40/lob-arena/pull/223) merged on September 23 at
`118fde384f1c73d90390227085504e31a0319ae0`; post-merge CI passed and Bugs
[#222](https://github.com/khab40/lob-arena/issues/222) and
[#224](https://github.com/khab40/lob-arena/issues/224) closed automatically.
Reviewing or merging #223 is no longer remaining work.

Next: record operator cost disposition and obtain the signed G9 exit decision
using the [verified results and handoff](../operations/g8/g8-final-results-20260923.md).
Story [#23](https://github.com/khab40/lob-arena/issues/23) remains In Progress;
Transformer [#24](https://github.com/khab40/lob-arena/issues/24) remains Todo until
the accepted LightGBM exit. No new G8 evaluation or production promotion follows.

The September 23 G9 target and gated September 24 Transformer start have passed.
Later dates remain baseline targets pending an evidence-backed reforecast.
This correction is tracked by [Bug #229](https://github.com/khab40/lob-arena/issues/229)
under #23 in [Project #3](https://github.com/users/khab40/projects/3).
Issue bodies and the project overview were updated and independently read back;
see the [tracking receipt](../evidence/g8-tracking-reconciliation-20260927.json).

## G8 complete; G9 exit decision pending — 2026-09-23

**The approved frozen C4 evaluation, independent verification and cloud cleanup
are complete.** Job `aijob-e00kd6g7vaqtngwv9r` finished at 09:41:25 UTC after
2h25m49.50s, within its three-hour limit. Exactly one replacement Job and one
scoring invocation ran; the frozen candidate and threshold were unchanged.

LightGBM measured **85.58% precision, 65.93% recall and 74.48% F1**, with 15 false
positives and 46 missed positive observations. Rules measured 0.89% precision and
100% recall, with 14,985 false positives. Both detected activity in all 27 observed
campaigns. Scope: 15,160 retained observations, three symbol sessions, one date;
research labels and row metrics do not establish production qualification.

Independent readers verified all 176 S3 objects, four final MLflow artifacts,
30 full dataset identities and 24 metrics with one recorded value each. The final
key is INACTIVE, temporary SSH rule absent, Job worker released and MLflow VM
STOPPED. See [results and G9 handoff](../operations/g8/g8-final-results-20260923.md),
[execution](../evidence/g8-final-execution-20260923.json) and
[verification](../evidence/g8-final-verification-20260923.json) in
[PR #223](https://github.com/khab40/lob-arena/pull/223), for
[story #23](https://github.com/khab40/lob-arena/issues/23).

**Next: record operator cost disposition and obtain G9's
signed exit decision.** Story #23 remains open through G9; Wave 2 is still gated.
No further G8 training, calibration, threshold selection or final scoring is needed.

The dated entries below retain historical snapshots; their then-pending gates
are superseded by this completion record.

## G8 final authorization preparation — 2026-09-23

**PR #220 is merged; all 22 checks passed.** The comparison audit, optimization
benchmark and production transport preparation are complete. The remaining
timeout review finding is fixed in [PR #223](https://github.com/khab40/lob-arena/pull/223),
linked to [Bug #222](https://github.com/khab40/lob-arena/issues/222) under story #23.
Requests, schema, signed context and renderer now agree on one or three hours;
28 inert contract tests pass. The frozen candidate and its lineage are unchanged.

The [refreshed unsigned review](../evidence/g8-final-review-20260923.json) binds
the repaired source commit. See the [final execution plan](../operations/g8/g8-final-authorization-20260923.md).
The [fresh probe receipt](../evidence/g8-final-transport-verification-20260923.json)
verifies the repaired package on Nebius; compute is released, VM stopped and final
key inactive. The [exact final proposal](../evidence/g8-final-approval-proposal-20260923.json)
is ready for separate replacement approval.
Remaining: fresh replacement-final approval, authenticated MLflow/output-intent
checks, one final evaluation, independent S3/MLflow verification and G9 disposition.
Nebius MCP safe mode requires an operator handoff for final-key deactivation.
**G8 remains open; the unsigned package does not authorize final access.**

## G8 comparison verified; production runtime preflight — 2026-09-23

**The comparison audit passed independently:** 377 files rehashed, 27 original
checkpoints verified and all 30 canonical replays exhausted. Nebius Job
`aijob-e00p01kcjvxcb53g7e` completed in 28 minutes 49 seconds, its supervisor exited
zero and compute was released. The VM is stopped and final key inactive. See the
[independent receipt](../evidence/g8-comparison-verification-20260923.json) and
[execution plan](../operations/g8/g8-comparison-preflight-20260922.md).

Production preflight found at least ten full comparison passes before publication.
[PR #220](https://github.com/khab40/lob-arena/pull/220), linked to
[Bug #221](https://github.com/khab40/lob-arena/issues/221) under
[LightGBM story #23](https://github.com/khab40/lob-arena/issues/23), now retains two
full comparisons and rechecks all bound input bytes before reuse. The
[Nebius benchmark](../evidence/g8-verification-reuse-verification-20260923.json)
passed eight repeated-copy checks, five changed-input rejections and fresh-process
recomputation. The [updated production transport probe](../evidence/g8-production-transport-probe-20260923.json)
verified 26 package files, 13 runtime overlays and the signed three-hour Job context.
Its compute is released, VM stopped and final key inactive. Synthetic timings do
not establish full production duration; three hours is a finite sizing proposal.

Step 1 is merged in PR #219. Step 2's comparison, optimization and unsigned package
are verified and merged in PR #220. Step 3 still requires replacement-specific
final authorization, live authorized output-intent/MLflow preflight, one evaluation
and independent results/lineage verification. The development reader's denied
output-prefix check remains unverified. **G8 is not closed; no final scoring ran.**

## G8 step 1 complete — 2026-09-22

**Selected-run lineage and all seven MLflow artifacts now verify.** The 90 apparent
mismatches were source URIs retained from G5 for shared name/digest identities.
The G5 and frozen G6 manifests contain exactly the same 90 full input records.
An externally anchored equivalence proof binds those exact alternate paths while
preserving all full-hash, feature-release, fold and context checks. No historical
run, model, calibration or threshold was changed. The prior 107-object durable
result readback remains valid. See [verification and evidence](../ml/lightgbm-lineage-verification.md).

The operator requested three separate PRs with analyse/plan/code/review/push
cycles and approved cloud operations in advance. Next is the existing supervised
comparison audit and production preflight. Then prepare replacement-specific
final authorization, evaluate once and independently verify the complete result.
**G8 remains open until those steps pass; G9 follows the verified result.**

## G8 tracking continuation — 2026-09-22

**G8 remains open.** The selected development run is reachable again through the
existing SSH rule; no permission change was needed. The live audit matched run
status, expected top-level parameters/metrics/tags and the dataset-name set, then
reported mismatches for all **90 dataset inputs**. It stopped before downloading
MLflow artifacts. The cause is unresolved: inspect individual mismatched fields
before deciding whether the checker or historical lineage needs correction.
Field-specific diagnostics now have local test coverage; that refinement has not
had a live readback. See the [tracking receipt](../evidence/lightgbm-tracking-readiness-20260922.json).

Both continuation attempts verified automatic VM shutdown. The second completed
within its 15-minute target, including recovery from a timed-out stop command.
The 107-object S3 verification remains valid; frozen model/calibration/configs
were unchanged. No model Jobs or final access occurred.

The shortest path to closure is: resolve selected-run lineage and verify its seven
artifacts; obtain and execute the supervised comparison-audit approval; bind the
production package and pass preflight; obtain replacement-specific final approval;
run once and independently verify the complete result. G9 disposition follows.
Additional hyperparameter search or recalibration is not required for G8.

## Earlier LightGBM retention chunk — 2026-09-22

The [independent audit](../ml/lightgbm-retention-audit.md) re-read and hash-verified
all **107 exact development result objects (12,551,368 bytes)** with the existing
reader identity. The frozen model and calibration were unchanged. The tool checks
MLflow parameters, metrics, per-shard lineage and seven artifacts, but the live
MLflow check remains **incomplete**: the restarted service was not verifiably ready
and its read connection reset. The VM is confirmed stopped. The operator-managed
window exceeded its proposed 15-minute bound; require an independent stop watchdog
before another startup. See the [receipt](../evidence/lightgbm-retention-audit-20260922.json).
G8 comparison, production package and final-authorization gates remain open.

## LightGBM remaining work plan — 2026-09-22

The current LightGBM candidate is already trained, selected, calibrated and frozen.
The immediate goal is **one authorized evaluation of the frozen C4 candidate, with
independently verified results and lineage**. Further tuning belongs to a separate
campaign. This analysis checks repository code, configs and retained artifacts,
including model and calibration hashes; MLflow findings reflect implementation and
saved receipts, not a fresh live-server audit.

1. **Preserve the completed experiment selection.** G6 completed nine Jobs: four
   search/ablation trials, two seed confirmations and three calibration comparisons.
   The selected `ablate-state` model uses 31 features, learning rate `0.1`, eight
   leaves, minimum leaf size two and 32 selected boosting iterations from a maximum
   of 60. No additional hyperparameter search is required for G8. Preserve the
   [campaign plan](../../configs/experiments/lightgbm-wave1/g6-campaign-20260907.json)
   and all trial/selection receipts, including rejected trials.

2. **Keep calibration and thresholds frozen; record their limitations.** Raw,
   Platt and isotonic were compared; isotonic won. The balanced threshold is
   `0.5769230769230769`, with validation F1 `0.6931407942`. The same validation fold
   supported early stopping, selection, calibrator fitting and threshold selection.
   Near-zero validation ECE therefore does not establish out-of-sample calibration.
   A future campaign should separate these stages using chronological groups or
   grouped out-of-fold predictions. See the [calibration evidence boundary](../use-cases/ml-training-selection.md#uc-ml-03-calibrate-and-freeze-operating-points)
   and [calibration guidance](https://scikit-learn.org/stable/modules/calibration.html).

3. **Retain the existing model freeze.** G7 is complete. The retained candidate,
   model, calibration and seven referenced evidence artifacts passed hash checks.
   Preserve weights, ordered features, preprocessing, calibration mapping, thresholds,
   data identities and image digest unchanged. Final-evaluation authorization is
   separate; earlier consumed approvals cannot authorize the replacement. Exact
   candidate and freeze identities are recorded in [ARD-0035](../architecture/ARD-0035-nebius-lightgbm-first.md).

4. **Complete one auditable configuration and artifact inventory.** Most material
   already exists across the campaign plan, request, candidate, training manifest,
   environment record and result storage. Consolidate an index linking resolved
   hyperparameters, feature exclusions/order, seeds, class weighting, early-stopping
   settings, calibration parameters, thresholds, data/split hashes, Git/image
   identities, Job IDs, MLflow IDs and checksums. Verify retrieval from durable
   storage so recovery does not depend on local `outputs/`. The first implementation
   chunk adds a [read-only candidate inventory](../ml/lightgbm-candidate-inventory.md):
   all 107 retained candidate-result objects are locally rehashed, and the index
   links resolved settings, artifacts, lineage and remote locations. Independent
   remote result retrieval passed for all 107 objects; live MLflow verification
   remains open on the dataset-input discrepancies above.

5. **Audit MLflow completeness and close tracking gaps.** Development logging
   already saves parameters, summary metrics, lineage, model weights, calibration
   manifests, importance and reliability evidence. Independently read back the
   selected run and trial records against their receipts, and make the configuration
   inventory and complete-release location discoverable. Current logging lacks
   per-iteration learning curves and does not explicitly upload every configuration
   or schema artifact. Add those capabilities for future experiments while preserving
   frozen evidence. See [tracking.py](../../backend/app/ml/lightgbm/tracking.py) and
   [retention and tracking](../use-cases/ml-model-serving.md#implemented-retention-and-tracking).

6. **Resolve G8's remaining execution prerequisites.** Complete the supervised
   comparison audit, then bind the unsigned production package to the corrected
   comparison evidence. Finish current storage, identity, image, MLflow and output
   checks; obtain replacement-specific final authorization. R2's cancelled attempt
   established no semantic pass. The [supervised audit proposal](../evidence/g8-comparison-supervised-proposal-20260921.json)
   remains a separate approval gate; this plan authorizes no workload.

7. **Run the authorized evaluation once and verify everything saved.** Retain
   scored outputs before logging; complete the C4 comparison, raw/calibrated Brier
   and ECE, classification metrics, uncertainty and resource evidence. Finish one
   MLflow evaluation run and the complete checksum-bound result release. Independently
   verify MLflow artifacts, dataset lineage, S3 contents and publication markers;
   use retained-output recovery without rescoring. Follow the
   [G8 completion procedure](../operations/g8/g8-completion-recovery.md).

8. **Close G9, then decide the next ML campaign and deployment work.** Record an
   explicit accept/reject/research-only disposition. If more development is justified,
   predeclare broader chronological validation, bounded hyperparameter trials,
   calibration separation, learning-curve logging and acceptance criteria before
   running Nebius Jobs. Model Registry version publication and promotion remain
   unimplemented: the existing namespace and logged model file are insufficient.
   Verified model packaging, version registration, promotion and rollback are
   subsequent delivery work under the [registration plan](../use-cases/ml-model-serving.md#planned-registration-and-promotion-procedure).

### Delivery chunks

- **Chunk 1 — frozen candidate inventory:** local byte verification, portable
  configuration/artifact index, inert tests and an execution receipt in one PR.
- **Chunk 2 — independent retention/tracking readback:** use exact inventory keys
  to verify durable storage and live MLflow metadata/artifacts; record missing
  evidence and make complete-release/configuration locations discoverable.
- **Chunk 3 — G8 completion:** separately approve the supervised comparison audit,
  finish package/preflight, obtain replacement-final approval, evaluate once and
  independently verify the published result. G9 follows that verified result.
- **Later campaign/delivery PRs:** learning curves and fuller config logging,
  improved calibration/selection protocol, then verified registry publication and
  promotion when justified by G9. Preserve the current frozen model throughout G8.

## Retained status snapshot — 2026-09-21

This is the dated status snapshot for the [main roadmap](ROADMAP-MAIN.md).
Dates are approved baseline targets, not a revised delivery forecast. A passed
software test, synthetic rehearsal or metadata audit does not close a model-quality gate.

## Sources and precedence

- [Project #3](https://github.com/users/khab40/projects/3) and linked issue states
  were read on 2026-09-21, together with all seven dated milestone descriptions.
- Merged implementation baseline: `origin/main` at `1deaafe7144c78043af027b274eb660a75fe34cb`.
- Readiness continuation: [merged PR #207](https://github.com/khab40/lob-arena/pull/207),
  merged on 2026-09-21 at 11:01 UTC. Its original comparison, capacity, registration
  and payload receipts are now part of the implementation baseline above.
- Gate receipts establish outcomes. Issue/board states establish work status.
  Milestone dates establish targets. Historical narrative and milestone counters
  must not override more specific evidence. Revalidate before execution.

## Milestones

| Milestone | Baseline target | Verified position and remaining dependency |
| --- | --- | --- |
| M1 corpus/infrastructure | 2026-09-11 | Corpus [#22](https://github.com/khab40/lob-arena/issues/22) closed; infrastructure [#20](https://github.com/khab40/lob-arena/issues/20) open/In Progress. Partially overdue. |
| M2 LightGBM | 2026-09-23 | [#23](https://github.com/khab40/lob-arena/issues/23) open/In Progress; G0–G8 complete; G9 cost disposition and signed exit pending. Wave 2 remains gated. |
| M3 Transformer | 2026-10-09 | [#24](https://github.com/khab40/lob-arena/issues/24) open/Todo; follows LightGBM exit. September 24 baseline start is at risk. |
| M4 cascade | 2026-10-23 | [#25](https://github.com/khab40/lob-arena/issues/25) open/Todo; needs verified standalone Transformer and leakage-safe feature release. |
| M5 integrated evidence | 2026-10-30 | [#90](https://github.com/khab40/lob-arena/issues/90) open/Todo; requires three-model Nasdaq comparison and LOBSTER robustness evidence. |
| M6 secure CEO UI | 2026-11-13 | [#91](https://github.com/khab40/lob-arena/issues/91) open/Todo; existing demo UI does not satisfy the secure five-step workflow. |
| M7 acceptance | 2026-11-20 | [#15](https://github.com/khab40/lob-arena/issues/15) and [#16](https://github.com/khab40/lob-arena/issues/16) open/In Progress; final rehearsal and verified acceptance remain. |

M1 infrastructure still needs repeatable/idempotent reconciliation, safe teardown,
billing notification/FOCUS integration and the broad-editor-permission disposition.
M2 supporting stories #14/#18/#19/#21 remain open/In Progress; corpus completion
alone does not close them. #84 (immutable image selection) remains open/Todo.
The investigator baseline (#17/#26) is in progress; model comparison #27 and
learned-evidence integration #28 remain Todo. Qwen explanations are not the
standalone market-sequence Transformer classifier.

BYO inbound adapter #87, detector adapter #88, expanded scenarios #85,
adversarial/customer-integration epics #92/#93 and storage expansion #94 remain
open/Todo and outside the dated critical path. Do not present them as delivered.

## Data and model gates

C0–C4 are complete for four dates: train 2019-01-30/2019-03-27, validation
2019-10-30, final test 2019-12-30. Both tabular and sequence projections exist.
The public-sample negatives use a research-control assumption, not independent
clean-window review. Client qualification retains its stronger governance requirements.

G5 reproducibility passed on September 7, G6's nine-Job campaign on September 10,
and G7 freeze on September 12. The selected isotonic LightGBM candidate remains
`5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff`.
R4 downloaded final data and failed before scoring; its authorization is consumed.
Do not claim the final fold has never been accessed or reuse that authorization.

The September 17 two-Job native synthetic rehearsal verified scoring followed by
workspace-loss recovery into the same MLflow run; independent readback verified
[all 64 S3 objects](../evidence/g8-independent-s3-readback-20260917.json).
The [production review package](../operations/g8/g8-production-package.md) is unsigned.
This is recovery engineering evidence, not a production G8 quality result.

Merged PR #207 records [89 original metadata objects](../evidence/g8-original-comparison-metadata-20260921.json)
and [32 GiB mounted capacity plus live C4 registration](../evidence/g8-capacity-registration-20260921.json).
The latter verifies 240 dataset inputs and 30 final-tabular entries without
reading final payload rows. Earlier 10 GiB/registration-pending observations are
historical. Its later [payload/readiness receipt](../evidence/g8-original-payload-verification-20260921.json)
records 294 original objects / 2,632,277,460 bytes staged and 377 files independently
rehashed. A new 25-file unsigned review binds those bytes, live registration and
32 GiB capacity. No rows were parsed, model Jobs submitted or final bucket accessed.
The [September 21 production transport probe](../evidence/g8-production-transport-probe-20260921.json)
completed on Job `aijob-e00samq5cpe1bysr4x`: exact runtime overlays, native mounts,
signed actual-Job context and independent package readback verified without parsing
protected rows or scoring. The recurring provider mount warning remains unexplained.
The operator approved the revised comparison audit, but Job
`aijob-e00ezdakxbj7m0xxfy` [failed closed](../evidence/g8-comparison-semantics-20260921.json)
with `ValidationError`. Its one-Job approval is consumed; no retry was submitted.
The local comparison metadata omitted required `preparation.logical_name`.
That defect is consistent with the failure; the original redacted result cannot
identify the exact call or how far protected parsing progressed. No scoring ran.
The [corrected retry proposal](../evidence/g8-comparison-semantics-retry-proposal-20260921.json)
was approved as PR #210. The separate corrected tree and all 377 files were
rehash-verified, preserving the original. R2 Job `aijob-e00v9yf6zxx3nkarn2`
[was cancelled](../evidence/g8-comparison-semantics-r2-20260921.json) after the expected
50-minute worker deadline with no worker result. Parsing progress and root cause
are unknown; neither approval nor elapsed time establishes semantic verification.
The [next proposal](../evidence/g8-comparison-supervised-proposal-20260921.json)
adds an injected supervisor, flushed stages and a five-minute startup-output gate.
It awaits approval for one new bounded Job; R2 approval is consumed.
Snapshot checks remain limited to hashes/footer counts; snapshot row/schema
consistency and prediction pairing remain unverified. The staging VM is stopped,
Job compute released and final key inactive. Successful comparison verification,
production-review rebinding, fresh preflight (including 20 GiB free space), canonical
request and replacement-specific authorization remain open.

G9 requires verified G8 evidence and a signed exit disposition; Transformer,
cascade and live learned-model integration remain planned. Candidate artifacts
in MLflow are not automatically registered model versions or serving deployments.
See the [ML lifecycle](../use-cases/ml-lifecycle.md) for implemented versus planned steps.

## GitHub milestone reconciliation

All [seven milestone descriptions](https://github.com/khab40/lob-arena/milestones)
were updated and read back on 2026-09-21 at 10:25 UTC. Titles, states and baseline
due dates were preserved. M2 now records merged PR #200, the successful 64-object
readback and separately identified PR #207 payload/readiness evidence. M1 retains
its open infrastructure work; downstream descriptions expose their dependency risk.

M1's API counters still reported zero issues despite assignments to #20/#22; use
linked issue states. Some issue bodies still name earlier main commits and omit
PR #207's later receipts. Those issue-body discrepancies remain flagged; this
update changed milestone descriptions, not issue bodies or board states.

Historical spend figures and consumed Job counts remain audit facts. The current
[execution policy](../ml/model-validation-execution-policy.md) supersedes old billing,
expiry and fixed-spend gates. Current operator instructions still govern each
execution scope; nothing in these documents grants cloud or final-test access.
