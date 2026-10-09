# Nebius Serverless Deployment

This is the entry point for retained Serverless integration and image tooling.
[Endpoint documentation](endpoint/README.md) owns interactive API/deployment
details; [Jobs documentation](jobs/README.md) owns batch arguments/artifacts.
Use the [ML lifecycle](../docs/use-cases/ml-lifecycle.md) for governed model work.

## Components

| Component | Purpose |
| --- | --- |
| `endpoint/` | Bounded incident/scenario/investigation APIs with explicit mock or local-vLLM mode |
| `jobs/` | Synthetic rule benchmarks, acquisition/preparation and governed LightGBM workloads |
| `transformer_inputs/`, `transformer_research/`, `transformer_role_audit/` | Separately packaged Transformer research/verification execution boundaries |
| `deployment.env.example` | Integration environment examples; not execution authorization |

## Endpoint Wiring

The browser calls FastAPI; Endpoint URLs and tokens remain server-side.

```text
NEBIUS_ENDPOINT_BASE_URL=https://<endpoint-host>
NEBIUS_INCIDENT_EXPLAINER_URL=https://<endpoint-host>/explain-event
NEBIUS_SCENARIO_GENERATOR_URL=https://<endpoint-host>/generate-scenario
ENDPOINT_TOKEN=<optional endpoint token>
```

