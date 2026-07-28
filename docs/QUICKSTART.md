# Quick Start - LOB Arena

Get the system running locally in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- 4GB+ RAM available
- ~2GB disk space for dependencies and artifacts

## 1. Clone and Configure

```bash
# Clone the repository
git clone https://github.com/khab40/lob-arena.git
cd lob-arena

# Copy environment template
cp .env.example .env

# (Optional) If you have a deployed Nebius endpoint, add it to .env:
# NEBIUS_TENANT_ID=your-tenant-id
# ENDPOINT_TOKEN=your-endpoint-token
# NEBIUS_ENDPOINT_BASE_URL=https://your-endpoint
```

## 2. Start the System

```bash
# Build and start all services
docker compose up --build

# First run takes 2-3 minutes. When ready, you'll see:
# backend  | Application startup complete
# frontend | Local:   http://localhost:5173/
```

This CPU-safe local path builds all four services (`java-kernel`, `agent-runner`,
`backend`, and `frontend`) from source, needs no Nebius
configuration or registry login, and falls back to deterministic mock responses.
The backend clears stale cloud settings while `NEBIUS_SERVERLESS_ENABLED=false`.
Real Nebius credentials are mounted only when `NEBIUS_CLI_CONFIG_DIR` is changed
from the repository's empty directory; see [Nebius Deployment](nebius-deployment.md).

## 3. Access the UI

Open your browser:

- **Frontend / Command Center**: http://localhost:5173
- **Arena**: http://localhost:5173/arena
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Java kernel status**: http://localhost:8081/api/kernel/status
- **Java arena state**: http://localhost:8081/api/arena/state

Optional Prometheus only:

```bash
docker compose --profile prometheus up --build
```

Prometheus scrapes operational metrics from the Java control plane, FastAPI,
and the agent runner and stores them as time series. Choose this profile when
you want to inspect scrape targets or run PromQL without starting Grafana.

Optional Prometheus and Grafana:

```bash
docker compose --profile grafana up --build
```

The Grafana profile starts both services. Grafana uses the automatically
provisioned Prometheus datasource to visualize service health, request rates and
latency, JVM/GC pressure, arena state, and agent-runner behavior.

- **Grafana dashboards**: http://localhost:3000
- **Prometheus**: http://localhost:9090

Use the `LOB Arena E2E Overview` dashboard first, then `LOB Arena Bottlenecks` if the arena appears slow.
Use `LOB Arena Detector Tournaments` to inspect local and Nebius tournament
outcomes, duration, scenario throughput, in-flight work, and artifact
collection.
The monitoring stack is read-only and optional: it is not part of exchange
execution or detector decisions. Detector precision, recall, and F1 remain
benchmark outputs rather than Prometheus runtime metrics. See
[Kernel Observability](kernel-observability.md) for the scrape map and dashboard
interpretation.

For real Nebius Serverless plus dashboards, configure `.env`, then run:

```bash
NEBIUS_SERVERLESS_ENABLED=true \
NEBIUS_CLI_CONFIG_DIR="$HOME/.nebius" \
docker compose --profile grafana up --build
```

### Optional Shared MLflow

The MLflow profile is independent of the core arena and monitoring profiles:

```bash
make mlflow-bootstrap
make mlflow-up
make mlflow-verify
```

Open <http://127.0.0.1:5500> and use the administrator credential from the
Git-ignored `deployments/mlflow/.env`. The verification creates the corpus,
LightGBM-development, governed-evaluation, and binary registered-model
namespaces and tests PostgreSQL plus S3-compatible artifact persistence.
PostgreSQL and MinIO are not published to the host. See
[Shared MLflow Tracking](mlflow-tracking-server.md).

## 4. Quick Test

In the Arena UI, click **Start** to begin a live simulation. You should see:

- Order book updates in real time
- Trading agents acting on each tick
- Detector alerts (icons in the right panel)

Or test via REST:

```bash
# Check system status
curl http://localhost:8000/api/status

# Check Nebius integration
curl http://localhost:8000/api/nebius/status

# Get current arena state
curl http://localhost:5173/api/arena/state

# Start a simulation
curl -X POST http://localhost:5173/api/simulation/start

# Inject a scenario
curl -X POST http://localhost:5173/api/scenarios/spoofing-like
```

## 5. Explore Features

### Live Arena Mode
- **Start/Pause/Reset** buttons control the simulation
- Watch normal agents trade
- Click **Inject Scenario** to trigger abuse-like behavior
- View detector confidence in the right panel

### Historical And Hybrid Replay

1. Open **Data Ingestion** and import a paired LOBSTER message/order-book
   dataset. The repository includes a small public fixture under
   [data/lobster/fixture](../data/lobster/README.md).
