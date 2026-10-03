# Transformer review repairs and execution plan — 2026-10-03

[Bug #286](https://github.com/khab40/lob-arena/issues/286), parent
[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3),
[PR #284](https://github.com/khab40/lob-arena/pull/284).

## Review repairs

As a validation engineer,
I want family discrimination and selected checkpoints verified against their evidence,
So that the comparison cannot hide false alerts or use the wrong trained epoch.

Actor: validation engineer. Goal: trustworthy research readback.
Value: prevent invalid quality conclusions before another GPU attempt.
Out of scope: startup transport repair, model execution, final-test access and promotion.
Verification: saved-artifact adversarial tests, full inert Transformer suite,
lint, review and CI. These tests neither load weights nor train a model.

Each named attack family now includes its positive targets and all shared
negative controls at threshold 0.5. Other families' positives are excluded.
Support counts and the population definition are explicit. Controls are reused,
so family totals must not be summed. Worker and reader use the same definition;
independent readback still recomputes metrics from authenticated saved predictions.
The old single-class populations also fail the calibration metric helper's
both-classes requirement, so this fixes a potential inference failure as well
as misleading family discrimination.

Trial verification now binds the selected checkpoint to the independently
derived best epoch, canonical epoch filename, exact slot object name, unique
published receipt and immutable inventory entry. Another inventoried checkpoint
cannot substitute for the selected epoch. The reader verifies bytes and receipts
without deserializing model weights.

```gherkin
Feature: Trustworthy Transformer research readback
  Scenario: Count shared control false alerts for each family
    Given positives from two attack families and shared negative controls
    When a model alerts on every target
    Then each family's precision reflects the control false alerts
    And another family's positives do not enter its population

  Scenario: Reject a substituted checkpoint
    Given verified history and predictions select epoch one
    And epoch two also has an immutable artifact receipt
    When the trial selects the epoch-two artifact
    Then independent verification rejects the trial

  Scenario: Accept a valid confirmation checkpoint
    Given a confirmation trial selects a later best epoch
    When its epoch, slot, publication receipt and inventory agree
    Then independent verification accepts the checkpoint binding
```

## Next few days

Dates below are targets in Asia/Tbilisi, conditional on repair and GPU capacity.
The [comparison decision](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md)
and existing resource bounds remain authoritative.

1. **3 October: close review repairs and unblock startup.** Verify P2 fixes in
   CI; retain the commit audit showing all existing commits below 200 changed
   lines for the P1 review disposition. Diagnose the failed smoke's publication
   readback and provider-context mismatch using retained evidence before changes.
   Prepare the corrected runtime, regression evidence and exact replacement scope;
   do not reuse the consumed request or silently increase the eight-Job allowance.
   Reconcile stale `PHASES.md` and #24 descriptions with current status.
2. **After startup repair: one replacement smoke.** Obtain applicable exact
   replacement authorization, then verify input support, CUDA behavior, the small
   real-data training run and durable artifact readback. A terminal container
   alone does not satisfy this gate. No full trial proceeds after a failed smoke.
3. **4 October target: fixed grid and seed confirmation.** Four fixed trials,
   select on S only, then seeds 7/2027 for the winning configuration. Six slots
   total at most 12 GPU-hours of configured timeouts. Verify results before
   dependent work; retain seed 42 as the candidate.
4. **5 October target: calibration and research decision.** Fit on C, choose
   operating points and compare on O, verify the complete result and record
   continue/stop/inconclusive. The combined inference/calibration slot is capped
   at one hour. Report baseline prior exposure and unmeasured baseline latency.
5. **After the decision: MLflow reconciliation and platform work.** Index the
   retained artifacts without retraining; resume #19–#21 separately. Cascade #25
   requires an explicit justified next study. G8/G9 remain closed.
