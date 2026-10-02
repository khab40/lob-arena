# Bounded Transformer development campaign — 2026-09-28

**2026-10-02 amendment:** the operator-approved [research fork](transformer-research-fork.md)
supersedes the platform/MLflow-first ordering below. Perform role checks inside the
first GPU Job, retain complete artifacts durably, and reconcile MLflow later.
The fixed model grid, input boundaries and exact-package execution gate remain.
The original config is retained unchanged for historical package verification.

Status: **implementation approved; readiness work in progress; no GPU execution authorized**.
[Story #24](https://github.com/khab40/lob-arena/issues/24) →
[Feature #16](https://github.com/khab40/lob-arena/issues/16) →
[Epic #15](https://github.com/khab40/lob-arena/issues/15),
[Project #3](https://github.com/users/khab40/projects/3).

As a detector developer,
I want a bounded, reproducible Transformer challenger on verified C4 sequences,
So that I can judge its development quality and resource use against LightGBM.

Actor: detector developer; reviewer: validation engineer.
Goal: one verified research candidate, or an explicit negative/infeasible result.
Value: decide whether richer sequence modeling merits further evaluation.
Acceptance: [Gherkin scenarios](transformer-gpu-campaign.feature), proposed and
not yet executed; implementation must map each to tests and runtime evidence.
Out of scope: new corpus/projection, final-test access, G8 rerun, production
promotion, hybrid features, distributed training and open-ended search.
Verification: static/inert checks locally; all model execution on Nebius
Serverless; independent versioned artifact and authenticated MLflow readback.

## 1. Establish readiness and immutable inputs

[PR #239](https://github.com/khab40/lob-arena/pull/239) merged at `8ee6e36`.
Its [r2 acceptance](../evidence/transformer-development-acceptance-r2-20260928.json)
verifies 185 object versions, 33,450 train and 9,210 validation targets,
64 steps, 60 ordered features and normalization on unique training targets.
Reuse its exact input inventory, root/tabular/sequence hashes, feature-release
ID/hash, normalization version/checksum and per-fold ordered row digests.
Do not reacquire, relabel, move rows between C4 folds or shorten sequences.
The 760–764 windows/second input measurement is not GPU model throughput.

First reconcile #19–#21 acceptance evidence. [Bug #244](https://github.com/khab40/lob-arena/issues/244)
reopened #19 as In Progress because application recovery and registration remain
incomplete. The 60-table restore does not prove application writes, model
registration, or deployment of the repository's MLflow version. Complete the
remaining readiness evidence before execution; do not infer upgrade permission.
Verify private connectivity, deployed/client versions, least-privilege writer,
artifact round trip and readback. The new experiment/model namespaces need an
explicit application-permission change; existing LightGBM access is insufficient.
Any missing platform/IAM work gets its own reviewed scope, not an implicit grant.

## 2. Predeclare development roles before looking at model scores

Keep C4 train/validation membership unchanged. Within validation only, create a
hashed role manifest for selection **S**, calibration **C**, and operating-point
selection **O**. Group all synthetic variants, replay seeds and overlapping
windows sharing a base source session into one indivisible group; merge groups
sharing source observations or label-horizon overlap. Verify source provenance,
not just distinct target row IDs. Never random-split overlapping row windows.

Sort groups by SHA-256 of canonical base-source identity; assign cyclically
S, C, O, without label/score-dependent retries. Record algorithm, exact group/row
lists, hashes, date/symbol/family counts and excluded/unavailable metrics. Require
at least one independent group and 20 positives and 20 negatives in each role;
these are engineering guards, not statistical power or production acceptance.
If this fails, stop before any GPU Job and propose a revised development-data
protocol. Do not fall back to sharing rows or search for a favorable assignment.
One validation date and potentially one symbol per role remain severe limits.

Only S selects epochs, architecture and learning rate. Only C fits calibration.
Only O selects thresholds and supplies held-out-from-calibrator diagnostics.
O becomes development selection data once thresholds are chosen; none of these
roles is an untouched final evaluation. Record all prior development exposure.
The previously inspected final fold cannot become an untouched Transformer test.

## 3. Implement the smallest causal classifier and one smoke gate

Use normalized values plus per-feature missingness indicators, linear projection,
fixed sinusoidal position encoding, pre-norm causal Transformer encoder, final
valid-token pooling and one binary `attack_active` logit. No IDs, labels or future
timestamps enter model features. Keep the 64-step projection and all 60 features.

| Fixed grid dimension | Values |
| --- | --- |
| Architecture | A: 2 layers, width 64, 4 heads, FFN 256; B: 2 layers, width 128, 4 heads, FFN 512 |
| AdamW learning rate | 0.0003; 0.001 |
| Search seed | 42 for all four combinations |
| Other settings | dropout 0.1; weight decay 0.01; betas (0.9, 0.999); epsilon 1e-8; gradient clip 1.0 |
| Schedule | linear warmup first 5% of planned updates, cosine decay to 10% of initial LR |
| Training | batch 64, no accumulation, at most 30 epochs, seeded epoch shuffle, no label-dependent sampling |
| Numerics | FP32, TF32 disabled, deterministic algorithms; no silent mixed-precision or kernel fallback |
| Loss | binary cross entropy with logits; train-only class/base-session weights, mean weight normalized to one |

Record the exact weight formula and counts in resolved config before launch:
each class has equal total weight; within a class, each base session has equal
weight; within each session/class cell, rows share that weight uniformly.
Use unweighted retained-row binary log loss on S for selection and report the
weighted training objective separately. No focal-loss, length, feature, optimizer
or precision search in this first campaign.

The smoke Job uses at most 1,024 train targets chosen by stable row identity,
two epochs, and both architectures for shape/gradient checks. Exercise causal
perturbation, padding/missingness, all-masked query handling, finite gradients,
single-target versus batch outputs and interrupted/resumed versus uninterrupted
training in the same Job. Do not use its quality to change the grid. Invalid or
empty target windows fail; padded query states must not contaminate valid states.
Explicitly translate the input contract's `true = allowed` attention mask to the
selected framework API; its Boolean conventions are not interchangeable.

## 4. Select checkpoints, then confirm seed stability

Validate S at each completed epoch. Select lowest unweighted binary log loss;
within 1e-6 prefer the earlier epoch. Stop after five consecutive epochs without
an improvement greater than 1e-6. Across the four complete, verified trials rank
by selected S loss, then lower parameter count, then canonical config hash.
Any missing/failed trial prevents ranking the incomplete matrix as successful.

Persist immutable epoch checkpoints before acknowledging progress: weights,
optimizer/scheduler, epoch/global step, Python/NumPy/CPU/CUDA RNG, sampler position,
precision state, resolved configuration and code/data/normalizer bindings.
Keep an append-only checkpoint inventory and selected-checkpoint digest. A
resume must verify these bindings; no fresh scheduler or silent new seed.
Same-runtime smoke resume must reproduce next-step state and logits within
declared absolute tolerance 1e-6; cross-device bitwise equality is not promised.
Failed/timeout Jobs consume their slot; replacement/resume Jobs need new approval.

Run the winning configuration at seeds 7 and 2027, selecting each epoch only on
S. Retain seed 42 as the candidate, never cherry-pick the best seed. Proposed
stability gate: S log-loss range ≤0.05 and raw-probability F1-at-0.5 range ≤0.05
across the three seeds. Report family recall and missing families. Failed gates
yield a research finding and stop before candidate freeze; no added search.

## 5. Calibrate saved predictions and freeze operating points

After grid/seed selection is sealed, a fresh GPU Job loads the seed-42 checkpoint
from versioned storage, verifies it and emits exactly aligned raw logits for C/O
and retained S reference rows. Compare S outputs to the training Job at absolute
tolerance 1e-6. No optimizer is loaded for inference; no weight changes occur.
Benchmark batches 1/16/64 after 20 warmups with 100 timed batches each; synchronize
CUDA and report model-only p50/p95 separately from preprocessing/end-to-end time.

One CPU Job fits a **fixed temperature scaler** on C only: p = sigmoid(logit/T),
T in [0.05, 20], minimize unweighted log loss, bounded scalar optimization,
maximum 200 evaluations and tolerance 1e-6. Persist objective, solver version,
convergence, boundary hits and T. No Platt/isotonic method search or refitting on O.
Non-convergence/non-finite results fail; a boundary solution is reported explicitly.
Compare raw versus calibrated O log loss, Brier and 10 fixed equal-width ECE bins.
If both Brier and ECE worsen beyond 1e-6, stop freeze rather than choose a new method.

On O, use the existing LightGBM operating-point rules/tie-breaks: maximum recall
at precision ≥0.90, maximum F1, maximum precision at recall ≥0.90. Preserve
unattainable floors as failure; never lower them. Report per-family, clean-window,
precision/recall/F1/PR-AUC and delay only where label/support semantics permit;
otherwise publish a reason. O threshold metrics are selection results.
Compare to retained frozen LightGBM development predictions on exact same row
identities, without retraining, threshold retuning or final-data reads. If that
prediction package is absent, mark comparison blocked; no hidden rescoring Job.
Prior LightGBM validation reuse makes this a development comparison, not a fair
new holdout claim. The frozen baseline and G8/G9 disposition remain unchanged.

## 6. Bind every configuration and artifact to MLflow

Use proposed experiment `lob-arena/transformer-development` and registry namespace
`lob-arena-transformer-attack-active` only after permission/readback preflight.
One campaign parent; child runs keyed by immutable campaign/trial/attempt IDs,
including failed trials, smoke, role audit, inference and calibration. Log each
epoch's train/S losses and resource samples with explicit steps. Record exact
Git SHA, image digest, Python/PyTorch/CUDA/cuDNN/driver/MLflow versions, GPU identity,
seeds, parameter count, resolved configs and config hashes, actual Job/resource
IDs, timeout, terminal state, duration, active GPU seconds and peak allocated/
reserved GPU memory. Report monetary cost as unknown/operator-managed, not zero.

Log metadata-only Dataset inputs with full corpus/split/projection/feature hashes,
feature-release ID, S/C/O role hashes, ordered row digests and normalizer digest.
Retain full SHA-256 alongside the existing shortened MLflow Dataset digest adapter.
Artifact inventory: approval/request/context receipts; dependency lock; resolved
data/model/training/selection/calibration/resource configs; role manifest;
normalizer/contract/schema; all checkpoint versions; learning curves; raw logits
and aligned prediction references; temperature/thresholds; metrics/reliability;
resource/failure logs; model card; checksum inventory and verification receipts.
Keep sensitive row artifacts in governed S3; MLflow gets permitted references and
aggregate evidence, never raw licensed records, credentials or private keys.

Use explicit logging, bounded retries and a durable event journal. Recover by
reconciling the same run/step/artifact hashes; reject conflicts or duplicate
ambiguous runs. Tracking loss must not trigger training/scoring again. A sealed
S3 package without authenticated MLflow readback is pending, not complete.
Independent verification checks every artifact's version/hash, config consistency,
row coverage, checkpoint selection, calibration-role isolation, metrics and model
signature. Register one version only after verification; retain registration and
research-only alias before/after receipts. No `champion` or production alias.
Freeze the package without refitting on train+validation. Serving adapter includes
preprocessing, weights, temperature, thresholds and exact input/output schema.

## 7. Enforce finite execution and evidence bounds

Nebius MCP service/help and project platform catalog checked September 28:
proposed GPU `gpu-l40s-a / 1gpu-8vcpu-32gb` (48 GB GPU memory); CPU
`cpu-e2 / 4vcpu-16gb`. Catalog presence does not prove quota/capacity or Job
admission: recheck and dry-run exact requests before execution. No larger-GPU
fallback. One Job at a time, non-preemptible, restart `never`, 100 GiB ephemeral
disk per Job, no persistent filesystem or public endpoint.

| Stage (execution order) | Jobs | Provider timeout each | Maximum GPU-hours |
| --- | ---: | ---: | ---: |
| CPU role/provenance and readiness audit | 1 | 1 hour | 0 |
| GPU smoke and resume/mask checks | 1 | 1 hour | 1 |
| GPU fixed four-trial grid | 4 | 2 hours | 8 |
| GPU two seed confirmations | 2 | 2 hours | 4 |
| GPU selected-checkpoint inference/readback | 1 | 1 hour | 1 |
| CPU calibration, threshold selection and package verification | 1 | 1 hour | 0 |
| **Total ceiling** | **10 (8 GPU + 2 CPU)** | **16 Job-hours** | **14** |

Internal workload deadlines reserve the final ten minutes for publication; stop
training before that deadline. Incomplete epochs/trials are failures, not extra
authorization. Bound prepared input cache to 8 GiB and retained outputs to 2 GiB
per Job / 20 GiB total; reject overflow before upload. Verify inputs once per
Job into immutable, digest-bound cache; never skip integrity checks or rescan
every source shard per minibatch. Observe CPU/GPU utilization to identify stalls.

Existing MLflow CPU VM: sequential tracking windows, target ≤16 active hours
across this campaign, stop whenever idle; no new disk/VM or live upgrade implied.
Record actual startup/idle/stop durations separately from Job ceilings. This is
an operational estimate, not a reinstated fixed billing/expiry gate. Apply the
[operator-managed policy](model-validation-execution-policy.md); no billing query
or invented dollar cap. Failed Jobs count; no automatic create/restart retries.

Before submission bind reviewed source, pinned image, exact config/input hashes,
output prefixes and versioned secret selectors to the finite slot ledger.
Generalize and test r2's CPU-specific execution binding for these exact GPU/CPU
presets; do not reuse the old approval or publisher unchanged. Arm the automatic
context publisher before create, require actual-Job signed context within five
minutes, resolve ambiguous creates by readback, and publish SUCCESS last with
no-overwrite writes. Independent readback anchors SUCCESS to provider logs.
Verify terminal worker/disk release; retain artifacts until approved disposition.

## 8. Deliver in reviewable chunks and make the decision explicit

1. **Readiness/config PR:** role audit, frozen campaign schema, namespace readiness,
   Gherkin coverage and exact execution packaging. Stop if roles/platform cannot
   support the design; propose the concrete repair before model implementation.
2. **GPU runtime PR:** causal classifier, trainer, checkpoint/resume, bounded
   publisher, resource collection and MLflow journal. Static checks first;
   request exact smoke execution approval only after code/image review.
3. **Campaign/freeze PR:** fixed grid and seeds, saved-logit calibration, threshold
   and registry readback, independently verified evidence and research decision.
   Exact remaining campaign bindings require approval before submission.

Each coherent PR: analyze → plan/human approval → code → review → tests → measure;
commits ≤200 changed lines. Model tests, including synthetic tests, run on Nebius.
Local/CI checks cover config, inert tensors, serialization and failure contracts
without executing models. A failed gate may finish a research chunk honestly.
No claim of full #24 completion until its separate serving/final-protocol and
feature-producer decision criteria are satisfied. October 9 remains a baseline,
not a promised finish date; reforecast after role feasibility and smoke evidence.

Approval of this plan authorizes the described implementation scope only.
Exact immutable Job packages, application/IAM changes, final evaluation, merge
and deletion retain their applicable separate authorization boundaries.

## API references checked for this proposal

- [PyTorch attention masks](https://docs.pytorch.org/docs/2.14/generated/torch.nn.MultiheadAttention.html):
  Boolean mask semantics require explicit conversion and boundary tests.
- [PyTorch reproducibility](https://docs.pytorch.org/docs/2.14/notes/randomness.html):
  seed and deterministic settings do not promise reproducibility across runtimes.
- [MLflow tracking](https://mlflow.org/docs/latest/ml/tracking/tracking-api/) and
  [registry workflow](https://mlflow.org/docs/latest/ml/model-registry/workflow/):
  explicit run/metric/artifact logging and separately audited model versions/aliases.
  These are API references, not evidence that the live server was upgraded.
- [ARD-0036](../architecture/ARD-0036-market-sequence-transformer.md) and
  [training/selection protocol](../use-cases/ml-training-selection.md) remain the
  governing research scope; this proposal narrows the first matrix explicitly.
