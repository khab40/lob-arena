# LOB Arena

**Historical and synthetic order-book validation for market surveillance research.**

![LOB Arena banner](assets/img/01-lob-arena-banner.jpg)

LOB Arena validates licensed historical data, replays it through a Java exchange,
injects bounded synthetic attacks, and compares detectors using reproducible
evidence. Deterministic rules produce incidents; AI explains their evidence.
Historical activity is never automatically labeled benign or abusive. The
platform provides neither trading signals nor compliance decisions.

## Start here

| Task | Guide |
Prometheus and Grafana form an optional, read-only observability plane; neither is
in the simulation or detector decision path. Prometheus scrapes operational
metrics from Java Spring Actuator, FastAPI, and the agent runner every 15 seconds
and stores the resulting time series. Grafana queries Prometheus and presents
provisioned dashboards for end-to-end health, Java/JVM behavior, component
latency, and bottleneck isolation. These runtime signals complement—but do not
replace—the precision, recall, F1, and latency artifacts produced by detector
tournaments.

```text
backend/          FastAPI AI/ML, experiments, serverless, and evidence APIs
java/             Java 25 arena, exchange kernel, orchestration, REST, and WebSocket
agent-runner/     Out-of-process normal, heavy, and LangGraph agents
frontend/         React UI for the arena, investigations, and tournaments
serverless/       Nebius Endpoint and Job images, prompts, and runners
deployments/      Shared MLflow and Nebius deployment assets
scripts/          Deployment, evidence, CI, and secret utilities
docs/             Architecture, deployment, safety, and benchmark docs
outputs/          Commit-safe benchmark artifacts
evidence/         Frozen deployment evidence bundles
```

## Screenshots

| Runtime and cloud status | AI Investigation Team |
| --- | --- |
| Run the application | [Quickstart](docs/deployment/QUICKSTART.md) |
| Understand ownership and data flow | [Architecture](docs/architecture.md) |

## Quick start

```bash
git clone https://github.com/khab40/lob-arena.git
cd lob-arena
cp .env.example .env
docker compose up --build
```

Open:

- Frontend: http://localhost:5173
- Retained Python AI API: http://localhost:8000
- Java control plane: http://localhost:8081/api/kernel/status
- Same-origin WebSocket: ws://localhost:5173/ws/arena

The default Compose path builds `java-kernel`, `agent-runner`, `backend`, and `frontend` from source with serverless access disabled and `NEBIUS_ENDPOINT_MODE=mock`. Java owns the deterministic kernel, live arena, scenarios, detectors, incidents, orchestration, REST controls, and WebSocket. Python retains AI/ML, experiments, and serverless work. Local Mock requires no Nebius credentials, private images, or GPU/vLLM runtime. The backend entrypoint clears stale endpoint, job-command, and object-storage values unless `NEBIUS_SERVERLESS_ENABLED=true`.

### Historical and hybrid replay

The Java exchange replays existing `canonical_csv_v1` order events, LOBSTER
message/order-book imports, and normalized Nasdaq TotalView-ITCH 5.x streams
through the same integer matching engine used by synthetic runs. LOBSTER
ingestion remains the existing paired-file workflow:
the Python adapter validates the public six-column message and `4 × depth`
order-book formats, writes aligned Parquet plus a checksummed manifest, and the
Java exchange reconstructs each contemporaneous book state from that immutable
stream.

The peer `nasdaq_itch` adapter streams length-prefixed plain or gzip ITCH input
without materializing an uncompressed session. It resolves daily Stock Locate
mappings and reconstructs `A`, `F`, `E`, `C`, `X`, `D`, and `U` visible-order
lifecycles for one symbol and bounded time window. The adapter emits the same
aligned Parquet columns plus additive ITCH provenance, while its manifest binds
`source_type=nasdaq_itch`, `format=itch_parquet_v1`, `venue=XNAS`, parser/config
versions, compressed-stream SHA-256, filters, message counts, output hashes, and
disk limits. Unsupported non-book messages are counted but never interpreted as
book mutations.

