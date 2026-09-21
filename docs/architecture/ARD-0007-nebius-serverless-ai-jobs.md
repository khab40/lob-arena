# ARD-0007: Nebius Serverless AI Jobs

Status: Accepted

Date: 2026-06-02

## Validation execution policy — 2026-09-16

The operator removed administrative submission/retention windows, billing checks
and fixed validation spend/VM limits until LightGBM and Transformers validation
have recorded outcomes. Apply the [validation execution policy](../model-validation-execution-policy.md)
in preference to older operational bounds in this record. No billing queries or
balance-refresh requests. Finite Job timeouts, execution identities, evidence
integrity and separate final-test authorization remain. This is an execution-policy
change, not model-quality acceptance or a completed G8/G9 milestone.

## Implementation Status

Status as of 2026-07-14: `[partial]`

Implemented:

- Detector tournament, batch benchmark, synthetic dataset factory, and parallel attack/detect batch scripts under `serverless/jobs/`.
- Job Dockerfile, example configs, Nebius job config, image build script, and submit script with dry-run support.
- Backend and UI paths for smart batch creation, artifact workbench access, usage evidence, and local parsing of benchmark artifacts.
- Completed production Job records, collected S3 evidence, metrics, runtime/cost notes, and reports are archived in the frozen [benchmark bundle](../../evidence/deployment-2026-07-14-1412/benchmarks/outputs/benchmark/EXP-390EFAC2/README.md).

Future work:

- Cost/runtime guardrails are documented but not enforced by a remote Job policy layer.

## Context

Experiment Mode needs repeatable offline work that is too heavy or too slow for
the live arena request path. The project needs batch simulations, synthetic
dataset generation, feature extraction, detector evaluation, and report
generation while keeping the UI responsive.

The job path must also control cost and runtime. Development runs should use
small synthetic batches before any larger challenge benchmark run.

## Decision

Use Nebius Serverless AI Jobs for offline experiment workloads:

```mermaid
graph TD
    Jobs["Nebius Serverless AI Jobs"]
    Batch["Batch simulations"]
    Scenario["Scenario generation"]
    Features["Feature extraction"]
    Evaluation["Evaluation runs"]
    Reports["Experiment reports"]

    Jobs --> Batch
    Jobs --> Scenario
    Jobs --> Features
    Jobs --> Evaluation
    Jobs --> Reports
```

The job runner accepts a bounded configuration, runs synthetic simulations,
collects detector outputs against known labels, and writes artifacts under a
run-specific output directory.

Phase 4 adds a smart attack/detect batch runner under `serverless/jobs/` that
can execute many independent simulations concurrently. The default demo command
uses 100 parallel workers so endpoint/job observability can show ramp-up and
ramp-down behavior.

## Job Flow

```mermaid
graph TD
    Config["Job config - runs, seed, regimes, scenarios"]
    Job["Nebius Serverless AI Job"]
    Sim["Synthetic simulation batch"]
    Labels["Scenario labels - ground-truth windows"]
    Features["Feature extraction - spread, imbalance, rates, depth"]
    Detectors["Detector evaluation runs"]
    Metrics["Precision / recall / F1 - latency and false positives"]
    Reports["Experiment reports - Markdown, JSON, charts"]
    ObjectStorage["Object Storage - S3 evidence archive"]
    BackendSync["Backend sync - local evidence + UI links"]

    Config --> Job
    Job --> Sim
    Sim --> Labels
    Sim --> Features
    Features --> Detectors
    Labels --> Metrics
    Detectors --> Metrics
    Metrics --> Reports
    Reports --> ObjectStorage
    ObjectStorage --> BackendSync
```

## Governed ML extension — 2026-09-21

The original synthetic benchmark scope below is historical. Separate acquisition
and preparation Jobs now ingest the approved public Nasdaq corpus, freeze
tabular/sequence projections, and run governed LightGBM development/evaluation
under [ARD-0035](ARD-0035-nebius-lightgbm-first.md). Transformer training remains
proposed. Agent-initiated model workloads, including synthetic training/scoring
rehearsals, run on Nebius; local mock tournament support is not an exception.
See [ML lifecycle use cases](../use-cases/ml-lifecycle.md).

## Original benchmark scope

In scope:

- small and medium synthetic benchmark batches
- detector tournament benchmarks
- parallel attack/detect batches across the normal-market control plus
  `spoofing_like_wall`, `layering_like`, `quote_stuffing`, and `liquidity_evaporation`
- synthetic dataset generation from simulator events
- feature extraction from event and snapshot artifacts
- benchmark reports, metrics, and charts

Out of scope:

- real market data ingestion
- real manipulation detection
- trading signals
- compliance decisioning
- unbounded or uncontrolled large-scale dataset generation

## Cost Controls

Default development runs should stay small:

- `runs=100` for smoke and local validation
- `runs=500` for medium comparison
- `runs=1000` only for final benchmark evidence when needed

Job configuration must make run count, scenario set, market regime, seed, and
output directory explicit.

## Artifact Contract

Jobs write artifacts compatible with
[ARD-0004: Benchmark Artifact Format](ARD-0004-benchmark-artifact-format.md):

```text
outputs/benchmark/<run_id>/
  benchmark_report.md
  benchmark_results.json
  detector_metrics.csv
  incidents.jsonl
  scenario_labels.jsonl
  charts/

outputs/serverless-batch/<run_id>/
  order_book_events.jsonl
  trades.jsonl
  attack_labels.jsonl
  blue_team_alerts.jsonl
  detector_metrics.csv
  generated_report.md
  manifest.json
```

## Consequences

Positive:

- Experiment Mode is separated from the live UI path.
- Detector quality can be measured repeatably.
- Reports and charts can be regenerated from artifacts.

Tradeoffs:

- Job configs and artifact schemas need versioning.
- Large runs can consume credits quickly if not bounded.
- Offline results may not exactly match live arena timing.

## Related Documentation

- `docs/nebius-deployment.md`
- `docs/benchmark-methodology.md`
- `serverless/jobs/README.md`
- [ARD-0004: Benchmark Artifact Format](ARD-0004-benchmark-artifact-format.md)
- [ARD-0006: Scenario Labeling and Reproducibility](ARD-0006-scenario-labeling-and-reproducibility.md)
