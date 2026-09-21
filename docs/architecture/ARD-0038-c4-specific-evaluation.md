# ARD-0038: C4-Specific Frozen Evaluation

Status: Accepted

Date: 2026-09-15

Implementation Status: `[implemented and synthetically rehearsed; production G8 open]`

## Context

The frozen Wave 1 C4 release and the seven-date benchmark share the readable
`nasdaq-public-sample-v1` name but have different protocol hashes. C4 has four
dates and a single test date, 2019-12-30, with AAPL, MSFT and NVDA. Applying the
seven-date acceptance contract would misrepresent both coverage and metrics.

## Decision

Use the separately approved C4 contract for this frozen candidate. Preserve
[ARD-0025](ARD-0025-governed-corpus-and-ml-benchmark.md) as the broader benchmark;
this record does not relax its qualification requirements or change the model,
features, calibration or operating thresholds from
[ARD-0031](ARD-0031-complete-lightgbm-v1.md).

- Bind the candidate file, semantic frozen root, test projection manifest and
  comparison-package hashes in `C4EvaluationProfile`.
- Require the original preparation manifest and exactly 27 distinct C3
  checkpoint releases, resolving 30 canonical replay domains. Verify complete
  inventories and exhaust canonical streams to check their hashes.
- Join predictions, projected observations and canonical snapshots by run,
  sequence, timestamp and tick; union original Java rules alerts at that tick.
  Missing, duplicate, unmatched or altered evidence fails closed.
- Measure retained supervised rows: precision, recall, F1, false alerts per
  million observations, negative-row false-positive rate and observed-campaign
  recall; report paired LightGBM-minus-rules differences and per-family counts.
- Report raw/frozen-calibrated Brier scores and ten-bin ECE. Use 2,000 paired
  whole-base-session bootstrap draws, seed 20260828, and 95% percentile intervals.
  Undefined values stay null; campaigns without retained positives are excluded
  from observed-campaign recall and explicitly recorded.
- Preserve `research_control_assumption` negative labels and `synthetic_scenario`
  positives. Three symbol sessions on one date cannot establish temporal
  generalization. Event-level false-alert rates and detection before realized
  benefit are excluded, not inferred from row metrics.

The shared logger independently re-evaluates original evidence before opening
or resuming a run. It compares the complete canonical report, snapshots report
bytes for upload, rejects duplicate JSON keys and disguised/downgraded C4 claims,
and indexes finite metrics under `c4.test.*`. MLflow remains an index under
[ARD-0027](ARD-0027-shared-mlflow-tracking.md).

## Implementation and verification

The implementation is in
[c4_evaluation.py](../../backend/app/ml/lightgbm/c4_evaluation.py),
[c4_replay_evidence.py](../../backend/app/ml/lightgbm/c4_replay_evidence.py) and
[tracking.py](../../backend/app/ml/lightgbm/tracking.py).
The injected runner accepts `--c4-evaluation-inputs`; `g8-evaluate-c4` separately
evaluates an existing verified result without rescoring or modifying it.
The runner option remains optional for legacy compatibility; the replacement
package must require and hash-bind it and the reviewed code overlays.

The [complete synthetic rehearsal](../evidence/g8-complete-c4-rehearsal-20260914.json)
verified 27 checkpoints, 30 replay domains and 198 paired observations in the
pinned image. Features/rules alerts are fixtures; remote transport is simulated.
The later [native rehearsal](../evidence/g8-native-recovery-20260917.json)
and [independent S3 readback](../evidence/g8-independent-s3-readback-20260917.json)
verify synthetic remote recovery. Original production comparison/registration
verification and the changed production transport remain separate gates;
fixture comparisons do not become actual Java evidence.

## Alternatives and consequences

Reusing the seven-date contract or regenerating a rules baseline would change
the evidence contract. Accepting report-supplied verification flags would permit
unverified claims. Independent evaluation costs additional comparison work but
does not rescore the model. Existing no-report logging remains compatible.

## Dependencies and related documentation

- [ARD-0035: Nebius qualification](ARD-0035-nebius-lightgbm-first.md) — execution and exit gates.
- [ARD-0039: Same-run MLflow recovery](ARD-0039-same-run-mlflow-recovery.md) — consumes independently verified C4 evidence.
- [C4 evaluation contract](../operations/g8/g8-c4-evaluation-contract.md) — detailed metrics and CLI contract.
- [G8 completion recovery](../operations/g8/g8-completion-recovery.md) — incident history and remaining gates.
