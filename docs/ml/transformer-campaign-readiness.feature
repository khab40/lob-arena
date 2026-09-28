Feature: Transformer campaign readiness
  As a validation engineer,
  I want immutable campaign settings and audited development roles,
  So that training cannot proceed on unsupported or overlapping evidence.

  Scenario: Reject an enlarged campaign despite a matching file checksum
    Given a configuration with extra trials or a larger resource envelope
    When the reviewed campaign configuration is loaded
    Then it is rejected even if its file checksum matches the supplied checksum

  Scenario: Keep source aliases together
    Given multiple replay sessions identify the same base source domain
    When validation roles are assigned
    Then the aliases receive one role
    And input enumeration order does not change the assignment

  Scenario: Distinguish metadata from payload verification
    Given checksum-bound C4 manifests without a completed label audit
    When the role metadata is prepared
    Then row inventories and source-group assignments are reported
    And payload verification and GPU readiness remain pending

  Scenario: Audit exact validation row coverage
    Given verified development windows and an immutable role assignment
    When class support is audited
    Then missing, duplicate, extra or final-test rows are rejected
    And each role must have at least 20 positive and 20 negative targets

  Scenario: Avoid treating separate row IDs as independent source evidence
    Given a successful class-support audit without source-provenance verification
    When its readiness result is produced
    Then GPU readiness remains false
    And the missing provenance and platform evidence is named