The small public [LOBSTER-compatible fixture](data/lobster/README.md) contains
synthetic test records covering add, partial cancel, delete, visible/hidden
execution, cross trade, and halt messages. It can be imported from **Data
Ingestion** without redistributing licensed market data. The older
[canonical CSV fixture](data/historical/README.md) remains supported.
The [synthetic ITCH fixture](data/nasdaq-itch/README.md) covers every supported
transition and contains no real Nasdaq session data.

In the Arena UI:

1. Import a LOBSTER pair or a bounded Nasdaq ITCH symbol window in **Data Ingestion**.
2. Select **Historical control**, choose the imported dataset, load it, and
   start replay for an unlabeled control run.
3. Select **Hybrid + attacks**, load the same dataset, then launch the existing
   spoofing-like or layering-like attack from **Scenario Setup**. Attacks are
   intentionally launched from the UI/API after the replay source is loaded;
   the historical importer never creates attacks or labels.

Historical records are immutable and never become benign ground truth. Only the synthetic overlay supplies attack labels, and detector features do not contain scenario labels or synthetic-only metadata. Historical and synthetic participant/order IDs use separate `HIST:` and `SYN:` namespaces.

At each replay step, records are ordered by exchange timestamp, historical
phase, source priority, actor ID, source sequence, and insertion sequence.
Historical records therefore win equal-timestamp ties; the attack generator
then reads only the reconstructed live book. It never reads a future Parquet
row. Batch comparisons may specify exactly one `trigger_source_sequence` or
`trigger_timestamp_ns`. Control and hybrid runs split at the same point, all
historical rows tied at that exchange timestamp are applied first, and later
rows are deferred. The attack seed is derived from the configured master seed,
dataset, scenario family, deterministic scenario number, and schedule hash.
The schedule hash also binds bounded parameters for the existing scenario
family. Synthetic-only and manually launched runs keep their previous defaults.

Example request bodies are committed as
[historical-control.json](configs/replay/historical-control.json) and
[hybrid-with-ui-attack.json](configs/replay/hybrid-with-ui-attack.json). Load
one with:

```bash
curl -sS -X POST http://localhost:8081/api/arena/data-source \
  -H 'Content-Type: application/json' \
  --data @configs/replay/historical-control.json
```

The Java comparison endpoint executes both modes over the same source:

```bash
curl -sS -X POST http://localhost:8081/api/arena/replay-comparison \
  -H 'Content-Type: application/json' \
  -d '{"dataset_id":"itch-aapl-window","scenario_family":"spoofing_like_wall","master_seed":42,"trigger_source_sequence":125000,"scenario_parameters":{"quantity_lots":30000},"max_ticks":10000}'
```

To reuse the tournament precision/recall/F1 calculation and create a
checksummed, signed validation bundle:

```bash
backend/.venv/bin/python scripts/run_historical_replay_comparison.py \
  --base-url http://localhost:8081 \
  --dataset sample-btcusdt-0945 \
  --scenario spoofing_like_wall \
  --master-seed 42 \
  --trigger-source-sequence 125000 \
  --scenario-parameters '{"quantity_lots":30000}' \
  --signing-key /secure/lob-validation-key.pem \
  --signer "Market Surveillance QA" \
  --output outputs/historical-replay/sample-btcusdt-0945
```

The bundle contains the control, hybrid, metrics, validation, signed manifest,
checksum, Ed25519 signature, and public-key artifacts. The signed manifest
binds every evidence payload by SHA-256 and byte size. It records Java-verified
Parquet hashes, repeat-run determinism, full-stream/historical/synthetic
hashes, source/event counts, injected-order lifecycle, detector metrics, and
before/during/after causal locality. Outside the labelled attack
neighbourhood, paired books must match exactly and book/event-flow metrics must
pass the documented statistical equivalence bounds. See
[Hybrid Dataset Validation](docs/data/hybrid-dataset-validation.md) for the
methodology, signing trust boundary, verification commands, and limitations.
For repeatable client deliveries, use the
[Client Historical Dataset Validation Runbook](docs/data/client-historical-dataset-validation-runbook.md).
The public fixture includes a
[signed sample report](data/lobster/fixture/validation/validation-report.json).

