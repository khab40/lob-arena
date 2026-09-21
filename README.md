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
[demo script](docs/publication/demo-script.md) cover the historical challenge demo.
The [submission index](docs/publication/challenge-submission.md) links measured
runtime/cost and frozen evidence. Those observations are not current estimates
or learned-model qualification.

- [Challenge submission index](docs/publication/challenge-submission.md)
- [Manual Nebius Control Panel evidence (100-workload Job + 12 real Endpoint calls)](evidence/manual-ui-2026-07-15/README.md)
- [Six-job production E2E evidence (1,200 workloads)](evidence/production-e2e-2026-07-15/README.md)
- [Production L40S/vLLM Endpoint evidence (25 real calls)](evidence/production-endpoint-2026-07-15/README.md)
- [Representative scenario benchmark](evidence/deployment-2026-07-14-1412/representative-scenario-benchmark.md)
- [Frozen benchmark bundle](evidence/deployment-2026-07-14-1412/benchmarks/outputs/benchmark/EXP-390EFAC2/README.md)
- [Frozen Nebius deployment bundle](evidence/deployment-2026-07-14-1412/README.md)


Freeze a new local evidence snapshot with `./scripts/freeze-release.sh`; add `--offline` when Docker, the backend, or Nebius CLI is unavailable.

## Development

CI validates retained Python tests and Ruff, frontend lint/build, the authoritative Java 25 kernel and live control plane, deterministic CPU evaluation, agent workspace contracts, Compose config, application Docker images, and Gitleaks. It intentionally does not build long-running Nebius Endpoint/Job images and does not run GPU/vLLM inference.

The commands below describe developer checks. Agents must apply the execution
policy above before running tests that train, score or exercise model runtime:

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

## Contributing

Keep local fallback explicit. Never commit credentials, private endpoints,
signed URLs or unredacted cloud logs; never print `.env`.
Use `docker compose config --quiet` and `./scripts/check-secrets.sh`.
Follow the [documentation ownership rules](docs/DOCUMENTATION_GUIDE.md).
