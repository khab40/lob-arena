# ARD-0006: Scenario Labeling and Reproducibility

Status: Accepted

Date: 2026-06-01

## Implementation Status

Status as of 2026-06-23: `[partial]`

Implemented:

- Scenario IDs, families, parameters, and metadata propagate through scenario
  controllers, agents, synthetic exchange events, separate labels, and
  benchmark outputs.
- Detector input remains a label-free numeric/event projection; scenario
  labels, attack seeds, and synthetic-only identifiers are not detector
  features.
- Benchmark and dataset scripts write scenario/attack labels for detector evaluation.
- Tests cover scenario launch, metadata preservation, and deterministic scenario behavior.
- Historical-only replay produces no ground truth. Hybrid replay writes ground
  truth only for the launched synthetic overlay and records the master/derived
  seeds in replay evidence.

Future work:

- Live-demo label records do not yet fully finalize every event/order ID linkage described in this ARD.
- Reproducible replay packaging from a saved label set is still limited to local benchmark and dataset scripts.

## Context

Scenario agents generate synthetic abuse-like behavior for demos and benchmarks. To measure detector precision and recall, the system needs ground-truth labels describing which scenario ran, when it was active, and which events belong to it.

The benchmark job also needs deterministic replay so results can be regenerated from a fixed seed.

## Decision

Every scenario launch must create a label record with:

- scenario id
- scenario family
- run id
- random seed
- start tick
- expected end tick or actual end tick
- involved synthetic agents
- event ids or order ids when available
- parameter values used by the scenario

The benchmark job writes these labels to `scenario_labels.jsonl` and evaluates detector incidents against labeled tick windows.

## Scenario Lifecycle

```mermaid
graph LR
    Start["Start"]
    Registered["Registered"]
    Armed["Armed - UI or benchmark selects scenario"]
    Active["Active - start tick reached"]
    CoolingDown["Cooling down - pattern completed"]
    Finished["Finished - cleanup done"]
    Labeled["Labeled - label written"]
    Done["Done"]

    Start --> Registered
    Registered --> Armed
    Armed --> Active
    Active --> CoolingDown
    CoolingDown --> Finished
    Finished --> Labeled
    Labeled --> Done
```

## Labeling Flow

```mermaid
graph TD
    Runner["1. UI or benchmark runner launches scenario"]
    Controller["2. Scenario controller receives seed and params"]
    PlannedLabel["3. Planned label window written"]
    Agent["4. Scenario agent activates"]
    Exchange["5. Exchange receives labeled order events"]
    Detectors["6. Detectors consume events and snapshots"]
    Complete["7. Scenario agent reports completion"]
    FinalLabel["8. Actual label window finalized"]

    Runner --> Controller
    Controller --> PlannedLabel
    Controller --> Agent
    Agent --> Exchange
    Exchange --> Detectors
    Agent --> Complete
    Complete --> FinalLabel
```

## Label Schema

```mermaid
graph TD
    ScenarioLabel["ScenarioLabel - label id, run id, family, seed, tick window, agent ids, event ids, parameters"]
    BenchmarkMatch["BenchmarkMatch - incident id, label id, match type, detection latency"]
    Metrics["Benchmark metrics"]

    ScenarioLabel --> BenchmarkMatch
    BenchmarkMatch --> Metrics
```

## Reproducibility Rules

- Use an explicit seed for every benchmark run.
- Persist scenario parameters alongside labels.
- Avoid wall-clock timestamps as the primary benchmark coordinate; use ticks.
- Keep label windows separate from detector output.
- Evaluate detector results against labels after the simulation run completes.
- Never infer benign ground truth from an unlabeled historical record.
- In hybrid mode, keep historical provenance and synthetic scenario labels in
  separate namespaces and artifacts.

## Consequences

Positive:

- Precision, recall, and F1 can be computed consistently.
- Scenario behavior can be replayed and debugged.
- Detector false positives and false negatives can be traced to label windows.

Tradeoffs:

- Scenario agents must expose their parameters.
- Benchmark output includes additional label artifacts.
- Live demos may need a lighter label path than offline benchmarks.

## Related Documentation

- `PHASES.md`
- `docs/ml/benchmark-methodology.md`
- [ARD-0004: Benchmark Artifact Format](ARD-0004-benchmark-artifact-format.md)
- [ARD-0023: Deterministic Hybrid Historical Replay](ARD-0023-hybrid-historical-replay.md)
