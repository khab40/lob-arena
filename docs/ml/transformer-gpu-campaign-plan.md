# Bounded Transformer development campaign — 2026-09-28

Status: **proposed; implementation approval pending; no GPU execution authorized**.
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

First reconcile #19–#21 acceptance evidence. Live GitHub #19 is CLOSED although
its body still lists incomplete application recovery and registration. Neither
closure nor the 60-table restore proves application writes, model registration,
or deployment of the repository's MLflow version. Resolve that discrepancy from
evidence before execution; do not infer permission to upgrade the live server.
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

