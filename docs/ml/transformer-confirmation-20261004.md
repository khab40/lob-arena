# Two-seed Transformer confirmation — 4 October 2026

Historical plan/execution record; reconciled 8 October 2026. The first seed-7 attempt failed; separately approved replacement confirmations passed.
[Current status](../roadmap/CURRENT_STATUS.md) owns remaining acceptance.
[ARD-0042](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md) owns research ordering;
pending instructions below do not authorize another run or reuse consumed approval.

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).
**Approved; sequence stopped after seed-7 startup failure.** The operator
approved the exact proposal and $25 additional cap. Seed 7 failed at context
delivery before training; seed 2027 was not submitted. See the
[failed-run report](experiments/transformer-confirmation-20261004/seed-7.md).
The package below is retained as the approved historical protocol; its original
proposal bytes remain unchanged. It authorizes no replacement Job.

As a researcher,
I want to repeat the selected Transformer configuration with seeds 7 and 2027,
So that I can measure initialization stability before calibration and comparison.

Actor: researcher. Goal: confirm the selected configuration. Value: detect
seed-sensitive quality without expanding the search. Verification: immutable
requests, provider dry-runs, independent artifact readback and three-seed ranges.
Out of scope: inference/calibration, final-test access, new image or permissions,
G8/G9, promotion, merge and deletion. Behavioral change: none; reuse the sealed
runtime, governed causal inputs, train-only normalization and exact row alignment.

```gherkin
Feature: Bounded Transformer confirmation
  Scenario: Repeat only the selected configuration
    Given all four grid results are independently verified
    When the approved confirmation requests execute
    Then width 128 and learning rate 0.0003 are used with seeds 7 and 2027
    And seed 42 remains the candidate rather than selecting the luckiest seed

  Scenario: Advance only after verified completion
    Given seed 7 has reached provider state COMPLETED
    When its independent readback verifies the exact configuration and artifacts
    Then seed 2027 may start within the approved spend allowance
    And no more than one Job runs at a time

  Scenario: Stop on failure or uncertainty
    Given a result cannot be independently verified or its cost bound is uncertain
    When the next Job is considered
    Then the sequence stops with existing evidence retained
    And no replacement or additional search is submitted

  Scenario: Wait for exact authorization
    Given the requests and dry-runs are prepared
    But their exact proposal and spend cap are not approved
    When execution readiness is checked
    Then no Job is submitted or signed execution context published
```

## Exact package and bounds

Approve the SHA-256 of the [proposal JSON](../evidence/transformer-confirmation-proposal-20261004.json).
It binds the [two exact requests and create commands](../evidence/transformer-confirmation-requests-20261004.json),
[readiness/pricing evidence](../evidence/transformer-confirmation-readiness-20261004.json)
and verified grid result record by hash. Raw canonical requests and existing
private signing custody remain in root
`outputs/transformer-startup-repair-20261003/p2/execution/`; do not regenerate them.
The preparation receipts and proposed ledger are in root
`outputs/transformer-confirmation-20261004/`.

| Order | Slot | Width | Learning rate | Seed | Maximum Job timeout |
|---|---|---:|---:|---:|---:|
| 1 | seed-7 | 128 | 0.0003 | 7 | 2 hours |
| 2 | seed-2027 | 128 | 0.0003 | 2027 | 2 hours |

Each Job uses one L40S, 8 vCPU, 32 GiB RAM, 100 GiB ephemeral disk, 1 GiB
shared memory, on-demand pricing and restart never. Maximum: two Jobs, four
timeout GPU-hours, concurrency one. Training uses batch 64, up to 30 epochs,
patience 5 and a 600-second publication reserve within the two-hour timeout.
Width/rate are derived from the four immutable grid results at runtime; the
package independently recomputes that winner and binds its exact trial hash.

Both requests bind the verified smoke and four grid SUCCESS/request receipts.
Their request graph does not enforce seed-to-seed ordering: the operator must
require seed 7 COMPLETED and independently verified before creating seed 2027.

Use runtime source `87ce8a933c40fe825569e3de6a8699b519808c34` and the original
digest-pinned image recorded in the proposal. Its repository is 47 characters,
within the 64-character limit. Four newer logging modules differ on main and
are intentionally absent from this image. The unchanged operator, validator
and readback modules were checked against the pinned source. This preserves
the verified dependency identities; no image build or upload is required.

## Proposed spend disposition

**Request: at most $25 additional excluding VAT, reserving $12.50 per Job.**
Keep the previous $50 grid reservation committed until actual billing is
reconciled. With the operator-reported $300 baseline, the proposed tracked
baseline-plus-reservations envelope is $375. That is not a reconciled current
bill or a provider-enforced account-wide cap.

The 4 October Nebius MCP calculator quotes $1.5484/hour for compute and
$0.0097222/hour for 100 GiB network SSD: $6.2324888 for four hours combined.
[Serverless uses Compute pricing](https://docs.nebius.com/serverless/pricing-quotas).
Each $12.50 reservation also covers one extra billing hour for provisioning and
termination accounting, 2 GiB of artifacts for 90 days, 16 GiB egress and
10,000 requests at the higher Standard request rate. The calculated subtotal
is about $5.04 per Job; the remaining $7.46 is contingency.
[Object Storage rates](https://docs.nebius.com/object-storage/resources/pricing).
The extra billing reserve does not authorize a longer-running Job.

Before each create, recheck current rates and require accounted confirmation
charges + outstanding confirmation commitments + the next reservation <= $25.
Unknown/unbounded costs or a failed assumption block admission. Retain each
full reservation until charges reconcile; savings do not authorize more Jobs.
This is an operator-managed admission ledger, not an automatic monetary cutoff.
The proposed approval includes cancellation of either listed Job to enforce its
bounds. Review retention on 2 January 2027; retention after the reserved period
needs a separate cost disposition, and the review does not authorize deletion.

## After exact approval

1. Retain the operator reply bound to the proposal hash; require reviewed/green
   CI, unchanged referenced hashes and a funded ledger. Recheck unused name and
   output prefix immediately before each create. No attester starts beforehand.
2. Use the existing root operator Python at
   `outputs/transformer-lineage-replacement-r2-reviewed-20260929/operator-venv/bin/python`,
   with `PYTHONPATH` pointing to this checkout's `backend` and the unchanged
   `scripts/transformer_research_operator.py`. SDK versions were verified before
   read-only preflight; preparation and dry-runs perform no model work.
3. Start that helper's `attest` for the exact evidence directory and seed slot,
   then run that slot's fully resolved `create_command` from the bound requests
   JSON once. Preserve nonempty `AI_AGENT`, otherwise set `codex`. On an ambiguous
   create or publication response, reconcile the existing identity; never resubmit.
4. Read bounded provider status/logs. Cancel the approved active Job if its
   runtime/spend assumptions fail; stop after failed or uncertain publication.
   Transient read calls may use 30 seconds initially, then 60/90/120 seconds;
   these retries never authorize replacement Jobs or extend the workload timeout.
5. Require COMPLETED and retain the unique versioned SUCCESS receipt. Run `collect`
   using the same evidence/slot, bundle
   `outputs/transformer-role-provenance-20260928/cpu-role-audit-evidence-20260929.json`
   and `docs/evidence/transformer-source-separation-receipt-20261002.json`.
   Require independent `verified`, exact seed/width/rate and complete artifact
   hashes before allowing the next seed.
6. Produce each [per-run Markdown report and charts](transformer-run-reporting.md)
   from verified artifacts, including loss/F1 versus epoch, selected epoch,
   confusion matrix, resource measurements and limitations. Preserve replayable
   MLflow events; online MLflow reconciliation follows research without reruns.
7. Compare the original seed-42 winner with both confirmations using the existing
   `seed_stability` policy. Both selection-loss and F1 ranges must be <=0.05.
   Report a failed gate honestly; do not choose another seed or expand search.
   Prepare calibration/comparison as a separate authorization after this stage.

Preparation verified 147 retained artifacts across all five prerequisites,
custody public-key continuity, immutable request validation and the winner.
Both exact Nebius MCP dry-runs passed; both read-only availability checks passed.
The 58 existing inert policy, stability, storage and operator tests passed with
the pinned SDK overlay and zero skips. No local training, GPU Job, attestation,
calibration or comparison was performed by this preparation.
