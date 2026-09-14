# G8 C4-specific evaluation contract

Status: implementation in review; not live-execution authority or a G8 exit.
The user approved this C4-specific contract on 2026-09-14. Candidate, calibration,
features and operating thresholds remain frozen. The replacement execution still
requires the exception and package-specific approval in
[G8 recovery](g8-completion-recovery.md).

## Why a separate contract is necessary

The frozen release and the seven-date benchmark share the readable identifier
`nasdaq-public-sample-v1` but have different protocol hashes. The C4 root contains
four dates: two training, one validation and one test date (2019-12-30). Its test
fold has AAPL, MSFT and NVDA, with 30 replay domains: three controls and 27
family/seed comparisons. It does not satisfy the seven-date benchmark contract.

The [metadata-only audit](evidence/g8-benchmark-compatibility-20260914.json)
verifies the candidate's C4 binding and records that incompatibility without
reading test rows. Exit code 2 from `g8-benchmark-readiness` is intentional for
these inputs, not permission to change the frozen hashes. The approved contract
does not retroactively make the seven-date benchmark compatible.

## Frozen inputs and provenance

`C4EvaluationProfile` binds the candidate file hash, semantic frozen-root hash,
test projection manifest hash and comparison-package file hash. Its calculation
policy is fixed in code; these identities must be included in the reviewed
execution package before any replacement authorization.

The comparison package references the original test preparation manifest and
exactly 27 distinct original C3 checkpoints. The preparation hash must equal
the C4 root's test source. Each checkpoint must have a valid complete release,
the frozen checkpoint identity, preparation binding and payload inventory.
This resolves exactly 30 canonical replay domains; no rules regeneration occurs.
Live availability of those checkpoints is **not yet verified**.

The evaluator verifies the existing model bundle and prediction release against
the frozen candidate, and verifies C4 projection artifacts. It joins every
prediction to the original projected observation and canonical snapshot using
run, sequence, timestamp and tick, checking labels and replay identities. Original
Java rules alerts are unioned at that same tick. Every canonical stream must be
exhausted and its stream hash verified before a report is accepted. Missing,
duplicate or unmatched observations fail evaluation.

## Metrics and limits

The observation unit is a retained supervised projection row, not a canonical
event. Negative labels remain `research_control_assumption`, not adjudicated clean
market activity. Positive labels remain `synthetic_scenario`.

- Both detectors: row precision, recall, F1, false alerts per million retained
  observations, negative-row false-positive rate, and observed-campaign recall.
- Paired LightGBM-minus-rules differences: precision, recall, F1, false alerts
  per million observations, and observed-campaign recall.
- LightGBM: raw and frozen-calibrated Brier scores and ten equal-width-bin ECE;
  reliability-bin counts, mean probabilities and positive rates are retained.
- Per-family positive-row recall and confusion counts are included as artifacts.
- Observed-campaign recall counts a hit on any retained positive observation;
  campaigns without retained positive observations are explicitly listed by the
  join adapter and excluded from this metric's denominator.

Uncertainty uses 2,000 paired whole-base-session bootstrap resamples, seed
20260828, with 95% percentile intervals. Undefined metrics stay null in the report
and are not indexed as zero in MLflow. Undefined bootstrap draws are counted.
One session produces no interval. The real test has only three symbol sessions
on one date: intervals are limited, conditional descriptions of those sessions,
not evidence of temporal generalization or independent market-wide sampling.

This contract does **not** compute false alerts per million canonical events or
detection before realized benefit, and does not establish seven-date benchmark
qualification. Those omissions are machine-readable. It makes no guarantee of
passing model acceptance thresholds, and must not be used to rename row-level
results into event-level acceptance evidence.

## MLflow and recovery boundary

The logger checks the report's exact metric inventory, prediction-manifest hash,
model binding, threshold, row count and declared observation semantics before
opening a run. It indexes finite point metrics under `c4.test.*`, tags the contract
and candidate/profile identities, and uploads the complete JSON report (including
uncertainty and reliability). Existing dataset lineage logging is retained.
The report's provenance is established by `evaluate_c4_release`, not by trusting
the `same_observations_verified` flag from an arbitrary JSON file. A live reviewed
runner must generate and bind this report before handing it to the logger.

`g8-evaluate-c4` only evaluates an already-scored, checksum-verified final result.
It writes a separate new report and never mutates the source result, scores,
submits a job, or writes MLflow. This command is a postprocessing primitive, not
the complete durable publication/log-only recovery implementation.

The frozen G8 runner is **not yet wired** to this evaluator. Its existing logging
and temporary workspace must not be treated as duplicate-safe or durable recovery.
Required next gates remain full frozen-image integration, persistent output
recovery, original C3 inventory availability, authenticated remote MLflow/S3
rehearsal, fresh spend/IAM checks and reviewed replacement authorization.

## Verification

`make lightgbm-wave1-g8-check` includes golden metric/uncertainty tests, metadata
guards, canonical-stream and join tamper tests, a 27-checkpoint inventory fixture,
and a real local MLflow report/metrics/artifact round-trip. The MLflow transport
fixture uses synthetic predictions and an explicitly synthetic silent rules
detector; it does not prove the entire canonical comparison path end to end.
No production test rows or remote final-read credentials are used by these tests.

Local validation on 2026-09-14: the G8 target passed 106 tests plus Ruff and the
existing CLI smoke checks. An additional 18 LightGBM-release, canonical-bundle
and dataset-lineage regression tests passed. Local MLflow emitted Python 3.14
`codecs.open` deprecation warnings; these were warnings, not failed assertions.
These results do not replace CI or the pinned-image/remote rehearsal gates.
