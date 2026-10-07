# Transformer research week: 4–10 October 2026

Reconciled 6 October, Asia/Tbilisi, against verified grid/confirmation/comparison results and live
GitHub tracking. [Story #24](https://github.com/khab40/lob-arena/issues/24) →
[Feature #16](https://github.com/khab40/lob-arena/issues/16) →
[Epic #15](https://github.com/khab40/lob-arena/issues/15),
[Project #3](https://github.com/users/khab40/projects/3).

**Goal: decide whether Transformer adds enough value over frozen LightGBM to
justify further research.** Continue, stop and inconclusive are valid outcomes.
This refreshes the existing plan; it does not change the experiment protocol or
authorize execution, final-test access, promotion, merging or cleanup.
Verification: reconcile saved evidence, repository documentation and GitHub state.

## 5 October comparison update

PR #315 merged and the exact one-hour L40S package/$6.25 cap was approved.
One comparison Job completed; all 15 new artifacts plus 229 prerequisites passed
offline reconciliation. [Results and four plots](experiments/transformer-comparison-r2-20261004/report.md).
The original verifier rejected a one-ULP aggregate difference; [Bug #317](https://github.com/khab40/lob-arena/issues/317)
adds bounded arithmetic reconciliation with exact hashes/rows/thresholds intact.
No model rerun. C-only temperature is 0.998497; on identical O rows Transformer
F1/AP are 1.00/1.00 versus LightGBM 0.545/0.436. Recommendation is
**continue_research**, accepted by the operator after PR #318 merged. Perfect development scores
require an unseen protocol and leakage/robustness review before broader claims.
The full $6.25 remains held; actual billing and online MLflow are unreconciled.
The dated execution snapshot below is historical.

## 4 October execution snapshot before replacement approval

The two-seed package in PR #296 was merged and explicitly approved with a $25
additional cap excluding VAT. Seed 7 failed at context delivery before training;
the local attester returned AttributeError without diagnostic origin. Seed 2027
was not submitted. [Failure report](experiments/transformer-confirmation-20261004/seed-7.md).
[Bug #306](https://github.com/khab40/lob-arena/issues/306) repairs diagnostics and
startup-path coverage. The original error's exact cause remains unknown.

PR #307's diagnostic repair is merged. Both exactly approved replacement Jobs
reached COMPLETED and passed independent readback. [Three-seed stability passed](transformer-confirmation-results-20261004.md):
selection-loss range 0.002395075568322679 and F1-at-0.5 range 0.0, below the 0.05
limits. Seed 42 / epoch 4 remains the candidate. PR #308 is merged.
Keep the full $25 confirmation commitment, including the failed attempt's $12.50,
until billing reconciliation. Calibration and LightGBM comparison have not run;
subsequent dates remain conditional and separate exact run/spend approval is required.

PR #311's checkpoint package was merged and exactly approved with a $6.25
additional cap. Its single comparison Job was cancelled during image download
because the observer omitted IMAGE_PULLING. The output prefix is empty and no
comparison result is verified. [Incident and repair](transformer-comparison-abort-20261004.md)
under [Bug #312](https://github.com/khab40/lob-arena/issues/312). The $6.25 remains
held. PR #313 merged with all 25 checks passed and Bug #312 is closed.
The [corrected r2 package](transformer-comparison-r2-20261004.md) preserves
the candidate and prerequisites; 252 inert tests (one expected skip), image
inspection, unused-name/prefix checks and exact dry-run passed. Zero r2 Jobs
created. Next: package review/CI, exact one-hour L40S authorization and proposed
$6.25 additional cap, then independent comparison verification and research decision.

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
2. **5 October — calibrate and compare: complete.** One exactly authorized
   replacement Job fitted temperature only on C (5,490 rows), selected declared
   operating points and compared identical O targets (2,470 rows). Frozen
   LightGBM predictions/calibrator/thresholds were reused; no refit or final access.
3. **5–6 October — save settings and lock holdout protocol: complete.**
   Operator chose continue_research and approved this implementation plan. #314
   saves the exact original seed-42/epoch-4 model and feature settings against
   seven retained artifact receipts. [Protocol](transformer-holdout-protocol-20261005.md)
   fixes prepared December C4 data, calibration and thresholds before access.
   PR #319 merged with green CI; seven retained artifacts reload identically.
4. **5–7 October — consumer/image merged; admission preparation active.** PR #321,
   #323 and review-policy #326 merged with green CI. The [sealed runtime and delivery](transformer-holdout-execution-package.md)
   preserve 13 numerical files and 48 dependencies; 403 inert regressions pass.
   P1 #325 now binds source identity to copied Git bytes and verifies 20 context files.
   Archived receipts authenticate original G8 prediction versions/hashes. The
   [admission chunk](transformer-holdout-admission.md) prepares authenticated saved
   64-row reference logits. PR #328 merged with all 25 checks passed; P1 #329
   is closed. The exactly approved three-JSON/62-HEAD audit completed, independently
   verifying 30 December runs / 15,160 aligned rows and all object versions `1`.
   [Evidence and exact inventory](transformer-holdout-metadata-results-20261006.md).
   Both temporary grants are removed and original policies independently verified.
   No December payloads or models ran; actual $0.01-cap billing is unreconciled.
   PR #331 and post-merge CI passed. The saved reference is published/versioned,
   image digest is published, and the [exact 252-input run package](transformer-holdout-run-20261006.md)
   passes SDK/local-CLI preflight, 258 inert holdout tests and provider dry-run.
5. **6 October — approval received; first Job admission repaired.** PR #337 merged
   with green CI and exact run/access/spend/signing/removal approval was received.
   Both grants were independently verified at final11/results12. The standalone
   watcher expired before separate submission; the guard rejected creation before
   intent or mutation. All 23 observations and fresh MCP reconciliation show the
   Job absent; no December payload read or model ran. [Bug #339](https://github.com/khab40/lob-arena/issues/339)
   adds coordinated same-process admission, durable intent and reserved observation
   time; 46 focused inert cases pass with independent review. Preserve old history
   and require exact recovery approval before the first evaluation. Retain the existing
   $6.25 reservation; no cap increase. Reference parity still precedes December reads.
   On 7 October, all 25 PR #340 checks passed on 8cde2d1. Both originals are
   independently restored at final12/2 rules and results13/9 rules. Removal at
   01:09 UTC followed the three-hour window's expiry; that overrun is recorded.
   The [same-input recovery](transformer-holdout-first-run-recovery-20261007.md)
   in root `outputs/transformer-holdout-first-run-recovery-20261007/` passes
   offline preflight and fresh provider dry-run without creation. Fresh approval
   precedes grants/evaluation; prompt removal precedes reporting and decision.
   On 7 October, the exact recovery was approved and Job aijob-e00gvk2fdn6cmjxvkg
   completed, passed CUDA parity and published all seven outputs. Original policies
   are restored at final14/results15 after about 1,691 seconds of access.
   Independent readback aborted on harmless probability rounding amplified in
   reductions. [Bug #345 and repair plan](transformer-holdout-verification-repair-20261007.md)
   preserve frozen outputs and the eight-ULP reduction bound. One original saved
   LightGBM prediction artifact is missing locally. Its approved one-file recovery
   stopped before credentials/GET; its grant was removed within one hour, restoring
   results17/9 rules. PR #346's verifier repair passed CI. The exact-current
   recovery needs new approval, with tool permission/preflight before access,
   fresh readback and safe admission diagnostics. No GPU rerun is required.
6. **7 October — verification recovery; report and first demo, then MLflow.** Recompute paired
   saved metrics and weak three-session uncertainty summaries; retain one Markdown
   report with plots, resources and limitations. December is a Transformer holdout,
   not a globally blind benchmark. No automatic retraining/reselection. Reconcile
   retained artifacts later under #19; platform #20/#21 follows research. #25 stays
   Todo until a separate justified cascade proposal. After Transformer research
   verification and the operator decision, prepare #90/#91's first mock: saved
   research-score playback, detector/source selection, pacing and exact alert/threshold
   identity. Verify backend/GUI flow;
   broader secure demo acceptance and full #24 closure remain separately assessed.

## Bounds and interpretation

Both comparison authorizations are consumed: initial cancelled attempt and one
completed replacement. **No further Job is needed for this comparison.** The
replacement used one L40S, 8 vCPU, 32 GiB RAM, 100 GiB disk, concurrency one and
restart never within one hour. Both $6.25 reservations remain held until billing.
The completed four-Job authorization is consumed. Its $50 reservation above the
operator-reported $300 baseline remains committed pending billing reconciliation;
the roughly $1 compute/disk estimate is not a bill or reusable authorization.
Any future study requires its own exact data/execution/spend approval.
The $25 confirmation commitment also remains held; neither completed Jobs nor
estimated savings release it or authorize further work.

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
research decision. The separately authorized fixed-candidate December protocol does not establish
production qualification; broader claims require a later unseen corpus.

Evidence: [grid results](transformer-training-grid-results.md),
[per-run reports](experiments/transformer-grid-20261003/index.md),
[selection and decision protocol](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md),
[live logging handoff](transformer-training-progress.md).
