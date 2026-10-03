# Transformer GPU smoke: independently verified — 2026-10-03

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).
Execution follows merged [PR #288](https://github.com/khab40/lob-arena/pull/288)
and exact proposal `be433e78cd6dc731b6e143bd29f05e07622a5338ad7a6c8f585641f68e2cecd1`.
The operator's reply, “one bounded GPU smoke”, authorized one replacement only.

**Outcome: the GPU smoke passed and its published result was independently verified.**
Job `aijob-e00t8wpga7gh6c64q7` reached COMPLETED. Its runtime was 4m39s;
creation through terminal state took 8m26s, including provisioning.
In Tbilisi time it was created at 19:57:49, started at 20:01:36 and finished at
20:06:15. The evidence JSON retains the precise UTC timestamps.

The runtime used the corrected digest image bound to source `87ce8a9`:
one L40S, 8 vCPU, 32 GiB RAM, 100 GiB disk, 1 GiB shared memory,
on-demand pricing, a one-hour timeout and restart never. Exactly one Job was
created. The earlier failed smoke remains retained; neither attempt was retried.

## What passed

- Signed provider-context delivery and byte/version-verified publication.
- Governed input/class-support checks and frozen baseline alignment. The worker
  downloaded 185 pinned development objects, totaling 30,034,660 bytes.
- CUDA causal attention, padding, missingness, batch invariance, finite gradient
  and checkpoint-resume checks for both width-64 and width-128 models.
- Calibration boundary and role checks in the GPU smoke routine.
- A real-data smoke on 1,024 training rows: two epochs, 32 optimizer steps,
  finite final weighted-minibatch loss of 0.1029298306.

Independent collection checked the terminal provider state, signed context,
request identity, object versions/hashes, role package and linked event journal.
All 15 inventory artifacts (7,769,350 bytes) were retained locally, including
two checkpoint files; the verifier hashed their bytes without loading weights.
The result and SUCCESS remain in versioned S3 under the exact approved prefix.
[Bound evidence record](../evidence/transformer-replacement-smoke-result-20261003.json).

Measured worker elapsed time was 277.36s, CPU time 282.32s and peak host RSS
2.69 GiB. GPU utilization and peak GPU memory were not measured. Actual cost
remains unknown under the operator-managed policy; elapsed time is not an invoice.
MLflow reconciliation is pending from retained artifacts, as the research fork allows.

## What this does not establish

This is execution validation, not a trained research candidate or evidence that
Transformer beats LightGBM. The displayed loss is a training-minibatch value,
not held-out quality. The fixed grid, selection, seed stability, calibration,
operating-point comparison and research decision are still pending.

Selection/calibration/operating-point support remains 1,250/5,490/2,470 rows,
with 45 positive examples in each role. The existing same-date, three-instrument,
synthetic-label and LightGBM validation-exposure limitations still apply.
The reused role-audit record retains generic platform/authorization flags;
it is not a global readiness certificate. This Job used its separate approved
research-fork request and verified provider context. No final-test access occurred.

## Next gate

Prepare exact requests for the predeclared width64/128 × learning-rate0.0003/0.001
grid, seed42: four sequential Jobs, each with the existing two-hour limit.
Bind each to this verified smoke receipt and the same frozen input/model protocol.
Obtain execution authorization before launching those Jobs. Verify every trial
before checkpoint selection, then proceed to the two confirmation seeds and the
calibration/comparison slot within their separately governed gates.

Do not rerun this smoke. The two consumed attempts plus the seven remaining
planned slots would total nine submissions and 15 allocated timeout-hours.
Raw execution/verification evidence and private signing custody remain in root
`outputs/transformer-startup-repair-20261003/p2/execution/`; custody is not committed.
