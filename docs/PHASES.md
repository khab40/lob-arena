# Project Phases

LOB Arena is built as:

- React visual arena
- Java 25/Spring live arena and WebSocket control plane
- Java synthetic exchange and order book
- normal and abuse-like agents
- Java deterministic detectors
- FastAPI AI/ML, experiments, evidence, and serverless adapters
- Nebius Serverless AI Job benchmark
- Nebius AI / LLM explanations

This project is an educational simulation. The scenarios are synthetic abuse-like patterns for demonstrating order-book anomaly detection and AI Investigator explanations.

## Nebius AI Serverless Build Challenge Overlay

Status: `[done]`

Current product narrative: LOB Arena is a Nebius AI Serverless-powered market surveillance command center. The Arena generates suspicious market workloads; Nebius AI Serverless investigates, explains, generates scenarios, and runs detector benchmarks.

Implementation phases:

- `[done]` Phase 1, Nebius AI Investigation Team via Serverless Endpoint: `POST /api/nebius/investigation-team/analyze` forwards incident, detector, order-book, trade, and metric context to `/investigation-team`, with deterministic mock fallback.
- `[done]` Phase 2, Nebius AI Scenario Generator via Serverless Endpoint: `POST /api/nebius/scenario-generator/generate` returns simulator-compatible scenario JSON with ground truth, replay metadata, expected detector behavior, and mock fallback.
- `[done]` Phase 3, Nebius AI Detector Tournament via Serverless Jobs: `POST /api/nebius/tournament/start` queues detector benchmark work, submits configured Nebius jobs when available, or completes a local mock tournament with the same response schema.
- `[done]` Challenge E2E smoke path: `POST /api/nebius/serverless-smoke/run` orchestrates one spoofing incident demo, labels missing cloud job templates as `real_nebius_pending`, and writes `outputs/serverless-smoke/` artifacts.

Primary docs:

- `docs/architecture/ARD-0015-nebius-ai-investigation-team.md`
- `docs/architecture/ARD-0016-ai-scenario-generator.md`
- `docs/architecture/ARD-0017-ai-detector-tournament.md`
- `docs/use-cases/nebius-serverless-use-cases.md`
- `docs/demo-script.md`

## Status Legend

- `[done]` Implemented and committed.
- `[partial]` Implemented enough for the current MVP, with known follow-up gaps.
- `[in progress]` Active roadmap work with implementation or governed execution underway.
- `[blocked]` Work cannot advance until its stated gate or external prerequisite passes.
- `[todo]` Not implemented yet.

## Phase 1: Core Live Arena

Status: `[done]`

Goal: build the minimum live simulator and visual order book loop.

Scope:

- order book
- matching engine
- normal agents
- simulation clock
- WebSocket state stream
- basic UI ladder

Deliverables:

- `[done]` `backend/app/exchange/order_book.py`
- `[done]` `backend/app/exchange/matching_engine.py`
- `[done]` `backend/app/agents/runtime.py` in-process `AgentManager` with deterministic intent sorting and per-tick deadlines
- `[done]` `backend/app/agents/market_maker.py`
- `[done]` `backend/app/agents/noise_trader.py`
- `[done]` `backend/app/agents/liquidity_taker.py`
- `[done]` `backend/app/arena/clock.py`
- `[done]` `backend/app/arena/engine.py`
- `[done]` `backend/app/websocket/broadcaster.py`
- `[done]` `backend/app/websocket/manager.py`
- `[done]` `backend/app/websocket/routes.py`
- `[done]` basic React order book ladder in the Arena screen

Exit criteria:

- `[done]` The simulator ticks continuously when started.
- `[done]` Normal agents generate baseline activity.
- `[done]` The backend can register hundreds of lightweight normal agents while keeping exchange mutation single-writer.
- `[done]` The matching engine updates the synthetic book.
- `[done]` Regression tests cover add/cancel/market flows, price-time priority, partial fills, modify-like quote updates, and L2 snapshots.
- `[done]` The frontend receives or can display live state.
- `[done]` The UI shows bids, asks, best levels, and basic market state.

## Phase 2A: Out-of-Process Agent Runners

Status: `[done]`

Goal: let normal agents run outside the exchange/backend container while preserving one authoritative exchange writer.

Deliverables:

- `[done]` HTTP remote-agent protocol using `MarketSnapshot` requests and `AgentIntent` responses.
- `[done]` backend `RemoteAgentClient` support through `ARENA_REMOTE_AGENT_URLS`.
- `[done]` separate `agent-runner` service and Dockerfile.
- `[done]` Docker Compose wiring for local backend + remote runner separation.
- `[done]` tests for remote intent parsing and local/remote manager composition.

Exit criteria:

- `[done]` Agents can run in a separate container.
- `[done]` Agent runners can be moved to another server by changing `ARENA_REMOTE_AGENT_URLS`.
- `[done]` The exchange/order book remains single-writer in the backend.

## Phase 2: Scenario Agents And Operator Controls

Status: `[done]`

Goal: add manually launched synthetic abuse-like scenarios and visible agent activity.

Scope:

- spoofing-like wall
- layering-like pattern
- Quote Stuffing Burst
- scenario buttons
- agent feed

Deliverables:

- `[done]` `SpoofingLikeAgent`
- `[done]` `LayeringLikeAgent`
- `[done]` `QuoteStuffingLikeAgent`
- `[done]` scenario launch controls in the UI
- `[done]` agent activity feed in the Arena screen
- `[done]` backend scenario controller endpoints

Exit criteria:

- `[done]` The UI can launch each scenario manually.
- `[done]` Active scenario state is visible in the UI.
- `[done]` Agent activity appears in the feed.
- `[done]` Scenario events are labeled for detector and benchmark use.

## Phase 3B: Baseline Liquidity And Quote Ownership

Status: `[done]`

Goal: keep the synthetic exchange two-sided and bounded while hundreds of agents quote into the same book.

Deliverables:

- `[done]` baseline liquidity guard restores configured bid/ask ladder after each tick.
- `[done]` runtime `set_level` intents update per-agent synthetic quotes instead of replacing whole price levels.
- `[done]` `ARENA_BASELINE_LIQUIDITY_*` and `ARENA_MAX_AGENT_QUOTE_SIZE` backend configuration.
- `[done]` regression tests for empty-side reseeding, additive shared-price liquidity, quote clamping, and long-run bounded depth.

Future work:

- `[todo]` browser controls for ladder and quote-cap tuning.
- `[todo]` dynamic reference-price model for drifting market regimes.

## Phase 3A: Heavy And LangGraph Remote Agents

Status: `[done]`

Goal: keep CPU-heavy and LangGraph-based agent decisions outside the exchange/backend process while preserving the same intent protocol.

Deliverables:

- `[done]` `HeavyAnalysisAgent` support with worker-pool execution.
- `[done]` `agent-runner` process-pool configuration for heavy agents.
- `[done]` generic LangGraph remote agents using `StateGraph` observe/decide nodes.
- `[done]` Docker image dependency on `langgraph` for the runner only.
- `[done]` environment controls for heavy and LangGraph agent counts, strategy, and worker pool size.

Exit criteria:

- `[done]` Expensive agent decision work runs outside the backend/exchange process.
- `[done]` LangGraph agents emit the same `AgentIntent` contract as other agents.
- `[done]` The backend stays framework-agnostic and remains the only exchange writer.

## Phase 3: Deterministic Detectors And Incidents

Status: `[done]`

Goal: add deterministic detector logic, confidence scores, incident cards, and evidence extraction.

Scope:

- microstructure features
- confidence scores
- incident cards
- evidence extraction

Deliverables:

- `[done]` `backend/app/detectors/features.py`
- `[done]` spoofing-like detector
- `[done]` layering-like detector
- `[done]` quote-stuffing detector
- `[done]` liquidity-shock detector
- `[done]` aggregate detector score model
- `[done]` incident card UI
- `[done]` Incident Details evidence section

Core features:

- spread bps
- top-N depth
- imbalance
- message rate
- cancel-to-trade ratio
- order lifetime
- wall size ratio

Validation:

- `[done]` Normal market-making features do not alert.
- `[done]` Spoofing-like, layering-like, and quote-stuffing detector paths have focused regression tests.
- `[done]` Deterministic simulation replay is covered for same-seed runs.
- depth change percentage

Exit criteria:

- `[done]` Detector confidence scores update as the simulation runs.
- `[done]` Scenario activity can create incident cards.
- `[done]` Each incident includes structured evidence.
- `[done]` Detector behavior is deterministic for a fixed simulation seed.

## Phase 4: Nebius Benchmark And Explanation Runtime

Status: `[partial]`

Goal: integrate Nebius serverless components for offline benchmark runs and AI Investigator explanations.

Scope:

- Serverless AI Job for benchmark
- Nebius AI endpoint for AI Investigator explanations
- deployment docs
- screenshots of Nebius logs and metrics

Deliverables:

- `[done]` `serverless/jobs/detector_tournament.py`
- `[done]` `serverless/jobs/synthetic_dataset_factory.py`
- `[done]` `serverless/jobs/job_config.example.yaml`
- `[done]` `serverless/jobs/dataset_job_config.example.yaml`
- `[done]` benchmark output directory structure
- `[done]` `serverless/endpoint/app.py`
- `[done]` endpoint explanation and scenario-generation prompts
- `[done]` backend client for endpoint calls
- `[done]` `/orderbook-alert` and `/investigation-report` endpoint contracts for smart detection and report generation
- `[done]` `serverless/jobs/run_batch_experiments.py` for parallel attack/detect batches
- `[done]` `serverless/jobs/nebius_job_config.yaml`
- `[done]` `serverless/jobs/render_job_config.py` for experiment-specific Nebius job config rendering
- `[done]` `serverless/endpoint/endpoint_config.yaml`
- `[done]` reproducibility scripts under `scripts/`
- `[done]` `AI Command Center` UI destination with model selection, inference, batch execution, GPU utilization, datasets, Managed Experiment operations, and artifact access to benchmark outputs
- `[done]` `docs/nebius-deployment.md`
- `[partial]` Four sanitized runtime/UI screenshots are committed under
  `assets/screenshots/`; dedicated real Nebius console log/metric screenshots
  are still needed for the remaining review-evidence gap.

Benchmark outputs:

- Detector tournament writes:
  - `outputs/benchmark/benchmark_report.md`
  - `outputs/benchmark/metrics.csv`
  - `outputs/benchmark/results.json`
- Synthetic dataset factory writes:
  - `outputs/synthetic-dataset/events.jsonl`
  - `outputs/synthetic-dataset/incidents.jsonl`
  - `outputs/synthetic-dataset/labels.jsonl`
  - `outputs/synthetic-dataset/snapshots.parquet` when Parquet dependencies are available
  - `outputs/synthetic-dataset/snapshots.parquet.jsonl` when Parquet dependencies are unavailable
  - `outputs/synthetic-dataset/manifest.json`
- `[done]` Optional chart artifacts:
  - `outputs/benchmark/charts/f1_by_scenario.png`
  - `outputs/benchmark/charts/confidence_distribution.png`
  - `outputs/benchmark/charts/detection_latency.png`

Exit criteria:

- `[done]` The benchmark job can run multiple synthetic scenarios.
- `[done]` Precision, recall, and F1 are reported by scenario family.
- `[done]` The explanation endpoint returns structured summaries for incidents.
- `[partial]` Deployment documentation includes commands; real Nebius logs/metrics screenshots are still needed for final review.
- `[done]` Real Nebius Endpoint and Job execution is archived in the committed jury evidence bundle with S3 evidence metadata and checksums.

## Phase 4.5: Experiment Manager

Status: `[done]`

Goal: add a first-class experiment manifest layer that coordinates benchmark intent, persisted artifacts, and report visibility without duplicating Nebius Control smart-batch execution.

Deliverables:

- `[done]` `backend/app/experiments/models.py` typed experiment request, status, mode, manifest, and delete response models.
- `[done]` `backend/app/experiments/repository.py` manifest persistence under `outputs/experiments/<experiment_id>/experiment.json`.
- `[done]` `backend/app/experiments/manager.py` experiment creation, listing, lookup, deletion, deterministic attack manifest generation, local batch submission, smart-batch-compatible artifact paths, and report history indexing.
- `[done]` `backend/app/experiments/attack_manifest.py` writes deterministic attack manifests to `outputs/experiments/<experiment_id>/attacks.jsonl` without running the simulator.
- `[done]` `backend/app/experiments/artifact_normalizer.py` copies local-batch outputs into canonical experiment-root artifact names and writes `artifact_index.json` without deleting originals.
- `[done]` `backend/app/experiments/investigation_pipeline.py` runs bounded AI investigation reports over top persisted batch alerts only.
- `[done]` `backend/app/experiments/aggregator.py` writes `experiment_summary.json`, `leaderboard.json`, and `benchmark_report.md` from normalized batch artifacts.
- `[done]` `backend/app/experiments/nebius_orchestrator.py` is the only boundary for real Nebius Serverless Job command-template submission/status/log/artifact adapters.
- `[done]` REST routes on the existing experiment API: `POST /api/experiments`, `GET /api/experiments`, `GET /api/experiments/{id}`, `DELETE /api/experiments/{id}`, `POST /api/experiments/{id}/generate-manifest`, `POST /api/experiments/{id}/run-local-batch`, `POST /api/experiments/{id}/normalize-artifacts`, `POST /api/experiments/{id}/run-investigations`, `GET /api/experiments/{id}/investigations`, `POST /api/experiments/{id}/aggregate`, `GET /api/experiments/{id}/summary`, `GET /api/experiments/{id}/leaderboard`, `GET /api/experiments/{id}/report`, `POST /api/experiments/{id}/render-nebius-job-config`, `POST /api/experiments/{id}/submit-nebius`, `GET /api/experiments/{id}/jobs`, `POST /api/experiments/{id}/refresh-jobs`, and `POST /api/experiments/{id}/collect-nebius-artifacts`.
- `[done]` experiment local batches reuse the same `serverless/jobs/run_batch_experiments.py` execution path as `/api/nebius/smart-batches`.
- `[done]` local batch outputs write to `outputs/experiments/<experiment_id>/local-batch/`, with one `local_parallel_batch` job record in `outputs/experiments/<experiment_id>/jobs.jsonl`.
- `[done]` when real Nebius job execution is not configured, `submit-nebius` writes a `real_nebius_pending` job record instead of pretending cloud execution happened.
- `[done]` when `NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE` is configured, `submit-nebius` executes the command, parses the job id, writes a queued `nebius_serverless_job`, and redacts persisted command output.
- `[done]` `refresh-jobs` can use optional status/log/artifact command templates and only marks a job completed after status and artifact collection both confirm completion.
- `[done]` `collect-nebius-artifacts` collects the existing Nebius job output file format from mounted output or `NEBIUS_JOB_ARTIFACTS_COMMAND_TEMPLATE` into the canonical experiment artifact layout without fabricating missing files.
- `[done]` `/api/nebius/observatory` includes experiment job summary counts when experiment jobs exist.
- `[done]` Reports summary includes managed experiment manifests alongside older attack-builder experiments.
- `[done]` `/nebius` Managed Experiment Lab drives the lifecycle through FastAPI: create, generate manifest, run local or production Jobs, synchronize S3 artifacts, aggregate, run bounded AI Investigator reports, and expose evidence to the UI.
- `[done]` `/nebius` Real Nebius Deployment panel exposes endpoint health checks, route smoke calls, rendered job config, submit-template readiness, latest cloud job status, and cloud artifact collection state without treating pending jobs as successful real-cloud runs.
- `[done]` Detection shows managed experiments with selected summary, scenario leaderboard, markdown benchmark report viewer, AI Investigator reports, `artifact_index.json` links, and original `local-batch` artifacts.
- `[done]` `/api/nebius/smart-batches` remains unchanged for Nebius AI smart-batch execution.
- `[done]` tests for create, list, get, report visibility, delete, deterministic attack manifests, attack counts, expected labels, a 3-run local batch, fake local-batch artifact normalization, mocked Nebius investigations, sample-CSV aggregation, and missing real Nebius config.
- `[done]` local HTTP verification created a 10-row mixed-scenario experiment in mock mode and confirmed manifest rows, normalized artifacts, original local-batch files, summary, leaderboard, benchmark report, and investigation artifacts under `outputs/experiments/<experiment_id>/`.
- `[done]` more than ten production Nebius Serverless AI Job runs validated container execution, scenario generation, detector evaluation, metric aggregation, reporting, logging, and artifact persistence.
- `[done]` the compact artifact bundle is committed and the judge-facing submission index includes measured runtime/cost records plus sanitized UI screenshot evidence.

Current behavior:

- New experiments start in `manifest_generated` status.
- Attack manifests use the experiment's `attack_count`, `scenarios`, and `seed`, preserve the requested scenario mix, and support 10, 100, and 1000-row experiments.
- Expected detector labels are generated for `normal_market`, `spoofing_like_wall`, `layering_like`, `quote_stuffing`, and `liquidity_evaporation`.
- `run-local-batch` ensures `attacks.jsonl` exists, runs the local parallel batch with experiment `attack_count`, `batch_size`, and `scenarios`, then updates status to `completed` or `failed`.
- `normalize-artifacts` maps `order_book_events.jsonl`, `trades.jsonl`, `attack_labels.jsonl`, `blue_team_alerts.jsonl`, `detector_metrics.csv`, `generated_report.md`, and `manifest.json` into `events.jsonl`, `trades.jsonl`, `labels.jsonl`, `alerts.jsonl`, `detector_metrics.csv`, `benchmark_report.md`, `batch_manifest.json`, and `artifact_index.json`.
- `run-investigations` reads `alerts.jsonl` or `local-batch/blue_team_alerts.jsonl`, selects the top alerts by confidence, calls the existing Nebius investigation-report client once per selected alert, and persists JSON/Markdown reports under `investigations/`.
- The investigation path is batch-only and never calls an LLM for every simulation tick.
- `aggregate` reads `detector_metrics.csv`, alerts, labels, and investigations, reuses CSV metrics as the source of truth, and writes `experiment_summary.json`, `leaderboard.json`, and `benchmark_report.md`.
- `render-nebius-job-config` renders `nebius_job_config.rendered.yaml` for the current experiment without submitting a cloud job.
- `submit-nebius` ensures `attacks.jsonl` exists, renders `nebius_job_config.rendered.yaml`, and records either `real_nebius_pending` when no submit template is configured or a queued `nebius_serverless_job` when the configured submit command returns a job id.
- `collect-nebius-artifacts` maps Nebius job output files into the same canonical artifacts as `normalize-artifacts`; when no mounted output or artifact command output is available, the experiment status becomes `cloud_artifacts_pending`.
- `nebius_mode` supports `mock`, `local_parallel_batch`, and `real_nebius_pending`.
- `smart_batch_id` is optional and is set to the local batch id after `run-local-batch` completes.
- Reports distinguish requested manifest row count from labeled attack rows because mixed experiments can include `normal_market` rows with `expected_has_attack=false`.

