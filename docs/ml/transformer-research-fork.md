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

1. Merge PR283 with its review repair; retain its evidence and defer live MLflow acceptance under19–21.
2. New PR from updated main: implement the existing two-layer causal model, weighted training, deterministic checkpoint selection/resume, calibration and comparison. Use the approved width64/128 × learning-rate0.0003/0.001 grid, seed42 and winner confirmation seeds7/2027; maximum30 epochs and patience5 remain unchanged.
3. Move authenticated input/class support and smoke checks into the first GPU Job before fitting. Keep frozen inputs, source grouping, train-only normalization and unchanged S/C/O roles. This replaces the separate CPU-first prerequisite; it does not skip its data checks.
4. Use Nebius Serverless Jobs only for model execution. Preserve existing L40S1-GPU/8-vCPU/32-GiB bounds, concurrency1,100-GiB disk and at most14 planned GPU-hours. Seal exact image/config/input/output identities before submission. Retain per-attempt resource/time/byte bounds; transport retries never silently create another model trial.
5. Save versioned artifacts and an append-only event journal before relying on MLflow. Use online MLflow if ready; otherwise reconcile after research. No recovery drill, registry acceptance, namespace grants or migration is a prerequisite for a durable research result.
6. Compare frozen LightGBM development predictions on exact rows. Verify availability before launch; if absent, explicitly include one frozen development-only scoring stage in the reviewed package. Never substitute the previously inspected final fold or compare unrelated aggregate scores.
7. Report quality deltas at the declared operating points, log loss/PR-AUC, calibration, per-family support, seed variation, latency and actual resource use. A missing comparison or incomplete grid is inconclusive. Dominated quality/cost supports stopping; improvement supports a separately scoped next study. No numerical superiority margin is invented after results.

Verification: inert/static checks locally; causal/mask/gradient/resume tests on the GPU before expensive trials; independent artifact/metric/lineage readback. The same-date, three-instrument synthetic-label limitations remain explicit. Research package verification and MLflow reconciliation have separate statuses.
