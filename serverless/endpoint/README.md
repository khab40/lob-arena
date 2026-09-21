# Serverless AI Endpoint

FastAPI container for Nebius Serverless AI Endpoint deployment.

It exposes the AI surfaces used by the backend:

- `GET /health`
- `POST /orderbook-alert`
- `POST /investigation-team`
- `POST /investigation-report`
- `POST /explain-event`
- `POST /explain-simulation`
- `POST /generate-report`
- `POST /generate-incident-report`
- `POST /generate-scenario`
- `POST /generate-smart-scenario`
- `POST /generate-market-abuse-scenario`

## Professional Surveillance Prompting

Investigation routes use a strict, evidence-first prompt designed for
Qwen2.5-14B-Instruct on one L40S GPU. The builder converts episode data into a
bounded summary (maximum 24,000 serialized characters), never sends raw LOB
streams, and validates the model's JSON before adapting it to the existing route
response. vLLM runs only for high anomalies, detector disagreement, completed
manipulation episodes, simulation summaries, and benchmark generation; ordinary events keep
the deterministic path. See [prompting contracts, budgets, and examples](../../docs/ml/surveillance-prompting.md).

## Modes

- `NEBIUS_ENDPOINT_MODE=mock` returns deterministic structured responses.
- `NEBIUS_ENDPOINT_MODE=local_vllm` calls a local OpenAI-compatible vLLM server
  at `LOCAL_VLLM_BASE_URL`; it does not load Transformers in FastAPI and does
  not call an external model gateway.

Local vLLM env:

```bash
NEBIUS_ENDPOINT_MODE=local_vllm
LOCAL_VLLM_BASE_URL=http://127.0.0.1:8001/v1
LOCAL_VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct
LOCAL_VLLM_HOST=127.0.0.1
LOCAL_VLLM_PORT=8001
LOCAL_VLLM_DTYPE=auto
LOCAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
LOCAL_VLLM_MAX_MODEL_LEN=16384
LOCAL_VLLM_ENABLE_PREFIX_CACHING=true
LOCAL_VLLM_MAX_NUM_SEQS=16
LOCAL_VLLM_TRUST_REMOTE_CODE=true
NEBIUS_PROMPT_SEED=42
NEBIUS_REQUEST_TIMEOUT_SECONDS=180
```

In `local_vllm` mode, `/endpoint/start.sh` starts FastAPI/Uvicorn on
`0.0.0.0:9000`, starts the local vLLM OpenAI-compatible server, then waits until
`http://127.0.0.1:8001/v1/models` is healthy. Startup logs include the vLLM
model, host, port, GPU memory utilization, max model length, readiness attempts,
and FastAPI start line.

## Deploy Local vLLM On L40S

Build and push the endpoint image, then create a Nebius Serverless Endpoint that
runs vLLM and FastAPI inside the container:

```bash
docker build --platform linux/amd64 \
  -f serverless/endpoint/Dockerfile \
  -t ghcr.io/<your-org>/lob-arena-endpoint:<tag> \
  serverless/endpoint
docker push ghcr.io/<your-org>/lob-arena-endpoint:<tag>

export NEBIUS_PARENT_ID=<project-id>
export NEBIUS_SUBNET_ID=<vpc-subnet-id>
export ENDPOINT_TOKEN=<endpoint-bearer-token>
export NEBIUS_ENDPOINT_IMAGE=ghcr.io/<your-org>/lob-arena-endpoint:<tag>
export NEBIUS_ENDPOINT_MODE=local_vllm
export NEBIUS_ENDPOINT_PLATFORM=gpu-l40s-d
export NEBIUS_ENDPOINT_PRESET=1gpu-16vcpu-96gb
export LOCAL_VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct
export LOCAL_VLLM_HOST=127.0.0.1
export LOCAL_VLLM_PORT=8001
export LOCAL_VLLM_BASE_URL=http://127.0.0.1:8001/v1
export LOCAL_VLLM_DTYPE=auto
export LOCAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export LOCAL_VLLM_MAX_MODEL_LEN=16384
export LOCAL_VLLM_ENABLE_PREFIX_CACHING=true
export LOCAL_VLLM_MAX_NUM_SEQS=16
export LOCAL_VLLM_TRUST_REMOTE_CODE=true

./scripts/create-nebius-ai-endpoint.sh
```

After creation, call the endpoint with the same endpoint auth token:

```bash
ENDPOINT_TOKEN=<endpoint-bearer-token> \
python scripts/call_endpoint.py \
  --base-url https://<endpoint-host> \
  --route orderbook-alert
```

## Cloud Validation

Apple Silicon Docker cannot realistically validate the L40S GPU path. Validate
`local_vllm` in Nebius with a pushed `linux/amd64` image:

