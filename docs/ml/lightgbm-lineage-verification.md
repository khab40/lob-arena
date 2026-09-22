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
