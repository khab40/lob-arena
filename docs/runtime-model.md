# Runtime Model

This document describes how the live arena runs, how agents participate in the exchange simulator, what the main UI screens show, and how runtime APIs and Nebius components fit together.

The continuous interactive arena and the versioned deterministic batch kernel are Java-only production authorities. Python remains for AI/ML, LangGraph-capable runner work, experiments, and serverless jobs.

## Live Exchange Loop

The exchange simulator ticks continuously while the arena is running. A normal local cadence is one tick every 250-500 ms, fast enough for a live visual demo while still leaving the UI readable.

```mermaid
flowchart TD
    Tick["Java arena tick<br/>250-500 ms"]
    Remote["Python agent-runner<br/>normal, heavy, ML/LangGraph"]
    Scenario["Java bounded scenarios"]
    Sort["Validate + deadline-filter + deterministic sort"]
    Exchange["Single-writer exchange + matching"]
    Guard["Restore baseline two-sided liquidity"]
    Detect["Feature extraction + deterministic detectors"]
    Persist["Events, incidents, snapshots, reports"]
    UI["WebSocket arena_state"]

    Tick -->|"MarketSnapshot"| Remote
    Tick --> Scenario
    Remote -->|"AgentIntent"| Sort
    Scenario -->|"labeled intent"| Sort
    Sort --> Exchange
    Exchange --> Guard
    Guard --> Detect
    Detect --> Persist
    Detect --> UI
    UI --> Tick
```

Java owns the clock and publishes each state update to connected browser clients. Java REST endpoints control start, pause, reset, scenario launch, incident lookup, and replay. FastAPI owns incident explanation, AI, experiment, and serverless APIs.

Agents run behind Python `agent-runner` `/decide` endpoints because this is the retained AI/ML and LangGraph boundary. Java concurrently gathers responses under a deadline, validates them, and sorts intents by tick, latency bucket, agent id, sequence, and kind before single-writer book mutation.

Runtime scale knobs:

```text
ARENA_DATA_RETENTION_DAYS=1
ARENA_REMOTE_AGENT_URLS=http://agent-runner:9100
ARENA_REMOTE_AGENT_TIMEOUT_MS=250
ARENA_TICK_INTERVAL_MS=500
ARENA_WEBSOCKET_STREAM_INTERVAL_MS=500
JAVA_ARENA_BASE_URL=http://java-kernel:8080
JAVA_ARENA_TIMEOUT_SECONDS=2
AGENT_RUNNER_AGENT_COUNT=24
AGENT_RUNNER_MAX_AGENT_COUNT=48
AGENT_RUNNER_HEAVY_AGENT_COUNT=0
AGENT_RUNNER_MAX_HEAVY_AGENT_COUNT=2
AGENT_RUNNER_HEAVY_AGENT_WORKERS=1
AGENT_RUNNER_MAX_HEAVY_AGENT_WORKERS=1
AGENT_RUNNER_LANGGRAPH_AGENT_COUNT=0
AGENT_RUNNER_MAX_LANGGRAPH_AGENT_COUNT=4
AGENT_RUNNER_LANGGRAPH_STRATEGY=liquidity_rebalancer
```

Docker Compose starts `java-kernel`, `agent-runner`, `backend`, and `frontend` together. Agents that miss the Java-side decision deadline are skipped for that tick. Runtime `set_level` intents update bounded per-agent synthetic quotes, worker-side `AGENT_RUNNER_MAX_*` values cap runner size, and Java restores baseline two-sided liquidity after each tick. Java writes arena events, attacks, incidents, and snapshots under `ARENA_OUTPUT_DIR`; FastAPI applies retention to its AI/serverless artifacts.

A runner exposes `POST /decide`, receives a read-only `MarketSnapshot`, and returns `AgentIntent` JSON. In Compose, Java points at `http://agent-runner:9100` by default. Only Java applies accepted intents to the exchange.

Heavy agents run expensive decision functions through a worker pool inside `agent-runner`. Generic LangGraph agents use `StateGraph` with `observe` and `decide` nodes, then emit the same `AgentIntent` contract. Java is deliberately unaware of whether an intent came from a simple function, ML model, process-pool worker, or LangGraph graph.