## Phase 5: Polish And Submission Assets

Status: `[partial]`

Goal: package the project so it is easy to understand, review, and present.

Scope:

- README
- GitHub banner and visual identity assets
- architecture diagram
- blog post
- short video
- research notes
- sample benchmark report
- UI shell presentation controls

Deliverables:

- `[done]` polished root `README.md` with `assets/img/ai-mada.jpg` GitHub banner
- `[done]` `docs/architecture.md`
- `[partial]` architecture diagrams exist in Mermaid docs; standalone assets under `assets/diagrams/` are still optional/future work.
- `[done]` blog post draft in `docs/linkedin-technical-blog-post.md`
- `[partial]` demo narration scripts and captions under `assets/demo-video/`; rendered demo video is still missing.
- `[done]` `docs/research-notes.md`
- `[done]` committed benchmark report and production evidence under `outputs/benchmark/`
- `[done]` final disclaimer and safety language in README/docs/UI
- `[done]` professional UI shell controls: compact sidebar toggle, day/night/system theme selector, and paused-state-stable Liquidity Map
- `[done]` multiuser platform foundation with demo fallback user/workspace, global workspace/user menu, case ownership metadata, report attribution, and audit trail records.
- `[done]` compact primary navigation ordered as Data Ingestion, Arena, Control Panel, and About
- `[done]` Command Center orchestrates endpoint status, scenario generation, AI investigation, detector tournaments, jobs, and artifacts
- `[done]` Arena three-section layout: Scenario / Attack Configuration, Market, and Detection
- `[done]` About and ARD-0001 architecture diagrams show Front, Back, Agent Runners Workspace, and Nebius Serverless Cloud

### Future work

- Durable backend organization/workspace, case assignment, and audit-log persistence APIs.
- Formal benchmark artifact schema versioning and advanced Judge Mode timeline selectors.
- Richer multi-user workflows and additional scenario families.

Exit criteria:

- `[done]` A reviewer can understand the system from the README and docs.
- `[done]` The demo can be started with documented commands.
- `[done]` The architecture and runtime model are documented.
- `[partial]` The project includes research notes, a blog draft, GitHub banner, UI controls, demo narration, sanitized screenshots, and committed benchmark evidence; the rendered video and published article URL remain publication work.
- `[done]` The submission avoids claims about real market manipulation detection, trading signals, or compliance use.

## Future Roadmap: Nebius Learned-Detector Program

Status: `[in progress]`

Roadmap decision date: 2026-08-16

Status reconciliation date: 2026-08-27

GitHub Project #3 currently contains 69 items: 50 `Done`, 12 `In Progress`
and 7 `Todo`. Those counts include epics, features and child stories, so they
describe workflow state rather than additive engineering effort. The active
detector sequence is GitHub Feature #16: Wave 1 / Story #23 is in progress;
Wave 2 / Story #24 and Wave 3 / Story #25 remain Todo. No Transformer or
Transformer-to-LightGBM implementation is claimed yet.

The next learned-detector work is deliberately sequential. Governed LightGBM
v1 is already implemented locally, so the first wave is not a second LightGBM
implementation. It is the production-shaped Nebius qualification of the
existing release boundary. Transformer work starts only after that baseline is
measured and frozen. The combined design then uses causal Transformer outputs
as additional LightGBM inputs so GPU-heavy sequence learning can improve a
CPU-efficient serving path.

### Shared Data Foundation: Selective Nasdaq To Nebius S3

Status: `[in progress; 4/12 scoped capabilities complete, approximately 33%]`

This percentage describes this data-foundation feature only, not total project
completion or model quality. The repository already has four required building
blocks: a bounded streaming Nasdaq ITCH 5.x parser; checksummed normalized
Parquet; deterministic historical/hybrid replay with causal feature generation;
and governed corpus/split plus LightGBM loading contracts. The remaining eight
capabilities are roadmap work:

- `[todo]` Freeze an exact source allowlist for the seven approved public
  Nasdaq sample files, AAPL/MSFT/NVDA, the 10:00-10:30 ET windows, depth 10 and
  chronological fold assignments.
