# Roadmap status — 2026-09-23

## G8 comparison verified; production runtime preflight — 2026-09-23

**The comparison audit passed independently:** 377 files rehashed, 27 original
checkpoints verified and all 30 canonical replays exhausted. Nebius Job
`aijob-e00p01kcjvxcb53g7e` completed in 28 minutes 49 seconds, its supervisor exited
zero and compute was released. The VM is stopped and final key inactive. See the
[independent receipt](../evidence/g8-comparison-verification-20260923.json) and
[execution plan](../operations/g8/g8-comparison-preflight-20260922.md).

Production preflight found at least ten full comparison recomputations before
publication, against a fixed one-hour Job timeout. The operator selected
verification reuse with unchanged byte-integrity checks, followed by a Nebius
benchmark. That repair is implemented in draft PR #220; its cloud benchmark and
updated production package are still pending. An earlier audit was cancelled by
a monitor bug after a log-fetch outage; the corrected startup latch is tested,
and that incomplete run is retained rather than counted as a pass.

Step 1 is merged in PR #219. Step 2 remains open until runtime preflight and the
updated package verify. Step 3 requires replacement-specific final authorization,
one evaluation and independent results/lineage verification. **G8 is not closed.**

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
| M2 LightGBM | 2026-09-23 | [#23](https://github.com/khab40/lob-arena/issues/23) open/In Progress; G0–G7 complete, G8 open, G9 blocked. Target at risk. |
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
