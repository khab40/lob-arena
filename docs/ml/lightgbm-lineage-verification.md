# Selected LightGBM lineage verification — 2026-09-22

As a validation engineer,
I want the frozen development run's dataset lineage and seven saved artifacts independently verified,
So that G8 preparation can rely on durable evidence without changing the candidate.

## Analysis and readiness

PR #218 restored live readback but found 90 dataset-input discrepancies. Its
receipt did not identify individual fields. Run-level metadata and dataset names
matched; artifact verification stopped before any downloads.

- Actor: validation engineer.
- Goal: explain every discrepancy and verify all seven governed artifacts.
- Value: establish exact frozen-candidate tracking lineage and recoverability.
- Out of scope: historical run edits, training, scoring, final-test access.
- Assumption: a checker correction is permissible only when supported by the
  historical producer and actual metadata; discrepancies cannot be ignored.
- Verification: inert regression fixtures plus bounded live GET-only readback.

```gherkin
Feature: Independently verify selected development lineage
  Scenario: Resolve a representation mismatch
    Given a frozen inventory and the existing selected development run
    When their dataset metadata uses the historical producer's representation
    Then the checker verifies equivalent identities and exact full hashes

  Scenario: Reject a real lineage difference
    Given a dataset source or full artifact hash differs from frozen evidence
    When the checker compares the selected run
    Then verification fails and identifies the field
    And no historical record is changed

  Scenario: Verify retained governed artifacts
    Given all selected-run lineage fields match frozen evidence
    When the seven exact governed artifacts are read back
    Then every size and SHA-256 matches the inventory
    And provider shutdown is independently verified
```

## Plan and cloud bounds

1. Capture field-specific discrepancies and inspect the historical producer.
2. Correct only proven checker defects; add independent regression fixtures.
3. Read back all 90 dataset inputs and seven exact artifacts with existing access.
4. Review the diff and receipts, run relevant checks, push this PR.

The operator approved cloud operations in advance on September 22. Use one
existing `cpu-e2/2vcpu-8gb` VM session with the prearmed watchdog: stop begins by
600 seconds, work deadline 420 seconds, target total 900 seconds (0.5 vCPU-hours,
2 GiB-hours). At most two metadata audit passes and seven artifact GETs; zero
model Jobs, new resources, permission changes or final access. If diagnosis
cannot finish in that window, retain it and stop rather than extend the session.
The local watchdog requires host/network/provider availability.


## Diagnosis and correction

All 90 discrepancies were source URIs. The exact G5 repeat-1 source location
remained registered while the selected G6 run reused identical name/digest pairs.
MLflow's [dataset store](https://github.com/mlflow/mlflow/blob/v3.3.2/mlflow/store/tracking/sqlalchemy_store.py)
reuses an existing dataset UUID by name and digest. Full artifact hashes, tags,
feature-release identity and all 90 retained input records are identical.

The [equivalence proof](../evidence/lightgbm-dataset-source-equivalence-20260922.json)
records the G5 request/training/checksum identities and canonical input-record hash.
The G5 retained result checksum inventory and collection-bound request were checked.
Supply it with `--dataset-source-proof` and `--dataset-source-proof-sha256`; the
checker binds it to the exact frozen inventory and permits only those exact source
paths. Full hashes, counts, fold membership, contexts and all other checks remain
mandatory. No historical MLflow record or frozen artifact is rewritten. Fresh
retrieval of the G5 input objects is outside this proof's availability claim.

The diagnosis session was stopped after collecting evidence. One additional
verification session uses the same per-session bounds, one metadata audit and
seven artifact GETs. Combined ceiling: two starts, 1 vCPU-hour / 4 GiB-hours at
the nominal 15-minute targets; actual duration and verified shutdown are retained.
Regression coverage rejects missing/incorrect anchors, different input records,
feature-release identity, buckets and final paths, and retains full-hash checks.


## Review and live result

The corrected live audit verified all **90 dataset inputs and seven artifacts**
(90,458 bytes), including model, training manifest, calibration, metrics, feature
importance and reliability evidence. The run metadata response hash is identical
before and after the checker correction. The existing historical run and frozen
candidate were unchanged. The independent receipt comparison rechecked every
artifact size/hash against the frozen inventory and the executed tool hashes.
See the [final receipt](../evidence/lightgbm-lineage-verification-20260922.json).

Review checked exact proof/inventory binding, full-hash rejection despite the
alternate URI, bucket/final-path rejection, unchanged transport bounds and no
remote writes. All 73 inert tests, Ruff, Markdown links and secret scanning pass.
The VM is independently confirmed stopped. This closes the selected-run tracking
step; comparison semantics, production preflight and final evaluation remain.
