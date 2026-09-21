# Architecture Records

This folder contains Architecture Record Documents (ARDs) for LOB Arena.

ARDs capture architecture decisions, context, tradeoffs, implementation phases, and links to supporting documentation. They are meant to complement the higher-level architecture overview in [../architecture.md](../architecture.md).

## Reading decisions

Accepted design is not proof of implementation or qualification. Read
[current status](../roadmap/CURRENT_STATUS.md) for progress and the
[architecture overview](../architecture.md) for current ownership.
Each record retains its own decision context and supersession status.

## Records

### Core System Design

- [ARD-0001: Overall Architecture](ARD-0001-overall-architecture.md) — Original separation decision; live ownership later superseded by ARD-0020
- [ARD-0002: WebSocket State Schema](ARD-0002-websocket-state-schema.md) — Real-time state messaging format for live arena updates

### Detector & Evidence Design

- [ARD-0003: Detector Evidence Model](ARD-0003-detector-evidence-model.md) — How detectors encode findings and confidence scores
- [ARD-0006: Scenario Labeling and Reproducibility](ARD-0006-scenario-labeling-and-reproducibility.md) — Ground-truth labeling for benchmark validation

### Data & Artifacts

- [ARD-0004: Benchmark Artifact Format](ARD-0004-benchmark-artifact-format.md) — Persisted data formats (JSON, Parquet, CSV, Markdown)
- [ARD-0022: Historical Market Data Ingestion And Replay](ARD-0022-historical-market-data-ingestion.md) — Paired LOBSTER validation, normalized Parquet storage, and dataset registration
- [ARD-0023: Deterministic Hybrid Historical Replay](ARD-0023-hybrid-historical-replay.md) — Historical/synthetic merge ordering, source immutability, ID/seed separation, labels, metrics, and evidence
- [ARD-0024: Versioned Causal Market-Abuse Feature Engineering](ARD-0024-versioned-causal-feature-engineering.md) — Stable feature names/types, rolling formulas, label isolation, split policy, Parquet, and quality artifacts
- [ARD-0025: Governed Corpus and ML Benchmark Protocol](ARD-0025-governed-corpus-and-ml-benchmark.md) — Independent clean labels, chronological grouped splits, Java-bound evaluation, session bootstrap, operational metrics, and signed release gates
- [ARD-0026: Governed LightGBM Release Boundary](ARD-0026-governed-lightgbm-release-boundary.md) — Phase 0 identity, provenance, calibration, operating-point, prediction, and checksummed bundle contracts
- [ARD-0027: Shared MLflow Tracking Plane](ARD-0027-shared-mlflow-tracking.md) — Docker deployment, storage, authentication, roadmap namespaces, and governance boundary
- [ARD-0028: Governed LightGBM Feature Loading](ARD-0028-governed-lightgbm-feature-loading.md) — Frozen feature-release hashes, exact session/campaign coverage, governed label reconstruction, replay-unit checks, and isolated final-test access
- [ARD-0029: Deterministic LightGBM Binary Training](ARD-0029-deterministic-lightgbm-binary-training.md) — Phase 2 training-only weighting, deterministic LightGBM settings, validation early stopping, and reproducible artifacts
- [ARD-0030: Float32 Governed Feature Release](ARD-0030-float32-governed-feature-release.md) — Versioned float32 Parquet, v1 compatibility, precision gates, and release/model migration rules
- [ARD-0031: Complete Governed LightGBM v1](ARD-0031-complete-lightgbm-v1.md) — Calibration, frozen thresholds, isolated test scoring, explanations, detector loading, paired evaluation and release verification
- [ARD-0032: Nasdaq TotalView-ITCH Ingestion](ARD-0032-nasdaq-itch-ingestion.md) — Streaming local ITCH parsing, lifecycle validation, aligned Parquet, quotas, and manifest-driven Java replay
- [ARD-0033: Deterministic Hybrid Injection Scheduling](ARD-0033-deterministic-hybrid-scheduling.md) — Exact historical trigger partitioning, scenario parameter hashes, label timing, and evidence bindings
- [ARD-0034: ITCH Market-Profile Calibration](ARD-0034-itch-market-profile-calibration.md) — Profile extraction, Java runtime selection, checksum/run binding, dynamic baselines, and held-out realism gates
- [ARD-0035: Nebius-First Qualification Of Governed LightGBM](ARD-0035-nebius-lightgbm-first.md) — CPU-first Nebius execution, evidence, performance, cost and exit gates for the existing LightGBM v1 boundary
- [ARD-0036: Governed Market-Sequence Transformer Challenger](ARD-0036-market-sequence-transformer.md) — Causal sequence contracts, bounded GPU training, standalone evaluation and the gate into derived-feature work
- [ARD-0037: Transformer-Derived Features Into LightGBM](ARD-0037-transformer-to-lightgbm-cascade.md) — Versioned Transformer feature releases, exact joins, CPU decision layer, fallback and governed promotion

