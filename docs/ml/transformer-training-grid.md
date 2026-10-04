# Four Transformer training trials — 2026-10-03

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).
Merged PR #290 records the independently verified GPU smoke. The operator then
instructed: “Prepare and authorize the **four training trials**: widths 64/128 ×
learning rates 0.0003/0.001, seed 42; sequential, maximum two hours each.”
That instruction authorizes this existing grid scope; it is retained verbatim in
the [exact request package](../evidence/transformer-training-grid-authorization-20261003.json).
The package is the immutable authorization record. **Execution is complete:**
all four Jobs passed independent verification; see the
[results and next steps](transformer-training-grid-results.md).

As a researcher,
I want the four predeclared Transformer configurations trained on governed inputs,
So that checkpoint selection can identify a candidate for comparison with LightGBM.

Actor: researcher. Goal: compare the fixed width/rate grid. Value: choose one
configuration without tuning against calibration or operating-point outcomes.
Out of scope: confirmation seeds, inference/calibration, final-test access,
new permissions, G8/G9, production promotion, merge and deletion.
Behavioral change: none; this package uses the frozen runtime unchanged.
Invariant: causal inputs, train-only normalization, exact row alignment,
selection-only checkpoint choice and independent publication verification remain.

```gherkin
Feature: Bounded fixed-grid Transformer research
  Scenario: Execute the declared search
    Given the verified smoke and four authorized configurations
    When the training grid is executed
    Then each configuration runs once with seed 42
    And no more than one Job runs at a time
    And each Job has a two-hour timeout

  Scenario: Stop after an unverifiable trial
    Given a trial has failed or its published result cannot be verified
    When the next trial is considered
    Then execution stops with the existing evidence retained
    And no replacement is automatically submitted

  Scenario: Select only after complete verification
    Given four independently verified trial results
    When the winning configuration is selected
    Then selection log loss determines the winner
    And ties use parameter count followed by trial hash
```

## Trials, resources and outputs

| Order | Slot | Width | Learning rate | Seed |
|---|---|---:|---:|---:|
| 1 | search-64-0003 | 64 | 0.0003 | 42 |
| 2 | search-64-001 | 64 | 0.001 | 42 |
| 3 | search-128-0003 | 128 | 0.0003 | 42 |
| 4 | search-128-001 | 128 | 0.001 | 42 |

Each Job: one L40S, 8 vCPU, 32 GiB RAM, 100 GiB ephemeral disk,
1 GiB shared memory, on-demand, restart never, 7,200-second timeout.
Training: at most 30 epochs, batch 64, patience 5; the runtime reserves
600 seconds within the timeout for publication. Seed 42 is an arbitrary fixed
seed for reproducibility, not evidence of robustness across initializations.
Four Jobs allocate at most eight timeout-hours. Under
[Bug #292](https://github.com/khab40/lob-arena/issues/292), the operator approved
**$50 additional; $350 total excluding VAT**. The $300 already spent in 2026 is
an operator-reported baseline as of October 3, not independently reconciled
billing or a new allowance. Actual incremental trial charges remain unreconciled.
No replacement is included.

Before each create, the operator must retain a spend-ledger entry showing
accounted incremental charges + outstanding commitments + a conservative
reservation for the next trial <= $50 excluding VAT. Include provisioning,
runtime, disk, requests, transfer and retained-artifact storage; unknown or
unbounded components block submission. Do not treat a published starting price
as a worst-case quote. This is an operator-managed admission limit, not an
automatic provider billing cutoff. Execution retained current pricing evidence
and four $12.50 reservations; all four Jobs completed and verified. The full
$50 stays reserved until billing reconciliation and cannot fund extra Jobs.
Keep the ledger in root `outputs/transformer-grid-20261003/spend-ledger.json`.

Inputs remain the pinned governed development corpus: 33,450 training rows and
1,250 selection rows. Calibration/operating-point roles remain separate.
The image is the exact smoke-tested digest and all 56 runtime modules match its
source commit. Each request binds the smoke's exact request and versioned SUCCESS.
Each trial retains configuration/lineage, normalization, target ledger, epoch
metrics/checkpoints, selected checkpoint, selection logits, resource measurements
and replayable MLflow events in its separate versioned S3 prefix. The bound is
2 GiB per slot, 128 MiB per object. Online MLflow availability is not required.

## Verification and execution handoff

Preparation passed all four immutable-request checks, all four provider dry-runs
and read-only checks that the four names/prefixes were unused before creation.
The 14 existing inert policy tests passed, including refusal to select from an
incomplete/duplicate/failed grid and deterministic tie-breaking. Secret scanning
and whitespace checks passed. No local training or scoring was performed.
The retained local receipts are in root `outputs/transformer-grid-20261003/`.
Exact requests and existing private signing custody stay in root
`outputs/transformer-startup-repair-20261003/p2/execution/`; do not regenerate them.

The procedure below was completed for each slot; do not replay consumed requests.
The separate result record binds all four Job identities and verified outputs.

1. Review this package and its CI; satisfy the spend-ledger gate above before
   each Job. Before execution, recheck request hashes,
   image/source bindings and the previous trial's terminal/verified result.
   The request dependency graph binds smoke only; the operator enforces the
   stronger sequential order above before each create.
2. Use the pinned operator venv described in the
   [startup handoff](transformer-research-startup-repair.md#execution-handoff-after-approval).
   Run its `preflight` for the current slot again immediately before creation.
3. Start `attest` for that same slot before its exact `create_command` in the
   JSON package. Supply `AI_AGENT=codex` if the harness has not set it.
   Submit once and retain the Job ID; reconcile ambiguous responses without
   resubmitting. Use bounded status/log reads while it runs.
4. Require COMPLETED; retain the unique published SUCCESS receipt, then use
   `collect` with the same bundle/source-receipt paths as the smoke handoff.
   Require independent `verified` before starting the next listed trial.
   Record actual elapsed time, CPU time, host RSS, peak allocated/reserved GPU
   memory and artifact sizes; leave unmeasured GPU utilization and unavailable
   billing costs explicit.
5. After all four pass, report their selection losses/F1, selected epochs and
   resource measurements, applying the frozen winner rule. Prepare confirmation
   seeds 7/2027 and later calibration/comparison separately. The grid alone
   cannot establish that Transformer beats LightGBM.
