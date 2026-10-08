# Transformer seed confirmation results — 4 October 2026

Both exactly authorized replacement Jobs completed and passed independent
verification. Three-seed stability passed. The candidate remains **width 128,
learning rate 0.0003, seed 42, epoch 4**; confirmation does not select a new winner.

[Story #24](https://github.com/khab40/lob-arena/issues/24) ·
[Project #3](https://github.com/users/khab40/projects/3) ·
[PR #308](https://github.com/khab40/lob-arena/pull/308)

| Seed | Selection log loss | F1 at 0.5 | Selected / stopped epoch |
|---|---:|---:|---:|
| 42, original candidate | 0.0024378335 | 1.0 | 4 / 9 |
| 7, confirmation | 0.0000427579 | 1.0 | 11 / 16 |
| 2027, confirmation | 0.0002310892 | 1.0 | 8 / 13 |

Loss range **0.0023950756** and F1 range **0.0** both satisfy the predeclared
maximum of 0.05. Each selected checkpoint has 45 true positives, 1,205 true
negatives and no errors on S. S is a tuning fold: 1,250 targets from NVDA on
2019-10-30. These scores do not establish generalization or a LightGBM advantage.
Probabilities remain uncalibrated; research labels are not real-world abuse truth.

[Per-run Markdown reports and charts](experiments/transformer-confirmation-r2-20261004/index.md)
retain every epoch's weighted training loss, unweighted selection loss/F1,
checkpoint choice, confusion matrix, resources and lineage. Different loss
weighting means the training and selection magnitudes are not directly comparable.

## Execution and independent verification

| Seed | Nebius Job | Runtime | Artifacts |
|---|---|---:|---:|
| 7 | `aijob-e00vjqjfhgp7s79mj4` | 358.79 s | 44 |
| 2027 | `aijob-e00kq6q1fnv1kkn40p` | 343.96 s | 38 |

Exactly two sequential L40S Jobs ran, one attempt each, within their two-hour
timeouts. Signed context delivery succeeded for both. Seed 7 passed independent
collection before seed 2027 submission. All **82 artifacts / 149,057,537 bytes**
are retained in versioned S3 and the root execution evidence directory.
Total provider runtime was **11m42.75s**. Both Job records are terminal COMPLETED.

Independent checks bind provider identity, signed context, exact request,
versioned publication, all artifact hashes, event chain, data roles, baseline
alignment, saved-logit metrics and deterministic epoch selection. Model weights
were not executed locally. The original failed Job and its evidence remain.

The approved image preserves original numerical source `87ce8a9`; assembly source
`7b88ea2` adds only the reviewed execution compatibility. Full immutable identities,
publication receipts and measurements are in the
[result evidence](../evidence/transformer-confirmation-results-20261004.json).

The first retained provider observations after context delivery were delayed by
119.48 s and 72.68 s respectively; subsequent saved gaps were below 22 s. The
records therefore do not demonstrate the runbook's 30-second cadence throughout.
Both terminal states and runtime bounds are verified. Start the observer before
submission in the next package so this coverage gap cannot recur.

## Preservation and cost disposition

Keep the full **$25 excluding VAT** commitment: $12.50 for the old failed attempt
plus $6.25 per new Job. Approximately **$0.50** is the two new Jobs' compute/disk
time estimate, including provisioning. It excludes storage, requests, egress and
VAT; actual billing remains unreconciled. No estimated savings authorize new work.

The local operator and plotting environments were incomplete and restored before
their respective use. A missing local metadata bundle stopped collection before
result GETs; its exact request-bound bytes were recovered from the approved local
image and hash-checked. Neither recovery changed the GPU runtime or repeated a
model run. Full configuration, normalization, checkpoints and replayable MLflow
events remain retained; online MLflow reconciliation is pending.

## Next approved-plan step

1. Prepare and review explicit compatibility for the original seed-42 checkpoint
   and five original publications plus the two verified replacement confirmations.
   Preserve original checkpoint bindings and record the new execution separately.
2. Prepare one calibration/comparison Job, at most one hour, with exact image,
   request, dry-run, resource and spend bounds; obtain separate authorization.
3. Fit temperature on C only, select declared operating points on O, and compare
   identical target rows with saved frozen LightGBM predictions. Independently
   verify results and present a continue/stop/inconclusive research decision.

No calibration, comparison, final-fold access or candidate freeze was performed
here. Story #24 remains In Progress. G8/G9 remain closed; platform maintenance
and online MLflow follow the research decision.
