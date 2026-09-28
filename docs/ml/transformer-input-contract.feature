Feature: Verified Transformer input contract

  Scenario: Reuse a governed sequence release
    Given matching development tabular and sequence manifests from the frozen C4 release
    When the input adapter verifies the release
    Then the contract binds the exact manifests and feature-release ID and hash
    And each retained target appears once in the baseline row order

  Scenario: Reject a future observation even when timestamps tie
    Given an active history containing a source sequence later than its target
    And both rows have the same timestamp
    When the history is verified
    Then the adapter rejects the history before emitting model inputs

  Scenario Outline: Reject an invalid sequence
    Given a governed fixture with <defect>
    When the adapter verifies the fixture
    Then it rejects the fixture before emitting model inputs

    Examples:
      | defect                                      |
      | a timestamp later than the target cutoff    |
      | a non-boolean mask or an internal mask hole  |
      | nonzero values or identifiers in padding    |
      | a wrong feature dimension or altered value  |
      | history from another replay domain or fold  |
      | a duplicated, missing or reordered target   |
      | an infinite feature value                   |

  Scenario: Distinguish real zero, missingness and padding
    Given one observed zero, one missing feature and one padded step
    When the adapter transforms the sequence
    Then the output values are finite
    And missingness is true only for the missing feature on the real step
    And padding is zero and excluded by the valid-step mask

  Scenario: Prevent attention to padding and later positions
    Given a left-padded sequence with several active steps
    When causal attention permissions are constructed
    Then an active query can attend only to active keys at or before its position

  Scenario: Fit each training observation once
    Given overlapping windows containing the same training rows
    When normalization is fitted
    Then observed counts and statistics equal fitting the unique training rows once

  Scenario: Keep validation data out of normalization
    Given a fitted training normalizer and a validation projection
    When validation values and labels are changed
    Then the normalizer bytes and fitting-row digest remain unchanged

  Scenario: Handle constant and wholly missing training features
    Given a constant training feature and a feature missing from every training row
    When their normalization artifact is saved and reloaded
    Then scale 1 and explicit observed counts are preserved
    And transformations remain finite with missingness preserved

  Scenario: Exclude labels from input values
    Given identical source features and row identities with changed target labels
    When both fixtures are transformed
    Then their input values and masks are identical
    And labels remain separate target metadata

  Scenario: Reject final-test access in development
    Given a final-test manifest and a development-mode adapter
    When the adapter is opened
    Then it rejects the manifest before reading any final-test shard

  Scenario: Preserve outputs across batch boundaries
    Given identical verified inputs and a frozen normalization artifact
    When the adapter uses different batch sizes
    Then ordered target IDs and logical output digests match exactly

  Scenario: Reject a changed normalization artifact
    Given a normalization artifact whose statistics or lineage binding were changed
    When the adapter loads it against the expected checksum
    Then it rejects the artifact before emitting model inputs
