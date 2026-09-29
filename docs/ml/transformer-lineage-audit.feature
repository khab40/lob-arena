Feature: Frozen validation metadata authentication

  Scenario: Verify a historical request without a later optional field
    Given a frozen C3 request whose producer did not emit the optional MLflow URI
    And its retained bytes match the frozen checkpoint binding
    When the current verifier checks the request
    Then the original binding is accepted without adding fields to the hashed record

  Scenario: Authenticate both bounded metadata phases
    Given the verified frozen CPU evidence bundle
    And operator approval for the exact two-phase metadata proposal
    When the authorized metadata collection completes
    Then 58 phase-one objects and 57 phase-two objects have version and checksum receipts
    And every requested member matches an authenticated frozen checkpoint inventory
    And source separation and GPU readiness remain unverified

  Scenario: Reject changed metadata before reading further objects
    Given an approved metadata phase
    When a request, inventory or member differs from its frozen binding
    Then collection stops at that object
    And no successful verification receipt is published

  Scenario: Reverify retained evidence before phase two
    Given phase-one metadata has been collected
    When retained phase-one metadata or its verification receipt has changed
    Then phase two rejects the evidence before any cloud read

  Scenario: Preserve unrelated permissions during phase replacement and removal
    Given the exact active temporary grant and unrelated existing rules
    When the next policy transition is rendered
    Then only the active phase rules are replaced or removed
    And the resulting policy respects the provider rule and path limits

  Scenario: Reject an ambiguous or oversized policy transition
    Given a partial, changed or duplicate temporary grant or insufficient policy capacity
    When a transition is requested
    Then no replacement policy is emitted
