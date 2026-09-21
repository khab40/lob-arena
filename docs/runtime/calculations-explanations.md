# LOB Arena Calculations and Workflow Explanations

## Table of Contents

- [Overview](#overview)
- [End-to-End Flow](#end-to-end-flow)
- [Step 1 — Runtime](#step-1--runtime)
  - [Local Demo](#local-demo)
  - [Nebius Cloud](#nebius-cloud)
  - [Execution Evidence](#execution-evidence)
- [Step 2 — Scenario Generator](#step-2--scenario-generator)
  - [Inputs](#inputs)
  - [Endpoint Generation Path](#endpoint-generation-path)
  - [Canonical Scenario Output](#canonical-scenario-output)
  - [Deterministic Fallback Generation](#deterministic-fallback-generation)
  - [Projection into Arena](#projection-into-arena)
  - [Replay in Arena](#replay-in-arena)
- [Step 3 — Investigation Team](#step-3--investigation-team)
  - [Input Evidence](#input-evidence)
  - [Investigation Output](#investigation-output)
  - [Detector Confidence vs Investigator Confidence](#detector-confidence-vs-investigator-confidence)
- [Detector Evidence Calculations](#detector-evidence-calculations)
  - [Bid and Ask Depth](#bid-and-ask-depth)
  - [Order-Book Imbalance](#order-book-imbalance)
  - [Spread in Basis Points](#spread-in-basis-points)
  - [Depth Change](#depth-change)
  - [Wall-Size Ratio](#wall-size-ratio)
  - [Cancel-to-Trade Ratio](#cancel-to-trade-ratio)
  - [Order Lifetime](#order-lifetime)
  - [Message Rate](#message-rate)
- [Detector Formulas](#detector-formulas)
  - [Spoofing-Like Detector](#spoofing-like-detector)
  - [Layering-Like Detector](#layering-like-detector)
  - [Quote-Stuffing Detector](#quote-stuffing-detector)
  - [Liquidity-Shock Detector](#liquidity-shock-detector)
  - [Evidence Flattening](#evidence-flattening)
- [Step 4 — Detector Tournament](#step-4--detector-tournament)
  - [Tournament Inputs](#tournament-inputs)
  - [Execution Modes](#execution-modes)
  - [Local Tournament Workload](#local-tournament-workload)
  - [Single Simulation Run](#single-simulation-run)
  - [Ground-Truth Mapping](#ground-truth-mapping)
  - [Detection Latency](#detection-latency)
  - [Tournament Metrics](#tournament-metrics)
  - [Generated Artifacts](#generated-artifacts)
- [Step 5 — Execution Trace](#step-5--execution-trace)
- [Datasets Used](#datasets-used)
- [Known Implementation Gaps](#known-implementation-gaps)
- [Worked Evidence Example](#worked-evidence-example)
- [Accurate Technical Description](#accurate-technical-description)

---

## Overview

The Nebius Control Panel combines three different mechanisms:

1. deterministic market simulation;
2. deterministic rule-based detectors;
3. optional Nebius LLM and Serverless execution for scenario generation, investigation, explanation, and batch processing.

The five Control Panel workflow steps are:

1. Runtime
2. Scenario Generator
3. Investigation Team
4. Detector Tournament
5. Execution Trace

The most important architectural distinction is:

```text
Nebius AI:
  scenario generation
  evidence explanation
  investigation synthesis
  batch orchestration

Deterministic LOB Arena code:
  order book
  feature calculation
  detector confidence
  alert threshold
  tournament ground-truth mapping
  precision / recall / F1
```

The AI does not currently calculate the primary detector confidence values. Those values come from explicit feature formulas and weighted rules in the backend.

---

## End-to-End Flow

```text
Scenario parameters
       ↓
Nebius Endpoint or deterministic template
       ↓
Canonical scenario + explicit ground truth
       ↓
Projection into an Arena attack scenario
       ↓
Arena simulation / order-book changes
       ↓
Feature extraction on each tick
       ↓
Four deterministic detector scores
       ↓
Incident and evidence
       ↓
Nebius Investigation Team explanation
       ↓
Tournament against known synthetic labels
       ↓
Precision / recall / F1 / latency + artifacts
```

The order book and matching engine remain authoritative. AI produces bounded scenarios and explanations, while detector confidence is calculated by deterministic formulas.

---

# Step 1 — Runtime

## What this step does

Runtime selects whether LOB Arena operates in:

- **Local Demo** mode; or
- **Nebius Cloud** mode.

The UI checks:

- whether an AI Endpoint URL is configured;
- whether the endpoint is healthy;
- whether authentication credentials exist;
- whether a Serverless Job submission command is configured.

Conceptually:

```text
endpointWillUseNebius =
    cloud mode
    AND at least one endpoint is configured
    AND endpoint health is healthy / ok / ready

jobWillUseNebius =
    cloud mode
    AND Job submission template is configured
```

If those conditions fail, LOB Arena falls back to deterministic local behavior and displays the fallback status instead of claiming a successful cloud run.

## Local Demo

In Local Demo:

- scenario generation uses deterministic templates;
- investigation uses deterministic investigator output;
- tournament defaults to deterministic mock output;
- no GPU is used;
- no Nebius credentials are required;
- the same API response schemas and UI panels are retained.

This makes the demo reliable, but a visible result in the panel does not automatically prove that a Nebius Endpoint or Serverless Job actually ran.

## Nebius Cloud

In Cloud mode:

- Scenario Generator can call the Nebius Endpoint;
- Investigation Team can call the Nebius Endpoint;
- Detector Tournament can submit a Nebius Serverless Job;
- the UI polls Job status;
- generated artifacts can be collected from S3;
- execution evidence can be synchronized into the local evidence archive.

The standard tournament path polls every two seconds. Managed cloud experiment Jobs use five-second polling.

## Execution Evidence

The **Sync evidence from S3** action concerns cloud execution evidence, not detector evidence.

Execution evidence can include:

- Job IDs;
- endpoint request metadata;
- cloud artifact metadata;
- S3 locations;
- Job logs;
- manifests;
- checksums;
- model and endpoint information.

This differs from detector evidence such as `wall_size_ratio = 9.4` or `message_rate_per_sec = 22`.

---

# Step 2 — Scenario Generator

## Inputs

The Control Panel sends:

- manipulation type;
- difficulty;
- symbol;
- duration in ticks;
- liquidity regime;
- volatility regime;
- seed.

Accepted values:

```text
Manipulation:
  spoofing_like_wall
  layering_like
  quote_stuffing
  liquidity_evaporation

Difficulty:
  easy
  medium
  hard
  adversarial

Liquidity:
  thin
  normal
  deep

Volatility:
  low
  medium
  high

Duration:
  30–600 ticks
```

Default request:

```text
manipulation_type = spoofing
difficulty        = medium
symbol            = AIMD
duration_ticks    = 120
liquidity         = thin
volatility        = high
seed              = 42
```

## Endpoint Generation Path

The frontend calls:

```http
POST /api/nebius/scenario-generator/generate
```

The backend then:

1. sends the bounded request through the Nebius client;
2. normalizes the response into a strict canonical schema;
3. fills missing or malformed fields with deterministic fallback values;
4. projects the canonical scenario into an Arena-compatible attack;
5. stores the canonical and projected forms;
6. preserves explicit ground truth.

## Canonical Scenario Output

The canonical scenario contains:

```text
scenario_id
title
description
manipulation_type
difficulty
symbol
duration_ticks
liquidity_regime
volatility_regime
events[]
ground_truth
expected_detector_behavior
explanation
replay information
source/model information
fallback reason
```

Ground truth contains:

- manipulation label;
- manipulation start and end windows;
- manipulator agent IDs;
- expected detector targets;
- positively labelled event IDs.

The synthetic generator therefore produces the answer key explicitly. This makes later comparison between detector predictions and known truth possible.

## Deterministic Fallback Generation

When the real Endpoint is unavailable, `mock_response()` creates a reproducible scenario.

The scenario ID is based on:

```text
manipulation type + symbol + stable seed
```

The approximate manipulation window is:

```text
start_tick = max(10, duration_ticks / 6)

end_tick =
    min(
        duration_ticks,
        max(start_tick + 12,
            duration_ticks - duration_ticks / 5)
    )
```

### Event templates

**Spoofing**

```text
1. place a large visible wall
2. cancel before execution
3. execute a smaller opposite-side trade
```

**Layering**

```text
1. place a first layer
2. add another adjacent layer
3. cancel layers after pressure appears
```

**Liquidity Evaporation**

```text
1. thin the top three levels on both sides
2. maintain reduced visible depth
3. widen the spread after depth collapse
```

**Quote stuffing**

```text
1. burst-submit quotes
2. rapidly cancel them
3. record message-rate and spread distortion
```

### Quantity calculation

```text
thin liquidity   → 250
normal liquidity → 500
deep liquidity   → 800
```

### Price-offset scale

```text
low volatility    → 0.05
medium volatility → 0.15
high volatility   → 0.35
```

## Projection into Arena

The canonical AI scenario is translated into the existing Arena attack configuration.

Examples:

```text
fakeOrderLevels:
  quote stuffing → 8
  other types    → 4

fakeOrderSizeMultiplier:
  easy / medium    → 6
  hard / adversarial → 10

cancelDelayTicks:
  quote stuffing → 4
  other types    → 12

realTradeSize:
  easy      → 120
  otherwise → 240

stealth:
  easy          → obvious
  medium / hard → medium
  adversarial   → subtle
```

## Replay in Arena

The Replay button does not necessarily replay the raw LLM event list event-for-event.

Instead it:

1. takes the generated canonical scenario ID;
2. retrieves the projected attack scenario;
3. invokes the existing named-scenario injection path;
4. lets `SimulationEngine` and `ScenarioController` execute it.

A precise description is:

> The AI generates a canonical scenario specification. LOB Arena then projects that specification onto one of the simulator’s supported executable scenario families.

---

# Step 3 — Investigation Team

## Input Evidence

The Investigation Team normally receives an Arena incident or a fallback demonstration incident.

Its input can include:

- detector scores;
- detector confidence;
- order-book features;
- incident tick;
- attack and scenario context;
- market snapshots or timeline events;
- flattened detector evidence.

The backend endpoint is:

```http
POST /api/nebius/investigation-team/analyze
```

The request and response are persisted in:

```text
nebius/investigation_team_reports.jsonl
```

## Investigation Output

The Investigation Team returns:

- manipulation type;
- executive summary;
- risk score;
- confidence;
- consensus;
- specialist agent findings;
- evidence timeline;
- recommended action.

Each specialist provides:

```text
name
role
finding
confidence
evidence items
```

The Investigation Team is therefore primarily an explanatory and adjudication layer, not the primary detector.

## Detector Confidence vs Investigator Confidence

### Detector confidence

Calculated mechanically from explicit feature formulas.

### Investigator confidence and risk score

Returned by the Investigation Team response.

- In real Endpoint mode, this is model-generated structured output based on supplied evidence.
- In fallback mode, it is deterministic mock investigator output.

The investigator’s `risk_score` is not yet a statistically calibrated probability of real market abuse. It is an explanatory risk assessment over synthetic evidence.

---

# Detector Evidence Calculations

The detector feature extractor uses:

- current top-five bid levels;
- current top-five ask levels;
- recent simulation events;
- previous tick’s top-five total depth;
- tick duration;
- active scenario metadata;
- current tick.

No external historical market dataset is required for live Arena feature calculation.

## Bid and Ask Depth

For the top five levels:

```text
bid_depth = Σ quantity of top 5 bids
ask_depth = Σ quantity of top 5 asks
total_depth = bid_depth + ask_depth
```

## Order-Book Imbalance

```text
imbalance =
    (bid_depth - ask_depth)
    / (bid_depth + ask_depth)
```

If total depth is zero, imbalance is set to zero.

Interpretation:

```text
+1 → almost entirely bid-side depth
 0 → approximately balanced
-1 → almost entirely ask-side depth
```

## Spread in Basis Points

```text
spread_bps =
    spread / mid_price × 10,000
```

## Depth Change

Relative to the previous tick:

```text
depth_change_pct =
    (current_total_depth - previous_total_depth)
    / previous_total_depth × 100
```

## Wall-Size Ratio

The code first calculates average visible level size:

```text
normal_side_depth =
    (bid_depth + ask_depth)
    / number_of_top_levels
```

It then sums all book quantity owned by the synthetic `abuser`:

```text
abuser_depth =
    Σ quantity where level.owner == "abuser"
```

Finally:

```text
wall_size_ratio =
    abuser_depth / normal_side_depth
```

If no abuser-owned quantity exists, the value defaults to `1.0`.

This feature uses privileged simulator information. A real surveillance implementation would normally infer suspicious ownership or coordination from participant identity, account linkage, order lineage, or behavioral patterns rather than from a direct `owner == "abuser"` label.

## Cancel-to-Trade Ratio

An event is counted as a cancellation when the word `cancel` appears in its stage or message.

A trade is counted when:

```text
event.agent_id == "TAKER_01"
```

Then:

```text
cancel_to_trade_ratio =
    number_of_cancel_events
    / max(1, number_of_trade_events)
```

This definition is simulator-specific.

## Order Lifetime

When an attack is active:

```text
order_lifetime_ms =
    (current_tick - scenario_start_tick)
    × tick_interval_seconds
    × 1000
```

Strictly speaking, this measures elapsed time since scenario start, not the true lifetime of an individual order.

## Message Rate

```text
message_rate_per_sec =
    number_of_recent_events
    / tick_interval_seconds
```

---

# Detector Formulas

All current detectors raise an alert at:

```text
confidence >= 0.75
```

Severity bands are:

```text
confidence >= 0.90 → critical
confidence >= 0.75 → high
confidence >= 0.45 → medium
otherwise          → low
```

## Spoofing-Like Detector

Components:

```text
wall =
    min(wall_size_ratio / 8, 1)

lifetime =
    1.0  when 500 ms <= order_lifetime <= 5,000 ms
    0.25 otherwise

cancel =
    min(cancel_to_trade_ratio / 3, 1)

imbalance =
    min(abs(order_book_imbalance) / 0.5, 1)
```

Final confidence:

```text
spoofing_confidence =
    0.60 × wall
  + 0.20 × lifetime
  + 0.10 × cancel
  + 0.10 × imbalance
```

Evidence exposed to the investigator:

- visible wall ratio;
- order lifetime;
- cancel-to-trade ratio.

## Layering-Like Detector

```text
wall =
    min(wall_size_ratio / 5, 1)

imbalance =
    min(abs(order_book_imbalance) / 0.35, 1)

depth =
    1.0  if ask_depth > bid_depth × 1.4
    0.35 otherwise
```

Final confidence:

```text
layering_confidence =
    0.45 × wall
  + 0.30 × imbalance
  + 0.25 × depth
```

Evidence:

- top ask depth;
- order-book imbalance.

The current special depth condition is ask-side-oriented and is not symmetric for buy-side layering.

## Quote-Stuffing Detector

```text
message =
    min(message_rate_per_sec / 18, 1)

cancel =
    min(cancel_to_trade_ratio / 8, 1)
```

Final confidence:

```text
quote_stuffing_confidence =
    0.75 × message
  + 0.25 × cancel
```

Evidence:

- messages per second;
- cancel-to-trade ratio.

## Liquidity-Shock Detector

```text
depth =
    min(abs(min(depth_change_pct, 0)) / 45, 1)

spread =
    min(spread_bps / 1, 1)

imbalance =
    min(abs(order_book_imbalance) / 0.55, 1)
```

Only negative depth changes contribute to the depth component.

Final confidence:

```text
liquidity_shock_confidence =
    0.45 × depth
  + 0.35 × spread
  + 0.20 × imbalance
```

Evidence:

- percentage depth change;
- spread in basis points.

## Evidence Flattening

All four detectors run for every feature vector. Scores over the threshold become alerts.

Evidence from all scores is flattened by key using first-value-wins behavior:

```python
evidence.setdefault(item.key, item)
```

If multiple detectors expose the same evidence key, later values do not overwrite the first one.

---

# Step 4 — Detector Tournament

## Tournament Inputs

Default values:

```text
number_of_scenarios = 100

manipulation_types:
  spoofing
  layering
  quote_stuffing

difficulty_mix:
  easy        20%
  medium      50%
  hard        20%
  adversarial 10%

detectors:
  spoofing_like
  layering_like
  quote_stuffing

random_seed = 42
execution_mode = local_mock
```

## Execution Modes

### `local_mock`

No simulation batch is executed. A deterministic leaderboard is returned immediately.

This is the default Control Panel mode.

### `local`

The backend starts a background task and executes:

```text
serverless/jobs/detector_tournament.py
```

as a local subprocess.

### `nebius`

When `NEBIUS_JOB_SUBMIT_COMMAND_TEMPLATE` is configured:

- the batch is submitted to Nebius;
- a Nebius Job ID is recorded;
- the UI polls status;
- logs and S3 artifacts are collected;
- metrics are reconstructed from downloaded artifacts.

If the Job submission template is missing, LOB Arena returns deterministic mock tournament output and records a fallback reason.

## Local Tournament Workload

The requested total is converted to approximately equal runs per selected scenario:

```text
effective_scenarios =
    min(requested_scenarios, local_limit)

runs_per_scenario =
    ceil(effective_scenarios / number_of_scenario_types)
```

Example with 100 requested scenarios and three scenario families:

```text
runs_per_scenario = ceil(100 / 3) = 34
actual simulations = 34 × 3 = 102
```

The local implementation can therefore run slightly more simulations than requested.

## Single Simulation Run

For each run and scenario:

```python
engine = SimulationEngine(seed=run_index + 17)
```

If the scenario is not `normal-market`, the relevant attack is launched.

The simulation runs for exactly 14 ticks.

At every tick:

1. all detector scores are read;
2. maximum confidence per detector is retained;
3. the first tick crossing `0.75` is retained;
4. detector types appearing in incidents are retained.

## Ground-Truth Mapping

The expected detector is hard-coded:

```text
spoofing_like_wall    → spoofing_like
layering_like         → layering_like
quote_stuffing        → quote_stuffing
liquidity_evaporation → liquidity_shock
normal_market         → no expected detector
```

For each detector and simulation:

```text
truth =
    detector == expected_detector

predicted =
    detector appeared in an incident
    OR max_confidence >= 0.75
```

Then:

```text
TP = truth AND predicted
FP = NOT truth AND predicted
FN = truth AND NOT predicted
```

## Detection Latency

The first alert tick is converted to milliseconds:

```text
latency_ms =
    max(0, first_alert_tick - 1)
    × tick_interval_seconds
    × 1000
```

The default tick interval is `0.5 seconds`.

Examples:

```text
alert at tick 1 → 0 ms
alert at tick 2 → 500 ms
alert at tick 3 → 1,000 ms
```

This is simulated market time, not wall-clock model-inference latency.

## Tournament Metrics

For each `(scenario, detector)` pair:

```text
precision =
    TP / (TP + FP)

recall =
    TP / (TP + FN)

F1 =
    2 × precision × recall
    / (precision + recall)
```

If a denominator is zero, the value is set to zero.

Average latency includes only detections for which that detector is the expected truth detector.

## Generated Artifacts

The Job produces:

```text
metrics.csv
results.json
benchmark_report.md
charts/f1_by_scenario.png
charts/confidence_distribution.png
charts/detection_latency.png
```

`results.json` contains per-run:

- truth;
- prediction;
- true positive;
- false positive;
- false negative;
- latency;
- maximum confidence.

---

# Step 5 — Execution Trace

Execution Trace explains where a result came from.

It should distinguish among:

```text
real Nebius Endpoint call
real Nebius Serverless Job
local simulator execution
deterministic mock fallback
```

The trace and evidence layer can include:

- execution mode;
- model name;
- Endpoint URL;
- Job status;
- Job ID;
- fallback reason;
- artifact paths;
- cloud output URI;
- token counts;
- latency;
- estimated cost;
- S3 evidence records.

The polished E2E flow is:

```text
AI-generated spoofing scenario
→ LOB simulation
→ detector alert
→ LLM explanation
→ investigation report
→ detector tournament
→ artifacts
```

Smoke-demo artifacts are written under:

```text
outputs/serverless-smoke/
```

Typical files include:

```text
summary.json
scenario.json
simulation_events.json
detector_alerts.json
investigation_report.md
tournament_result.json
serverless_job.json
manifest.json
```

---

# Datasets Used

## Live Arena

The live Arena uses internally generated synthetic data:

- simulator-maintained order book;
- normal-agent actions;
- injected attack-agent actions;
- matching-engine events;
- snapshots;
- detector features;
- incidents.

No public exchange dataset is loaded by the detector during live Arena execution.

## Scenario Generator

The generator creates a synthetic labelled scenario.

- In mock mode it uses deterministic templates.
- In real Endpoint mode an LLM generates structured scenario content, which is normalized and bounded before it enters the simulator.

## Tournament

The basic tournament does not load NASDAQ, LOBSTER, FI-2010, ABIDES output, or another external benchmark dataset.

It creates new simulations for every run:

```python
SimulationEngine(seed=run_index + 17)
```

and applies hard-coded scenario-to-detector ground truth.

The current benchmark is best described as:

> A deterministic synthetic regression benchmark for LOB Arena’s own scenario and detector implementations.

It is not yet an independent external validation benchmark.

---

# Known Implementation Gaps

## 1. `difficulty_mix` is accepted but not applied by the basic batch runner

The UI sends easy, medium, hard, and adversarial proportions, but `serverless/jobs/detector_tournament.py` does not use difficulty.

A tournament configured as 90% adversarial therefore runs the same basic scenario mechanics as one configured as 90% easy, unless a separate cloud wrapper transforms the workload first.

## 2. `random_seed` is accepted but not used by the basic tournament runner

The request includes `random_seed`, but simulations use:

```python
seed = run_index + 17
```

Changing the Control Panel seed does not currently affect this script.

## 3. Number of scenarios is not exact

The value is converted to equal `runs_per_scenario`, which can overshoot the requested total.

## 4. One expected detector per attack family

For a spoofing scenario:

```text
spoofing_like = positive
every other detector = negative
```

A liquidity detector that correctly observes a liquidity effect during spoofing is counted as a false positive.

The benchmark therefore measures scenario-family classification more than general anomaly detection.

## 5. Normal-market metrics can be misleading

Normal market has no expected detector. If no alert occurs:

```text
TP = 0
FP = 0
FN = 0
precision = 0
recall = 0
F1 = 0
```

A perfectly quiet detector therefore receives F1 equal to zero.

Normal-market evaluation should also report:

```text
true negatives
false-positive rate
specificity
balanced accuracy
```

## 6. Ground truth is coarse

The canonical generated scenario contains manipulation windows and positive event IDs, but the basic tournament reduces truth to:

```text
scenario family → one expected detector
```

It does not yet score:

- temporal overlap with the labelled attack window;
- event-level precision and recall;
- early versus late detection;
- participant attribution;
- order-level attribution;
- manipulation phase detection.

## 7. Detector evidence uses simulator privilege

`wall_size_ratio` directly sums levels whose owner is `abuser`.

That is acceptable for synthetic debugging but unavailable in anonymous real market data.

A stronger observable-only implementation should use:

- size relative to nearby levels;
- distance from touch;
- cancellation probability;
- execution ratio;
- replenishment pattern;
- side switching;
- participant or order linkage when available.

## 8. Order lifetime is actually scenario elapsed time

The feature is calculated from attack start tick, not from individual order insertion and cancellation timestamps.

It should be renamed to `scenario_elapsed_ms` or replaced with real order-level lifetime statistics.

## 9. Scenario catalog is intentionally bounded

Scenario generation and tournament execution accept only the four native Arena scenarios. The liquidity-shock detector evaluates the `liquidity_evaporation` workload.

## 10. Layering is asymmetric

The layering detector checks excessive ask depth only:

```text
ask_depth > bid_depth × threshold
```

A symmetric implementation should support:

```text
ask_depth > bid_depth × threshold
OR
bid_depth > ask_depth × threshold
```

---

# Worked Evidence Example

Assume the spoofing detector receives:

```text
wall_size_ratio       = 7.2
order_lifetime_ms     = 1,500
cancel_to_trade_ratio = 1.5
imbalance             = -0.25
```

Components:

```text
wall      = min(7.2 / 8, 1)       = 0.90
lifetime  = 1.00
cancel    = min(1.5 / 3, 1)       = 0.50
imbalance = min(0.25 / 0.5, 1)    = 0.50
```

Confidence:

```text
0.60 × 0.90
+ 0.20 × 1.00
+ 0.10 × 0.50
+ 0.10 × 0.50

= 0.54 + 0.20 + 0.05 + 0.05
= 0.84
```

Result:

```text
confidence = 0.84
alert      = true
severity   = high
```

The evidence values do not form an additional score. They are the underlying feature values that support the calculated confidence of `0.84`.

---

# Accurate Technical Description

A technically accurate description of the current implementation is:

> LOB Arena generates bounded, explicitly labelled synthetic market-abuse scenarios using a Nebius AI Endpoint or deterministic fallback. Scenarios are projected into an authoritative limit-order-book simulator. On every simulation tick, deterministic feature extractors calculate depth, imbalance, spread, cancellation, message-rate, wall-size, and timing features. Four weighted rule-based detectors convert those features into confidence scores and incidents. The Nebius AI Investigation Team explains the resulting structured evidence. Detector tournaments replay synthetic scenario families locally or through Nebius Serverless Jobs and compare detector alerts with hard-coded scenario labels using precision, recall, F1, false positives, false negatives, and simulated detection latency.

This separation is useful because the core evidence remains reproducible and auditable. The UI should, however, clearly indicate that the main numerical detector scores come from deterministic formulas rather than from an AI model classifier.
