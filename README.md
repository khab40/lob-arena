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
| --- | --- |
| Run the application | [Quickstart](docs/deployment/QUICKSTART.md) |
| Understand ownership and data flow | [Architecture](docs/architecture.md) |
| Check delivered versus planned work | [Current status](docs/roadmap/CURRENT_STATUS.md) |
| Choose a workflow | [Use cases](docs/use-cases/README.md) |
| Train, evaluate or inspect learned models | [ML lifecycle](docs/use-cases/ml-lifecycle.md) |
| Find a detailed specification | [Documentation index](docs/README.md) |

## Quick start

```bash
git clone https://github.com/khab40/lob-arena.git
cd lob-arena
cp .env.example .env
docker compose up --build
```

Open the UI at http://localhost:5173, Python AI API at http://localhost:8000,
or Java status at http://localhost:8081/api/kernel/status. The same-origin arena
WebSocket is `ws://localhost:5173/ws/arena`.

Default Compose builds Java, Python, the agent runner and frontend from source.
Local Mock needs no Nebius credentials or GPU. Serverless access is disabled;
the backend clears stale cloud settings unless explicitly enabled.
See the quickstart for prerequisites, configuration and troubleshooting.

Agent-initiated training, scoring, model fixtures and frozen-runtime validation
run on Nebius Serverless Jobs under the [execution policy](docs/ml/model-validation-execution-policy.md).
Local orchestration, static checks and artifact inspection remain available.

## Architecture

Java owns the exchange, live REST/WebSocket controls, replay and agent
orchestration. Python owns ingestion, offline ML, AI and cloud integration.
Agents return bounded intents; they cannot mutate the exchange. MLflow indexes
verified artifacts and never grants release approval. Prometheus/Grafana are
optional read-only diagnostics.

The [canonical architecture diagram](docs/architecture.md#system-high-level-design)
shows these boundaries. Historical publication posters are not current design references.

## Historical and hybrid replay

Use the [replay quickstart](docs/data/replay-quickstart.md) for LOBSTER/ITCH
imports, control-versus-hybrid comparison, signatures and market-profile commands.
The [client validation runbook](docs/data/client-historical-dataset-validation-runbook.md)
owns delivery checks; [hybrid validation](docs/data/hybrid-dataset-validation.md)
owns equivalence tests and trust boundaries.

## Model-ready causal features

The [feature reference](docs/ml/feature-engineering-lightgbm.md) owns formulas,
configuration, label isolation and causal prefix guarantees. The
[LightGBM runbook](docs/ml/lightgbm-v1-runbook.md) owns commands and artifacts;
the [ML lifecycle](docs/use-cases/ml-lifecycle.md) distinguishes implemented
training and sequence materialization from planned Transformer/cascade/serving work.
Software completion or synthetic recovery does not establish production quality.

<a id="role-of-prometheus-and-grafana"></a>

## Observability and cloud setup

Use [kernel observability](docs/runtime/kernel-observability.md) for the
Prometheus/Grafana profiles and dashboards, [MLflow operations](docs/ml/mlflow-tracking-server.md)
for tracking, and [Nebius deployment](docs/deployment/nebius-deployment.md)
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
