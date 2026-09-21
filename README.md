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
for opt-in endpoint/job configuration. Missing submit templates must remain
explicitly pending; configuration examples are not execution authorization.

## Automated grader

From a fresh checkout of the default `main` branch, run exactly:

```bash
make grader-smoke
```

This credential-free command installs locked dependencies when needed, launches the backend and frontend on local ephemeral ports, submits one fixed-seed Local Mock scenario, and validates backend health, the rendered frontend, detector output, results metrics, event data, and all eight artifacts. It uses temporary output and prints `GRADER_OK` only after every check succeeds. It does not require Docker, cloud credentials, a GPU, or access to Nebius services.


## Demo and evidence

[Video walkthrough](https://youtu.be/PZOrEwa4lqg) and
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
