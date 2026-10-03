# Transformer versus LightGBM research fork — 2026-10-02

Operator approval: “yes, follow the new plan fork … concentrate on the new fork PR to validate Transformer idea vs LightGBM … all platform maintenance can be done later, after research work done.” The operator also permits keeping the existing MLflow VM running if needed.

[Story #24](https://github.com/khab40/lob-arena/issues/24) → [Feature #16](https://github.com/khab40/lob-arena/issues/16) → [Epic #15](https://github.com/khab40/lob-arena/issues/15), [Project #3](https://github.com/users/khab40/projects/3).

As a researcher,
I want a bounded Transformer challenger measured against the frozen LightGBM model on identical development targets,
So that I can continue or reject the Transformer approach based on quality, stability and resource cost.

Actor: researcher. Goal: a reproducible development comparison and continue/stop decision. Value: test whether sequence modeling warrants its cost. Out of scope: final-test access, production promotion, G8/G9 reruns, new corpus and infrastructure migration.

```gherkin
Feature: Research-first Transformer comparison
  Scenario: Preserve a training result while tracking is unavailable
    Given governed development inputs and valid separated roles
    When a GPU trial completes while MLflow is unavailable
    Then its configuration, checkpoints, predictions and metrics remain in versioned durable storage
    And later tracking reconciliation does not repeat training

  Scenario: Reject unsupported roles before fitting
    Given an assigned development role has insufficient positive or negative support
    When the campaign validates its inputs within the GPU Job
    Then no optimizer step executes
    And the retained result explains why the experiment cannot answer the hypothesis

  Scenario: Compare the selected candidate fairly within development limits
    Given a completed fixed grid and predeclared confirmation seeds
    When Transformer and frozen LightGBM predictions are compared
    Then both predictions align exactly to the same development targets and labels
    And calibration, threshold selection and prior exposure are identified
    And quality deltas, seed spread, latency and compute are reported

  Scenario: Accept a negative research outcome
    Given the complete comparison shows no improvement sufficient to justify Transformer cost
    When the researcher reviews the result
    Then the recommendation can be to stop Transformer work and retain LightGBM
    And no extra search or final-test access happens automatically
```

## Execution path

Architecture: [Transformer design](../architecture/ARD-0036-market-sequence-transformer.md)
and [comparison and experiment sequence](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md).

1. Merge PR283 with its review repair; retain its evidence and defer live MLflow acceptance under19–21.
2. New PR from updated main: implement the existing two-layer causal model, weighted training, deterministic checkpoint selection/resume, calibration and comparison. Use the approved width64/128 × learning-rate0.0003/0.001 grid, seed42 and winner confirmation seeds7/2027; maximum30 epochs and patience5 remain unchanged.
3. Move authenticated input/class support and smoke checks into the first GPU Job before fitting. Keep frozen inputs, source grouping, train-only normalization and unchanged S/C/O roles. This replaces the separate CPU-first prerequisite; it does not skip its data checks.
4. Use Nebius Serverless Jobs only for model execution. Preserve existing L40S1-GPU/8-vCPU/32-GiB bounds, concurrency1,100-GiB disk and at most14 planned GPU-hours. Seal exact image/config/input/output identities before submission. Retain per-attempt resource/time/byte bounds; transport retries never silently create another model trial.
5. Save versioned artifacts and an append-only event journal before relying on MLflow. Use online MLflow if ready; otherwise reconcile after research. No recovery drill, registry acceptance, namespace grants or migration is a prerequisite for a durable research result.
6. Compare frozen LightGBM development predictions on exact rows. Verify availability before launch; if absent, explicitly include one frozen development-only scoring stage in the reviewed package. Never substitute the previously inspected final fold or compare unrelated aggregate scores.
7. Report quality deltas at the declared operating points, log loss/PR-AUC, calibration, per-family support, seed variation, latency and actual resource use. A missing comparison or incomplete grid is inconclusive. Dominated quality/cost supports stopping; improvement supports a separately scoped next study. No numerical superiority margin is invented after results.

Verification: inert/static checks locally; causal/mask/gradient/resume tests on the GPU before expensive trials; independent artifact/metric/lineage readback. The same-date, three-instrument synthetic-label limitations remain explicit. Research package verification and MLflow reconciliation have separate statuses.

## Implementation and remaining execution work

The [protocol amendment](../../configs/experiments/transformer/research-fork-20261002.json)
preserves the original config hash and records the changed ordering. It is not an
executable Job request. GELU feed-forward activation, final layer normalization
and bounded golden-section temperature fitting resolve previously unspecified
implementation choices. The original authorization files remain unchanged.

The research core now provides authenticated role materialization; two-layer
causal attention with padding/missingness handling; weighted AdamW training;
epoch checkpoints with code/data/config/RNG bindings; fixed-grid and seed checks;
calibration on C; and comparison on O with frozen baseline thresholds. Checkpoint
acknowledgement requires a version ID and matching checksum. Trial completion
remains pending independent verification, and the grid selector rejects it until
the verifier reports success.

Local verification covers inert policy, saved-prediction arithmetic, alignment,
seed receipts, versioned publication faults and operator handshake. GPU-only mask,
causal, gradient, batch, resume and calibration
checks are implemented but have not run. Neither a trained model nor a measured
Transformer advantage exists yet.

Remaining work in this research track:

1. Diagnose and repair startup of the first smoke attempt, which failed before
   model execution; preserve its consumed request and publication evidence.
   The source-bound CUDA image was published and the exact dry-run passed.
2. Prepare any replacement within explicitly approved bounds, run the campaign,
   independently verify every
   result, then present the continue/stop decision. Keep platform maintenance
   deferred; reconcile MLflow from retained artifacts afterward.

## Execution package — 2026-10-03

The worker reads 185 pinned development objects (30,034,660 bytes), verifies
class support and ordered targets, then trains only inside Nebius Jobs. The
first slot performs CUDA behavior checks and a 1,024-row, two-epoch real-data
smoke before any full trial. All eight slots use one L40S, 8 vCPU, 32 GiB RAM,
100 GiB disk and explicit 1 GiB shared memory; concurrency remains one.

The versioned S3 publisher conditionally creates every artifact, reads back its
exact version and checksum, and publishes SUCCESS only after the result,
inventory and linked event journal are durable. Ambiguous writes stop without
retrying. Checkpoints retain optimizer/RNG state and source/data/config bindings.
The independent reader validates selected epochs, saved-logit metrics, seed
stability, calibration optimality and per-family results without loading weights.

The operator helper checks its SDK before retrieving existing development
credentials into memory. It binds a freshly observed provider Job to the signed
request and refuses expired worker intents. Read-only orchestration permits
three transient retries with 30/60/90/120-second timeouts; permission errors and
ambiguous mutations are not retried. Provisioning time is separate from the
worker's five-minute context handshake. No permissions are added by this package.

Frozen LightGBM predictions are available for all 9,210 validation targets:
selection 1,250, calibration 5,490, operating point 2,470. Original prediction IDs
are authenticated and mapped through frozen run lineage to governed target IDs;
ordered hashes and labels are checked again in the worker. The saved raw scores
use the existing frozen isotonic mapping; no LightGBM refit or rescore is needed.
Its calibrator previously saw the full validation fold, which remains a comparison
limitation. LightGBM latency is unmeasured because saved predictions are reused.

Implementation and receipts belong to [PR #284](https://github.com/khab40/lob-arena/pull/284).
Exact execution requests, signing custody and readback evidence are retained in
the root `outputs/transformer-research-fork-20261002/` directory. The protocol
amendment's null package fields are not execution authority: the operator helper
creates separate immutable requests only after the source/image identities exist.

[Bug #285](https://github.com/khab40/lob-arena/issues/285): keep the repository
portion of the image reference at most 64 characters. The original 65-character
name failed provider dry-run; the identical digest under `tr` passed. Request
validation now enforces this boundary locally. Submission still uses a full
digest, never a mutable-tag workaround.

The protocol permits at most eight GPU Jobs: smoke, four grid trials, two seed
confirmations and inference/calibration comparison. Their existing timeouts total
14 GPU-hours. The amended inference worker must account for calibration within
its one-hour slot; it must not silently add the old CPU calibration Job.

Execution status, 2026-10-03: smoke Job `aijob-e00qpnac5v335pddbn` failed with
`PublicationUncertain` before signed-context delivery and model execution.
Reconciliation found only INTENT, with no SUCCESS or execution context. The
attempt is consumed; it is not a quality result or permission for an automatic
replacement. See [current status](../roadmap/CURRENT_STATUS.md).
