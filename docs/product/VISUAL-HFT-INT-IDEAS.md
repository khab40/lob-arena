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

