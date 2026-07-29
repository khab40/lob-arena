# Architecture Records

This folder contains Architecture Record Documents (ARDs) for LOB Arena.

ARDs capture architecture decisions, context, tradeoffs, implementation phases, and links to supporting documentation. They are meant to complement the higher-level architecture overview in [../architecture.md](../architecture.md).

## Implementation Summary

Status as of 2026-07-28:

| ARD | Implementation | Notes |
|-----|----------------|-------|
| [ARD-0001](ARD-0001-overall-architecture.md) | `[partial]` | Production execution evidence, runtime/cost notes, and screenshots are archived; roadmap features remain |
| [ARD-0002](ARD-0002-websocket-state-schema.md) | `[done]` | Optional exported JSON schema and load-test throttling |
| [ARD-0003](ARD-0003-detector-evidence-model.md) | `[done]` | Broader threshold calibration against historical-style replay datasets |
| [ARD-0004](ARD-0004-benchmark-artifact-format.md) | `[partial]` | A committed evidence bundle exists; canonical schema versioning remains incomplete |
| [ARD-0005](ARD-0005-nebius-endpoint-contract.md) | `[partial]` | Real endpoint execution is archived; production hardening remains |
| [ARD-0006](ARD-0006-scenario-labeling-and-reproducibility.md) | `[partial]` | Live label finalization and full event/order ID linkage remain incomplete |
| [ARD-0007](ARD-0007-nebius-serverless-ai-jobs.md) | `[partial]` | Completed Job records, S3 evidence, and runtime/cost notes are archived; remote policy guardrails remain future work |
| [ARD-0008](ARD-0008-nebius-serverless-ai-endpoints.md) | `[partial]` | Endpoint investigations, latency evidence, and sanitized screenshots are archived |
| [ARD-0009](ARD-0009-judge-mode-investigation-reports.md) | `[partial]` | Dedicated Judge Mode timeline selector is not fully implemented |
| [ARD-0010](ARD-0010-agent-runner-execution.md) | `[done]` | Auth/signing and durable transport for remote runners are future work |
| [ARD-0011](ARD-0011-exchange-liquidity-invariant.md) | `[done]` | Dynamic reference-price tracking and UI tuning are future work |
| [ARD-0013](ARD-0013-ui-shell-preferences.md) | `[done]` | Screenshot capture and broader light-mode chart tuning are future work |
| [ARD-0015](ARD-0015-nebius-ai-investigation-team.md) | `[done]` | Investigation endpoint is the primary interactive Nebius AI Serverless workflow |
| [ARD-0016](ARD-0016-ai-scenario-generator.md) | `[done]` | Scenario generation endpoint produces simulator-compatible AI Scenario Generator workloads |
| [ARD-0017](ARD-0017-ai-detector-tournament.md) | `[done]` | Serverless Jobs contract and local fallback power the AI Detector Tournament workflow |
| [ARD-0018](ARD-0018-canonical-exchange-event-stream.md) | `[done]` | All ten canonical exchange-stream steps are implemented and verified; future dataset mappings use the completed adapter boundary |
| [ARD-0019](ARD-0019-python-reference-java-kernel-migration.md) | `[done]` | All 18 parity and sole-Java-kernel migration steps are implemented |
| [ARD-0020](ARD-0020-java-arena-websocket-agent-orchestration.md) | `[done]` | Java owns the live arena, WebSocket, agent orchestration, scenarios, detectors, incidents, and journals |
| [ARD-0021](ARD-0021-local-observability-grafana.md) | `[done]` | Prometheus/Grafana observability includes bounded detector-tournament lifecycle telemetry and a provisioned operations dashboard |
| [ARD-0022](ARD-0022-historical-market-data-ingestion.md) | `[done]` | FastAPI validates paired LOBSTER CSV files and atomically registers normalized Parquet datasets |
| [ARD-0023](ARD-0023-hybrid-historical-replay.md) | `[done]` | Java deterministically merges immutable LOBSTER history with UI-launched synthetic attacks while isolating labels and provenance |
| [ARD-0024](ARD-0024-versioned-causal-feature-engineering.md) | `[done]` | Source-agnostic causal snapshot features, typed Parquet, quality metadata, leakage checks, and session-grouped split contract |
| [ARD-0025](ARD-0025-governed-corpus-and-ml-benchmark.md) | `[done]` | Governed corpus/adjudication, frozen splits, Java-bound evaluation, streaming features, clustered statistics, regime/worst-decile analysis, and signed releases |
| [ARD-0026](ARD-0026-governed-lightgbm-release-boundary.md) | `[phase-0 done]` | Stable LightGBM training/release identity, validation-only calibration, operating modes, predictions, and checksummed artifact contracts |
| [ARD-0027](ARD-0027-shared-mlflow-tracking.md) | `[done]` | Authenticated shared MLflow tracking with PostgreSQL metadata, S3-compatible artifacts, and governed experiment/model namespaces |
| [ARD-0028](ARD-0028-governed-lightgbm-feature-loading.md) | `[phase-1 done]` | Externally anchored feature release, reconstructed labels, replay-unit binding, exact fold inventory, and separate development/test access |

Current UI architecture note: the product shell exposes Data Ingestion, Arena,
Control Panel, and About in that order. Scenario setup, incidents,
investigations, detector tournaments, deployment status, and experiment
artifacts are folded into Arena or Control Panel. The About and ARD-0001
diagrams document the execution boundaries.

## Records

### Core System Design

- [ARD-0001: Overall Architecture](ARD-0001-overall-architecture.md) — System-wide architecture: interactive path, batch path, and component responsibilities
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

- [Nebius Serverless Use Cases](../use-cases/nebius-serverless-use-cases.md) — Product use cases and concrete API flows

## ARD Format

Each ARD includes:

| Section | Purpose |
|---------|---------|
| **Status** | Accepted, Proposed, Rejected, Superseded |
| **Date** | When the record was written |
| **Implementation Status** | What has landed and what is still missing |
| **Context** | Business and technical background |
| **Decision** | What was decided and why |
| **Architecture** | Diagrams and component overview |
| **Implementation Impact** | How the decision affects development |
| **Alternatives Considered** | Rejected approaches and rationale |
| **Consequences** | Tradeoffs and implications |
| **Related Documentation** | Links to supporting docs and other ARDs |

## How to Use ARDs

1. **Understand a design decision**: Find the relevant ARD and read the Context → Decision → Consequences sections
2. **Implement a feature**: Check which ARDs apply, review implementation impact
3. **Make a new decision**: Use an ARD as a template (copy an existing one and follow the format)
4. **Trace architecture lineage**: Links in "Related Documentation" connect ARDs and other documents

## Workflow & Traceability

All ARDs are linked in the main [Architecture](../architecture.md) document and in [Use Cases](../USE_CASES.md) to show which decisions support which workflows.

This ensures:
- ✓ No stale decisions (ARDs are always referenced)
- ✓ Clear traceability (decisions → implementation → workflows)
- ✓ Single source of truth (decisions recorded in ARDs, not scattered in comments)