```bash
export NEBIUS_ENDPOINT_IMAGE=ghcr.io/<your-org>/lob-arena-endpoint:<tag>
docker buildx build --platform linux/amd64 \
  -f serverless/endpoint/Dockerfile \
  -t "${NEBIUS_ENDPOINT_IMAGE}" \
  --push \
  serverless/endpoint

export NEBIUS_PARENT_ID=<project-id>
export NEBIUS_SUBNET_ID=<vpc-subnet-id>
export ENDPOINT_TOKEN=<endpoint-bearer-token>
export NEBIUS_ENDPOINT_MODE=local_vllm
export NEBIUS_ENDPOINT_PLATFORM=gpu-l40s-d
export NEBIUS_ENDPOINT_PRESET=1gpu-16vcpu-96gb
export LOCAL_VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct
export LOCAL_VLLM_HOST=127.0.0.1
export LOCAL_VLLM_PORT=8001
export LOCAL_VLLM_BASE_URL=http://127.0.0.1:8001/v1
export LOCAL_VLLM_DTYPE=auto
export LOCAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export LOCAL_VLLM_MAX_MODEL_LEN=16384
export LOCAL_VLLM_ENABLE_PREFIX_CACHING=true
export LOCAL_VLLM_MAX_NUM_SEQS=16
export LOCAL_VLLM_TRUST_REMOTE_CODE=true

./scripts/create-nebius-ai-endpoint.sh
```

After Nebius reports the endpoint URL and ID:

```bash
export NEBIUS_ENDPOINT_BASE_URL=https://<endpoint-host>
export NEBIUS_ENDPOINT_ID=<endpoint-id>
export ENDPOINT_TOKEN=<endpoint-bearer-token>

curl -fsS -H "Authorization: Bearer ${ENDPOINT_TOKEN}" \
  "${NEBIUS_ENDPOINT_BASE_URL%/}/health"

./scripts/validate-local-vllm-endpoint.sh validate
./scripts/validate-local-vllm-endpoint.sh logs
```

Expected success:

```text
endpoint_mode=local_vllm
model_mode=local_vllm
local_vllm_model=Qwen/Qwen2.5-14B-Instruct
latency_ms > 0 for /orderbook-alert and /investigation-report
```

## Local Run

```bash
uvicorn app:app --host 0.0.0.0 --port 9000
```

Health:

```bash
curl http://localhost:9000/health
```

Explain incident:

```bash
curl -X POST http://localhost:9000/explain-event \
  -H 'Content-Type: application/json' \
  -d '{
    "incident_id":"INC-000001",
    "title":"Quote Stuffing detected",
    "type":"quote_stuffing",
    "agent":"ABUSER_01",
    "confidence":0.91,
    "severity":"High",
    "evidence":[
      {"key":"message_rate","label":"Message rate","value":42,"unit":"events/sec"}
    ],
    "replay":{"market":{"mid":68125,"spread":2}}
  }'
```

Generate scenario:

```bash
curl -X POST http://localhost:9000/generate-scenario \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt":"Generate a bounded quote-stuffing red-team scenario.",
    "constraints":{
      "scenario_family":"quote_stuffing",
      "market_regime":"volatile",
      "goal":"hard_to_detect"
    }
  }'
```

Generate canonical market-abuse scenario:

```bash
curl -X POST http://localhost:9000/generate-market-abuse-scenario \
  -H 'Content-Type: application/json' \
  -d '{
    "manipulation_type":"spoofing",
    "difficulty":"medium",
    "symbol":"AIMD",
    "duration_ticks":120,
    "liquidity_regime":"thin",
    "volatility_regime":"high",
    "seed":42
  }'
```

Score an order-book window:

```bash
curl -X POST http://localhost:9000/orderbook-alert \
  -H 'Content-Type: application/json' \
  -d '{
    "bids":[{"price":68120,"quantity":12.4,"owner":"abuser"}],
    "asks":[{"price":68130,"quantity":1.8,"owner":"normal"}],
    "features":{"wall_size_ratio":8.2,"message_rate":21,"cancel_to_trade_ratio":5.4},
    "scenario_hint":"spoofing_like_wall"
  }'
```

## Backend Wiring

After deployment, set backend env:

```bash
NEBIUS_ENDPOINT_BASE_URL=http://<endpoint>
# Optional per-route overrides:
NEBIUS_INCIDENT_EXPLAINER_URL=http://<endpoint>/explain-event
NEBIUS_SCENARIO_GENERATOR_URL=http://<endpoint>/generate-scenario
NEBIUS_MARKET_ABUSE_SCENARIO_URL=http://<endpoint>/generate-market-abuse-scenario
NEBIUS_ORDERBOOK_ALERT_URL=http://<endpoint>/orderbook-alert
NEBIUS_INVESTIGATION_REPORT_URL=http://<endpoint>/investigation-report
ENDPOINT_TOKEN=<optional endpoint token>
```

## Docker

```bash
docker build --platform linux/amd64 -f serverless/endpoint/Dockerfile -t nebius-market-abuse-endpoint serverless/endpoint
docker run --rm -p 9000:9000 nebius-market-abuse-endpoint
```

The endpoint image is intended for Nebius `linux/amd64` GPU runtimes such as
L40S. Local Apple Silicon Docker inference testing is not required; Docker
Desktop does not expose Apple GPU/MPS to Linux containers.
