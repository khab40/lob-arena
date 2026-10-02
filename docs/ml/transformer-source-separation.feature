Feature: Frozen C4 source-domain separation
  As a validation engineer,
  I want observations and labels confined to complete development roles,
  So that selection, calibration and operating-point selection cannot reuse them.

  Scenario: Keep whole instrument ancestry in one role
    Given authenticated C4 metadata and the reviewed instrument-local producer
    And the predeclared selection, calibration and operating-point roles
    When source separation is verified
    Then all ten replays of each instrument remain in one role
    And its source ancestry includes book state before the requested output interval
    And all thirty validation runs and 9210 supervised rows are covered

  Scenario: Keep pointwise labels in their replay domain
    Given authenticated controls with no synthetic label windows
    And authenticated hybrids with one supported inclusive producer tick window each
    When label domains are verified
    Then all twenty-seven synthetic windows remain in their instrument roles
    And no absolute label timestamps are inferred from tick coordinates
    And negative labels retain the research-control assumption

  Scenario: Reject a divided source domain
    Given a role assignment that divides one instrument's replay variants
    When source separation is verified
    Then no success receipt is published

  Scenario: Reject incomplete run coverage
    Given missing, duplicated or unexpected validation runs
    When source separation is verified
    Then no success receipt is published

  Scenario: Reject a changed producer contract
    Given a producer identity or normalized source filter outside the reviewed contract
    When source separation is verified
    Then no success receipt is published

  Scenario: Reject unsupported label semantics
    Given a label with timestamp bounds, future-horizon fields or unsupported tick bounds
    When label domains are verified
    Then no success receipt is published

  Scenario: Authenticate retained evidence before making separation claims
    Given retained metadata that differs from its frozen authenticated bindings
    When offline source separation is requested
    Then verification fails before a success receipt is published
    And no cloud data or model execution is requested

  Scenario: Preserve an existing receipt
    Given an existing output receipt
    When offline source separation is requested at that output path
    Then the existing bytes remain unchanged
    And the request fails

  Scenario: Preserve the limits of a successful source proof
    Given a successful instrument-domain separation proof
    When the receipt is produced
    Then shared trading time and unproven statistical independence are reported
    And payload observation identities are not claimed to have been reenumerated
    And class support and GPU readiness remain unverified
    And CPU and GPU execution remain unauthorized