2. Open Arena, select **Historical control**, choose the imported dataset, and
   load it for an unlabeled control replay.
3. Select **Hybrid + attacks**, load the same dataset, then launch spoofing-like
   or layering-like from the existing Scenario Setup panel.

Historical data is never automatically labeled benign. Only the synthetic
scenario creates ground truth. For API/config examples and comparison artifact
generation, see [Historical and hybrid replay](../README.md#historical-and-hybrid-replay).

### Command Center Demo
- Open `/nebius`
- Use **Run Serverless E2E Demo** or the Runtime workflow steps
- The flow shows endpoint health, AI investigation, detector tournament status, and artifacts

### Incident Investigation
- Click on an incident badge to open Incident Details
- View detector evidence and timeline
- Click **Run AI Investigator** to get a Nebius AI explanation or a clearly labeled simulated fallback

### Advanced Features
- WebSocket connection: `ws://localhost:5173/ws/arena`
- Nebius AI: open `/nebius` in the frontend
- Batch benchmark and smart attack/detect jobs: See [Nebius Deployment](nebius-deployment.md)
- Red-team scenario generation: See [Use Cases](USE_CASES.md)

### Phase 4 Reproducibility

```bash
python scripts/generate_scenarios.py
python scripts/run_local_eval.py
python scripts/submit_nebius_job.py --dry-run
python scripts/call_endpoint.py --base-url http://localhost:9000 --route orderbook-alert
```

## Next Steps

- **Understand the architecture**: Read [Architecture Overview](architecture.md)
- **Review functional scope**: Read [Functional Overview](FUNCTIONAL_OVERVIEW.md)
- **Learn the workflows**: Read [Use Cases](USE_CASES.md)
- **Operate shared MLflow**: Read [Shared MLflow Tracking](mlflow-tracking-server.md)
- **Deploy to Nebius**: Read [Nebius Deployment](nebius-deployment.md)
- **Run benchmarks**: Read [Benchmark Methodology](benchmark-methodology.md)
- **Inspect runtime health**: Read [Kernel Observability](kernel-observability.md)
- **Understand the design**: Read [Architecture Records](architecture/README.md)

## Troubleshooting

### Port Already in Use
If ports 5173, 8000, 8081, 50051, or 9100 are in use:
```bash
# Change ports in docker-compose.yml or use:
docker compose up --build -p my-project
```

### CLI Not Detected
If you see `cli_installed: false` in `/api/nebius/status`:
- This is expected in mock mode
- The Nebius CLI will be used when endpoints are configured
- See [Nebius Deployment](nebius-deployment.md) for setup

### Build Fails
```bash
# Rebuild project services without deleting unrelated Docker data
docker compose build --no-cache
docker compose up
```

### WebSocket Connection Issues
Ensure you're connecting to `ws://localhost:5173/ws/arena` (WebSocket), not `http://`.

## Stopping the System

```bash
# Stop all services
docker compose down

# Remove volumes (clears data)
docker compose down -v
```

## Common API Endpoints

```bash
# System health
curl http://localhost:8000/health
curl http://localhost:8000/api/status
curl http://localhost:8000/api/nebius/status

# Simulation control
curl -X POST http://localhost:5173/api/simulation/start
curl -X POST http://localhost:8000/api/simulation/pause
curl -X POST http://localhost:8000/api/simulation/reset

# Scenarios
curl -X POST http://localhost:5173/api/scenarios/spoofing-like
curl -X POST http://localhost:8000/api/scenarios/layering-like
curl -X POST http://localhost:8000/api/scenarios/quote-stuffing
curl -X POST http://localhost:8000/api/scenarios/liquidity-evaporation

# Incidents
curl http://localhost:8000/api/incidents
curl http://localhost:8000/api/incidents/INC-000001
curl -X POST http://localhost:8000/api/incidents/INC-000001/explain

# Nebius AI red-team generation (local mock by default)
curl -X POST http://localhost:8000/api/red-team/generate-scenario \
  -H 'Content-Type: application/json' \
  -d '{"scenario_family":"quote_stuffing","market_regime":"volatile","goal":"hard_to_detect"}'
```

## Documentation Index

- [Full Documentation](../README.md)
- [Architecture Overview](architecture.md)
- [Use Cases](USE_CASES.md)
- [Runtime Model](runtime-model.md)
- [Kernel Observability](kernel-observability.md)
- [Benchmark Methodology](benchmark-methodology.md)
- [Nebius Deployment](nebius-deployment.md)
- [Safety & Disclaimers](safety-and-disclaimers.md)

## Support

For issues, check:
- [Architecture Records](architecture/README.md) for design decisions
- [Research Notes](research-notes.md) for detector design
- [Use Cases](USE_CASES.md) for workflow documentation
