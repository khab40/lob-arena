Feature: Governed Transformer development-input verification

  Scenario: Consume the exact approved development release
    Given an approved inventory of development object versions and checksums
    When the verification Job downloads its inputs
    Then each downloaded object matches its approved identity and size
    And no unlisted or final-test object is read

  Scenario: Verify the complete development row population
    Given the frozen 90 tabular and sequence shard pairs
    When all governed inputs pass the consumer contract
    Then 33450 training rows and 9210 validation rows are consumed exactly once per pass
    And each shard matches its approved ordered target identity digest

  Scenario: Preserve preprocessing across batch sizes
    Given the same approved inputs in three fresh verification processes
    When batch sizes 16, 64 and 256 are used
    Then normalization artifact bytes and logical output digests match
    And separate timing and peak-memory measurements are recorded

  Scenario: Reject a changed input before successful publication
    Given an input whose version, checksum, scope or causal content differs from the approved contract
    When verification is attempted
    Then the Job fails without publishing a success marker
    And bounded failure evidence is retained

  Scenario: Preserve an existing output package
    Given an object already exists at the proposed run output prefix
    When execution preflight checks the destination
    Then the new execution is rejected without overwriting any object

  Scenario: Bound execution and prevent an automatic rerun
    Given one submitted input-verification Job with restart policy never
    When it fails or exceeds its finite provider timeout
    Then terminal state and available diagnostics are retained
    And another Job requires review of the failure

  Scenario: Independently verify a completed package
    Given a completed Job with a published result package
    When an independent reader downloads and verifies its artifacts
    Then the saved configuration and normalizer match their published checksums
    And the result binds the exact code, image, inputs and Job identity

  Scenario: Deliver signed context without an interactive handoff
    Given an armed publisher bound to the reviewed request
    When the exact provider Job publishes its matching intent
    Then signed context is published within the startup window
    And no additional interactive step is required

  Scenario: Reject late context delivery
    Given a terminal Job or an intent at least 240 seconds old
    When signed context delivery is attempted
    Then no context object is written

  Scenario: Diagnose a startup timeout before input access
    Given a Job that has not received its signed context
    When the startup deadline expires
    Then the failure record identifies the context stage
    And no governed input is downloaded
