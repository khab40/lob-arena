# Use cases

LOB Arena supports synthetic demos, historical/hybrid replay, governed model
development and AI-assisted evidence review. Historical activity is not
automatically benign or abusive; outputs are not trading or compliance decisions.
Use [current status](../roadmap/CURRENT_STATUS.md) for qualification and
[functional scope](../product/FUNCTIONAL_OVERVIEW.md) for acceptance boundaries.

## Workflow catalogue

| Actor and task | Action and result | Detailed owner |
| --- | --- | --- |
| Operator: run a demo | Start Local Mock, launch a bounded scenario, inspect incidents and explicit real/fallback mode | [Quickstart](../deployment/QUICKSTART.md), [demo script](../publication/demo-script.md) |
| Operator: use live arena | Start/pause/reset Java replay and observe complete state over WebSocket | [Runtime model](../runtime/runtime-model.md) |
| Data steward: register history | Validate a licensed pair or ITCH window, write immutable normalized files, register verified hashes/counts | [Client runbook](../data/client-historical-dataset-validation-runbook.md), [ITCH decision](../architecture/ARD-0032-nasdaq-itch-ingestion.md) |
| Researcher: compare hybrid replay | Run historical control and a namespaced attack over the same source; preserve separate truth and signed comparison | [Replay quickstart](../data/replay-quickstart.md), [validation contract](../data/hybrid-dataset-validation.md) |
| Reviewers: freeze a corpus | Review clean windows independently, adjudicate conflicts, verify coverage and chronological splits, sign release | [Corpus protocol](../data/governed-corpus-benchmark-protocol.md) |
| ML engineer: develop a detector | Prepare causal features, train, calibrate/select using validation, freeze candidate and request separate final evaluation | [ML lifecycle](ml-lifecycle.md) |
| Reviewer: inspect MLflow | Inspect permitted lineage, metrics and artifacts after repository verification | [MLflow operations](../ml/mlflow-tracking-server.md) |
| Reviewer: investigate an incident | Select incident, submit bounded evidence through FastAPI, inspect typed AI report or explicit fallback | [Investigation decision](../architecture/ARD-0015-nebius-ai-investigation-team.md) |
| Scenario designer: generate variants | Provide bounded constraints, persist canonical ground truth and launchable scenario projection | [Generator decision](../architecture/ARD-0016-ai-scenario-generator.md) |
| Detector engineer: run tournament | Submit labeled scenario families and compare durable metrics, leaderboard and reports | [Tournament decision](../architecture/ARD-0017-ai-detector-tournament.md) |
| Researcher: generate fixtures | Generate labeled event/snapshot/incident artifacts and a manifest | [Job contract](../../serverless/jobs/README.md) |
| Reviewer: inspect timeline window | Request bounded timeline investigation; dedicated Judge Mode selection remains a separate UI gap | [Judge Mode decision](../architecture/ARD-0009-judge-mode-investigation-reports.md) |
| Builder: publish evidence | Package sanitized screenshots, demo, deployment and benchmark receipts | [Submission index](../publication/challenge-submission.md) |

## Live Arena Mode

