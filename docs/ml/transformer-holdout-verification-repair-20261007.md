# Completed Transformer holdout — verification repair, 7 October 2026

Tracking: [Bug #345](https://github.com/khab40/lob-arena/issues/345), under
[Transformer #24](https://github.com/khab40/lob-arena/issues/24), [Project #3](https://github.com/users/khab40/projects/3).

The approved frozen-inference Job `aijob-e00gvk2fdn6cmjxvkg` completed and
published all seven result objects. The original request, immutable image,
model, calibration and operating points remain frozen. No training, selection,
LightGBM rescoring or G8 rerun occurred. Original independent readback **aborted**;
reviewed offline replay now verifies the complete declared population. The
operator research decision remains pending.

All temporary access is removed. The completed Job's grants were restored at
final version **14 / 2 rules** and results version **15 / 9 rules** after about
1,691 seconds, within the approved three-hour window. After the later one-file
recovery handoff, Nebius MCP confirmed the complete original results policy at
**17 / 9 rules**; after the corrected recovery it is **19 / 9 rules**.
The $6.25 execution reservation remains held with actual
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
elsewhere; the original final LightGBM prediction Parquet was initially missing locally.
Its pinned identity is version `1`, **931,523 bytes**, SHA-256
`05298a29c1875a26b638bda26be43d6e79e0c978818779502ee964db1f5ead9f`.
A read-only archive search found historical verification metadata, not its bytes.

The reviewed verifier repair is in [PR #346](https://github.com/khab40/lob-arena/pull/346).
The first one-file recovery proposal was approved and its grant applied, but
the helper stopped with a validation error before its exclusive collection
directory, credential lookup or S3 GET. Independent review confirmed those
boundaries. The operator removed the rule; exact original-policy restoration
was verified after **1,245.650055 seconds**, within its one-hour access bound.
That first invocation retained no baseline bytes or recovery success receipt.

The retained grant observation aged beyond its 120-second admission limit while
tool permission was pending. Local package and approval checks pass, and the
stale observation is rejected. This is consistent with the failure, but the
original helper recorded no admission stage, so its exact cause is unproven.
The corrected package records safe admission stages and requires outside-sandbox
offline permission/preflight before a new grant, then fresh readback immediately
before collection. It preserves the freshness, access, GET and spend bounds.
The restored resource version changed; the corrected package received new exact
authorization before any new grant or read.

The corrected recovery retained the exact baseline and complete input reference
with **one GET**, within 300 seconds. The operator removed the temporary rule,
with complete original-policy restoration independently verified at results19/9
after **139.547514 seconds**, within one hour. Full offline replay then verified
all **15,160 rows**, signed Job identity, seven publication objects, three input
references, frozen settings and source lineage. Separate-agent receipt review is
clear. The original failed readback and first recovery receipts remain immutable.

Verification SHA-256: `329158009e8de6b73ff7571acd414cab5cbcfcc760edd8963d61884349a81869`.
Reviewed verifier source: `da50440846d3afd05d94b93fad0a8606720d4ca9`; frozen
execution source remains `fe5eaaa931791d3c3e809a1d0c2ff8a6811dc508`.
Offline replay performs no cloud or model execution; its original publication
version receipts are reconstructed explicitly from the pinned hash chain.

Next: reviewed report and the operator research decision. No GPU replacement is required. Research
interpretation and the operator decision must precede #90/#91 demo work.
December represents only three source sessions on one date with research labels;
LightGBM previously saw this test population. No production quality or promotion
claim follows from this run. Online MLflow/platform reconciliation remains later.