Per-route overrides and the complete route list live in the
[Endpoint reference](endpoint/README.md#backend-wiring). Unconfigured endpoints
return typed mock output with source/fallback metadata.

Compose keeps Serverless integration disabled by default. For an already
authorized and configured environment:

```bash
NEBIUS_SERVERLESS_ENABLED=true \
NEBIUS_CLI_CONFIG_DIR="$HOME/.nebius" \
docker compose up --build
```

`--profile prometheus` adds metrics; `--profile grafana` adds the full dashboard
stack. Java remains the live exchange owner.

## Local Smoke Test

A mock Endpoint can run on port 9000 as shown in the
[local Endpoint examples](endpoint/README.md#local-run). Point backend overrides
at `http://localhost:9000/explain-event` and `/generate-scenario`. This validates
wiring/response shape, not GPU inference or cloud execution.

## Container Build

From the repository root:

```bash
./scripts/build-serverless-images.sh
```

Equivalent Make target:

```bash
make serverless-build
```

Run endpoint health and jobs 3-run smoke checks against locally loaded images:

```bash
SMOKE=true ./scripts/build-serverless-images.sh
make serverless-smoke
```

Push images after local build/smoke succeeds:

```bash
PUSH=true ./scripts/build-serverless-images.sh
make serverless-push
```

The script options are environment variables:

```bash
IMAGE_NAMESPACE=ghcr.io/khab40
TAG=latest
ENDPOINT_IMAGE=ghcr.io/khab40/lob-arena-endpoint:latest
JOBS_IMAGE=ghcr.io/khab40/lob-arena-jobs:latest
PUSH=false
PLATFORM=linux/amd64
SMOKE=false
```

For example:

```bash
IMAGE_NAMESPACE=ghcr.io/<your-org> TAG=<tag> ./scripts/build-serverless-images.sh
PUSH=true IMAGE_NAMESPACE=ghcr.io/<your-org> TAG=<tag> ./scripts/build-serverless-images.sh
SMOKE=true IMAGE_NAMESPACE=ghcr.io/<your-org> TAG=<tag> ./scripts/build-serverless-images.sh
```

By default, the script builds these local tags:

```text
ghcr.io/khab40/lob-arena-endpoint:latest
ghcr.io/khab40/lob-arena-jobs:latest
```

Anonymous registry verification on 2026-07-13 confirmed the jobs `latest` and
`artifacts-v2` tags and the Endpoint `vllm-qwen-v11` tag. Each published image
includes `linux/amd64`; the Endpoint `latest` tag is not published. Local builds
may still use `latest`, but production Endpoint deployment examples use the
versioned public tag. VM and Kubernetes deployment scripts build and push their
application images to the explicitly configured namespace.

Smoke checks:

```text
Endpoint: docker run endpoint image, call GET /health.
Jobs: docker run jobs image with run_batch_experiments.py --runs 3 --batch-size 2.
```

## Deployment Smoke Workflow

After the endpoint, backend, and jobs image are available, run the end-to-end
deployment smoke workflow:

```bash
NEBIUS_ENDPOINT_BASE_URL=http://localhost:9000 \
BACKEND_BASE_URL=http://localhost:8000 \
JOBS_IMAGE=ghcr.io/khab40/lob-arena-jobs:latest \
./scripts/serverless-smoke.sh
```

For a deployed endpoint:

```bash
NEBIUS_ENDPOINT_BASE_URL=https://<endpoint-host> \
BACKEND_BASE_URL=https://<backend-host> \
ENDPOINT_TOKEN=<optional-endpoint-token> \
JOBS_IMAGE=ghcr.io/<your-org>/lob-arena-jobs:<tag> \
./scripts/serverless-smoke.sh
```

The script writes `outputs/serverless-smoke/summary.json` and stores raw
responses in the same directory. It checks endpoint `/health`,
`/orderbook-alert`, `/investigation-report`, runs the jobs image locally with
three runs, creates a backend experiment with 10 attacks, runs the local batch,
and optionally submits/collects Nebius job artifacts when command templates are
configured. Real Nebius job submission is not required for the smoke to pass;
when not configured, it is marked pending in the summary.

Equivalent manual commands:

```bash
docker build --platform linux/amd64 -f serverless/endpoint/Dockerfile \
  -t ghcr.io/khab40/lob-arena-endpoint:latest \
  serverless/endpoint

docker build -f serverless/jobs/Dockerfile \
  -t ghcr.io/khab40/lob-arena-jobs:latest \
  .
```

## First Deployment Checklist

1. Build and push `nebius-market-abuse-endpoint`.
2. Deploy it as a Nebius Serverless AI Endpoint with `scripts/create-nebius-ai-endpoint.sh`.
3. Copy the public endpoint URL into backend env:
   - `NEBIUS_INCIDENT_EXPLAINER_URL`
   - `NEBIUS_SCENARIO_GENERATOR_URL`
4. Start the backend and frontend.
5. In Arena, create an incident and click Nebius AI Investigator.

Local-vLLM L40S endpoint:

```bash
export NEBIUS_PARENT_ID=<project-id>
export NEBIUS_SUBNET_ID=<vpc-subnet-id>
export ENDPOINT_TOKEN=<endpoint-bearer-token>
export NEBIUS_ENDPOINT_IMAGE=ghcr.io/<your-org>/lob-arena-endpoint:<tag>
export NEBIUS_ENDPOINT_MODE=local_vllm
export NEBIUS_ENDPOINT_PLATFORM=gpu-l40s-d
export NEBIUS_ENDPOINT_PRESET=1gpu-16vcpu-96gb
export LOCAL_VLLM_BASE_URL=http://127.0.0.1:8001/v1
export LOCAL_VLLM_MODEL=Qwen/Qwen2.5-14B-Instruct
export LOCAL_VLLM_HOST=127.0.0.1
export LOCAL_VLLM_PORT=8001
export LOCAL_VLLM_DTYPE=auto
export LOCAL_VLLM_GPU_MEMORY_UTILIZATION=0.90
export LOCAL_VLLM_MAX_MODEL_LEN=16384
export LOCAL_VLLM_ENABLE_PREFIX_CACHING=true
export LOCAL_VLLM_MAX_NUM_SEQS=16
export LOCAL_VLLM_TRUST_REMOTE_CODE=true

./scripts/create-nebius-ai-endpoint.sh
```
6. In Lab/Judge flow, call `POST /api/red-team/generate-scenario`.
7. Build and push `nebius-market-abuse-jobs`.
8. Run the detector tournament job with `jobs/job_config.example.yaml`.
9. Run the synthetic dataset job with `jobs/dataset_job_config.example.yaml`.

## Cost Controls

- Keep endpoint mode as `mock` for initial connectivity tests.
- Use `--runs 100` and `--samples 100` until the full path works.
- Switch `NEBIUS_ENDPOINT_MODE=local_vllm` only after backend-to-endpoint wiring is verified.

## Safety

All endpoint and job outputs are synthetic educational artifacts. They are not
real market abuse detections, trading signals, or compliance decisions.
