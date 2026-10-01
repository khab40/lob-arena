# Transformer metadata runtime readiness — 2026-10-01

Fixes [Bug #266](https://github.com/khab40/lob-arena/issues/266) and
[Bug #268](https://github.com/khab40/lob-arena/issues/268), children of
[Story #24](https://github.com/khab40/lob-arena/issues/24), Feature #16 / Epic #15,
in [Project #3](https://github.com/users/khab40/projects/3).

The approved amended r2 audit stopped before any GET because its execution
interpreter lacked botocore. Earlier probes substituted the S3 client and missed
that dependency. The attempt remains consumed. Operator removal restored the
original bucket policy and settings at version 140 after 240.126501 seconds.
No metadata or model result was produced by that attempt.

As a platform operator,
I want the actual metadata runtime checked before temporary access,
So that missing dependencies and runtime drift cannot escape inert unit tests.

As a platform operator,
I want preflight and collection to isolate credentials consistently,
So that ambient shell tokens cannot invalidate the pinned reader identity.

Actor: platform operator. Goal: verify the exact execution interpreter and real
S3 client before requesting a grant. Value: catch provisioning failures offline.
Out of scope: cloud retry, grants, GPU/model workloads, final access and G8/G9.
Verification: negative dependency/configuration cases, real SDK construction with
network blocked, exact-runtime CLI probe, and required SDK-enabled CI coverage.

```gherkin
Feature: Actual metadata runtime readiness
  Scenario: Missing SDK stops preflight
    Given the execution interpreter lacks the pinned S3 SDK
    When offline preflight is requested
    Then it fails before credentials or network access
    And it produces no readiness receipt or attempt marker
  Scenario: Verify the real client before access
    Given verified backend sources and pinned runtime dependencies
    When preflight constructs the real S3 client with dummy credentials and sockets blocked
    Then it records the interpreter, dependency inventory and proposal identity
    And the client has the approved endpoint, timeouts and no retries
  Scenario: Reject runtime drift
    Given a readiness receipt from another interpreter or dependency inventory
    When the approved collection is invoked
    Then it fails before credential lookup or S3 requests
  Scenario: Require preflight before the grant
    Given readiness was recorded after temporary access started
    When collection is invoked
    Then it refuses credential lookup and collection
  Scenario: Preserve a consumed attempt
    Given the earlier audit attempt is consumed
    When an offline runtime check succeeds
    Then that attempt remains blocked
  Scenario Outline: Ignore ambient credential settings
    Given the operator shell contains <setting>
    And the pinned reader lookup supplies a valid access-key pair
    When the live metadata client is constructed
    Then it retains only that pair with no session token
    And the caller environment is unchanged
    Examples:
      | setting                                 |
      | AWS_SESSION_TOKEN                       |
      | AWS_SECURITY_TOKEN                      |
      | both session token variables            |
      | an invalid AWS_PROFILE                  |
      | an invalid AWS_CREDENTIAL_EXPIRATION     |
  Scenario: Preserve the environment after a failure
    Given the operator has an existing shell environment
    When credential lookup or client construction fails
    Then the shell environment is unchanged
    And no S3 request occurs
```

## Repair and execution order

The same SHA-bound operator now supports `preflight` instead of a phase number.
It verifies proposal/script/backend pins, loads the actual collector and client,
checks the proposal's exact Python/dependency versions and constructs the real
S3 client. Dummy credentials replace the environment temporarily; socket and
subprocess calls are blocked. The client is closed and the environment restored
on success or failure. The retry check uses `total_max_attempts=1`, which
[Botocore defines as no retry](https://docs.aws.amazon.com/botocore/latest/reference/config.html);
the SDK may also populate its default retry mode. This path neither obtains real credentials nor calls S3.

`runtime-readiness.json` binds the proposal, script and backend tree to the
interpreter path, environment prefix, Python version and complete installed
package inventory. Before each live phase, the operator requires that receipt
predate the grant, repeats real-client readiness and compares the runtime.
Failures still obey the exclusive attempt marker and cleanup rule.

Both preflight and live client construction use the same cleared, temporary
credential environment. Live lookups collect the two pinned values locally and
validate the reader identity before entering it. The constructed client retains
the static pair after the caller environment is restored; ambient session tokens,
profiles and credential expiration cannot alter that pair. This operator is a
single-process, sequential command; the temporary environment is process-global.

1. Provision a dedicated operator environment from the existing
   `serverless/transformer_inputs/requirements.txt`; do not assume the backend
   development environment has cloud dependencies.
2. Stage the verified backend snapshot, SHA-bound script and exact proposal in
   its fresh output directory. Verify retained input evidence before access.
3. Run `PYTHON -B SCRIPT PROPOSAL_SHA ROOT OUTPUT preflight` using the exact Python
   executable intended for collection. Require success and inspect the receipt
   before preparing or requesting any operator policy handoff.
4. After exact replacement approval, verify the applied policy through Nebius
   MCP. Run the same executable/script/proposal with phase `1` or `2`.
5. After success or any abort, complete the approved policy replacement/removal
   and independent readback. Never clear attempt markers or reuse an old approval.

Use `python -m pytest` for SDK-enabled tests so the selected Python environment,
not a launcher with a different interpreter, supplies the dependencies.

## Checks that prevent recurrence

Inert tests retain namespace, origin, credential and one-attempt coverage.
Separate tests exercise missing dependencies, wrong versions, wrong transport
settings, blocked network/process access and environment restoration. A required
CI step installs the pinned verifier requirements and runs the **real** client
construction test; that step cannot silently skip a missing SDK.
It also exercises real live-client construction with dummy lookup responses,
both token aliases, profile/expiration contamination and a clean control. No
network or external credential command is permitted in these tests.

The actual operator environment is also exercised offline against the complete
frozen backend. Passing unit tests alone is not evidence that a cloud interpreter
is ready. A new replacement proposal and exact approval remain necessary; this
repair does not authorize another audit attempt.

Validation evidence: [runtime checks](../evidence/transformer-runtime-preflight-20261001.json)
and [r2 abort cleanup](../evidence/transformer-lineage-runtime-abort-20261001.json).
The [r3 replacement proposal](../evidence/transformer-lineage-replacement-r3-proposal-20261001.json)
is prepared for review, not execution. Its exact Python executable is included
in the proposal and enforced by preflight and execution.
