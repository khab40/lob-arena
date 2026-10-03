# Verified Transformer training grid — 2026-10-03

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3),
[PR #291](https://github.com/khab40/lob-arena/pull/291).

All four authorized GPU trials completed once, sequentially, and passed
independent publication verification. The fixed selection rule chooses
**width 128, learning rate 0.0003, seed 42, checkpoint epoch 4**.
The [machine-readable result index](../evidence/transformer-training-grid-results-20261003.json)
binds the authorization, runtime, per-trial receipts, selected checkpoints and
resource measurements. The [original execution package](transformer-training-grid.md)
records the bounds and behavioral acceptance criteria.

[Per-experiment reports and charts](experiments/transformer-grid-20261003/index.md)
show the recorded epoch losses, selection F1 and selected-checkpoint errors.
The [reporting workflow](transformer-run-reporting.md) generates these from verified
artifacts after collection, before online MLflow reconciliation.

## Results and interpretation

All trials used 33,450 training rows and the same 1,250-row selection fold
(45 positive, 1,205 negative), batch 64, at most 30 epochs and patience 5.
Lower raw selection log loss determines the winner; ties use parameter count
then trial hash. F1 at probability 0.5 is descriptive and did not select it.

| Width | Learning rate | Selection log loss | Selection F1 at 0.5 | Selected / stopped epoch |
|---:|---:|---:|---:|---:|
| 64 | 0.0003 | 0.01273812 | 0.928571 | 9 / 14 |
| 64 | 0.001 | 0.02999683 | 0.896552 | 6 / 11 |
| **128** | **0.0003** | **0.00243783** | **1.000000** | **4 / 9** |
| 128 | 0.001 | 0.03610110 | 0.918367 | 3 / 8 |

The winner classified all 45 positive and 1,205 negative selection rows correctly
at 0.5. This fold was used repeatedly for checkpoint and configuration selection;
perfect selection F1 does not establish generalization or superiority to LightGBM.
Evidence covers one seed and governed research labels. Calibration and the
operating-point comparison have not run. Source separation does not imply
statistical independence, and LightGBM's prior validation exposure remains a
limitation of the later development comparison.

## Execution, preservation and measurements

All four ran on Nebius Serverless: one L40S, 8 vCPU, 32 GiB RAM and 100 GiB
ephemeral disk each, on-demand, restart never, two-hour timeout. The smoke-tested
immutable image and source were unchanged. No model workload ran locally.
Signed provider context preceded training; each COMPLETED result passed separate
S3 readback before the next Job was created. No replacement was submitted.

| Slot | Provider runtime (s) | Training loop (s) | Host peak (GiB) | GPU allocated / reserved (MiB) |
|---|---:|---:|---:|---:|
| search-64-0003 | 382.36 | 62.74 | 2.678 | 133.59 / 152 |
| search-64-001 | 354.67 | 48.96 | 2.689 | 133.59 / 152 |
| search-128-0003 | 328.31 | 40.73 | 2.674 | 182.65 / 196 |
| search-128-001 | 355.75 | 35.82 | 2.688 | 182.65 / 196 |

Training-loop time includes selection evaluation and checkpoint publication.
Total provider runtime was 23m41s; creation-to-terminal allocations totaled
38m33s, excluding gaps between trials. GPU utilization and inference latency
were not measured. Small allocated memory does not itself measure utilization.

The independently checked inventory contains 132 artifacts / 125,784,318 bytes,
including 42 epoch checkpoints, selection predictions, configuration, normalization,
target ledgers, input/role/baseline verification, measurements and MLflow events.
Artifacts remain in four versioned S3 prefixes named in the per-trial receipts;
SUCCESS version/hash anchors each inventory. Root
`outputs/transformer-startup-repair-20261003/p2/execution/` holds matching local
readbacks. Online MLflow reconciliation is pending; no registry promotion occurred.

The approved $50 incremental reservation above the operator-reported $300 baseline
remains committed until billing reconciliation. Exact compute/disk quotes applied
to creation-to-terminal time estimate **$1.00 excluding VAT**, excluding storage,
requests and transfer; this is not the billed total. The retained spend ledger
includes provisioning/teardown contingency and storage funding through December 31.
Its review date does not authorize artifact deletion or additional Jobs.

## Next bounded research steps

1. Prepare and review the winner's two confirmation runs, seeds 7 and 2027,
   with unchanged width/rate and no further search. Obtain exact run/spend
   authorization before submission; the four-trial authorization is consumed.
2. Verify seed stability, then use the declared calibration and operating-point
   roles for temperature calibration, threshold selection and an exact-row
   comparison with frozen LightGBM. Preserve all seeds and rejected checkpoints.
3. Report quality, uncertainty, per-family behavior and inference resources;
   decide continue, stop or inconclusive. Freeze any retained research package
   with configuration, checkpoints, hashes and replayable MLflow lineage.

These steps preserve the research fork's final-test boundary. G8/G9 remain closed.
MLflow reconciliation and platform acceptance follow research; no hybrid work
or production promotion is implied by the selection result.
