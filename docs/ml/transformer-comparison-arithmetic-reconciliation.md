# Comparison arithmetic reconciliation — 5 October 2026

[Bug #317](https://github.com/khab40/lob-arena/issues/317),
[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).

As a validation engineer,
I want saved metrics checked within a narrowly bounded float64 allowance,
So that different CPU reduction orders do not reject equivalent arithmetic.

The approved r2 Job completed and published its immutable result. Original
readback rejected raw O log loss: worker `0.0005067766777381927`, local
`0.0005067766777381926`. This is one float64 ULP (`1.0842021724855044e-19`).
Every other comparison and family value reproduced exactly. The original
failure and numeric difference remain in the root execution evidence.

The corrected checker permits at most eight ULPs of the independently computed
value, only for log loss, Brier score, expected calibration error, bin mean
probability and log-loss delta. It has no absolute tolerance floor. Structure,
types, counts, flags, thresholds, precision/recall/F1, average precision and all
lineage, signatures and artifact checksums remain exact. Nonfinite values fail.
The result is never changed to match the independent calculation.

Actor: validation engineer. Goal: equivalent saved arithmetic without weakening
decisions. Value: reproducible independent verification across architectures.
Out of scope: model execution, fitting, image changes, full cloud recollection,
new Job, final access or promotion. Verification: real one-ULP snapshot,
eight/nine-ULP boundary tests, strict decision/tampering tests and CI.

```gherkin
Feature: Independently verify saved comparison arithmetic
  Scenario: Accept equivalent float64 reductions
    Given exact artifact identities, target rows, counts and thresholds
    And a named aggregate differs by at most eight float64 ULPs
    When independent arithmetic is checked
    Then verification accepts the aggregate without changing the saved result
  Scenario: Reject altered decisions
    Given a changed threshold, count, flag or nonfinite aggregate
    When the result is independently checked
    Then verification rejects it
```

Reconciliation retains the original collection failure. Two version-pinned
publication metadata GETs recover SUCCESS and its checksums manifest; full
artifact verification then uses already-fetched local bytes and the seven fixed,
previously verified prerequisite inventories. The corrected verifier source is
bound separately in the reconciliation receipt. This is a post-run verifier
repair; the approved GPU image, source, request and published artifacts stay intact.
