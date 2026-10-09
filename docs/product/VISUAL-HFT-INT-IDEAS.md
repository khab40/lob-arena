# VisualHFT Integration Ideas for LOB Arena

**Status:** integration and collaboration concept  
**Project:** LOB Arena  
**External project:** [VisualHFT](https://visualhft.com/)  
**Repository:** [visualHFT/VisualHFT](https://github.com/visualHFT/VisualHFT)  
**Historical research snapshot:** 2026-10-04
**Compacted:** 2026-10-08

This is a historical concept snapshot. Proposed capabilities and illustrative examples
are unimplemented; this document does not authorize implementation, model workloads
or outreach. External connector/depth observations below belong to that snapshot
and need live verification before implementation. The [full concept record](https://github.com/khab40/lob-arena/blob/1417a4e4bfb6803bc967b4469b85e4f379759e8e/docs/product/VISUAL-HFT-INT-IDEAS.md)
retains the original examples, benefit pitches and unsent outreach draft.

## 1. Strategic Fit

The proposed boundary is VisualHFT for market observation/analyst visualization,
and LOB Arena for governed replay, controlled attack injection, detector comparison
and surveillance evidence. LOB Arena should remain Linux/cloud-friendly and
independent of the Windows/WPF desktop runtime. Reuse or port connector logic only
after license review; a native normalized-event gateway is an alternative.

## 2. Add the Seven Public Crypto Feeds

The historical concept listed public L2 feeds from:

| Venue | Typical/default depth |
|---|---:|
| Binance | 10 |
| Bitfinex | 25 |
| Kraken | 25 |
| KuCoin | 25 |
| Gemini | 20 |
| Bitstamp | 10 |
| Coinbase | 25 |

The useful idea is not only the connectors themselves, but the normalization layer that maps venue-specific symbols and event shapes into a common schema.

Normalize venue-specific symbols and event shapes into a common schema, for
example `BTCUSDT`, `tBTCUSD` and `BTC-USD` into `BTC/USD`. Use native adapters,
a Linux-friendly gateway or a normalized event API/bus usable from Nebius Jobs
and batch replay; the desktop application must not become a runtime dependency.

## 3. Cross-Venue Surveillance: Highest-Value Extension

Use peer consensus to distinguish market-wide moves, venue-local quoting or
liquidity stress and corrupt/stale data. An isolated +0.91 imbalance against
peers near +0.04–0.08 has a different interpretation from all venues moving
together near +0.68–0.75; neither pattern alone proves abuse.

### Candidate cross-venue features

| Feature | Surveillance interpretation |
|---|---|
| Venue imbalance vs peer consensus | unusual local pressure |
| Cancellation rate vs peers | abnormal quote churn |
| Spread deviation | venue-local liquidity stress |
| Depth deviation | abnormal liquidity addition/removal |
| Mid-price residual | venue-specific dislocation |
| Return residual vs composite | local move not confirmed elsewhere |
| Resilience vs peers | unusual refill/recovery |
| OTR/TTO divergence | abnormal order/trade mix |
| Liquidity-gap divergence | local liquidity vacuum |
| Lead/lag residual | abnormal propagation / price discovery |
| Correlation break | venue behavior decoupled from peers |

## 4. Reuse Microstructure Studies as Model Features

Useful VisualHFT-style studies include:

- LOB imbalance;
- VPIN;
- order-to-trade ratio;
- trade-to-order ratio;
- market resilience;
- resilience bias;
- liquidity gaps;
- spread and depth;
- cancellation/update statistics;
- multi-venue price and liquidity comparisons.

These should be treated as **features**, not standalone proof of manipulation.

A proposed feature engine combines these indicators with causal LOB sequences
and cross-venue divergence for separately evaluated LightGBM/Transformer
candidates. A threshold such as VPIN alone must not establish manipulation.

### Research questions

LOB Arena can test:

- whether VPIN improves spoofing/layering detection;
- whether OTR reduces or increases false positives;
- whether resilience adds useful post-event context;
- whether cross-venue residuals improve precision;
- which engineered features improve a separately trained development candidate
  compared against the unchanged frozen LightGBM baseline;
- which features become redundant when the Transformer sees raw sequence data;
- whether cross-venue context reduces false alerts during market-wide volatility.

This turns common microstructure indicators into measurable surveillance research.

---

## 5. Event Capture: Convert Alerts into Cases

LOB Arena should maintain a rolling market-data buffer and persist a bounded before/after window whenever a detector fires.

A bounded capture example is 30 seconds before and after a trigger. The
before/after window supports investigation and replay; future/post-trigger context
must not leak into causal detector inputs.

A case could contain:

```yaml
case_id:
venue:
symbol:
event_timestamp:

suspected_pattern:
lightgbm_score:
transformer_score:
ensemble_score:
detector_votes:

pre_event_window:
post_event_window:

lob_sequence:
trades:
cancellation_metrics:
lob_imbalance:
otr:
tto:
vpin:
resilience:

cross_venue_context:
data_quality:

model_explanation:
evidence_artifacts:
replay_id:
```

This moves LOB Arena from only a detector benchmark toward a **surveillance evaluation + investigation evidence platform**.

---

## 6. Real-Market Replay + Synthetic Manipulation Injection

Combine recorded market background with controlled synthetic attack injection
and deterministic replay. Compare rules, frozen LightGBM and a separately
verified Transformer using precision, recall, detection delay, false positives
and robustness. Keep synthetic attack labels distinct from assumed historical
control labels; realistic background alone does not validate ground truth.

## 7. Feed Quality Must Be First-Class

Real-time surveillance can confuse data failures with market anomalies.

Missing messages can resemble liquidity disappearance. Preserve health metadata
so detector reports can distinguish market anomalies, data anomalies and uncertainty.

Every event/session should preserve feed-health metadata such as:

```yaml
data_quality_score:
feed_gap:
sequence_valid:
snapshot_resync:
reconnect_recently:
book_crossed:
stale_feed:
clock_quality:
receive_latency_ms:
exchange_latency_ms:
malformed_event_count:
dropped_event_count:
```

Alerting should distinguish:

- market anomaly;
- data anomaly;
- uncertain because of feed quality.

This is likely to improve production false-positive behavior materially.

---

## 8. Timestamp Integrity

Do not collapse all timing into one generic `timestamp`.

Preserve at least:

```yaml
exchange_timestamp:
receive_timestamp:
normalized_timestamp:
sequence_number:
venue:
symbol:
source:
```

Optional:

```yaml
source_timestamp_quality:
clock_offset_estimate:
ingest_latency_us:
processing_latency_us:
```

Why this matters:

A claim such as:

> “Binance led Gemini by 14 ms”

may reflect network/clock differences rather than market causality.

Lead/lag and propagation features are only trustworthy when timestamp semantics and timestamp quality are explicit.

---

## 9. L2 Now, L3 Later

Public multi-venue feeds are mainly L2 price-level depth.

L2 already supports:

- imbalance;
- spread;
- depth changes;
- replenishment;
- cancellation approximations;
- liquidity gaps;
- resilience;
- cross-venue divergence;
- sequence-model experiments.

L3/order-level data later enables:

- individual order lifetime;
- cancel/re-add sequences;
- order replacement;
- queue behavior;
- persistent layering signatures;
- richer order-level temporal patterns.

Design the normalized event model so future L3 support does not require a full pipeline rewrite.

---

## 10. Surveillance Wording / Attribution Caution

Public crypto order-book data usually supports behavioral inference, not participant attribution.

Use wording such as:

- suspected spoofing pattern;
- manipulation-like behavior;
- anomalous order-book activity;
- suspicious layering signature;
- surveillance alert;
- detector score.

Avoid claiming:

- confirmed manipulation;
- identified manipulator;
- proven market abuse;

unless participant/account evidence and an appropriate investigative process exist.

---

## 11. Build a LOB Arena Surveillance Plugin for VisualHFT

A future study/plugin could display score, suspected pattern, detector votes,
cross-venue context and data quality, with click-through to supporting evidence.
It must not imply that an ensemble or live learned-detector adapter exists today.

Click-through could show:

- event timeline;
- order-book visualization;
- venue comparison;
- detector feature values;
- model probabilities;
- evidence window;
- replay button;
- explanation / analyst notes.

## 12. Trigger / Webhook Integration And Collaboration

A metric/event webhook from VisualHFT to LOB Arena is a possible first bridge.
Longer term, LOB Arena would own normalization and surveillance scoring and publish
alerts/scores/evidence to a VisualHFT plugin. Either direction needs an approved
adapter contract, timestamp/feed-quality handling and verified license boundaries.

Possible collaboration scopes are a small multi-venue surveillance experiment,
a score/evidence plugin, or adversarial replay. Benefit pitches and the unsent
outreach draft remain in the historical concept record linked above. This
concept grants no outreach, implementation or workload approval.

## 17. Target Architecture

```text
                 7 LIVE CRYPTO VENUES
                          │
                          ▼
                NORMALIZED EVENT BUS
                          │
       ┌──────────────────┼──────────────────┐
       ▼                  ▼                  ▼
   LOB state       microstructure       feed quality
                  feature engine         monitoring
       │                  │                  │
       └──────────────────┼──────────────────┘
                          ▼
                CROSS-VENUE CONTEXT
                          │
                          ▼
              LOB ARENA DETECTOR STACK
                          │
               ┌──────────┴──────────┐
               ▼                     ▼
            LightGBM             Transformer
               └──────────┬──────────┘
                          ▼
                       ENSEMBLE
                          │
                    anomaly score
                          │
              ┌───────────┴────────────┐
              ▼                        ▼
        event capture             live alert
       pre/post window                 │
              │                        │
              └───────────┬────────────┘
                          ▼
                   FORENSIC CASE
                          │
            ┌─────────────┴─────────────┐
            ▼                           ▼
     VisualHFT plugin             LOB Arena UI
```

Replay path:

```text
Real recorded market
        +
Synthetic attack injection
        ↓
deterministic replay
        ↓
detector benchmark
```

---

## 18. Recommended Priority

### P0 — architecture / validation

1. Define the canonical normalized event schema.
2. Preserve:
   - `exchange_timestamp`
   - `receive_timestamp`
   - `normalized_timestamp`
   - `sequence_number`
   - venue
   - symbol
   - data-quality metadata.
3. Review VisualHFT connector implementations and license boundaries.
4. Decide whether to port logic or build independent adapters.

### P1 — live feeds

5. Implement 2 venues first, preferably Binance + Coinbase/Kraken.
6. Validate:
   - snapshots;
   - deltas;
   - reconnects;
   - gap handling;
   - book reconstruction;
   - timestamp semantics.
7. Add the remaining venues only after the normalized contract is stable.

### P2 — cross-venue features

8. Build venue-consensus metrics.
9. Add divergence features.
10. Train a separate development candidate with cross-venue context and compare it
    against the unchanged frozen LightGBM baseline.
11. Repeat for Transformer.
12. Measure false-positive changes, not just overall accuracy.

### P3 — capture and replay

13. Add rolling event capture.
14. Persist detector-triggered before/after windows.
15. Add deterministic replay.
16. Introduce real-market + synthetic-attack replay.

### P4 — collaboration

17. Contact VisualHFT with a concrete experiment rather than a generic partnership request.
18. Offer one small proof of concept:
    - Binance + Coinbase;
    - one symbol;
    - one detector;
    - one VisualHFT-facing score tile or report.
19. If useful, evolve into a plugin/study.

---

## 19. Recommended First Proof of Concept

Keep the first integration intentionally small.

### Scope

- instrument: `BTC/USD`;
- venues: Binance + Coinbase;
- data: L2;
- window: live capture + deterministic replay;
- detectors:
  - frozen LightGBM baseline;
  - current Transformer;
- features:
  - local LOB imbalance;
  - cancellation/update rates;
  - spread/depth;
  - cross-venue imbalance residual;
  - price residual;
  - feed-quality state.

### Output

For every alert:

```yaml
alert_id:
venue:
symbol:
timestamp:

suspected_pattern:
lightgbm_score:
transformer_score:
ensemble_score:

cross_venue_anomaly_score:
data_quality_score:

evidence_window:
replay_id:
```

### Success criteria

The PoC is valuable if it demonstrates at least one of:

- cross-venue context reduces false positives;
- real-market replay exposes detector weaknesses not visible in synthetic data;
- feed-quality state prevents spurious alerts;
- Transformer and LightGBM respond differently to venue-local vs market-wide events;
- the resulting evidence is useful enough to display in VisualHFT.

---

## 20. Core Strategic Principle

The desirable product boundary is:

> **VisualHFT = observe and investigate the market.**  
> **LOB Arena = challenge, detect, evaluate, and explain surveillance behavior.**

The three highest-priority ideas are therefore:

1. **live normalized multi-venue feeds;**
2. **cross-venue surveillance features;**
3. **event capture + real-market adversarial replay.**

Build those before investing heavily in additional UI or LLM-agent layers.

LLMs are likely more valuable later for:

- alert summarization;
- investigation narratives;
- evidence assembly;
- case triage;
- analyst assistance;

than for deciding directly from raw high-frequency LOB events whether market manipulation occurred.