Known limitation: LOBSTER exposes aggregate depth snapshots but not participant
identity, and selected windows can begin after orders were originally entered.
The replay therefore represents historical liquidity as deterministic
per-price `HIST:` level orders while preserving every source message sequence
and its aligned post-event snapshot. Synthetic orders remain separate and
retain their own lifecycle. This is deterministic and faithful at the visible
depth supplied by LOBSTER, but it cannot recover queue priority or participant
identity absent from the source files.
The configured replay batch (`LOB_ARENA_HISTORICAL_ROWS_PER_TICK`, default
`250`) controls throughput, not injection precision. Scheduled comparisons
partition a prefetched batch at the resolved source row, include all
equal-timestamp historical rows, and defer the remainder.

Architecture decisions are recorded in
[ARD-0022](docs/architecture/ARD-0022-historical-market-data-ingestion.md) for
ingestion/storage and
[ARD-0032](docs/architecture/ARD-0032-nasdaq-itch-ingestion.md) for the ITCH
adapter and source-neutral manifest contract, and
[ARD-0033](docs/architecture/ARD-0033-deterministic-hybrid-scheduling.md) for
exact in-window scheduling and evidence bindings, and
[ARD-0023](docs/architecture/ARD-0023-hybrid-historical-replay.md) for hybrid
ordering, provenance, seed derivation, label isolation, metrics, and artifacts.

### ITCH-calibrated interactive simulation

`market_profile_v1` compiles a normalized ITCH training window into versioned
empirical distributions for arrival intensity, inter-event time, order size,
distance from touch, lifetime, cancellation/execution mix, spread, top depth,
imbalance, volatility, refill, and resilience. The compiled parameters select
the synthetic reference price, ladder spacing, level quantities, depth slope,
and seeded reference-price update cadence. The existing hardcoded BTCUSDT
configuration remains the regression control.

Build a profile and evaluate it against a distinct held-out ITCH window:

```bash
backend/.venv/bin/python scripts/build_market_profile.py \
  --dataset-dir data/processed/lobster/itch-aapl-training \
  --profile-id aapl-2026-01-02-v1 \
  --output configs/market-profiles/aapl-2026-01-02-v1.json \
  --held-out-dataset-dir data/processed/lobster/itch-aapl-held-out \
  --report-output outputs/calibration/aapl-2026-01-02-v1-realism.json \
  --arena-base-url http://localhost:8080
```

For held-out evaluation, the selected profile must be visible to the running
Java control plane at the output path. The evaluator captures calibrated and
hardcoded Java runs twice with the same seed, rejects trace mismatches, computes
six pre-registered quantile distances from the observed simulator states,
includes actual before/during/after liquidity-evaporation response metrics, and
emits a canonical report SHA-256. It rejects reuse of the training dataset as
holdout. The Arena's **Calibrated synthetic** source loads profiles
from `configs/market-profiles`; Java validates the canonical profile checksum,
binds the profile SHA and master seed to each run, stays the single writer, and
updates the reference path deterministically. The committed
[`fixture-aapl-itch-v1`](configs/market-profiles/fixture-aapl-itch-v1.json) is
derived only from the synthetic binary fixture and is a contract example, not
evidence of real-market realism. Real Nasdaq session files and derived bounded
windows remain local/licensed artifacts and are never committed.

See [ARD-0034](docs/architecture/ARD-0034-itch-market-profile-calibration.md)
for the profile, runtime, evaluation, and trust-boundary decision.

### Model-ready causal features

The retained Python AI/ML layer converts the Java canonical event stream from
LOBSTER, synthetic, or hybrid runs into the same versioned causal feature
schema and a governed LightGBM v1 binary detector. It writes typed Parquet, run
metadata, and a feature-quality report. The Phase 1 governed loader requires an
externally hash-anchored feature release, revalidates clean adjudications,
reconstructs labels from governed ground truth, binds market units to canonical
Java replays, exposes only supervised rows, and separates development access
from the frozen test fold. Unlabeled history never becomes benign ground truth.

