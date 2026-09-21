# ARD-0004: Benchmark Artifact Format

Status: Accepted

Date: 2026-06-01

## Implementation Status

Status as of 2026-07-13: `[partial]`

Implemented:

- Local detector tournament writes benchmark JSON, CSV, Markdown report, and optional chart artifacts.
- Synthetic dataset factory writes events, incidents, labels, snapshots, and manifest artifacts, with a JSONL fallback when Parquet dependencies are unavailable.
- Smart batch runner writes serverless-batch style artifacts for attack/detect experiments.
- A sanitized production evidence sample is retained in the compact frozen [`EXP-390EFAC2` bundle](../../evidence/deployment-2026-07-14-1412/benchmarks/outputs/benchmark/EXP-390EFAC2/README.md).

Future work:

- The canonical ARD path shape is run-specific (`outputs/benchmark/<run_id>/...`), while the current local detector tournament path still uses flatter files such as `outputs/benchmark/results.json`, `metrics.csv`, and `benchmark_report.md`.
- The original tournament artifact set below lacks one complete versioned
  contract. Later governed corpus, projection and model releases do have strict
  versioned schemas under ARD-0025/0026/0031/0038. The legacy tournament output
  is not a substitute for those releases.

## Context

The Nebius Serverless AI Job must run many synthetic simulations and produce artifacts that are easy to inspect, reproduce, and cite in submission material. The benchmark should compare detector outputs against known scenario labels and preserve enough raw data for debugging.

## Decision

Write benchmark artifacts under a run-specific output directory:

```text
outputs/benchmark/<run_id>/
  benchmark_report.md
  benchmark_results.json
  incidents.jsonl
  detector_metrics.csv
  scenario_labels.jsonl
  events.jsonl
  snapshots.parquet
  charts/
    f1_by_scenario.png
    confidence_distribution.png
    detection_latency.png
```

The canonical machine-readable summary is `benchmark_results.json`. CSV and Markdown outputs are derived from the same metrics.

## Artifact Pipeline

```mermaid
graph TD
    Config["job_config.yaml - runs, scenarios, seed"]
    Runner["Batch Benchmark Runner"]
    SimEvents["events.jsonl"]
    Snapshots["snapshots.parquet"]
    Labels["scenario_labels.jsonl"]
    Incidents["incidents.jsonl"]
    Metrics["detector_metrics.csv"]
    Results["benchmark_results.json"]
    Charts["chart image files"]
    Report["benchmark_report.md"]

    Config --> Runner
    Runner --> SimEvents
    Runner --> Snapshots
    Runner --> Labels
    Runner --> Incidents
    Labels --> Metrics
    Incidents --> Metrics
    Metrics --> Results
    Results --> Charts
    Results --> Report
    Charts --> Report
```

## Artifact Relationships

```mermaid
graph TD
    BenchmarkRun["BenchmarkRun - run id, seed, run count"]
    SimulationRun["SimulationRun"]
    ScenarioLabel["ScenarioLabel - family and tick window"]
    Event["Event stream"]
    Snapshot["Order book snapshot"]
    Incident["Incident - detector and confidence"]
    Metric["DetectorMetric - precision, recall, F1"]

    BenchmarkRun --> SimulationRun
    SimulationRun --> ScenarioLabel
    SimulationRun --> Event
    SimulationRun --> Snapshot
    SimulationRun --> Incident
    ScenarioLabel --> Metric
    Incident --> Metric
```

## Consequences

Positive:

- Benchmark results are reproducible and auditable.
- Human and machine-readable outputs are both available.
- Charts and reports can be regenerated from JSON/CSV.

Tradeoffs:

- Output directories can grow quickly.
- Artifact versioning is required once schemas change.
- Parquet support may require optional dependencies in lightweight environments.

## Related Documentation

- `docs/ml/benchmark-methodology.md`
- `serverless/jobs/README.md`
- [ARD-0006: Scenario Labeling and Reproducibility](ARD-0006-scenario-labeling-and-reproducibility.md)
