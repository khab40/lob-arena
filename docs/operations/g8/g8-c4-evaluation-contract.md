# G8 C4-specific evaluation contract

> **Status reconciliation — 2026-09-21:** Durable replacement integration and native synthetic recovery are now implemented. Original comparison metadata is verified; full payload verification remains a separate gate at this snapshot.
> See [current roadmap evidence](../../roadmap/CURRENT_STATUS.md) and the
> [execution policy](../../ml/model-validation-execution-policy.md). Earlier
> dated receipts retain their values; obsolete billing/expiry gates do not apply.

Architecture decision: [ARD-0038](../../architecture/ARD-0038-c4-specific-evaluation.md).

Status (2026-09-15): core evaluator/provenance merged in PR #171; injected-runner
C4 integration and full synthetic rehearsal merged in PR #172. Recovery APIs
subsequently merged in PRs #175 and #176. This paragraph records September 15;
subsequent durable integration/native rehearsal completion is summarized above.
Not live-execution authority or a G8 exit.
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

The [metadata-only audit](../../evidence/g8-benchmark-compatibility-20260914.json)
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
Original metadata availability is verified in PR #207; full checkpoint payload
availability/integrity remains unverified at the [dated snapshot](../../roadmap/CURRENT_STATUS.md).

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

The shared logger requires original C4 evidence inputs and independently invokes
`evaluate_c4_release` before opening a run. It compares the complete submitted
report against the computed result using canonical JSON SHA-256, including the
candidate/profile identities, metrics, uncertainty, coverage and model binding.
Self-asserted flags or hashes are never sufficient. Schema downgrades, wrapped C4
claims and duplicate JSON keys fail closed. The logger captures the report once,
uses a private snapshot for both parsing and artifact upload, and records its
byte hash as `c4_evaluation_report_sha256`.

It indexes finite point metrics under `c4.test.*`, tags the verified contract and
candidate/profile identities, and uploads the complete report. Existing dataset
lineage and non-C4/no-report logging remain supported. Recomputing comparison
metrics over existing predictions does not retrain, recalibrate or rescore the
model, but requires the original comparison evidence to be available.

For the bundle CLI, pair `--benchmark-results <report>` with
`--c4-evaluation-inputs <inputs.json>`. This evidence-location manifest contains
`profile`, `frozen_root`, `projection`, `comparison` and `candidate` paths, resolved
relative to the manifest's directory. It accepts no verification assertions.
If a postprocessing report contains source-result identities, set the optional
`source_result` path to the original immutable scored result (default: parent of
the logging artifact root). The logger verifies that complete result, its exact
prediction manifest and all three source identity fields. Keep a separate logging
artifact copy when adding reports; never mutate the original scored result.

`g8-evaluate-c4` only evaluates an already-scored, checksum-verified final result.
It writes a separate new report and never mutates the source result, scores,
submits a job, or writes MLflow. This command is a postprocessing primitive, not
the complete durable publication/log-only recovery implementation.

The injected G8 runner now accepts `--c4-evaluation-inputs`, rejects inconsistent
frozen metadata before remote readiness/intent/download operations, computes the
C4 report from its actual scored output, and supplies the report and original
inputs to the shared logger for independent re-evaluation. It does not score again.
The unchanged image needs the reviewed evaluator/tracking overlays. The option
remains optional for legacy compatibility; replacement submission must require and
hash-bind the C4 profile and code before live authorization. Its existing logging
and temporary workspace must not be treated as duplicate-safe or durable recovery.
Required next gates remain persistent output recovery, original C3 inventory
availability, authenticated remote MLflow/S3 rehearsal, fresh spend/IAM checks and
reviewed replacement authorization.

## Verification

`make lightgbm-wave1-g8-check` includes golden metric/uncertainty tests, metadata
guards, canonical-stream and join tamper tests, a 27-checkpoint inventory fixture,
and a real local MLflow report/metrics/artifact round-trip. The MLflow transport
fixture uses synthetic predictions and an explicitly synthetic silent rules
detector at the checkpoint/join input. Candidate/model/root/projection verification
and evaluator invocation are real; the fixture does not prove the entire canonical
comparison path end to end.
No production test rows or remote final-read credentials are used by these tests.

Local validation on 2026-09-14: the G8 target passed 106 tests plus Ruff and the
existing CLI smoke checks. An additional 18 LightGBM-release, canonical-bundle
and dataset-lineage regression tests passed. Local MLflow emitted Python 3.14
`codecs.open` deprecation warnings; these were warnings, not failed assertions.
These results do not replace CI or the pinned-image/remote rehearsal gates.

Follow-up: `g8_rehearsal.py --c4` now adds a complete synthetic original-format C3
inventory and C4 layout, without substituting checkpoint validation, the canonical
join, evaluator or shared logger. Its 27 checkpoints resolve 30 replay domains and
198 paired observations; it counts one call to the real final-scoring function and
verifies one local MLflow run, report bytes/hash and all indexed point metrics.
The rules alerts and numeric features are fixture-generated, not Java execution
or production results. The exact frozen-image run with reviewed module overlays
passed on 2026-09-14; see the
[hash-bound receipt](../../evidence/g8-complete-c4-rehearsal-20260914.json) and
[reproduction instructions](g8-completion-recovery.md#reproduce-offline).
Follow-up local validation passed 121 G8 tests plus Ruff/CLI checks and the same
18 release/canonical-bundle/dataset-lineage regressions. Remote transport and
durable recovery remain separate unpassed gates.
