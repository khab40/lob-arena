# Live training progress and selection summaries — 2026-10-03

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).

As a researcher,
I want live epoch progress and a final selection explanation,
So that I can understand training behavior and why a checkpoint was retained.

Actor: researcher. Goal: observe the neural-network run. Value: diagnose progress
and interpret optimization without waiting for MLflow. Out of scope: changing
the optimizer, selection policy, frozen results, authorization or data access.
Verification: inert event, orchestration and publication tests; no local model run.

```gherkin
Feature: Observable Transformer training
  Scenario: Observe a completed epoch
    Given an authorized trial is training
    When an epoch finishes and its checkpoint publication is acknowledged
    Then the live log shows loss, selection F1, learning rate, time and best epoch
    And the durable journal retains the same epoch summary

  Scenario: Understand checkpoint selection
    Given a trial stops after patience or its epoch limit
    When its training summary is emitted
    Then the selected epoch, selected metrics and stop reason are shown
    And selection is explained using raw selection log loss

  Scenario: Keep progress separate from verified completion
    Given training has emitted progress
    When checkpoint or terminal publication fails
    Then no independently verified completion is claimed
    And the terminal failure record remains identifiable
```

Plan: introduce a torch-free, scalar-only JSONL progress helper; log worker phase
starts and trial/epoch boundaries; persist completed-epoch summaries after their
checkpoint acknowledgement; explain grid selection at its existing decision
point; keep terminal publication records unchanged. Add inert tests and update
the runtime handoff. No per-batch, raw-row, tensor, credential or exception-text logs.

Checkpoint selection uses improvement in raw selection log loss greater than
`1e-6`; an insufficient improvement keeps the earlier checkpoint. Patience is
five epochs. F1 at 0.5 is diagnostic. Grid selection compares the four verified
trials by selected loss, then parameter count, then trial hash. Width 128 / rate
0.0003 / seed 42 / epoch 4 won the completed grid; calibration remains separate.

The completed grid used immutable source `87ce8a9` and its recorded image.
This logging change is for a future runtime package. Current dependency readback
requires identical source/image identities, so a rebuilt logging image cannot
silently consume that grid. Keep the current campaign on its pinned image unless
an explicit compatibility design/package is reviewed. Do not weaken lineage
checks, rebuild a sealed request, or rerun completed trials to obtain richer logs.

## What the logs show

| Event | Useful fields |
|---|---|
| Phase/input readiness | Current phase, slot and row counts per data role |
| Trial start | Width, rate, seed, AdamW, schedule, batch size, limits and resume epoch |
| Epoch start | Epoch number, maximum epochs and completed optimizer steps |
| Epoch completion | Weighted training loss, raw selection loss, F1 at 0.5, elapsed seconds, first/last learning rate, best epoch, patience count and checkpoint hash |
| Training completion | Selected checkpoint and metrics, stopping reason, steps, parameter count, elapsed training time and peak GPU memory |
| Grid selection | All four candidates and the selected width/rate/seed/epoch, with the selection rule |

Each line is flushed JSON. Epoch completion follows acknowledged checkpoint
publication; its summary is also retained in the existing versioned event journal.
At the 30-epoch limit this adds at most 30 epoch summaries and one training summary;
dependent runs also retain one grid-selection event. Existing artifact/readback
bounds cover these events. Phase/start events are stdout-only.
Epoch time includes selection evaluation and checkpoint publication. First/last
learning rates describe the optimizer steps actually scheduled in that epoch.
Weighted training loss and raw selection loss use different weighting; their gap
is not directly an overfitting measure. F1 uses an uncalibrated 0.5 threshold.

Progress carries `evidence_status=progress_not_independent_verification`.
The final `status=published` or `status=failed` record retains its existing schema;
consumers must select that terminal record instead of parsing all stdout as one JSON
object. A broken stdout pipe is tolerated, while deadlines and journal failures
still propagate. The durable SUCCESS receipt and independent readback remain
required before treating the experiment as verified.

The grid-selection summary runs when a dependent run consumes the four verified
search results. An individual search Job cannot declare the whole-grid winner.
The [saved reports and plots](experiments/transformer-grid-20261003/index.md)
already explain the completed grid without rerunning it.

Verification: 90 inert progress, operator, policy, storage and readback tests pass.
Independent review found and fixed a deadline-propagation issue; its regression
passes. No cloud or model run was used to validate this future logging code.
