# LOB Arena Deployment Modes

Deployment entry point:

```bash
deployments/deploy.sh <mode> [--dry-run] [--skip-build] [--skip-smoke]
```

For the current recommended split, use the lighter helper instead:

```bash
scripts/deploy-nebius-partial.sh --dry-run
scripts/deploy-nebius-partial.sh
```

It deploys only the Nebius execution surfaces: endpoint image, jobs image, GPU
local-vLLM endpoint, and backend/job env wiring. The frontend, backend, and
agent-runner stay on local Docker Compose until there is a concrete need for a
public cloud app host.

The generated backend environment enables the serverless branch of the single
`docker-compose.yml`. Prometheus can be added with `--profile prometheus`, and
`--profile grafana` adds both Prometheus and Grafana.

Prometheus is the operational metric collector and time-series store for Java
Actuator, FastAPI, and agent-runner endpoints. Grafana queries that Prometheus
instance and renders the pre-provisioned LOB Arena dashboards. Both profiles are
optional, local, and read-only; they do not deploy a production monitoring
platform to Nebius or participate in simulation and detector decisions. See
[Kernel Observability](../docs/runtime/kernel-observability.md) for the scrape targets,
dashboard roles, and profile commands.

For a small Nebius VM app host, use:

```bash
export NEBIUS_VM_HOST=<vm-public-ip-or-dns>
export IMAGE_NAMESPACE=ghcr.io/<owner>
export TAG=vm-demo
export NEBIUS_ENDPOINT_BASE_URL=<deployed-local-vllm-endpoint-url>
export ENDPOINT_TOKEN=<endpoint-bearer-token>

scripts/deploy-nebius-vm.sh --dry-run
scripts/deploy-nebius-vm.sh
```

This deploys only `frontend`, `backend`, and `agent-runner` to the VM with
Docker Compose. By default it installs Docker on a fresh VM; set
`NEBIUS_VM_BOOTSTRAP_DOCKER=false` if the VM is already managed. Keep GPU
inference on Nebius Serverless Endpoint and detector tournaments on Nebius
Serverless Jobs. For thousands of logical agents, raise
`AGENT_RUNNER_AGENT_COUNT`/`AGENT_RUNNER_MAX_AGENT_COUNT` on the VM first; move
to Kubernetes CPU node pools when you need multiple runner shards with separate
service addresses in `ARENA_REMOTE_AGENT_URLS`.

For the later Kubernetes path:

```bash
export KUBE_CONTEXT=<context>
export IMAGE_NAMESPACE=ghcr.io/<owner>
export TAG=k8s
export K8S_PUBLIC_ORIGIN=https://<app-host>
export K8S_API_BASE_URL=https://<app-host>
export K8S_WS_URL=wss://<app-host>/ws/arena
export K8S_AGENT_RUNNER_REPLICAS=4

scripts/deploy-nebius-k8s.sh --dry-run
scripts/deploy-nebius-k8s.sh
```

Start with `K8S_BACKEND_REPLICAS=1`; the backend owns in-memory arena state and
local output files today. The Kubernetes runner uses a StatefulSet so the
backend can call every shard by stable pod DNS. Scale `K8S_AGENT_RUNNER_REPLICAS`
first for thousands of simulated agents. Add durable storage/session routing
before raising backend replicas.

Modes:

- `local-demo` runs the local Docker Compose demo with deterministic Nebius fallback.
- `nebius-cloud-demo` creates Nebius endpoint/job resources and runs the app against them.
- `production-nebius` creates Nebius endpoint/job resources and requires storage, DB, MLflow, observability, IAM, and secrets settings.

Lifecycle covered by every mode:

```text
simulate -> detect -> explain -> investigate -> report -> audit -> benchmark
```

Examples:

```bash
deployments/deploy.sh local-demo
deployments/deploy.sh nebius-cloud-demo --dry-run
deployments/deploy.sh production-nebius --dry-run
```

Mode configuration lives in `deployments/modes/*.env`. Local `.env` values are loaded after the mode file, so real tokens and resource IDs stay outside git.

Production required variables:

- `NEBIUS_SUBNET_ID`
- `NEBIUS_ENDPOINT_TOKEN`
- `AIMADA_OBJECT_STORAGE_URI`
- `AIMADA_POSTGRES_DSN`
- `AIMADA_MLFLOW_TRACKING_URI`
- `AIMADA_OBSERVABILITY_ENDPOINT`
- `AIMADA_IAM_PROFILE`
- `AIMADA_SECRETS_BACKEND`

Each run writes a deployment report to `outputs/deployments/<mode>-latest.env`.