## UI Shell Runtime

The shared shell keeps presentation preferences in browser-local state, not backend state. Theme mode is stored as `lob-arena.themePreference` with `system`, `light`, and `dark` values. System mode follows `prefers-color-scheme` and applies the resolved mode through the document `data-theme` attribute. Shared widgets, status chips, order-book levels, Recharts timelines, tooltips, and the Liquidity Map canvas read semantic theme tokens rather than fixed dark colors.

Arena timeline-style widgets should only append frames when the backend tick advances. This keeps the Liquidity Map visually stable while the arena is paused or has not started from the UI.

## Agent Model

### Always-On Agents

These agents provide baseline market activity whenever the arena is running.

| Agent | Runtime Behavior |
| --- | --- |
| `TopOfBookMarketMaker` | Maintains bid and ask liquidity around the current mid price. |
| `DeterministicNoiseTrader` | Sends deterministic small depth updates to create background activity. |
| `PeriodicLiquidityTaker` | Occasionally sends aggressive buy or sell orders that consume visible liquidity. |
| Additional generated normal agents | Scale the same lightweight decision model to hundreds of registered agents. |

### Scenario Agents

Scenario agents are launched manually from the UI. They run for a bounded interval and inject labeled synthetic behavior for detector and explanation demos.

| Scenario Agent | Runtime Behavior |
| --- | --- |
| `SpoofingLikeAgent` | Places a large short-lived visible wall, then cancels before execution. |
| `LayeringLikeAgent` | Places multiple same-side levels, then cancels them as a group. |
| `QuoteStuffingLikeAgent` | Generates many place and cancel updates in a short time window. |
| `LiquidityEvaporationScenario` | Removes visible depth quickly and stresses liquidity-shock features. |
| `PanicSelloffScenario` | Sends aggressive sell pressure to simulate a sudden disorderly move. |

## Main UI Screens

### 1. Arena

The Arena screen is the live operator view.

Top bar:

```text
[Running/Paused] [Tick] [Selected Scenario] [Connection/Source] [Start] [Pause] [Reset]
```

Left section - Scenario / Attack Configuration:

- selected scenario and attack configuration
- Start / Pause / Reset controls
- attack builder and scenario launch controls

Center section - Market:

- Standard or Battlefield visualization mode
- order book ladder
- mid-price, spread, depth, and microstructure metrics
- switchable Heatmap and Timeline secondary views

Right section - Detection:

- detector confidence
- Evidence / Timeline tabs
- Incident Details with AI Investigator and AI cost/latency metrics

Scenario launcher examples:

```text
[Spoofing-like Wall]
[Layering-like Pattern]
[Quote Stuffing Burst]
[Liquidity Evaporation]
```

### 2. Incident Details

Incident Details opens when the user selects an incident card or when a new high-severity alert is raised.

```text
Suspicious Event Detected

Type: Spoofing-like liquidity wall
Agent: ABUSER_01
Confidence: 0.91
Severity: High

Evidence:
- ask depth increased 480%
- order lifetime 1.8 sec
- cancellation before execution
- imbalance shifted from +0.08 to -0.74

AI explanation:
...
```

Incident Details should show detector evidence first, then the generated explanation. AI text is supporting context, not the source of truth.

### 3. Detection / Experiments Benchmark Review

Detection and Experiments summarize offline detector quality by scenario family, replay evidence, generated reports, and Managed Experiment artifacts.

| Scenario | Precision | Recall | F1 |
| --- | ---: | ---: | ---: |
| Spoofing-like wall | 0.91 | 0.86 | 0.88 |
| Layering-like | 0.84 | 0.79 | 0.81 |
| Quote stuffing | 0.96 | 0.92 | 0.94 |
| Liquidity shock | 0.89 | 0.83 | 0.86 |

## Historical And Hybrid Runtime

```mermaid
flowchart TD
    Source["Validated normalized LOBSTER dataset"]
    Batch["Read next bounded source batch"]
    Historical["Apply historical phase"]
    Scenario["Apply synthetic scenario phase"]
    Combined["Combined Java live book"]
    Checkpoint["Canonical combined-book checkpoint"]
    Detector["Deterministic detectors"]
    Labels["Separate synthetic labels"]

    Source --> Batch
    Batch --> Historical
    Historical --> Scenario
    Scenario --> Combined
    Combined --> Checkpoint
    Combined --> Detector
    Scenario --> Labels
    Checkpoint --> Batch
```

