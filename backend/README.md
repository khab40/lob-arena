# Backend

Retained Python service for LOB Arena AI/ML, Nebius, experiments, evidence, and
serverless workflows. Java owns the live arena, scenarios, deterministic
detectors/incidents, agent orchestration, REST controls, and WebSocket stream.
Compatibility arena routes below are thin HTTP clients to Java.

## Current Routes

- `GET /health`
- `GET /api/status`
- `GET /api/nebius/status`
- `POST /api/nebius/red-team-scenario`
- `POST /api/red-team/generate-scenario`
- `GET /api/arena/state`
- `GET /api/data-ingestion/lobster/candidates`
- `POST /api/data-ingestion/lobster/candidates/{candidate_id}/import`
- `GET /api/data-ingestion/datasets`
- `POST /api/simulation/start`
- `POST /api/simulation/pause`
- `POST /api/simulation/reset`
- `POST /api/scenarios/spoofing-like`
- `POST /api/scenarios/layering-like`
- `POST /api/scenarios/quote-stuffing`
- `POST /api/scenarios/liquidity-evaporation`
- `GET /api/incidents`
- `GET /api/incidents/{incident_id}`
- `POST /api/incidents/{incident_id}/explain`

## Local Development

```bash
uv sync
export JAVA_ARENA_BASE_URL=http://127.0.0.1:8081
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Health checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/status
curl http://localhost:8000/api/nebius/status
curl http://localhost:8000/api/arena/state
curl -X POST http://localhost:8000/api/simulation/start
curl -X POST http://localhost:8000/api/simulation/pause
curl -X POST http://localhost:8000/api/simulation/reset
curl -X POST http://localhost:8000/api/scenarios/spoofing-like
curl -X POST http://localhost:8000/api/scenarios/layering-like
curl -X POST http://localhost:8000/api/scenarios/quote-stuffing
curl -X POST http://localhost:8000/api/scenarios/liquidity-evaporation
curl http://localhost:8000/api/incidents
curl http://localhost:8000/api/incidents/INC-000001
curl -X POST http://localhost:8000/api/incidents/INC-000001/explain
curl -X POST http://localhost:8000/api/red-team/generate-scenario \
  -H 'Content-Type: application/json' \
  -d '{"scenario_family":"quote_stuffing","market_regime":"volatile","goal":"hard_to_detect","constraints":{"max_duration_seconds":5}}'
curl -X POST http://localhost:8000/api/nebius/red-team-scenario \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"short spoofing-like wall in a thin book","constraints":{"scenario_type":"spoofing_like_wall"}}'
```

Nebius integration variables:

```bash
NEBIUS_TENANT_ID=your-tenant-id
NEBIUS_ENDPOINT_BASE_URL=https://your-nebius-endpoint
ENDPOINT_TOKEN=optional-token
```

The backend derives `/explain-event` and `/generate-scenario` from `NEBIUS_ENDPOINT_BASE_URL`. You can still set `NEBIUS_INCIDENT_EXPLAINER_URL` and `NEBIUS_SCENARIO_GENERATOR_URL` as explicit overrides. When endpoint URLs are not configured, the backend returns typed mock responses.

Java WebSocket browser smoke test through the frontend Nginx gateway:

```js
const ws = new WebSocket("ws://localhost:5173/ws/arena");
ws.onmessage = (event) => console.log(JSON.parse(event.data));
ws.onopen = () => ws.send(JSON.stringify({ type: "arena_control", action: "start" }));
```

Frontend websocket mode:

```bash
VITE_ARENA_MODE=websocket
VITE_ARENA_WS_URL=ws://localhost:5173/ws/arena
```

Tests:

```bash
uv run pytest
```

LOBSTER batch ingestion reads paired CSV files from `../data/lobster` and
writes registered datasets under `../data/processed/lobster`. Override those
paths with `ARENA_LOBSTER_RAW_DIR` and `ARENA_HISTORICAL_DATA_DIR`.
The Data Ingestion UI can import a one-minute, five-minute, or full-file time
window. Window end times are exclusive, and each window is registered as a
separate dataset that can be selected in the Arena.

The Java arena consumes those normalized datasets through:

- `GET /api/arena/historical-datasets`
- `POST /api/arena/data-source`
- `POST /api/arena/replay-comparison`

Use `source_type: historical` for an unlabeled control or `source_type: hybrid`
before launching an existing attack from Scenario Setup. Import never assigns
benign or attack ground truth. Hybrid ground truth comes only from the
subsequent synthetic scenario launch. The source Parquet and manifest remain
immutable; Java records historical snapshots from source data while scenarios
and detectors use the combined live book.

See [ARD-0022](../docs/architecture/ARD-0022-historical-market-data-ingestion.md)
for ingestion and
[ARD-0023](../docs/architecture/ARD-0023-hybrid-historical-replay.md) for
ordering, seed derivation, provenance, labels, and artifact guarantees.

## Feature generation

The offline feature pipeline consumes canonical Java exchange-event JSONL or
the paginated Java `/api/arena/exchange-events` endpoint. It emits one causal
row per combined-book checkpoint using the same `lob_features_v1` contract for
LOBSTER, synthetic, and hybrid runs. Immutable historical-source snapshots are
validated as provenance but are not prediction rows.

From the repository root:

```bash
make generate-features FEATURE_OVERWRITE=1
```

Labels are a separate optional input and are joined only after numeric feature
calculation. No labels input leaves rows unlabeled. See
[Causal Feature Engineering for a Future LightGBM Detector](../docs/feature-engineering-lightgbm.md)
for direct CLI examples, formulas, Parquet types, and leakage-safe split rules.

Coverage:

```bash
uv run pytest --cov=app --cov-report=term-missing
```