### Frozen Evaluation and Recovery

- [ARD-0038: C4-Specific Frozen Evaluation](ARD-0038-c4-specific-evaluation.md)
- [ARD-0039: Same-Run MLflow Evaluation Recovery](ARD-0039-same-run-mlflow-recovery.md)
- [ARD-0040: Completed-Release Publication Recovery](ARD-0040-completed-release-publication-recovery.md)

### Agent Execution

- [ARD-0010: Agent Runner Execution Architecture](ARD-0010-agent-runner-execution.md) — Local, remote, heavy, and LangGraph-compatible agent execution
- [ARD-0011: Exchange Liquidity Invariant And Agent Quote Ownership](ARD-0011-exchange-liquidity-invariant.md) — Baseline ladder guard and additive per-agent quote ownership
- [ARD-0018: Canonical Exchange Event Stream](ARD-0018-canonical-exchange-event-stream.md) — Versioned add, modify, cancel, execute, and L2 snapshot stream for simulation and historical data
- [ARD-0019: Python Reference And Java Kernel Migration](ARD-0019-python-reference-java-kernel-migration.md) — Completed parity-gated cut-over to the sole Java 25 deterministic kernel
- [ARD-0020: Java Arena WebSocket And Agent Orchestration](ARD-0020-java-arena-websocket-agent-orchestration.md) — Live arena and orchestration cut-over with Python retained for AI/ML and serverless work
- [ARD-0021: Local Observability With Prometheus And Grafana](ARD-0021-local-observability-grafana.md) — Optional local monitoring stack, scrape contracts, and dashboards

### UI Shell And Presentation

- [ARD-0013: UI Shell Preferences And Demo Presentation](ARD-0013-ui-shell-preferences.md) — Banner asset, theme preference, compact navigation, and paused-state-stable visualizations

### Nebius Integration

- [ARD-0005: Nebius Endpoint Contract](ARD-0005-nebius-endpoint-contract.md) — API contracts for incident explanations and scenario generation
- [ARD-0007: Nebius Serverless AI Jobs](ARD-0007-nebius-serverless-ai-jobs.md) — Batch job execution for benchmarks and dataset generation
- [ARD-0008: Nebius Serverless AI Endpoints](ARD-0008-nebius-serverless-ai-endpoints.md) — Interactive serverless AI endpoint integration
- [ARD-0009: Judge Mode Investigation Reports](ARD-0009-judge-mode-investigation-reports.md) — Investigation and report generation workflows
- [ARD-0015: Nebius AI Investigation Team](ARD-0015-nebius-ai-investigation-team.md) — Phase 1 build plan and implementation record for AI investigation via Nebius AI Serverless Endpoint
- [ARD-0016: AI Scenario Generator](ARD-0016-ai-scenario-generator.md) — Phase 2 build plan and implementation record for scenario generation via Nebius AI Serverless Endpoint
- [ARD-0017: AI Detector Tournament](ARD-0017-ai-detector-tournament.md) — Phase 3 build plan and implementation record for detector tournaments via Nebius Serverless Jobs

### Use Cases

- [ML lifecycle use cases](../use-cases/ml-lifecycle.md) — Data, training, calibration, selection, MLflow retention and planned serving
- [ML documentation review](ml-documentation-review-20260921.md) — Corrections, evidence and implementation gaps

- [Nebius Serverless Use Cases](../use-cases/nebius-serverless-use-cases.md) — Historical July payload/acceptance examples

## Writing records

Keep status/date, context, decision, alternatives and consequences. Add detail
or a diagram only where it explains a unique requirement or boundary.
Follow [documentation ownership](../DOCUMENTATION_GUIDE.md); link to current
status and operational procedures rather than copying them into each record.
