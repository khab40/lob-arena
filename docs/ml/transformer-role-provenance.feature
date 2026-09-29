Feature: Frozen Transformer validation provenance
  As a validation engineer,
  I want preparation and checkpoint metadata bound to frozen C4,
  So that unrelated metadata cannot justify independent validation roles.

  Scenario: Verify the complete validation metadata chain
    Given the frozen development manifests and all 29 authorized metadata objects
    When provenance metadata is verified
    Then all 30 validation replay domains match the frozen shard inventory
    And normalized source identities and object versions are retained

  Scenario: Reject an altered or incomplete chain
    Given missing metadata or a changed checksum, source identity or replay domain
    When provenance metadata is verified
    Then verification fails without reading sequence or event payloads

  Scenario: Reject a reference outside the approved metadata keys
    Given preparation metadata that references another date, bucket or checkpoint
    When the metadata collector validates the reference inventory
    Then it rejects the inventory before fetching any referenced checkpoint

  Scenario: Enforce bounded metadata access
    Given denied access or metadata exceeding the reviewed byte or time limit
    When the collector reads the exact metadata inventory
    Then collection fails and retains receipts for completed reads
    And no permission changes or automatic retries occur

  Scenario: Keep source separation as a separate proof
    Given a complete and checksum-valid metadata chain
    When the provenance report is produced
    Then source observation and label horizon separation remain unverified
    And GPU readiness remains false

  Scenario: Reuse verified evidence after temporary access removal
    Given the retained metadata receipts, frozen manifests and train-only normalizer
    When the CPU audit evidence bundle is prepared offline
    Then its bytes are deterministic and every included file is checksum-bound
    And metadata access is not reopened
    And source separation and execution authorization remain unverified

  Scenario: Reject changed audit evidence
    Given a missing, altered, extra or oversized evidence file
    When the CPU audit evidence bundle is verified
    Then verification fails before any payload read or cloud operation

  Scenario: Preserve an existing audit bundle
    Given an existing bundle at the requested destination
    When another bundle is prepared at that destination
    Then preparation fails and the existing bytes remain unchanged

  Scenario: Respect provider policy limits without broadening the grant
    Given 29 approved metadata keys and two existing bucket policy rules
    When the operator handoff policy is prepared
    Then three temporary rules contain 10, 10 and 9 paths
    And the same principal receives the same role on exactly the approved keys
    And both existing rules remain unchanged

  Scenario: Reject insufficient policy capacity
    Given existing rules leave insufficient capacity for the temporary grant
    When the operator handoff policy is prepared
    Then preparation fails before any cloud update

  Scenario: Preserve concurrent policy changes during removal
    Given the three exact temporary rules and unrelated current rules
    When the removal policy is prepared
    Then only the temporary rules are removed
    And unrelated current rules remain unchanged
