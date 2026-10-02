Feature: Bounded Transformer role audit

  Scenario: Bind the frozen evidence before accessing payloads
    Given the reviewed bundle and source receipt checksums
    When either evidence file changes
    Then the worker rejects it before any governed payload request

  Scenario: Preserve exact validation coverage
    Given the predeclared validation roles and verified C4 adapter
    When the audit records validation targets
    Then each target occurs once in its frozen run and order
    And each role reports its positive and negative counts

  Scenario: Independently verify class support
    Given the restricted target ledger and bound metadata
    When independent readback recomputes the audit
    Then changed aggregates or reordered targets are rejected

  Scenario: Retain inadequate support without changing roles
    Given a role with fewer than twenty rows of either class
    When the audit completes
    Then the published audit reports insufficient support
    And the role assignment remains unchanged
    And GPU readiness remains false

  Scenario: Bind the actual bounded CPU Job
    Given an execution request with frozen resources and identities
    When provider readback differs from the request
    Then the publisher refuses to sign an execution context

  Scenario: Reject a stale or changed execution intent
    Given an intent older than the allowed delivery window
    When the publisher checks its exact object version
    Then no execution context is published

  Scenario: Preserve the enclosing deadline
    Given a phase running inside the Job processing deadline
    When the phase requests a longer timeout
    Then the enclosing deadline still ends processing at its original time

  Scenario: Refuse ambiguous publication retries
    Given a result write whose provider outcome is unknown
    When publication stops
    Then no automatic retry or later failure marker is written
    And the attempt requires independent readback

  Scenario: Verify all published versions
    Given a completion hash from the provider Job log
    When independent readback collects the result
    Then missing versions and changed bytes are rejected
    And all row aggregates are independently recomputed
