# LOB Arena Nebius AI Serverless Demo Script

## Goal

Show LOB Arena as a Nebius AI Serverless-powered market surveillance command center in under five minutes. The demo works fully in local mock mode and keeps the same UI/API contracts for real Nebius execution.

## Setup

Repository: [https://github.com/khab40/lob-arena](https://github.com/khab40/lob-arena)

```bash
git clone https://github.com/khab40/lob-arena.git
cd lob-arena
cp .env.example .env
docker compose up --build
```

Open http://localhost:5173. The app should land on `AI Command Center`.

Local Demo requires no login, endpoint token, or deployed Nebius endpoint.

## Step 1: Generate AI Scenario

Preferred path:

1. In `Command Center`, click `Run Serverless E2E Demo`.
2. Show the story line:
   `AI-generated spoofing incident -> LOB simulation -> detector alert -> LLM explanation -> investigation report -> detector tournament -> artifacts`.
3. Confirm current mode:
   - `local` for local deterministic execution
   - `real_nebius_pending` when Nebius job command templates are missing
   - `real_nebius` when the real command-template path is configured
4. Open `outputs/serverless-smoke/manifest.json`.

Manual backup path:

1. In `Nebius AI Scenario Generator`, choose:
   - manipulation type: `Spoofing`
   - difficulty: `Medium`
   - symbol: `AIMD`
   - duration: `120`
   - liquidity: `Thin`
   - volatility: `High`
2. Click `Generate Nebius AI Scenario`.
3. Show:
   - `Powered by Nebius AI Serverless Endpoint`
   - scenario id
   - ground truth label
   - expected detector signals
   - event timeline

Screenshot: `AI Scenario Generator` result.

## Step 2: Replay Scenario In Arena

1. Click `Replay in Arena`.
2. Open or switch to **Arena** if needed.
3. Show that the generated scenario is projected into the existing simulator replay path.
4. Point out that replay uses synthetic ground truth, not real market data.

Screenshot: Arena replay or active workload state.

## Step 3: Run Nebius AI Investigation Team

1. Return to `AI Command Center`.
2. In `Nebius AI Investigation Team`, click `Run Nebius AI Investigation Team`.
3. Show:
   - final verdict
   - risk score
   - confidence
   - agent findings
   - evidence timeline
   - recommended action

Screenshot: `Nebius AI Investigation Team` result.

## Step 4: Run Detector Tournament

1. In `Nebius AI Detector Tournament`, keep the default `100` workloads, batch size `20`, scenarios, and seed `42`.
2. Click `Create benchmark`, then `Generate manifest`.
3. Click `Run Local Demo tournament` for the deterministic path, or `Run serverless job` in Cloud mode.
4. Click `Aggregate` after execution completes.
5. Show:
   - `Powered by Nebius Serverless Jobs`
   - latest execution and Job status
   - detectors and models compared
   - precision, recall, F1, and latency leaderboard
   - downloadable artifacts

Screenshot: Detector Tournament status and metrics.

## Step 5: Show Leaderboard And Artifacts

1. Show the leaderboard rows.
2. Open artifact links if available:
   - `metrics.csv`
   - `results.json`
   - `benchmark_report.md`
   - F1 / confidence / latency charts
3. Explain that the same response shape is used when Nebius Serverless Jobs are configured.
4. For the polished E2E path, open:
   - `outputs/serverless-smoke/summary.json`
   - `outputs/serverless-smoke/scenario.json`
   - `outputs/serverless-smoke/simulation_events.json`
   - `outputs/serverless-smoke/detector_alerts.json`
   - `outputs/serverless-smoke/investigation_report.md`
   - `outputs/serverless-smoke/tournament_result.json`
   - `outputs/serverless-smoke/serverless_job.json`
   - `outputs/serverless-smoke/manifest.json`

Screenshot: Detector Tournament leaderboard and artifact links.

## Real Nebius Path

For a real Nebius run:

```bash
NEBIUS_ENDPOINT_MODE=local_vllm
NEBIUS_ENDPOINT_BASE_URL=<deployed-endpoint-base-url>
ENDPOINT_TOKEN=<endpoint-token>
NEBIUS_JOB_IMAGE=<job-image>
NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE=<submit-command-template>
NEBIUS_JOB_STATUS_COMMAND_TEMPLATE=<status-command-template>
NEBIUS_JOB_LOGS_COMMAND_TEMPLATE=<logs-command-template>
NEBIUS_JOB_ARTIFACTS_COMMAND_TEMPLATE=<artifacts-command-template>
```

The interactive path calls the Nebius AI Serverless Endpoint. The batch path uses Nebius Serverless Jobs for detector tournament compute.
If command templates are not configured, the E2E smoke demo still writes local artifacts but labels cloud job state as `real_nebius_pending`.

## Judge Talking Points

- Nebius AI Serverless Endpoint is used for interactive investigation and scenario generation.
- Nebius Serverless Jobs are used for scalable detector tournaments.
- Local mock mode exists for reliable judging and preserves the same API contracts.
- All outputs are synthetic and educational; LOB Arena is not a real compliance system.
