# Agent Runner

Separate process/container for normal-agent decisions.

The Java arena remains the authoritative exchange. This Python runner is retained for AI/ML, heavy, and LangGraph-capable decision work: it receives read-only market snapshots on `POST /decide` and returns `AgentIntent` objects. Java validates, sorts, and applies those intents as a single writer.

Environment:

```bash
AGENT_RUNNER_AGENT_COUNT=24
AGENT_RUNNER_MAX_AGENT_COUNT=48
AGENT_RUNNER_HEAVY_AGENT_COUNT=0
AGENT_RUNNER_MAX_HEAVY_AGENT_COUNT=2
AGENT_RUNNER_HEAVY_AGENT_COMPLEXITY=20000
AGENT_RUNNER_HEAVY_AGENT_WORKERS=1
AGENT_RUNNER_MAX_HEAVY_AGENT_WORKERS=1
AGENT_RUNNER_LANGGRAPH_AGENT_COUNT=0
AGENT_RUNNER_MAX_LANGGRAPH_AGENT_COUNT=4
AGENT_RUNNER_LANGGRAPH_STRATEGY=liquidity_rebalancer
AGENT_RUNNER_AGENT_ID_PREFIX=REMOTE
AGENT_RUNNER_DECISION_TIMEOUT_SECONDS=0.05
```

These are the code and Compose defaults. Requested normal, heavy, worker and
LangGraph counts are clamped to their corresponding `AGENT_RUNNER_MAX_*`
values; `/health` reports effective counts and limits. Increasing a requested
count alone does not increase its cap. Java's per-tick deadline still applies;
see [runtime controls](../docs/runtime/runtime-model.md).

Endpoints:

- `GET /health`
- `GET /agents`
- `GET /metrics`
- `POST /decide`

LangGraph agents are implemented in `langgraph_agents.py` with `StateGraph`. They use the same `/decide` request and `AgentIntent` response contract as other remote agents.

Metrics are dependency-free Prometheus text metrics for local Grafana dashboards:

- `agent_runner_decide_requests_total`
- `agent_runner_decide_duration_seconds`
- `agent_runner_intents_returned`
- `agent_runner_agents`
- `agent_runner_up`