LightGBM v1 now provides deterministic CPU training, validation-only
Platt/isotonic calibration, frozen high-precision/balanced/high-recall modes,
schema-locked test predictions, per-alert tree contributions, a fail-closed
detector adapter, explicit MLflow development/evaluation logging, and a
checksummed model bundle. Software completion is not a performance claim. The
Wave 1 G0–G7 are complete: reproducibility passed, G6 selected the
`ablate-state` feature subset and isotonic calibration, and G7 froze the
candidate. Production G8 evaluation remains open and G9 disposition blocked.
R4 downloaded the final release but failed before scoring; a replacement needs
its own signed authorization. Native synthetic same-run MLflow recovery and
independent S3 readback are recorded, without implying production qualification.

The C0–C4 shared data foundation is implemented for the four-date research
corpus. Only approved Nasdaq files are acquired; selected AAPL/MSFT/NVDA windows,
source/replay provenance and immutable development/final projections are retained.
Tabular and 64-step causal feature-sequence views share target identities and
chronological assignments. Transformer training and the exact-joined cascade
remain planned. See the [ML lifecycle](docs/use-cases/ml-lifecycle.md) and
[four-date data flow](docs/data/nasdaq-public-sample-v1-data-flow.md).
This research-only qualification does not replace appropriately licensed data,
independent clean-window review or a signed governed test release for
production/client performance claims.

The active learned-detector milestone is one sequential, demoable E2E flow:
qualify tabular LightGBM first, train a standalone causal market-sequence
Transformer, evaluate a separate Transformer-to-LightGBM cascade using
versioned scores/embeddings, and package one identical-row comparison. Nasdaq
is the primary governed benchmark; the frozen candidates then run against the
repository LOBSTER sample as a separate no-retuning robustness challenge. The
Transformer and cascade models are specified but not implemented. A separately
qualified and verified tabular LightGBM bundle is the planned rollback and missing-feature
fallback. The later secure demo UI is tracked by Story #91: selectively restore
the archived Google Auth foundation, update ingestion and Nasdaq replay, add a
campaign-wide experiment/results/report view, and provide a one-page management
summary. Presentation work follows the verified technical flow; authentication
and backend authorization must land earlier if sensitive data is exposed in a
shared deployment.

