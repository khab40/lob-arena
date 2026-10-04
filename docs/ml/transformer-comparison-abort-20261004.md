# Comparison attempt stopped during startup — 4 October 2026

[Story #24](https://github.com/khab40/lob-arena/issues/24) ·
[Bug #312](https://github.com/khab40/lob-arena/issues/312) ·
[Project #3](https://github.com/users/khab40/projects/3).

The exactly authorized one-hour L40S Job
`aijob-e00ma26ee5bavrb8nb` was **cancelled** after the local observer rejected
the supported `IMAGE_PULLING` state. No verified calibration or comparison
result exists. The output prefix is empty, and no signed context was published.
This is an orchestration failure; the research outcome remains **inconclusive**.

## Input, intended process and actual output

- Input: unchanged width-128 / learning-rate-0.0003 / seed-42 / epoch-4 checkpoint,
  seven verified publications, governed C/O rows and frozen LightGBM predictions.
- Intended process: verify checkpoint compatibility, fit temperature on C,
  compare aligned O predictions and publish independently verifiable results.
- Actual output: provider startup logs, observer/attester failure receipts,
  cancellation confirmation and an empty-prefix readback. No loss, quality,
  calibration or inference-latency values are available; no plots can be drawn.

The package passed its 289 inert checks and exact dry-run. Those checks omitted
the image-pull transition in the new observer. The observer maintained its own
three-state list while the existing shared `LIVE_STATES` already contained
`IMAGE_PULLING`. The retained provider snapshot reproduces that mismatch.
The attester continued waiting for INTENT until cancellation; its later
provider-validation failure is not evidence of a checkpoint or model failure.

## Repair and verification

The observer now uses the shared live states. STARTING and IMAGE_PULLING share
one uninterrupted ten-minute startup budget. Failure receipts retain a bounded
provider-state identifier, without arbitrary response text. Regressions cover
the actual provider snapshot, the full lifecycle, image-pull timeout transitions,
unknown states, identity/resource drift and closed admission.

75 focused and 294 broader inert tests, plus Ruff, pass. No model/image change or cloud rerun is
part of this repair. The historical approved proposal and its file hashes remain
unchanged; the repaired helper does not inherit the consumed execution approval.

## Cost and next step

The **$6.25 reservation remains held**, alongside the earlier $25 confirmation
commitment. Actual charges are not reconciled; no estimated savings are released.
The Job is terminal and the local helper processes have exited.

Review the repair, then prepare a fresh replacement identity and exact package
with separate authorization before another Job. Do not reuse the empty but
consumed attempt prefix. Preserve seed 42 and all prior results; no retraining,
new search, final-test access or production promotion is authorized.

[Bound evidence](../evidence/transformer-comparison-abort-20261004.json).
Durable local evidence: `outputs/transformer-comparison-20261004/`.
