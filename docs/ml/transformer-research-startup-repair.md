# Transformer startup repair and replacement — 2026-10-03

[Bug #287](https://github.com/khab40/lob-arena/issues/287), child of
[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).
The implementation starts from merged PR #284 (`585b1bc`); its P2 repairs remain.

As a platform operator,
I want the startup handshake to accept equivalent provider metadata while checking exact bytes and resources,
So that the bounded GPU experiment can reach input validation and training.

Actor: platform operator. Goal: fix startup and prepare a replacement for review.
Value: reach the Transformer comparison. Out of scope: launching during repair,
new access, final data, promotion, platform maintenance and G8/G9.

```gherkin
Feature: Verified research startup
  Scenario: Verify case-equivalent metadata
    Given a versioned object whose bytes match its receipt
    When the provider names its checksum metadata Sha256
    Then artifact verification succeeds

  Scenario: Reject missing or ambiguous checksums
    Given missing, incorrect or duplicate checksum metadata
    When the artifact is read
    Then verification fails without retrying publication

  Scenario: Sign only the requested pricing model
    Given an exact on-demand research request
    When the observed provider specification is checked
    Then matching on-demand pricing is accepted
    But missing or preemptible pricing is rejected

  Scenario: Preserve a failed attempt
    Given an existing or unverifiable publication prefix
    When the worker tries to claim that prefix
    Then it stops without any follow-up publication
    And a replacement requires a distinct reviewed request
```

## Diagnosis and repair

One HEAD and one bounded, versioned GET proved that the old INTENT was saved
correctly: version `1`, 1,598 bytes, exact authorized request checksum. Nebius
returned SDK metadata key `Sha256`; the old reader required `sha256`. The checksum
was present, not missing. The provider also returned `pricing_model.on_demand`,
which the expected specification omitted. The strict context comparison would
therefore have rejected the Job after publication was repaired.
[Retained forensic fixture](../evidence/transformer-research-startup-diagnosis-20261003.json).

The reader accepts checksum-key casing only; missing, wrong and ambiguous values
still fail. Version, length and actual-byte verification remain mandatory.
Expected resources now include explicit on-demand pricing. Safe diagnostics show
the stage and exception types without exposing exception text. A failed claim
cannot publish into an occupied or unverified prefix. The new campaign uses
`transformer-research-c4-20261003-r2`; the consumed r1 evidence is unchanged.

Verification: 781 inert Transformer tests, Ruff and diff checks passed. Tests
replay the actual provider spec and mixed-case SDK response through claim,
operator signing and worker context verification. The sealed linux/amd64 image
passed dependency/baseline checks; all 56 Transformer Python files match source
`87ce8a933c40fe825569e3de6a8699b519808c34`. The published child digest is
`sha256:b713f1ffeb3c2ba5e4ab09dd2cdb829c6d659a915dd140a113bcabdf6c1909d9`.
Later documentation commits do not change this runtime source.

The exact provider dry-run passed without creating a resource. Live read-only
preflight found the name and prefix unused at 14:26:26 UTC.
[Readiness receipt](../evidence/transformer-startup-readiness-20261003.json).
Neither inert tests nor dry-run prove CUDA execution or a model-quality result.

## Exact replacement proposal

P2 follow-up [Bug #289](https://github.com/khab40/lob-arena/issues/289) corrects
terminal publication diagnostics: failures in `result.json` or `SUCCESS`
publication now report `publication`, preserving any committed object without
retry or another marker. Four injected PUT/readback faults reproduced the wrong
`preflight` stage before the repair; the successful completion control passed.
All five regression cases now pass; no model runs locally.
[Regression receipt](../evidence/transformer-publication-p2-regression-20261003.json).
The unexecuted proposal starting `f86cdb69` is superseded by the hash below.

[Proposal JSON](../evidence/transformer-replacement-smoke-proposal-20261003.json),
SHA-256 `be433e78cd6dc731b6e143bd29f05e07622a5338ad7a6c8f585641f68e2cecd1`.
It binds the source, immutable image, exact request, configuration and command.
Approval is pending. This proposes one smoke Job: one L40S, 8 vCPU, 32 GiB RAM,
100 GiB disk, 1 GiB shared memory, one hour, restart never, concurrency one.
It checks governed inputs, CUDA behavior and a 1,024-row/two-epoch training smoke.
Grid, seed and comparison Jobs are not authorized by this proposal.

The original eight-slot/14-timeout-hour plan has consumed one failed smoke.
One replacement adds one submission and one timeout-hour; completing all later
slots would total nine submissions/15 timeout-hours, including the failed Job.
These are timeout allocations, not measured GPU use or a billing cap.
The published L40S starting rate is $1.55/GPU-hour; an hour at that starting rate
is $1.55 before provisioning, storage and taxes. Exact cost remains unknown under
the existing operator-managed policy. [Price source](https://nebius.com/prices).

## Execution handoff after approval

1. Require review and green CI for the latest PR head, then record approval of the
   exact proposal hash. Recheck image digest, request and bound-file hashes.
2. Use the pinned root operator venv and this runtime's `PYTHONPATH`. Run
   `transformer_research_operator.py preflight` again with evidence directory
   `outputs/transformer-startup-repair-20261003/p2/execution` and slot `smoke`.
3. Start the same helper's `attest` action before the single create command in
   the proposal. It waits for the worker INTENT, rechecks the provider, and signs
   the exact context. Keep the attester running during provisioning; retain its
   result and the returned Job identity in the root evidence directory.
4. Poll bounded status/log snapshots. Do not resubmit on failures or uncertain
   writes. Preserve the original and replacement evidence independently.
5. Require provider state COMPLETED. Save the unique worker log record's
   `success_object` value to `execution/smoke/success-receipt.json`. This is a
   receipt to verify, not a trusted success assertion. If missing or ambiguous,
   stop and reconcile the publication by version before proceeding.
6. Run helper `collect` for the same evidence/slot, with `--bundle` set to root
   `outputs/transformer-role-provenance-20260928/cpu-role-audit-evidence-20260929.json`
   and `--source-receipt` set to this checkout's
   `docs/evidence/transformer-source-separation-receipt-20261002.json`.
   Its hash is bound in the request. Collection rechecks terminal context and pinned object bytes,
   validates the smoke result, and retains `verification.json` and artifacts.
   Only verified success can unlock preparation of dependent slots.

All model execution remains on Nebius. MLflow reconciliation remains a later
step from retained artifacts; no training rerun is required to restore tracking.