- `[todo]` Add a Nebius acquisition/preparation runner that never crawls or
  mirrors Nasdaq and rejects undeclared hosts, redirects, files and byte counts.
- `[todo]` Download each approved full-market gzip only when sequential ITCH
  extraction requires it; use ephemeral Job scratch or private lifecycle-bound
  quarantine and retain only selected rows in durable S3 releases.
- `[todo]` Normalize all three selected instruments in one pass per source and
  publish immutable provenance, quality, replay and feature inventories.
- `[todo]` Freeze one root corpus/split identity and publish development/test
  `tabular_projection_v1` artifacts for governed LightGBM training and scoring.
- `[todo]` Publish fold-isolated `sequence_projection_v1` artifacts with causal
  cutoffs, masks and deterministic row-to-sequence identities for Wave 2.
- `[todo]` Adapt the Transformer training/scoring programs to consume that
  sequence projection, then materialize `transformer_feature_release_v1` only
  from a verified standalone checkpoint.
- `[todo]` Exact-join Transformer scores/embeddings to the tabular rows for the
  Wave 3 cascade; reject stale/incompatible features and fall back visibly to
  the verified tabular LightGBM model.

All four candidates—rules, tabular LightGBM, standalone Transformer and the
Transformer-to-LightGBM cascade—must use identical immutable evaluation rows.
The purpose is to test whether relevant historical microstructure and causal
temporal context improve predictions; improvement is an acceptance result to
measure, not a roadmap claim. The detailed transfer, retention, split and
consumer contracts are in the
[public market-data plan](nebius-public-market-data-lightgbm-plan.md).

### Execution Order And Gates

| Wave | Status | Primary Nebius resource | Outcome | Exit gate before next wave |
| --- | --- | --- | --- | --- |
| 1. Nebius LightGBM baseline | `[in progress]` | CPU Serverless AI Jobs, Standard Object Storage, shared MLflow | Train, calibrate, evaluate and package governed LightGBM v1 on immutable cloud inputs; publish runtime, throughput and cost evidence | Reproducible bundle verifies; declared quality/latency gates pass; cost per million scored rows is measured; no frozen-test reruns for tuning |
| 2. Market-sequence Transformer | `[todo]` | Time-boxed GPU Serverless AI Jobs with CPU preprocessing/evaluation | Train and calibrate a causal sequence challenger on the same split and label contracts | Standalone Transformer bundle verifies; GPU hours/cost and inference latency are recorded; comparison with Wave 1 uses identical evaluation rows |
| 3. Transformer to LightGBM cascade | `[todo]` | Ephemeral GPU batch feature extraction followed by CPU Serverless AI Jobs | Materialize versioned causal Transformer embeddings/scores and train LightGBM with those features plus the existing tabular set | Ablation proves or rejects incremental value; serving-cost and failure-mode gates pass; champion/rollback decision is signed |

### Wave 1: Qualify LightGBM On Nebius First

Goal: establish the cheapest, fastest learned-detector baseline before paying
for sequence-model development.

Planned work:

- `[done]` Establish the Wave 1 project, budget controls, four governed bucket
  boundaries, three least-privilege identities, development-to-final denial
  proof, Container Registry path, and shared MLflow stack.
- `[done]` Replace the failed S3 filesystem-mount design with the July-proven
  pattern: MysteryBox environment credentials plus prefix-scoped S3 API
  download/upload through ephemeral job disk.
- `[done]` Close G4. Two mount-based Jobs stalled before container start;
  three no-volume Jobs failed on an old image or incorrect entrypoint; attempt
  6 reached the runner but failed before training on an AWS CLI v1/v2 pager
  incompatibility. Attempt 7 then completed the governed workload, matched the
  reviewed resources and image identity, and published 25 result objects plus
  `SUCCESS`. Seven of the 20 development-job slots are consumed and 13 remain.
  Spend was reconciled at USD 8.57 including VAT; all 16 gates passed, MLflow
  is stopped and G5 is unlocked. No rerun is authorized or needed.
- `[in progress]` Build the selective official-public-sample data foundation,
  root corpus/split and fold-isolated tabular/sequence projections required for
  G5-G8 and the later Transformer/cascade waves.
- `[todo]` Run deterministic-repeat, tuning, calibration and one governed
  evaluation workflow through CPU Serverless AI Jobs.
- `[todo]` Store immutable inputs and outputs in Standard Object Storage and
  index hashes, parameters, metrics and artifact pointers in shared MLflow.
- `[todo]` Compare rules and LightGBM on identical rows, including per-family
  recall, PR-AUC, clean-window false alerts, detection delay and calibration.
- `[todo]` Measure wall-clock duration, rows/second, CPU utilization, peak
  memory, active compute time and estimated cost per run and per million rows.
