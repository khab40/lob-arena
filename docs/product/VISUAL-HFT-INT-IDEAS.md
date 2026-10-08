# VisualHFT Integration Ideas for LOB Arena

**Status:** integration and collaboration concept  
**Project:** LOB Arena  
**External project:** [VisualHFT](https://visualhft.com/)  
**Repository:** [visualHFT/VisualHFT](https://github.com/visualHFT/VisualHFT)  
**Reviewed:** 2026-10-04

This is a historical concept snapshot. Proposed capabilities and illustrative examples
are unimplemented; this document does not authorize implementation, model workloads
or outreach.

## 1. Strategic Fit

VisualHFT and LOB Arena are complementary rather than directly competitive.

VisualHFT is strong in:

- live multi-venue market-data ingestion;
- order-book normalization;
- microstructure studies;
- replay and event capture;
- feed/infrastructure monitoring;
- visualization and analyst workflows;
- plugin/study extensibility.

LOB Arena’s existing strengths and proposed directions include:

- governed historical + synthetic order-book validation;
- controlled attack injection;
- reproducible detector benchmarking;
- LightGBM and Transformer comparison;
- proposed detector ensembles;
- surveillance-oriented evidence and evaluation.

The preferred product boundary is:

> **VisualHFT = observe and investigate the market.**  
> **LOB Arena = challenge, detect, evaluate, and explain surveillance behavior.**

Do **not** turn LOB Arena into another VisualHFT-style desktop UI. Use VisualHFT ideas and, where appropriate, compatible/open-source components as an observation/data layer while keeping LOB Arena as the surveillance intelligence and validation layer.

---

## 2. Add the Seven Public Crypto Feeds

VisualHFT currently uses public L2 feeds from:

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

Example:

```text
BTCUSDT
tBTCUSD
BTC-USD
   ↓
BTC/USD
```

Target ingestion shape:

```text
Binance ─┐
Kraken ──┤
Coinbase ┤
Bitfinex ┤
Gemini ──┼──> normalized event schema ──> LOB Arena
KuCoin ──┤
Bitstamp ┘
```

### Implementation constraints

Do **not** make LOB Arena dependent on the VisualHFT Windows/WPF application.

LOB Arena should remain:

- Linux-friendly;
- cloud-friendly;
- Python-friendly;
- usable from Nebius jobs and batch replay;
- independent from a desktop GUI runtime.

Preferred approaches:

1. study/port connector logic where license-compatible;
2. implement equivalent native adapters;
3. introduce a small Linux-friendly market-data gateway;
4. use a normalized event API/bus between feeds and LOB Arena.

---

## 3. Cross-Venue Surveillance: Highest-Value Extension

The strongest idea is not “seven feeds.” It is **cross-venue context**.

A single-venue detector cannot easily distinguish:

- genuine market-wide movement;
- venue-local abnormal quoting;
- venue-local liquidity stress;
- stale or corrupt market data;
- manipulation-like order-book behavior.

A multi-venue layer provides a market consensus.

```text
                Binance ─┐
                Kraken  ─┤
                Coinbase ─┤
                Bitfinex ─┼──> normalized multi-venue LOB
                Gemini   ─┤
                KuCoin   ─┤
                Bitstamp ─┘
                          │
                          ▼
                 market consensus
                          │
                          ▼
             LOB Arena detector stack
                          │
                          ▼
              venue-specific anomaly
```

Example:

```text
Binance      +0.91 imbalance
Coinbase     +0.08
Kraken       +0.04
Bitstamp     +0.06
Bitfinex     +0.07
```

This is much more suspicious than:

```text
Binance      +0.75
Coinbase     +0.71
Kraken       +0.68
Bitstamp     +0.73
Bitfinex     +0.69
```

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

This can become a named LOB Arena capability:

> **Cross-Venue Market Abuse Surveillance**

---

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

Bad:

```text
VPIN > threshold => manipulation
```

Better:

```text
raw LOB sequence
      │
      ├── LOB imbalance
      ├── OTR
      ├── TTO
      ├── VPIN
      ├── resilience
      ├── spread
      ├── depth slope
      ├── cancellations
      ├── replenishment
      └── cross-venue divergence
             │
             ▼
     LightGBM + Transformer
             │
             ▼
        ensemble score
```

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

```text
                        live feeds
                            │
                    rolling 60s buffer
                            │
                            ▼
                     LOB Arena model
                            │
                   P(spoofing)=0.94
                            │
                            ▼
                         TRIGGER
                            │
              ┌─────────────┴─────────────┐
              │                           │
           -30 sec                     +30 sec
              │                           │
              └─────────────┬─────────────┘
                            ▼
                    SURVEILLANCE CASE
```

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

This should be a major LOB Arena direction.

Synthetic simulation provides controlled labels.  
Real feeds provide realistic noise.

Combine them:

```text
REAL RECORDED MARKET
BTC/USD, Binance
09:30:00 → 09:45:00

        +

SYNTHETIC ATTACK INJECTION
spoofing / layering / etc.

        ↓

HYBRID REPLAY

        ↓

LightGBM
Transformer
Ensemble
baseline detectors

        ↓

Precision / Recall
Detection delay
False positives
Robustness
```

Possible names:

- Real-Market Adversarial Replay
- Surveillance Red-Team Replay
- Hybrid Historical + Synthetic Replay
- Counterfactual Market Abuse Replay

This directly strengthens the LOB Arena thesis:

- pure synthetic data can be unrealistic;
- pure historical data lacks reliable labels;
- hybrid replay gives realistic background conditions plus known attack ground truth.

---

## 7. Feed Quality Must Be First-Class

Real-time surveillance can confuse data failures with market anomalies.

Example:

```text
missing feed messages
      ↓
apparent liquidity disappearance
      ↓
detector fires
      ↓
false manipulation alert
```

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

A collaboration artifact could be a VisualHFT study/plugin showing LOB Arena results.

Example:

```text
┌──────────────────────────────┐
│ LOB Arena Surveillance       │
│                              │
│        0.87 HIGH             │
│                              │
│ Suspected: Layering          │
│ Ensemble: 3/3                │
│                              │
│ LightGBM      0.91           │
│ Transformer   0.84           │
│ Rule engine   0.77           │
│                              │
│ Cross venue   ANOMALOUS      │
│ Data quality  GOOD           │
└──────────────────────────────┘
```

Click-through could show:

- event timeline;
- order-book visualization;
- venue comparison;
- detector feature values;
- model probabilities;
- evidence window;
- replay button;
- explanation / analyst notes.

### Product division

**VisualHFT**

- trader/analyst workstation;
- visualization;
- market-data connectors;
- microstructure studies;
- replay;
- operational feed monitoring.

**LOB Arena**

- surveillance intelligence;
- detector stack;
- attack injection;
- adversarial replay;
- benchmark/evaluation harness;
- model comparison;
- evidence generation.

This is better than rebuilding an entire trading-style GUI inside LOB Arena.

---

## 12. Trigger / Webhook Integration

A simple first integration could be:

