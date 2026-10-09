# Replacement confirmations — 4 October 2026

Historical plan/execution record; reconciled 8 October 2026. Both replacement confirmations completed and three-seed stability passed.
[Current status](../roadmap/CURRENT_STATUS.md) owns remaining acceptance.
[ARD-0042](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md) owns research ordering;
pending instructions below do not authorize another run or reuse consumed approval.

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).
PR #307 merged as `6a61a6f`; its 25 checks passed. This package prepares the
replacement requested after that merge. **Execution awaits exact approval.**
No Job or signed context was created during preparation.

As a researcher,
I want two fresh confirmations of the selected Transformer with preserved lineage,
So that I can measure seed stability without repeating the grid or losing failures.

Actor: researcher/platform operator. Goal: seeds 7 then 2027, width 128/rate 0.0003.
Value: a bounded, independently verified stability decision.
Out of scope: further search, calibration, inference, final access, IAM changes,
promotion, merge and deletion. Verification: inert tests, image equivalence,
provider dry-runs, reviewed package hashes and later independent result readback.

```gherkin
Feature: Replacement Transformer confirmations
  Scenario: Preserve consumed execution evidence
    Given the previous seed-7 Job failed before training
    When replacement requests are prepared
    Then they use a fresh fixed namespace
    And the failed Job and its evidence remain unchanged

  Scenario: Verify the exact historical prerequisites
    Given the five smoke and grid receipts match their immutable references
    When a replacement verifies those publications
    Then their original source, image, signature and artifact hashes must match
    And any additional or changed prerequisite is rejected

  Scenario: Require a working attester before submission
    Given the attester matches the reviewed request and signing custody
    When readiness and a successful absent-Job poll are observed
    Then submission requires a fresh heartbeat and both live process identities
    And a failed or uncertain attempt stops the sequence without resubmission
```

## Sealed package

[Proposal](../evidence/transformer-confirmation-r2-proposal-20261004.json),
[exact requests and commands](../evidence/transformer-confirmation-r2-requests-20261004.json),
[readiness](../evidence/transformer-confirmation-r2-readiness-20261004.json),
[image equivalence](../evidence/transformer-confirmation-r2-image-20261004.json).

The image is assembled from original numerical source `87ce8a9`/image `b713f1f…`
with compatibility overlay `7b88ea2`. All 14 base layers and 269 existing runtime
files are unchanged, including model, training, dependencies, inputs, baseline and
selection policy. Four execution modules and the source-identity file change.
Reports distinguish assembly source/executed image from numerical source/base image.
The newer live epoch logger is still outside this numerical runtime; saved epoch
artifacts provide loss/F1 curves and checkpoint-selection reports after each run.

The v2 namespace admits only seeds 7/2027. It can read its own publication and
exactly five fixed legacy prerequisites, sharing the original read budget.
It cannot read the failed old seed-7 slot or use the old seed-2027 request.
The original AttributeError cause remains unknown; PR #307 repairs diagnostics,
and this package prevents silent attester failure from admitting another Job.

## Proposed spend disposition

Keep the existing **$25 excluding VAT** confirmation cap. The failed attempt's
$12.50 reservation remains held pending actual billing; propose **$6.25 per new
Job**, sequential, maximum two hours each. No estimated saving is released.
Refreshed compute/disk pricing plus one extra billing hour, 2 GiB/90-day storage,
16 GiB egress and 10,000 requests totals about $5.04 per Job, leaving $1.21
contingency. The extra billing hour does not extend the workload's two-hour limit.
[Storage prices](https://docs.nebius.com/object-storage/resources/pricing) and
[registry pricing](https://docs.nebius.com/container-registry/resources/pricing)
were checked on 4 October; registry service is free. This is an operator-managed
admission cap, not a provider monetary cutoff. The $375 baseline-plus-reservations
envelope is not a current bill. Stop if any scoped cost is unknown or exceeds its
reservation. Review retention on 2 January 2027; no deletion is authorized.

## Execution handoff after exact approval

1. Bind the retained operator reply to the proposal SHA-256. Require reviewed,
   green CI and unchanged referenced file/request/image hashes. Refresh costs
   and unused name/prefix checks immediately before each create.
2. Use the existing pinned operator Python and `PYTHONPATH=<checkout>/backend`.
   Existing custody remains at
   `outputs/transformer-startup-repair-20261003/p2/execution/context-private.key`;
   pass it with `--custody`. It is not copied into the new package.
3. Start `transformer_confirmation_supervisor.py run` in a retained process,
   binding proposal/request/operator hashes, exact evidence/slot and custody.
   Keep JSONL/stderr/status under that slot's new `supervisor/` directory.
   Use `inspect` with the same proposal/request hashes; require the returned
   **`admission_ready` to equal true**, not merely exit code zero. It requires
   ready + absent-provider poll + live process start identities + <=3s heartbeat.
   Once a Job is observed, admission is permanently closed for that attempt;
   later NotFound or repeated readiness messages require reconciliation.
   The initial readiness window is 120s; the attester is never restarted.
4. Reserve $6.25 before submitting the exact command once. Local CLI 0.12.283
   explicitly supports `--async`; MCP help differs, so use the validated local
   command. Retain the create process and Operation response. Monitor supervisor
   and provider while submission runs. No automatic create/publication retry.
   Ambiguity requires identity reconciliation, never a second create.
5. If the supervisor fails or its heartbeat expires, stop admission. If a Job
   was submitted, reconcile/cancel that exact identity under the approved bound,
   preserve diagnostics and stop the sequence. Check provider at least every
   30s after context delivery; enforce a three-hour create-to-terminal accounting
   bound in addition to the two-hour runtime timeout. Cancel the exact active
   Job if resource/cost/runtime assumptions fail. Only read-only requests may
   use three retries with increasing 60/90/120s timeouts after an initial 30s.
6. Require provider COMPLETED, unique versioned SUCCESS, and independent `collect`
   verification of exact trial, signature, request, artifact hashes and metrics.
   Use the retained role bundle and source-separation receipt. Produce the
   [per-run Markdown and charts](transformer-run-reporting.md), retaining MLflow
   event records. Seed 2027 is admitted only after verified seed 7.
7. Compare seed 42/7/2027 using `seed_stability`: selection-loss and F1 ranges
   must each be <=0.05. Keep seed 42; never select the luckiest confirmation.
   Calibration/comparison is a later package requiring checkpoint-origin
   compatibility and separate authorization; this image does not admit inference.

Supervisor CLI arguments are documented by `--help`; the proposal binds its exact
bytes. It supervises only its own child and never creates/cancels cloud resources.
Durable local evidence lives in root `outputs/transformer-confirmation-r2-20261004/`.
