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
SMOKE=true ./scripts/build-serverless-images.sh
```

The first builds images. `SMOKE=true` inspects Endpoint/Jobs image metadata,
checks the Jobs AWS CLI version and imports LightGBM/MLflow/PyArrow plus the
Wave 1 runner. It does **not** start Endpoint health checks, train/score a model
or execute a three-run simulation batch. `make serverless-smoke` invokes this
same build/import check.

Options match [the build script](../scripts/build-serverless-images.sh):

```text
IMAGE_NAMESPACE=ghcr.io/khab40
TAG=latest
PLATFORM=linux/amd64
TARGET=all                 # all | endpoint | jobs
PUSH=false
SMOKE=false
```

`ENDPOINT_IMAGE` and `JOBS_IMAGE` override local tags; `TARGET` selects the build.
Authorized image publication uses `PUSH=true` or `make serverless-push`.
Local build tags are not immutable Job deployment identities. Before building,
uploading or submitting a Job image, apply the
[repository-length/digest preflight](../docs/operations/digest-pinned-jobs.md).
No build command grants cloud-run authorization.

## Deployment Smoke Workflow

[`scripts/serverless-smoke.sh`](../scripts/serverless-smoke.sh) is a separate
runtime workflow: Endpoint health/alert/report requests, a three-run Jobs-image
rule batch, a ten-attack managed experiment and local batch, with optional Job
submission/collection if command templates are configured.

It writes responses and `summary.json` to `outputs/serverless-smoke/` by default.
Cloud execution may remain pending while smoke succeeds. Review its selected
Endpoint, Job configuration and execution bounds before an authorized run;
Endpoint inference and model workloads follow the applicable
[execution policy](../docs/ml/model-validation-execution-policy.md).

## First Deployment Checklist

1. Follow the [Endpoint deployment procedure](endpoint/README.md#deploy-local-vllm-on-l40s) for its selected mode/resources and authorization.
2. Configure backend URLs and check explicitly labelled mock/real/fallback state.
3. Use the [Jobs reference](jobs/README.md#experiment-job-config-rendering) and current digest policy for a separately authorized batch package.
4. Retain execution identities, terminal/readback evidence and collected artifacts.

The old tag-oriented first-deployment examples and July registry observations
are retained in the
[historical revision](https://github.com/khab40/lob-arena/blob/d896efe8ca501c1ef8e6c63442f3433948a6405e/serverless/README.md).
They are not current registry state or approved Job instructions.

## Cost Controls

Keep finite resource/time/Job-count bounds and required execution evidence.
[Validation execution policy](../docs/ml/model-validation-execution-policy.md)
owns current operator limits; historical smoke sizes are examples, not new
spend/access authorization.

## Safety

Synthetic outputs are educational evidence, not verified real manipulation,
trading signals or compliance decisions. Historical acquisition and governed
model artifacts retain their distinct provenance and qualification contracts.
