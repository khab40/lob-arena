# Coordinated Transformer holdout admission

Tracking: [Bug #339](https://github.com/khab40/lob-arena/issues/339) under
[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).

As a validation engineer,
I want first-Job submission and supervision to share one local process,
So that tool dispatch cannot exhaust the admission window before submission.

The original 6 October observer-only attempt expired before creation. Its
proposal, 23 absent observations and no-creation reconciliation remain immutable.
Restore its temporary policies after the abort. A corrected package needs fresh
exact recovery authorization and a separate evidence directory; it still proposes
the first GPU holdout evaluation, with unchanged numerical inputs and image.

```gherkin
Feature: Coordinated first holdout admission

  Scenario: Create immediately after verified absence
    Given an exactly authorized recovery attempt with verified policies
    And no attempt receipt exists in its execution directory
    When supervision verifies the approved Job identity is absent
    Then one durable creation intent is retained before submission
    And submission runs in the same process with observation time reserved

  Scenario: Reconcile uncertain creation
    Given the one submission outcome is uncertain
    When the approved Job becomes visible
    Then its exact provider identity and specification are verified
    And context is delivered at most once without another creation

  Scenario: Refuse an existing Job
    Given the approved Job identity is already present before admission
    When coordinated submission starts
    Then no creation or context delivery occurs
    And the existing Job is not cancelled
```

The supervision adapter's optional admission callback executes only after its
first absent observation. It rejects an existing Job and admission time at or
below 30 seconds; the callback must retain a durable exclusive intent and bound
creation to the remaining admission time minus the 30-second observation reserve.
Ambiguity consumes the attempt. Existing ownership checks, one context delivery,
the two-hour accounting bound and cancellation reserve remain unchanged.

The coordinated CLI wiring and corrected exact package are pending. No runtime
authorization is granted by this document, and aborted attempt receipts must
never be renamed or removed to restart an unchanged package.