- `[todo]` Publish a verified model bundle with candidate and rollback
  identities. Promotion remains a governed decision, not an automatic result
  of a single metric.

Why this is first:

- LightGBM training and inference are CPU-friendly and already implemented.
- Serverless Jobs terminate when work completes, avoiding idle VM cost while
  preserving container, log and resource evidence.
- Standard Object Storage is the low-cost durable boundary; enhanced-throughput
  storage is deferred until measured I/O shows that it is needed.
- The resulting quality, latency and cost baseline determines whether a
  Transformer is worth its additional complexity and GPU spend.

Wave 1 exit criteria:

- Three identical repeat runs produce matching governed identities and
  equivalent metrics within declared tolerances.
- The final-test fold is opened once after operating modes are frozen.
- Cloud artifacts include job ID, image digest, Git SHA, input hashes,
  checksums, resource shape, timestamps, measured throughput and estimated
  cost.
- Performance claims remain scoped to synthetic/fixture or separately governed
  licensed data, as applicable.

### Wave 2: Add The Market-Sequence Transformer

Goal: measure whether causal temporal context improves the frozen Wave 1
baseline enough to justify GPU training and a larger operational surface.

Planned work:

- `[todo]` Define a versioned causal sequence contract with event-time cutoff,
  sequence length, stride, padding/masking, feature ordering and split binding.
- `[todo]` Use CPU Jobs for sequence materialization and time-boxed GPU Jobs for
  training; do not use the vLLM investigation endpoint for this classifier.
- `[todo]` Run architecture-size, sequence-length, encoding, class-weight/focal
  loss and seed-stability experiments using validation only.
- `[todo]` Register preprocessing, model weights, calibration, thresholds,
  checkpoint hash, parameter count, GPU hours and cost metadata.
- `[todo]` Compare standalone Transformer and LightGBM on the exact same frozen
  observations and operational gates.

Wave 2 exit criteria:

- No future event or post-cutoff aggregation enters a sequence representation.
- GPU endpoints/jobs are bounded by timeout and budget and leave no idle GPU
  compute after the campaign.
- The Transformer either clears a predeclared incremental-value gate or is
  retained as research evidence without promotion.

### Wave 3: Combine Transformer Outputs Into LightGBM

Goal: test a cost-aware cascade in which the Transformer becomes an offline or
bounded-batch temporal feature extractor and LightGBM remains the final
tabular decision layer.

Planned work:

- `[todo]` Freeze a `transformer_feature_release_v1` contract containing the
  source model/checkpoint hash, sequence contract hash, row/replay identity,
  causal cutoff, embedding or score schema, null policy and content checksum.
- `[todo]` Materialize Transformer-derived features without exposing labels or
  future events, then join them to `lob_features_v2` only by governed row and
  replay identities.
- `[todo]` Train a new LightGBM candidate with the existing feature set plus
  Transformer scores/embeddings. Do not overwrite the Wave 1 model family.
- `[todo]` Run ablations for tabular-only LightGBM, standalone Transformer,
  Transformer-to-LightGBM, and any late-fusion comparator on identical inputs.
- `[todo]` Measure incremental quality against GPU feature-generation cost,
  CPU inference throughput, staleness, unavailable-feature fallback and
  operational complexity.

Wave 3 exit criteria:

- The cascade wins only if it clears predeclared quality, clean-window,
  calibration, latency, throughput and cost gates.
- The Wave 1 tabular LightGBM bundle remains a verified rollback and fallback
  when Transformer features are absent, stale or incompatible.
- The promotion record identifies every model, feature, split and evaluation
  hash and documents whether the cascade was accepted or rejected.

### Feature: Extensible Inbound Data Adapter Framework

Status: `[todo; GitHub Feature #87; partial source-adapter foundation exists]`

Goal: make future batch or streaming market-data sources—including vendors and
formats not known today—addable through a versioned adapter package instead of
source-specific changes across ingestion, replay, feature and model code. This
does not imply automatic understanding of an unknown format; each source still
requires an explicitly reviewed adapter implementation and mapping.

Current foundation:

- `IngestionSourceAdapter` already defines candidate discovery and bounded
  import, and LOBSTER/Nasdaq ITCH implement peer adapters.
- Normalized Parquet, source-neutral manifests, canonical Java replay and
  causal features provide a usable downstream target.
- Registration and source types are still hard-coded, capability discovery is
  absent, and there is no third-party adapter conformance kit.

Planned work:

- `[todo]` Version an `inbound_data_adapter_v1` descriptor and protocol for
  discovery, authorization, acquisition/streaming, validation, normalization,
  provenance, retention and capability reporting.