Historical-only and hybrid modes use the same Java book and source window. In
historical-only mode the synthetic phase is empty. In hybrid mode, the scenario
runs after the current source batch and can read the reconstructed current book
but not unread Parquet rows. Historical identities use `HIST:` and synthetic
identities use `SYN:`. Only the synthetic scenario produces attack labels.

## Runtime Ownership

| Area | Implemented owner | Main responsibility |
| --- | --- | --- |
| Integer order book, matching and deterministic kernel | `java/simulation-kernel` | FIFO book mutation, execution, canonical ordering, hashing, scenario programs and batch determinism |
| Live scheduling, historical replay, detectors and browser state | `java/control-plane` | Single-writer arena, LOBSTER/CSV adapters, REST, WebSocket, incidents, journals and agent orchestration |
| Remote agent decisions | `agent-runner` | Convert read-only `MarketSnapshot` into bounded `AgentIntent`; never mutate the book |
| LOBSTER ingestion and local registry | `backend/app/data_ingestion` | Discover, validate, normalize and atomically register immutable local datasets |
| Corpus, features and ML release boundary | `backend/app/corpus`, `backend/app/features`, `backend/app/ml` | Independent negative labels, frozen splits, causal features and hash-bound model contracts |
| AI, experiments and Nebius jobs | `backend/app/api`, `backend/app/nebius`, `backend/app/experiments` | Evidence explanation, scenario generation, batch orchestration and artifact collection |
| Shared experiment tracking | Docker `mlflow` profile | Authenticated run/model index backed by PostgreSQL and S3-compatible artifacts |

## Offline ML Lifecycle

The shared tracking server is outside the live exchange path:

```mermaid
graph LR
    Events["Canonical events + snapshots"]
    Truth["Separate labels + reviewed negatives"]
    Corpus["Signed corpus + frozen split"]
    Features["lob_features_v1"]
    Model["LightGBM v1<br/>next delivery"]
    Evaluation["Rules vs model evaluation"]
    Release["Checksummed model release"]
    MLflow["MLflow tracking + registry"]

    Events --> Corpus
    Truth --> Corpus
    Corpus --> Features
    Features --> Model
    Model --> Evaluation
    Evaluation --> Release
    Corpus -. "hashes" .-> MLflow
    Model -. "development runs" .-> MLflow
    Release -. "verified artifacts" .-> MLflow
```

MLflow does not receive exchange write authority, decide which windows are
clean, fit preprocessing, select thresholds, open the test fold, or sign a
release. Those responsibilities remain in the governed repository pipelines.

## API Ownership

Representative Java control-plane endpoints:

```text
GET  /api/kernel/status
GET  /api/arena/state
GET  /api/arena/exchange-events
GET  /api/arena/historical-datasets
POST /api/simulation/start
POST /api/simulation/pause
POST /api/simulation/reset
POST /api/arena/data-source
POST /api/arena/replay-comparison
POST /api/scenarios/{scenario}
GET  /api/incidents
```

Representative FastAPI AI/data endpoints:

```text
GET    /health
GET    /api/status
GET    /api/data-ingestion/lobster/candidates
POST   /api/data-ingestion/lobster/candidates/{candidate_id}/import
GET    /api/data-ingestion/datasets
GET    /api/nebius/status
POST   /api/incidents/{incident_id}/explain
POST   /api/nebius/tournament/start
GET    /api/experiments
POST   /api/experiments
```

The frontend routes arena traffic directly to Java where practical and uses
FastAPI for ingestion, AI, experiment, and serverless functions. Consult the
generated FastAPI OpenAPI page and Spring controller tests for the complete
current contract.

## Related Documentation

- [High-Level Architecture](architecture.md)
- [Functional Overview](FUNCTIONAL_OVERVIEW.md)
- [Use Cases](USE_CASES.md)
- [Hybrid Dataset Validation](hybrid-dataset-validation.md)
- [Shared MLflow Tracking Server](mlflow-tracking-server.md)
