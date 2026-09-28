Feature: Bounded governed Transformer development
  As a detector developer,
  I want reproducible GPU training and a verified research candidate,
  So that I can assess sequence modeling against the frozen LightGBM baseline.

  Scenario: Reject overlapping validation roles before GPU execution
    Given selection and calibration rows share a base source session or observations
    When the development role audit runs
    Then the campaign is blocked before a GPU Job is submitted
    And no automatic reassignment or shared-role fallback occurs

  Scenario: Reject insufficient calibration support
    Given a role has fewer than 20 positive or 20 negative targets
    When the role manifest is verified
    Then training is blocked pending a reviewed development protocol

  Scenario: Preserve causal predictions under padding perturbation
    Given a valid target window and the frozen normalizer
    When padded or causally forbidden input positions are changed
    Then the target logit remains unchanged within absolute tolerance 0.000001
    And valid query outputs remain finite

  Scenario: Reject a window with no valid target
    Given a window whose steps are all padded
    When the classifier input is verified
    Then the window is rejected before scoring

  Scenario: Select without calibration or operating-point labels
    Given four complete verified seed-42 trials and sealed selection roles
    When a configuration and epoch are selected
    Then only selection-role loss determines their ranking
    And calibration and operating-point labels do not influence training choices

  Scenario: Refuse selection from an incomplete matrix
    Given one of the four trials failed or has unverifiable artifacts
    When campaign selection is requested
    Then no successful candidate selection is recorded
    And the failed trial retains its consumed Job slot

  Scenario: Resume the exact training state
    Given a verified checkpoint and an identical pinned runtime
    When the smoke test resumes the next training step
    Then state and logits match the uninterrupted reference within absolute tolerance 0.000001
    And altered data or configuration bindings are rejected

  Scenario: Preserve the declared seed candidate
    Given verified selected-configuration runs at seeds 42, 7 and 2027
    When stability is assessed
    Then loss and fixed-threshold F1 ranges are reported against declared limits
    And seed 42 remains the candidate if both limits pass
    And a failed limit prevents freeze without extra trials

  Scenario: Fit calibration separately from threshold selection
    Given a frozen checkpoint and versioned logits with exact role identities
    When temperature calibration and operating points are computed
    Then temperature fitting uses calibration rows only
    And thresholds use operating-point rows only
    And threshold metrics are labeled as development selection results

  Scenario: Preserve an unattainable operating requirement
    Given no threshold attains a required precision or recall floor
    When operating points are selected
    Then freeze fails with the unmet floor recorded
    And no lower floor is substituted

  Scenario: Recover tracking without executing a model again
    Given sealed artifacts and interrupted MLflow publication
    When the same run is reconciled from its event journal
    Then artifact hashes and metric steps are checked before missing records are written
    And no training or scoring Job is launched
    And conflicting or ambiguous records block completion

  Scenario: Register only an independently verified package
    Given versioned weights, preprocessing, calibration, thresholds and configuration
    When independent S3 and authenticated MLflow readback succeeds
    Then registration binds verified identities to one research model version
    And any research alias change has a before-and-after receipt
    And no production alias is changed

  Scenario: Enforce the finite campaign
    Given a ledger capped at eight GPU and two CPU Jobs with concurrency one
    When a stage fails or consumes its finite provider timeout
    Then its slot remains consumed and terminal evidence is retained
    And no replacement or automatic restart occurs
    And worker and ephemeral disk release are independently checked

  Scenario: Keep development approval separate from final evaluation
    Given approval for the bounded development campaign
    When its data access and completion claim are audited
    Then no final-test objects were read
    And G8 and G9 remain closed with frozen evidence unchanged
    And untouched future evaluation requires a separate protocol and authorization