- `[todo]` Add an explicit registry/factory so an approved adapter can be added
  without editing the core ingestion service or downstream model programs.
- `[todo]` Keep vendor fields inside versioned provenance/extensions while
  requiring canonical events, snapshots, timestamps, lifecycle semantics and
  immutable checksummed manifests at the adapter output.
- `[todo]` Support declared batch, object-storage and bounded streaming modes
  with allowlists, secret isolation, byte/time/resource quotas and fail-closed
  schema/version negotiation.
- `[todo]` Publish a conformance kit with golden fixtures for deterministic
  repeat import, causal-prefix invariance, lifecycle integrity, malformed-input
  rejection, resource bounds and Java replay equivalence.
- `[todo]` Require licence/terms and redistribution metadata, retention policy,
  source hash, adapter/config hash and a review record before a new adapter can
  feed a governed corpus.

Exit gate: a fixture third adapter can be registered through configuration,
passes the conformance kit, produces the canonical immutable dataset contract
and runs through replay/features without source-specific downstream branches.

### Feature: Pluggable Detector Adapter And Test Harness

Status: `[todo; GitHub Feature #88; model-specific adapter and external-alert evaluation foundations exist]`

Goal: let LOB Arena test LightGBM, Transformer, the hybrid cascade, approved
third-party detectors and future detector extensions through one versioned
adapter contract and the same governed scenarios, rows, metrics and evidence
pipeline. An adapter may be in-process, a remote API, a container or a batch
scorer, but it never receives exchange-write, label or future-data access.

Current foundation:

- The governed benchmark already accepts a fully verified LightGBM release as
  an external alert source, and detector tournaments produce normalized metrics
  and artifacts.
- The existing runtime detector adapter is deliberately LightGBM-specific;
  Transformer and cascade implementations do not yet exist, and there is no
  common detector contract, registry or black-box conformance suite.

Planned work:

- `[todo]` Version a `detector_adapter_v1` capability, request, response,
  health and error contract for in-process, synchronous API, asynchronous and
  batch scorers.
- `[todo]` Send only the approved causal event/feature prefix plus governed row,
  replay and cutoff identities; never send labels, future events, reviewer
  decisions or unopened final-fold metadata.
- `[todo]` Normalize probabilities, scores, alerts, evidence pointers, model
  version, timing and failure state into the canonical detector observation
  schema used by evaluation and reports.
- `[todo]` Implement contract wrappers for rules, governed LightGBM,
  standalone Transformer and Transformer-to-LightGBM cascade, plus a reference
  external detector adapter and extension template.
- `[todo]` Add an approved adapter registry with endpoint/image allowlists,
  scoped secrets, TLS/auth policy, timeouts, retry/idempotency rules, rate and
  payload limits, backpressure, circuit breaking and complete audit metadata.
- `[todo]` Add a conformance harness for contract compatibility, deterministic
  replay where declared, causal isolation, row coverage, malformed output,
  timeout/partial failure, calibration, latency, throughput and data-minimizing
  logs/artifacts.
- `[todo]` Run every registered detector type through the existing tournament
  and governed paired metrics on identical immutable rows, reporting
  unavailable or incomparable outputs explicitly rather than imputing success.

Exit gate: the LightGBM wrapper, a Transformer-compatible fixture, a hybrid
wrapper fixture and one out-of-process detector all pass the same conformance
suite and produce comparable signed evidence. Java remains the only exchange
writer, and failure of one adapter does not disable the other verified detector
paths.

### Cost And Operations Guardrails

- Use Serverless AI Jobs for bounded training, batch inference and evaluation;
  they use Compute pricing but remove idle job VMs and disks after completion.
- Use CPU resources for LightGBM, preprocessing, calibration and final cascade
  scoring. Reserve GPUs for Transformer training and bounded feature
  materialization.
- Keep interactive GPU endpoints stopped by default and delete them after a
  campaign when fast restart is unnecessary; stopped endpoint disks may still
  incur storage cost. The existing vLLM endpoint remains an AI Investigator
  surface and is not a detector-training dependency.
- Use Standard Object Storage in the same region by default. Promote selected
  data to Enhanced Throughput only after a measured I/O bottleneck and explicit
  cost comparison.
- Every campaign has a maximum job count, timeout, resource preset and spending
  envelope. Record actual billed usage before increasing scale.
- No Transformer or cascade work begins until the preceding wave has a verified
  evidence bundle and recorded go/no-go decision.

Primary architecture records:

- `docs/nebius-lightgbm-wave1-implementation-plan.md`
- `docs/architecture/ARD-0035-nebius-lightgbm-first.md`
- `docs/architecture/ARD-0036-market-sequence-transformer.md`
- `docs/architecture/ARD-0037-transformer-to-lightgbm-cascade.md`
