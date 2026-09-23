# G8 final authorization and verification — 2026-09-23

Tracking: [story #23](https://github.com/khab40/lob-arena/issues/23),
[Bug #222](https://github.com/khab40/lob-arena/issues/222),
[Project #3](https://github.com/users/khab40/projects/3).

As a validation engineer,
I want one authorized evaluation of the frozen C4 candidate with independent
result and lineage verification,
So that G8 records measured quality and an evidence-backed G9 disposition.

PR #219 verified the 90 dataset inputs and seven selected-run MLflow artifacts.
PR #220 is merged with all 22 checks passing. It completed the comparison audit,
verification reuse benchmark and unsigned production transport probe. These
establish preparation evidence, not final model quality or final authorization.

The [refreshed review](../../evidence/g8-final-review-20260923.json) binds source
`14a4d1a6b0931c822995224d2a5e8d657538e1e6`. Its
[independently verified transport probe](../../evidence/g8-final-transport-verification-20260923.json)
completed as `aijob-e00b762dxhnvtj2qk9`: 26 files, 13 overlays and the signed
three-hour context verified. Compute is released, the VM stopped and final key
inactive. The unsigned package was preserved by verified rename, leaving the
canonical production path free. The recurring provider mount warning remains
unexplained; actual mounts and hash readback passed.

The [exact approval proposal](../../evidence/g8-final-approval-proposal-20260923.json)
binds this review and evidence to one final evaluation. Four version-pinned secret
metadata readbacks are ACTIVE; no secret payload was retrieved. Fresh authorized
output/MLflow checks still precede final access. No final authorization is signed.

## Acceptance scenarios

```gherkin
Feature: One authorized frozen C4 evaluation
  Scenario: Reject a package that cannot launch
    Given a resource timeout other than 3600 or 10800 seconds
    When request metadata is validated before signing
    Then validation fails

  Scenario: Preserve the separate final gate
    Given an unsigned production review
    When preparation and non-final transport checks pass
    Then final-test access and evaluation remain unauthorized

  Scenario: Execute the approved replacement once
    Given fresh replacement-specific approval bound to the reviewed package
    And authenticated MLflow and unused output-intent checks pass
    And the actual Nebius Job context is verified and signed
    When the frozen candidate is evaluated
    Then exactly one scoring execution is recorded with its original lineage
    And an ambiguous submission does not cause another submission

  Scenario: Verify before closing G8
    Given retained scored evidence and completed publication
    When independent readers verify S3 bytes and MLflow artifacts and metrics
    Then the measured acceptance outcome and G9 disposition are recorded
    And a failed quality threshold is reported without tuning or rescoring
```

## Execution plan

1. Fix the remaining PR #220 timeout review finding. Resource validation,
   published schema, signed context and launcher must accept the same two
   windows. Non-final requests retain their one-hour ceiling. Run inert
   contract/schema tests locally; review and commit the repair.
2. Rebuild the unsigned review from that clean commit. Preserve the frozen
   candidate, comparison proof and R4 history. Recheck all 26 physical files,
   13 overlays and three archive hashes. Run one credential-free Nebius transport
   probe for the changed bytes, with no protected rows or model execution.
3. Prepare an exact final review: one `cpu-d3/4vcpu-16gb` Job, 100 GiB disk,
   10800-second timeout, restart `never`, existing 32 GiB filesystem and fixed
   new run `nasdaq-g8-replacement-r5-20260917`. The Job ceiling is 12 vCPU-hours
   and 48 GiB-hours; production runtime remains unproven. Spend monitoring follows
   the [operator-managed policy](../../ml/model-validation-execution-policy.md).
4. Obtain fresh replacement-final approval only after the concrete review is
   ready. Bind candidate authorization, canonical request and signed replacement
   plan; retain the separate actual-Job context. The consumed R4 approval cannot
   authorize this execution. Use a single preserved create intent.
5. Start the existing MLflow VM for staging, authenticated readiness and final
   publication. Keep it running while needed, then stop and verify it, following
   the operator-managed policy; do not reuse the ten-minute probe watchdog for a
   three-hour final Job. Check output prefix and intent using the authorized
   final identity before final reads. AccessDenied is not proof of emptiness.
6. Resolve final-key shutdown before activation. Nebius MCP safe mode excludes
   `deactivate`; the operator must run the reviewed deactivation command when
   final access/publication is complete. Retain readback showing INACTIVE.
   A concrete operator cleanup handoff is required before opening this window.
7. Submit once, verify provider resources/image/volumes and sign the actual Job
   context within the runner's five-minute wait. Retain logs and native evidence.
   Preserve sealed results on failure; any later publication-only recovery needs
   its own reviewed scope and must never score again.
8. Independently verify final S3 inventory, hashes and SUCCESS marker, same-run
   MLflow artifacts/metrics and candidate/feature/calibration lineage. Record
   actual acceptance results, stop idle compute and prepare G9 disposition.

Out of scope: training, calibration changes, hyperparameter selection, threshold
changes, tuning after final access, automatic rescoring, Git merge or deletion.
Local verification covers inert metadata and static contracts only. Runtime
checks run on Nebius. This plan grants no final-test authorization.
