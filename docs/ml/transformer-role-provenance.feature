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