Java owns the exchange and broadcasts arena state. Agent runners receive
read-only snapshots and return bounded intents. UI preferences remain browser
state. See the [live tick sequence](../architecture.md#live-tick-sequence).

## UI Shell Personalization

Choose day/night/system theme and compact navigation. Preferences stay local to
the browser and do not change simulation or detector state; no Nebius call is
needed. See [UI preferences](../architecture/ARD-0013-ui-shell-preferences.md).

## Manual Scenario Launch

Use Scenario Setup to launch spoofing-like walls, layering-like patterns,
quote-stuffing bursts or liquidity evaporation. Only synthetic scenarios create
attack labels. The [scenario decision](../architecture/ARD-0006-scenario-labeling-and-reproducibility.md)
owns lifecycle/reproducibility; generated variants use the same bounded launch path.

## Historical Session Registration

Import a complete session or bounded window. Validate schema, alignment,
book invariants and provenance; atomically publish normalized files and manifest
before registration. Keep licensed raw records out of MLflow by default.
Follow the [client runbook](../data/client-historical-dataset-validation-runbook.md).

## Hybrid Historical Replay

Load the same dataset for **Historical control** and **Hybrid + attacks**;
launch an existing scenario only after loading the replay source. Compare
detector metrics and causal-locality evidence without labeling the historical
control clean. [Hybrid validation](../data/hybrid-dataset-validation.md)
defines the signed evidence and statistical acceptance rules.

## Governed Corpus Release

The [corpus protocol](../data/governed-corpus-benchmark-protocol.md) owns coverage,
independent blinded review, adjudication, embargo and exact artifact bindings.
Its client-governance requirements are distinct from the four-date C4
research-control assumption. Typed contracts and CLIs exist; a multi-reviewer
product API/UI is not implied. See [data preparation](ml-data-preparation.md).

## Shared MLflow Tracking

Verify repository contracts before logging approved metadata/artifacts into
corpus, development or governed-evaluation namespaces. Raw rows remain outside
tracking. Namespace creation and artifact logging do not implement model-version
promotion. [MLflow operations](../ml/mlflow-tracking-server.md) owns setup and
[model serving](ml-model-serving.md) describes planned registration/retention.

## Governed LightGBM v1

Follow [training and selection](ml-training-selection.md) for training-only
fitting, validation reuse, calibration, candidate selection and checkpoints.
Use the [LightGBM runbook](../ml/lightgbm-v1-runbook.md) for commands. Final scoring
requires its own authorization; recovery rehearsal is not production quality.
Transformer training, cascade and live learned serving remain planned.

## Incident Investigation

Select an incident and Analyze. FastAPI loads bounded evidence and calls the
configured endpoint; the UI displays typed results and real/fallback mode.
Credentials stay on the server and the explanation does not change detector
scores. See [endpoint flow](../architecture/ARD-0005-nebius-endpoint-contract.md#endpoint-flow).

## Red-Team Scenario Generation

Provide attack family, market condition, objective, stealth, duration, agent count
and difficulty. The bounded output is persisted as an `AttackScenario`, selectable
as `ATTACK-*` source context for scenario grids/batches. A typed mock fallback is
explicit. [ARD-0016](../architecture/ARD-0016-ai-scenario-generator.md) owns payloads,
canonical ground truth, injection and acceptance requirements.

## Detector Tournament Benchmark

The [tournament interface](../architecture/ARD-0017-ai-detector-tournament.md)
owns run/status/artifact APIs. The Job CLI accepts `--runs`, `--scenarios`,
`--detectors` and `--output`, producing `benchmark_report.md`, `metrics.csv`
and `results.json`. [Benchmark methodology](../ml/benchmark-methodology.md)
and [calculation limitations](../runtime/calculations-explanations.md) define
what these legacy synthetic metrics measure. Apply the execution policy below.

## Synthetic Dataset Generation

`serverless/jobs/synthetic_dataset_factory.py` accepts `--samples` and `--output`.
It emits events, incidents, labels, manifest and Parquet snapshots, with
`snapshots.parquet.jsonl` fallback when Parquet support is absent. Preserve the
format distinction; see [job artifacts](../../serverless/jobs/README.md).

## Judge Mode Investigation Report

The proposed selection flow bundles a bounded timeline window, requests a
structured investigation and exposes completion or mock fallback. Do not infer
a completed dedicated selector from the report API. See
[ARD-0009](../architecture/ARD-0009-judge-mode-investigation-reports.md).

## Challenge Submission Evidence

Use the [submission index](../publication/challenge-submission.md) for endpoint,
Job and deployment receipts, screenshots and video. Frozen challenge evidence
is historical; it does not qualify later learned models.

## Execution and planned scope

Endpoints handle interactive explanations and scenario drafts; Jobs handle
offline workloads. Agent-initiated model work must follow the
[Nebius execution policy](../ml/model-validation-execution-policy.md).
The [main roadmap](../roadmap/ROADMAP-MAIN.md) owns the sequential LightGBM,
Transformer, cascade, integrated evidence and secure CEO workflow.
BYO data/detector productization is parked; shared sensitive deployments still
require authentication and backend authorization before exposure.
