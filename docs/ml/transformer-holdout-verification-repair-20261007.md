# Completed Transformer holdout — verification repair, 7 October 2026

Tracking: [Bug #345](https://github.com/khab40/lob-arena/issues/345), under
[Transformer #24](https://github.com/khab40/lob-arena/issues/24), [Project #3](https://github.com/users/khab40/projects/3).

The approved frozen-inference Job `aijob-e00gvk2fdn6cmjxvkg` completed and
published all seven result objects. The original request, immutable image,
model, calibration and operating points remain frozen. No training, selection,
LightGBM rescoring or G8 rerun occurred. Independent readback **aborted**;
there is no passing verification receipt or research decision yet.

All temporary access is removed. Nebius MCP independently confirmed the complete
original policies at final version **14 / 2 rules** and results version
**15 / 9 rules**. Each grant lasted about 1,691 seconds, within the approved
three-hour window. The $6.25 execution reservation remains held with actual
billing unreconciled. Earlier dated execution snapshots describe their then-current
state; the prior observer attempt and access overrun remain disclosed.

As a validation engineer,
I want completed frozen holdout outputs to remain independently verifiable,
So that harmless platform rounding does not require another model run.

```gherkin
Feature: Recoverable frozen holdout verification

  Scenario: Verify equivalent calibration across machines
    Given published probabilities differ by at most one float64 ULP from frozen calibration
    And decisions, stable ranking, ties and reliability bins are unchanged
    When independent readback recomputes metrics from those verified probabilities
    Then the existing eight-ULP reduction bound remains enforced

  Scenario: Reject a changed publication
    Given a saved holdout publication
    When a probability exceeds one ULP or changes a decision, ranking, tie or bin
    Then independent readback rejects it

  Scenario: Replay an interrupted verification without cloud access
    Given verified publication objects and exact input responses were retained
    When offline readback is requested
    Then every byte hash, size and original version is checked
    And no cloud or model client is called
```

Diagnosis found **602 / 15,160** published probabilities differing from macOS
recalculation by exactly one float64 ULP. All frozen decisions, rankings, ties
and reliability bins stayed identical. Nevertheless, recalculating probabilities
before reducing metrics amplified input rounding to 57 ULP in one family log
loss and 10 ULP in its Brier score. Increasing the aggregate tolerance would
weaken the wrong check.

The repair checks each saved probability against independent calibration,
accepting at most one adjacent float64 value with exact discrete behavior.
Metrics and paired bootstrap then use those verified published probabilities.
The existing eight-ULP reduction policy remains unchanged. Runtime callers
without published probabilities retain their original calculation.

The read-only retention store saves verified responses immediately, including
the three verifier inputs and each publication's original version receipt.
An offline store checks exact references, size, SHA, version and path containment;
it cannot publish, claim an execution or call S3. Inert tests cover a failed
full declared-population verification followed by offline replay, changed versions,
bytes, probability boundaries and symlink paths. Reviews and corrections are
retained in root `outputs/transformer-holdout-verifier-repair-20261007/`.

Seven actual published outputs remain under root
`outputs/transformer-holdout-first-run-recovery-20261007/collected/`.
The original collector fetched three verifier inputs but kept their responses
only in memory. The development reference and final manifest are retained
elsewhere; the original final LightGBM prediction Parquet is missing locally.
Its pinned identity is version `1`, **931,523 bytes**, SHA-256
`05298a29c1875a26b638bda26be43d6e79e0c978818779502ee964db1f5ead9f`.
A read-only archive search found historical verification metadata, not its bytes.

Next: independently review the repairs, obtain separate authorization to recover
that one exact saved prediction object, remove its temporary grant, then complete
offline verification and the report. No GPU replacement is required. Research
interpretation and the operator decision must precede #90/#91 demo work.
December represents only three source sessions on one date with research labels;
LightGBM previously saw this test population. No production quality or promotion
claim follows from this run. Online MLflow/platform reconciliation remains later.