Two commercial Tier-1 extensibility features are defined and deliberately
parked until that E2E demo exits. A versioned inbound data
adapter registry will let explicitly reviewed future batch or streaming sources
map into the canonical immutable dataset contract; the existing hard-registered
LOBSTER and Nasdaq ITCH adapters are its partial foundation. A distinct
pluggable detector adapter and conformance harness will run LightGBM,
Transformer, the hybrid cascade, approved third-party detectors and future
extensions on the same causal governed inputs and comparable tournament
evidence. When resumed, the customer detector is the system under test and our
models are reference comparators. Neither adapter may bypass provenance,
fold/label isolation or the Java single-writer boundary. See the
[active roadmap](docs/roadmap/PHASES.md#feature-extensible-inbound-data-adapter-framework).

Generate the checked-in reproducible fixture:

```bash
make generate-features FEATURE_OVERWRITE=1
```

For governed historical or hybrid runs, `generate_features.py` can merge
locally verified clean-window adjudications into the replay labels. Only
explicit reviewed windows become label zero; every other historical row stays
unlabeled. See the
[governed corpus protocol](docs/data/governed-corpus-benchmark-protocol.md#commands)
for the complete command and required artifact bindings.

The formulas, configuration, label boundary, prefix-invariance guarantee, and
session-grouped training rules are documented in
[Causal Feature Engineering for LightGBM](docs/ml/feature-engineering-lightgbm.md),
[ARD-0024](docs/architecture/ARD-0024-versioned-causal-feature-engineering.md),
[ARD-0028](docs/architecture/ARD-0028-governed-lightgbm-feature-loading.md), and
[ARD-0031](docs/architecture/ARD-0031-complete-lightgbm-v1.md).
Operational commands and artifact boundaries are in the
[Governed LightGBM v1 Runbook](docs/ml/lightgbm-v1-runbook.md).

Compose options can be combined:

| Runtime | Command |
| --- | --- |
| Core only | `docker compose up --build` |
| Core + Prometheus | `docker compose --profile prometheus up --build` |
| Core + Prometheus + Grafana | `docker compose --profile grafana up --build` |
| Shared MLflow tracking | `make mlflow-bootstrap && make mlflow-up && make mlflow-verify` |
| Core + Nebius Serverless | `make docker-up-serverless` |
| Core + Nebius Serverless + monitoring | `make docker-up-all` |

The older `monitoring` profile remains an alias for the Prometheus/Grafana pair:

```bash
docker compose --profile monitoring up --build
```

Open Grafana at http://localhost:3000 and Prometheus at http://localhost:9090. Grafana is provisioned with end-to-end, Java, component, bottleneck, and detector-tournament dashboards.

### Role of Prometheus and Grafana

| Component | Role in LOB Arena |
| --- | --- |
| Prometheus | Pulls and stores operational time-series metrics from `java-kernel:8080/actuator/prometheus`, `backend:8000/metrics`, `agent-runner:9100/metrics`, and Prometheus itself. Its target view and PromQL UI help verify scrape health and inspect raw metrics. |
| Grafana | Uses Prometheus as its automatically provisioned datasource and turns those metrics into the `LOB Arena E2E Overview`, `LOB Arena Java Kernel`, `LOB Arena Components`, `LOB Arena Bottlenecks`, and `LOB Arena Detector Tournaments` dashboards. |

Use `--profile prometheus` when raw metrics and PromQL are sufficient. Use
`--profile grafana` when you also want dashboards; this profile starts both
services. Both are opt-in local diagnostics and are not required for a valid
simulation, AI investigation, or detector tournament. See
[Kernel Observability](docs/runtime/kernel-observability.md) for the metric sources,
dashboard workflow, and troubleshooting guidance.

Detector-tournament orchestration exposes bounded lifecycle telemetry—runs,
completion status, duration, scenario throughput, in-flight work, and Nebius
artifact collection—through the backend `/metrics` endpoint. The
`LOB Arena Detector Tournaments` dashboard visualizes these signals. Prometheus
does not scrape short-lived tournament processes or use tournament IDs as
labels; detailed leaderboards remain durable artifacts.

## Automated grader

From a fresh checkout of the default `main` branch, run exactly:

```bash
make grader-smoke
```

This credential-free command installs locked dependencies when needed, launches the backend and frontend on local ephemeral ports, submits one fixed-seed Local Mock scenario, and validates backend health, the rendered frontend, detector output, results metrics, event data, and all eight artifacts. It uses temporary output and prints `GRADER_OK` only after every check succeeds. It does not require Docker, cloud credentials, a GPU, or access to Nebius services.


## Hardware Configuration, Runtime, Cost and Expected Outputs

### Hardware Configuration

#### Local Development

| Component | Requirement |
|-----------|-------------|
| CPU | 4+ vCPUs (8 recommended) |
| Memory | 8 GB minimum (16 GB recommended) |
| Disk | 5 GB free |
| Docker | Docker Engine + Docker Compose |
| OS | Linux, macOS or Windows |

The default Local Mock mode does **not** require a GPU or Nebius credentials.

#### Nebius Production Configuration

| Component | Configuration |
|-----------|---------------|
| AI Endpoint | NVIDIA L40S (`gpu-l40s-d`) |
| Endpoint preset | `1gpu-16vcpu-96gb` |
| Model | `Qwen/Qwen2.5-14B-Instruct` |
| Runtime | vLLM |
| Batch execution | Nebius Serverless Jobs (`cpu-d3`, 4 vCPU / 16 GB RAM) |

### Approximate Runtime and Cost

| Workflow | Runtime | Approximate Cost |
|----------|--------:|-----------------:|
| Local Docker demo | 3–5 min | $0 |
| Local detector tournament (10 scenarios) | ~0.7 s | $0 |
| Nebius Serverless Job (5 scenarios) | ~181 s | ~$0.005 |
| Nebius Endpoint investigation (2 requests) | P50 24.2 s / P95 28.8 s | ~$0.023 |

Measured on representative production runs. Actual runtime and billing depend on model, startup latency and current Nebius pricing.

### Expected Outputs

Running the end-to-end demo produces:

**Interactive outputs**

- Synthetic market abuse scenario
- Order-book replay
- Detector alerts
- AI Investigation Team report
- Detector Tournament leaderboard
- Execution trace

**Generated artifacts**

Artifacts are written under `outputs/serverless-smoke/`, including:

- `summary.json`
- `scenario.json`
- `simulation_events.json`
- `detector_alerts.json`
- `investigation_report.md`
- `tournament_result.json`
- `serverless_job.json`
- `manifest.json`

Benchmark execution additionally produces metrics, leaderboard reports, manifests and checksum-verified evidence bundles under `outputs/benchmark/` and `evidence/`.


## Demo

**Video walkthrough:** [LOB Arena — real Nebius cloud E2E demo](https://youtu.be/PZOrEwa4lqg)

1. Open the AI Command Center.
2. Run the Serverless E2E demo.
3. Review the generated scenario and order-book events.
4. Inspect detector alerts and incident evidence.
5. Run the AI Investigation Team.
6. Run or inspect the Detector Tournament.
7. Open synchronized artifacts and evidence records.

Generated local demo artifacts are written under `outputs/serverless-smoke/`.

## Evidence

The public evidence is sanitized and checksum-verified: credentials, bearer tokens, signed URLs, and private Endpoint hostnames are excluded.

- [Challenge submission index](docs/publication/challenge-submission.md)
- [Manual Nebius Control Panel evidence (100-workload Job + 12 real Endpoint calls)](evidence/manual-ui-2026-07-15/README.md)
- [Six-job production E2E evidence (1,200 workloads)](evidence/production-e2e-2026-07-15/README.md)
- [Production L40S/vLLM Endpoint evidence (25 real calls)](evidence/production-endpoint-2026-07-15/README.md)
- [Representative scenario benchmark](evidence/deployment-2026-07-14-1412/representative-scenario-benchmark.md)
- [Frozen benchmark bundle](evidence/deployment-2026-07-14-1412/benchmarks/outputs/benchmark/EXP-390EFAC2/README.md)
- [Frozen Nebius deployment bundle](evidence/deployment-2026-07-14-1412/README.md)

The corrected production evidence records six completed Nebius Jobs with 1,200 disjoint-seed workloads plus 25 real L40S/vLLM Endpoint calls. A separate manual Control Panel session adds one completed 100-workload Job, 12,414 events, seven AI investigation reports, 12 real Endpoint calls, and synchronized Object Storage artifacts.

Freeze a new local evidence snapshot with `./scripts/freeze-release.sh`; add `--offline` when Docker, the backend, or Nebius CLI is unavailable.

## Nebius Cloud

Real cloud execution is opt-in. Configure the variables below, confirm that `$HOME/.nebius` contains `config.yaml` and `credentials.yaml`, and review [docs/deployment/nebius-deployment.md](docs/deployment/nebius-deployment.md):

```bash
NEBIUS_SERVERLESS_ENABLED=true \
NEBIUS_CLI_CONFIG_DIR="$HOME/.nebius" \
docker compose up --build
```

Add `--profile prometheus` for metrics only or `--profile grafana` for the full dashboard stack. `make docker-up-serverless` and `make docker-up-all` are equivalent shortcuts.

Core variables:

```bash
NEBIUS_SERVERLESS_ENABLED=true
NEBIUS_CLI_CONFIG_DIR=/absolute/path/to/.nebius
ENDPOINT_TOKEN=endpoint-auth-token
NEBIUS_ENDPOINT_BASE_URL=https://your-nebius-endpoint
NEBIUS_ENDPOINT_MODE=local_vllm
NEBIUS_ENDPOINT_PLATFORM=gpu-l40s-d
NEBIUS_ENDPOINT_PRESET=1gpu-16vcpu-96gb
LOCAL_VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct
NEBIUS_JOB_IMAGE=ghcr.io/khab40/lob-arena-jobs:<tag>
NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE='...'
NEBIUS_JOB_STATUS_COMMAND_TEMPLATE='...'
NEBIUS_JOB_ARTIFACTS_COMMAND_TEMPLATE='...'
NEBIUS_JOB_OUTPUT_URI=s3://...
```

If Job command templates are missing, the backend records `real_nebius_pending` instead of pretending a cloud run completed.

## Development

CI validates retained Python tests and Ruff, frontend lint/build, the authoritative Java 25 kernel and live control plane, deterministic CPU evaluation, agent workspace contracts, Compose config, application Docker images, and Gitleaks. It intentionally does not build long-running Nebius Endpoint/Job images and does not run GPU/vLLM inference.

Run the main checks locally:

```bash
uv sync --project backend --dev --frozen
PYTHONPATH=. uv run --project backend ruff check backend serverless scripts
PYTHONPATH=. uv run --project backend pytest -c backend/pyproject.toml backend/tests
(cd frontend && corepack enable && pnpm install --frozen-lockfile && pnpm run lint && pnpm run build)
(cd java && ./gradlew clean check)
docker compose --env-file .env.example config --quiet
./scripts/check-secrets.sh
```

Common dev commands:

```bash
make grader-smoke
make backend-dev
make frontend-dev
make backend-test
make serverless-benchmark
make secrets-plan
make secrets-check
```

## Documentation

| Topic | File |
| --- | --- |
| Quick start | [docs/deployment/QUICKSTART.md](docs/deployment/QUICKSTART.md) |
| Architecture | [docs/architecture.md](docs/architecture.md) |
| Architecture decisions | [docs/architecture/README.md](docs/architecture/README.md) |
| Functional capability map | [docs/product/FUNCTIONAL_OVERVIEW.md](docs/product/FUNCTIONAL_OVERVIEW.md) |
| Use cases | [docs/use-cases/README.md](docs/use-cases/README.md) |
| Current phases and learned-detector roadmap | [docs/roadmap/PHASES.md](docs/roadmap/PHASES.md) |
| Nebius LightGBM Wave 1 execution gates | [docs/roadmap/nebius-lightgbm-wave1-implementation-plan.md](docs/roadmap/nebius-lightgbm-wave1-implementation-plan.md) |
| Runtime model | [docs/runtime/runtime-model.md](docs/runtime/runtime-model.md) |
| Prometheus and Grafana observability | [docs/runtime/kernel-observability.md](docs/runtime/kernel-observability.md) |
| Benchmark methodology | [docs/ml/benchmark-methodology.md](docs/ml/benchmark-methodology.md) |
| Causal LightGBM feature engineering | [docs/ml/feature-engineering-lightgbm.md](docs/ml/feature-engineering-lightgbm.md) |
| Governed corpus and ML benchmark protocol | [docs/data/governed-corpus-benchmark-protocol.md](docs/data/governed-corpus-benchmark-protocol.md) |
| Shared MLflow tracking server | [docs/ml/mlflow-tracking-server.md](docs/ml/mlflow-tracking-server.md) |
| Nebius deployment | [docs/deployment/nebius-deployment.md](docs/deployment/nebius-deployment.md) |
| L40S migration | [docs/archive/l40s-migration.md](docs/archive/l40s-migration.md) |
| Prompting layer | [docs/ml/surveillance-prompting.md](docs/ml/surveillance-prompting.md) |
| Safety | [docs/product/safety-and-disclaimers.md](docs/product/safety-and-disclaimers.md) |
| Challenge submission | [docs/publication/challenge-submission.md](docs/publication/challenge-submission.md) |
| Documentation guide | [docs/DOCUMENTATION_GUIDE.md](docs/DOCUMENTATION_GUIDE.md) |

## Maintainer Notes

- Keep README concise; put detailed API examples in docs.
- Keep local fallback honest and explicitly labeled.
- Do not commit credentials, private endpoints, signed URLs, or unredacted cloud logs.
- Never print or attach `.env`; inspect only named non-secret keys and use `docker compose config --quiet` for validation.
- Run `./scripts/check-secrets.sh` before publishing evidence.

## ML architecture and workflow

Start with [Architecture](ARCHITECTURE.md) and the [ML lifecycle guide](docs/use-cases/ml-lifecycle.md)
for source data, chronological partitions, LightGBM/Transformer inputs, training,
checkpoints, calibration, selection, MLflow retention and planned streaming use.
The guide separates implemented LightGBM and sequence-data capabilities from
proposed Transformer, cascade, registry-promotion and live-serving work.
