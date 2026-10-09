# LOB Arena Calculations and Workflow Explanations

This reference owns the retained Python synthetic rule-detector and tournament
formulas. Java owns the live arena under [ARD-0020](../architecture/ARD-0020-java-arena-websocket-agent-orchestration.md).
Simulator-privileged rule features are not the causal `lob_features_v2` ML
contract. Governed training/calibration/evaluation uses the
[ML lifecycle](../use-cases/ml-lifecycle.md) and
[Nebius execution policy](../ml/model-validation-execution-policy.md).

The [pre-reconciliation narrative](https://github.com/khab40/lob-arena/blob/d896efe8ca501c1ef8e6c63442f3433948a6405e/docs/runtime/calculations-explanations.md)
preserves the earlier workflow description and former gaps. It is historical:
the maintained runner now applies exact counts, seed and difficulty and computes
temporal/attribution metrics.

## Table of Contents

- [Overview](#overview)
- [End-to-End Flow](#end-to-end-flow)
- [Step 1 — Runtime](#step-1--runtime)
- [Step 2 — Scenario Generator](#step-2--scenario-generator)
- [Step 3 — Investigation Team](#step-3--investigation-team)
- [Detector Evidence Calculations](#detector-evidence-calculations)
- [Detector Formulas](#detector-formulas)
- [Step 4 — Detector Tournament](#step-4--detector-tournament)
- [Step 5 — Execution Trace](#step-5--execution-trace)
- [Datasets Used](#datasets-used)
- [Known Implementation Gaps](#known-implementation-gaps)
- [Worked Evidence Example](#worked-evidence-example)
- [Accurate Technical Description](#accurate-technical-description)

## Overview

The demo combines deterministic simulation, rule detectors and optional Nebius
generation/investigation services. Rules calculate their scores and alert
thresholds; the AI Investigator explains structured evidence. Its risk/confidence
is explanatory output, not a calibrated probability of real market abuse.

Mock outputs establish response compatibility, not measured detector quality or
proof that an Endpoint/Job executed. Learned-model implementation, qualification
and live integration remain separate from this synthetic rules path.

## End-to-End Flow

```text
Bounded scenario specification + separate ground truth
  -> named Arena scenario projection
  -> authoritative Java live exchange (or retained offline batch simulation)
  -> numeric rule features -> detector scores -> incidents/evidence
  -> optional AI investigation
  -> synthetic tournament metrics and retained artifacts
```

## Step 1 — Runtime

The [runtime model](runtime-model.md) owns current Java/Python boundaries and
worker caps. The [Serverless entry point](../../serverless/README.md) owns wiring
and distinguishes build/import checks from runtime smoke tests. Local mock
responses require no cloud execution; a configured cloud route still records
fallback if the Endpoint or Job path fails.

## Step 2 — Scenario Generator

[ARD-0016](../architecture/ARD-0016-ai-scenario-generator.md#canonical-schema)
owns accepted enums, complete request/response examples, fallback and persistence.
The Replay action projects a canonical specification onto one of four supported
named scenarios; it does not replay arbitrary LLM events event for event.
Specification ground truth must not be substituted for executed scenario labels.

## Step 3 — Investigation Team

[ARD-0015](../architecture/ARD-0015-nebius-ai-investigation-team.md) owns evidence
shaping, fallback metadata and structured assessment. The request is a bounded
summary, not an unbounded raw exchange stream. Detector scores are mechanical
rule outputs; investigator risk/confidence is model-generated in Endpoint mode
and deterministic mock output in fallback mode.

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

The four retained Python rule detectors raise an alert at:

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


# Step 4 — Detector Tournament

The maintained runner is
[`serverless/jobs/detector_tournament.py`](../../serverless/jobs/detector_tournament.py).
[ARD-0017](../architecture/ARD-0017-ai-detector-tournament.md) owns API modes and
orchestration; the [Jobs reference](../../serverless/jobs/README.md#detector-tournament)
owns runner arguments and filenames.

## Tournament Inputs

The API accepts `number_of_scenarios` from 1 to 1000; scenario names are
`spoofing_like_wall | layering_like | quote_stuffing | liquidity_evaporation`.
Direct runner plans can also include the `normal_market` negative control.
Difficulty is `easy | medium | hard | adversarial`, with default weights
20% / 50% / 20% / 10%. `random_seed` defaults to 42.
Requested API mode is `local_mock | local | nebius`.

## Execution Modes

- `local_mock`: return deterministic rows without simulation execution or runner artifacts.
- `local`: run the retained, capped rule tournament through the existing background task; only one local tournament executes at a time.
- `nebius`: use the configured Job path; missing configuration returns mock rows with a fallback reason.

These are application capabilities. Agent-initiated model workloads, including
synthetic training/scoring/evaluation rehearsals, run on Nebius under their own
authorization. Local rule simulation does not waive that policy.

## Local Tournament Workload

The facade passes exactly
`effective_scenarios = min(requested_scenarios, local_limit)` to `--runs`.
There is no ceil-per-family overshoot.

`exact_balanced_plan(N, families, seed)` creates exactly N entries by cycling
families, then shuffles them with the supplied seed. For N=100 and three
families, the counts are 34 / 33 / 33. The weighted difficulty plan normalizes
weights, floors N × weight, allocates the remaining entries by fractional
remainder, then shuffles with `random_seed + 1`.

Each run's seed is independently derived as:

```text
digest = SHA-256("lob-arena:<random_seed>:<run_index>")
run_seed = first_8_digest_bytes_as_big_endian_integer mod 2,147,483,647
```

[`run_planning.py`](../../backend/app/evaluation/run_planning.py) owns this
algorithm. Difficulty selects baseline depth/normal-agent profiles; seeded
variation changes reference price, tick spacing, depth and agent count.

## Single Simulation Run

Each planned scenario/difficulty pair creates
`SimulationEngine(seed=run_seed, **engine_profile(difficulty, seed=run_seed))`,
launches the selected attack unless it is `normal_market`, and executes
14 ticks. The runner retains each detector's maximum confidence, alert ticks,
incident presence and linked event/participant/order evidence.

## Ground-Truth Mapping

Every selected detector is evaluated against binary attack-active truth:

```text
truth = scenario != "normal_market"
predicted = detector appeared in an incident OR max_confidence >= 0.75

TP = truth AND predicted
FP = NOT truth AND predicted
FN = truth AND NOT predicted
TN = NOT truth AND NOT predicted
```

Scenario family groups reports; it does not declare other detectors negative
during an injected attack. Temporal/attribution evaluation uses the executed
scenario label when available, not the generated specification's expected score.

## Detection Latency

```text
latency_ms = max(0, first_alert_tick - 1) × tick_interval_seconds × 1000
```

The default interval is 0.5 seconds: ticks 1 / 2 / 3 correspond to
0 / 500 / 1000 ms. This is simulated market time, not wall-clock inference
latency. Average latency includes detections in positive runs.

## Tournament Metrics

[`ground_truth.py`](../../backend/app/evaluation/ground_truth.py) owns exact
null/rounding and attribution behavior:

```text
precision = TP / (TP + FP)
recall = TP / (TP + FN)
F1 = 2 × precision × recall / (precision + recall)
specificity = TN / (TN + FP)
false_positive_rate = FP / (FP + TN)
```

Undefined denominators produce null. F1 is zero when recall is zero; otherwise
it is null when its inputs/denominator are undefined. A quiet normal-market run
therefore has null precision/recall/F1, specificity 1 and false-positive rate 0.

For a labelled run, temporal overlap is the intersection-over-union of alert
ticks and the inclusive primary manipulation window. First alert is classified
as early, on time, late or missed. Event, participant and order precision/recall
compare linked evidence IDs with label IDs; absent truth linkage yields null,
not fabricated attribution. A phase is detected when any alert intersects its
inclusive phase window. An unlabeled negative control has no phase/attribution
truth; its alert timing is false positive or not applicable.

## Generated Artifacts

The runner writes `metrics.csv`, `results.json`, `benchmark_report.md`,
`charts/f1_by_scenario.png`, `charts/confidence_distribution.png` and
`charts/detection_latency.png`. Per-run rows retain scenario, difficulty,
derived seed, truth, predictions/confusion counts, maximum confidence, latency,
temporal overlap, attribution and phase findings.

# Step 5 — Execution Trace

Record whether output came from an Endpoint, a Serverless Job, a local rule
simulation or a deterministic mock. Preserve IDs, mode/model, fallback reason,
artifact/manifest/checksum references and measured latency where available.
The API smoke workflow writes `outputs/serverless-smoke/<experiment_id>/`;
the shell smoke workflow has its separately selected output directory.
Neither mock rows nor pending-cloud metadata prove a Job executed.

# Datasets Used

This basic tournament generates its own synthetic simulation runs; it does not
load Nasdaq, LOBSTER, FI-2010 or ABIDES as an external validation benchmark.
The live Java Arena separately supports historical/hybrid replay under
[ARD-0023](../architecture/ARD-0023-hybrid-historical-replay.md). That capability
does not make the basic synthetic tournament an independent market benchmark.

# Known Implementation Gaps

The retained Python rules have explicit limitations:

- `wall_size_ratio` uses synthetic `owner == "abuser"` information unavailable in anonymous real data.
- `order_lifetime_ms` is elapsed time since scenario start, not measured order lifecycle.
- Cancellation/trade proxies use simulator event messages and `TAKER_01`, rather than a venue-neutral order-flow contract.
- The layering depth condition is ask-side-oriented.
- The fixed 14-tick synthetic benchmark is a regression comparison, not evidence of production surveillance quality.
- Temporal/attribution metrics exist, but their validity depends on actual label and detector-evidence linkage; null is not an observed score.

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
