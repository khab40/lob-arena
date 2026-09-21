# Building LOB Arena: An Adversarial Market-Surveillance Evaluation Platform with Nebius Serverless AI

![LOB Arena concept showing the synthetic market-abuse evaluation arena](../assets/img/03-lob-arena-red-vs-blue.jpg)
*LOB Arena is a synthetic arena for evaluating market-abuse detectors and AI-assisted investigations on Nebius Serverless AI.*

Market-surveillance teams can purchase historical order-book data from exchanges and specialist market-data vendors. The harder problem is obtaining complete, reliable ground-truth labels that identify which sequences represent manipulation, which reflect legitimate trading behaviour, and how a surveillance system should respond.

Even with high-quality historical data, benchmarking remains difficult. Teams need repeatable scenarios, known agent intentions, consistent ground truth, controlled market conditions, and comparable metrics across detector designs and market regimes.

This was the motivation for **LOB Arena**.

LOB Arena is an open-source platform for generating synthetic limit-order-book activity, injecting bounded abuse-like scenarios, benchmarking surveillance detectors, and using Nebius Serverless AI to produce structured investigations and explanations.

**Repository:** [https://github.com/khab40/lob-arena](https://github.com/khab40/lob-arena)

**Video demo:** [LOB Arena — real Nebius cloud E2E walkthrough](https://youtu.be/PZOrEwa4lqg)

I built the project for the **#NebiusServerlessChallenge** as an engineering environment rather than as a claim that an AI model can independently detect real market manipulation.

The goal is to create a controlled, reproducible arena in which the ground truth is known because the scenarios are generated deliberately.

![LOB Arena functional diagram showing simulation, detection, incidents, AI investigation, and detector benchmarking](../assets/img/02-lob-arena-functional-diagram-improved.jpg)

*LOB Arena’s functional flow: simulate bounded market-abuse scenarios, detect suspicious behaviour, create incidents, investigate with AI, and benchmark detector performance.*

That creates a concrete engineering surface: generate market events, inject labeled scenarios, run deterministic detectors, preserve structured evidence, and use AI to explain what the detector already found.

The architecture has two main execution paths.

The interactive path uses a React and Vite frontend, a FastAPI control plane, a separate agents workspace, and a Nebius Serverless AI Endpoint. The batch path uses Nebius Serverless AI Jobs for repeatable synthetic workloads, detector evaluation, aggregation, and artifact generation.

![Architecture diagram connecting the frontend, backend, agent-runner workspace, Nebius Serverless Endpoint and Jobs, Object Storage, and evidence UI](../assets/img/04-lob-arena-architecture-improved.jpg)

*LOB Arena separates the React interface, authoritative FastAPI runtime, agents workspace, and Nebius Endpoint and Job execution paths.*

LOB Arena was validated on real Nebius production infrastructure. The latest evidence set contains six newly completed 200-workload Nebius Serverless AI Jobs, in addition to earlier deployment checks. I also deployed a vLLM-backed Nebius Serverless AI Endpoint and exercised routes for scenario generation, incident analysis, investigation reporting, order-book alert analysis, and structured market-event explanation. Those runs produced Job artifacts, detector metrics, reports, logs, and Endpoint responses. This validation proves the execution contracts; it does not turn LOB Arena into a real-market surveillance product.

Job lifecycle records and generated artifacts are archived to Nebius Object Storage. Endpoint execution metadata is archived through the same evidence layer without presenting private credentials or sensitive transport details to the browser. The backend can synchronize archived evidence from S3-compatible storage back to backend-local storage, and the UI exposes the synchronized records and downloadable artifacts. This creates a traceable path from production execution, through durable storage, to evidence that a reviewer can inspect.

## The interactive path

The frontend renders the live arena: order-book ladders, price and spread charts, liquidity heatmaps, agent activity, detector confidence, incident cards, replay, and report views.

The browser sends commands over WebSocket. The FastAPI backend runs the simulation and publishes complete `arena_state` messages. This keeps the browser away from simulation internals, server credentials, and direct Endpoint access.

During an interactive run, LOB Arena uses the separate `agent-runner/` workspace to generate normal synthetic market activity.

At each simulation tick, the backend sends a read-only order-book snapshot to the workspace through its `/decide` API. The workspace returns typed `AgentIntent` objects rather than mutating the market directly. The backend validates and deterministically sorts those intents, remains the single authoritative writer, and applies accepted actions to the synthetic exchange and matching engine.

The workspace runs several kinds of trading agents. Top-of-book market makers refresh visible liquidity on both sides. Deterministic noise traders make small cadence-based changes at selected levels. Periodic liquidity takers alternate bounded synthetic buys and sells. Optional LangGraph agents can choose which side to quote from observed depth imbalance. Optional CPU-heavy agents exercise a more computationally expensive decision path for workload testing.

This separation lets the frontend display agent activity while the backend preserves ordering, timeouts, validation, and reproducibility.

None of these agents connects to a broker, exchange, or real market. They trade only inside LOB Arena’s synthetic order book and cannot emit real orders or trading signals.

Inside the backend, the core loop is intentionally deterministic. A synthetic exchange, order book, and matching engine process actions from market-making, liquidity-taking, and noise agents. Scenario agents can then inject the four implemented workloads: Spoofing-like Wall, Layering-like Pattern, Quote Stuffing Burst, and Liquidity Evaporation.

The key word is “bounded.” These are synthetic patterns for education and detector testing, not instructions for real market activity.

## Why detection and explanation are separate

Nebius Serverless AI Endpoints do not make LOB Arena’s original detection decision.

A deterministic detector produces structured evidence first: spread, visible depth, imbalance, message rate, cancel-to-trade ratio, wall-size ratio, order lifetime, confidence scores, and scenario labels.

The backend then sends a compact incident payload to the Endpoint. The Endpoint can return a readable explanation, investigation assistance, recommended review actions, or a bounded synthetic scenario draft.

This split matters because it keeps the workflow auditable. AI is used for explanation, narration, investigation assistance, and bounded scenario generation. Structured detector evidence remains the source of truth.

![Structured JSON contract for surveillance-style LLM output](../assets/img/07-structured-json-output.jpg)

*Endpoint responses are parsed as structured JSON so the UI can separate classification, confidence, evidence, counter-evidence, and recommended actions.*

## The batch path

Nebius Serverless AI Jobs fit the offline evaluation path naturally. Instead of asking a live request to run dozens or hundreds of simulations, a Job can execute repeatable synthetic workloads, evaluate detector output against labels, aggregate metrics, and persist reports and artifacts before terminating.

![Nebius deployment and evidence flow from production execution to synchronized review artifacts](../assets/img/05-nebius-deployment-evidence-flow.jpg)

*Production Job and Endpoint evidence is archived to Object Storage, synchronized by the backend, and exposed as reviewable UI records and downloads.*

The outputs are designed to be reviewable: JSON records, CSV metrics, Markdown reports, logs, and chart-ready data. The metric vocabulary includes precision, recall, F1, false positives, false negatives, and detection latency against known synthetic labels.

The repository is organized around those boundaries.

`backend/` contains the FastAPI application, simulation engine, exchange model, detectors, incident storage, Nebius client, evidence synchronization, and report generation.

`agent-runner/` contains the agents workspace service, its `/health`, `/agents`, and `/decide` contracts, normal synthetic agents, optional CPU-heavy agents, and bounded LangGraph strategies.

`frontend/` contains the React arena, Detection workflow, Scenario Generator, Nebius AI controls, evidence views, and visualization components.

`serverless/` contains the Endpoint application, Job runners, Dockerfiles, and example deployment configurations.

`docs/` contains architecture decisions, deployment notes, benchmark methodology, safety framing, and challenge-submission material.

`outputs/benchmark/` contains the public sanitized benchmark and production-evidence sample.

## Four evidence layers

I use four explicit names in the repository so small integration checks are not confused with production validation.

### Smoke Contract Test

The **Smoke Contract Test** is the smallest end-to-end integration check. It verifies that scenario generation, simulation, detector routing, investigation output, tournament execution, and artifact contracts connect correctly.

The deliberately small one-run detector example covers spoofing-like and quote-stuffing scenarios. Matching detectors reach precision 1.0, recall 1.0, and F1 1.0, with an average detection latency of 1,500 ms in that fixture.

Those perfect values are integration evidence only. They validate labels, routing, metric calculation, and artifact persistence on a deliberately simple deterministic fixture. They are not evidence of real-world surveillance accuracy, robustness, or compliance suitability.

### Local Reproducibility Benchmark

The **Local Reproducibility Benchmark** is the deterministic path another practitioner can run with Docker Compose. It generates labeled synthetic workloads and produces metrics, leaderboards, reports, and artifacts without requiring Nebius credentials.

Its purpose is reproducibility: the same configuration and seed should preserve the evaluation contract and make failures inspectable. Local execution is not presented as proof that a cloud Job or Endpoint ran.

### Production Execution Validation

The **Production Execution Validation** covers the real Nebius infrastructure path. More than ten Serverless AI Job runs validated container startup, scenario execution, detector evaluation, aggregation, reporting, logging, and artifact persistence. The vLLM-backed Endpoint separately validated interactive routes.

This layer answers a deployment question: do the packaged Job and Endpoint contracts operate on production infrastructure and produce reviewable outputs? It does not answer whether the synthetic detector generalizes to real markets.

### Representative Production Run

The **Representative Production Run** is the compact, sanitized evidence sample committed for review. It preserves Job records, normalized detector metrics, a detector/model leaderboard, investigation results, an evidence index, a benchmark report, a manifest, and checksums.

The public bundle intentionally excludes credentials, authorization headers, private Endpoint hostnames, signed URLs, and raw environment-specific logs. It also reconciles the benchmark denominator explicitly: the representative 100-workload run contains 80 labeled attack rows and 20 normal-market control rows. A judge can inspect the evidence without access to the private Nebius account or Object Storage bucket.

![LOB Arena detection pipeline connecting labeled workloads to metrics, reports, and production evidence](../assets/img/06-detector-tournament-pipeline.jpg)

*Detector Tournament results connect labeled synthetic workloads to metrics, leaderboards, reports, and sanitized production-execution evidence.*


## Why Nebius Serverless AI

LOB Arena uses Nebius Serverless AI in two materially different ways.

The **Serverless AI Endpoint** supports interactive operations such as AI Investigation Team analysis, incident explanation, structured investigation reports, bounded synthetic scenario generation, and market-event summarization. The representative deployment uses an NVIDIA L40S configuration, the `1gpu-16vcpu-96gb` preset, `Qwen/Qwen2.5-14B-Instruct`, and vLLM inference.

**Serverless Jobs** support offline evaluation: running multiple synthetic scenarios, comparing detector predictions with ground truth, calculating precision, recall, F1 and latency, generating leaderboards, writing reports, and persisting artifacts. The representative Job configuration uses the `cpu-d3` preset with four virtual CPUs and 16 GB of memory.

Using both products demonstrates more than a single inference request. The Endpoint handles interactive AI, while Jobs provide the repeatable batch-compute layer required by the benchmarking workflow.

## Results

LOB Arena now demonstrates an end-to-end workflow from synthetic scenario generation to reviewable investigation and benchmark evidence.

The corrected production benchmark consists of six completed Nebius Serverless Job executions.

Each experiment used a distinct base seed and generated 200 independently seeded workloads. Across the full production set, LOB Arena processed:

- 6 Nebius Serverless Jobs
- 1,200 synthetic workloads
- 148,958 simulation events
- 1,200 unique derived run seeds
- zero seed overlap between experiments
- six distinct event-stream SHA-256 digests
- six distinct detector-metrics SHA-256 digests

The aggregate detector results were:

| Metric | Result |
|---|---:|
| True positives | 710 |
| False negatives | 250 |
| False positives | 0 |
| True negatives | 240 |
| Precision | 1.000 |
| Recall | 0.740 |
| F1 | 0.850 |
| Specificity | 1.000 |
| False-positive rate | 0.000 |

Spoofing-like Wall and Quote Stuffing Burst achieved recall of 1.0. Layering-like Pattern achieved 230 detections out of 240 workloads, for recall of 0.958.

Liquidity Evaporation produced 240 false negatives and recall of 0.0. This is the principal benchmark finding: the detector suite performs strongly on three scenario families but has a complete blind spot for Liquidity Evaporation.

This result demonstrates the purpose of LOB Arena. The platform is not designed merely to produce favorable scores; it is designed to expose detector weaknesses under reproducible, explicitly labeled workloads.

The six Jobs produced 42 synchronized output artifacts. Their measured lifecycle time was 1,308.436 seconds in total, including queueing, status polling, and artifact collection. This is not equivalent to provider-billed compute time.

Cloud pricing rates were not configured for the corrected production set, so no dollar cost is claimed for those six Jobs.

The initial six-Job production set had exposed an evidence-quality bug: different seeds were stored in experiment metadata but were not forwarded into Job arguments. That repeated set remains audit history only and is not used in these benchmark claims.

### Endpoint and manual UI evidence

The production Endpoint evidence adds 25 completed L40S/vLLM calls: 17 Investigation Team requests, four investigation reports, and four scenario generations. All 25 completed without fallback and were uploaded to S3. They used 25,084 prompt tokens and 13,345 completion tokens, 38,429 tokens total; all 17 Investigation Team responses preserved the validated structured assessment, and P50 latency was 27.141 seconds.

I then ran the workflow manually through the Control Panel. That session completed a separate 100-workload Nebius Job with 100 unique derived seeds and 12,414 events. Its matched confusion counts were TP 60, FN 20, FP 0, and TN 20: precision 1.000, recall 0.750, and F1 0.857. The same session made 12 real Endpoint calls (16,279 tokens), including two schema-validated Investigation Team responses and seven JSON investigation reports; all 12 evidence records were uploaded to S3. The [sanitized manual UI bundle](../evidence/manual-ui-2026-07-15/README.md) preserves the metrics and execution boundary.

The manual result reinforced the main detector finding: Spoofing-like Wall, Layering-like Pattern, and Quote Stuffing Burst were detected in all 20 matched workloads, while Liquidity Evaporation was missed in all 20. The Polished E2E local stages also completed, but its cloud child lookup returned `NotFound`; I do not count that child as a completed Job. The independently submitted 100-workload managed experiment is the cloud-completion evidence.

The detector metrics validate the synthetic evaluation and execution contracts. They should not be interpreted as claims about production-market surveillance accuracy.

## What I learned

The most important design choice was separating “detect” from “explain.” In many AI prototypes, the model is asked to be both judge and storyteller. That is convenient, but difficult to evaluate.

In LOB Arena, detectors are deterministic functions over synthetic order-book state. They create incidents with explicit evidence. The AI layer translates that evidence into plain language, helps organize an investigation, narrates the result, or generates a bounded scenario. It does not silently replace detector logic or become the source of ground truth.

I also found that evidence transport is part of the product architecture. A successful cloud status is useful, but a reviewer needs the associated metrics, reports, logs, timestamps, and artifacts. Archiving to Object Storage, synchronizing through the backend, and exposing downloads in the UI turns an execution claim into an inspectable chain.

The next research steps are to increase benchmark and scenario diversity, develop adaptive adversarial agents, and measure detector degradation as market regimes change. I also want to calibrate synthetic behavior using publicly available market distributions, build richer incident replay tools, and compare deterministic and learned detectors under the same labels and evaluation contracts.

That comparison matters. A learned detector should not receive a more forgiving evaluation path because its internals are more complex. Deterministic and learned approaches should consume compatible evidence, preserve the same ground truth, report the same metric families, and produce artifacts another practitioner can inspect.

Public repository: [https://github.com/khab40/lob-arena](https://github.com/khab40/lob-arena)

Safety disclaimer: LOB Arena is synthetic and educational. It uses no real trading data, does not detect real market manipulation, does not provide trading signals, and is not suitable for compliance decisions.

#NebiusServerlessChallenge
