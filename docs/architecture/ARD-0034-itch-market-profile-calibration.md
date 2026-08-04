# ARD-0034: ITCH Market-Profile Calibration

Status: Phase 3 Accepted and Implemented

Date: 2026-08-04

## Context

The synthetic arena is interactive and deterministic, but its default ladder
uses fixed BTCUSDT spacing, quantity, and reference price. Historical ITCH
replay cannot model counterfactual participant reactions, so calibrated causal
experiments must remain a separate all-synthetic mode.

## Decision

- `market_profile_v1` is extracted only from normalized `itch_parquet_v1`
  events and aligned snapshots whose manifest and output hashes verify.
- The profile records distributions for intraday arrival intensity,
  inter-event time, add size, distance from touch, order lifetime,
  cancellation/execution ratios, spread, depth, imbalance, mid volatility,
  refill, and resilience.
- Compilation produces bounded integer parameters for the existing Java
  synthetic runtime: reference price, baseline levels, ladder spacing, base
  quantity, depth slope, normal-agent target, order-size target, refill time,
  and reference-update interval/step.
- The profile is canonical JSON with a content SHA-256. Java recomputes the
  checksum before loading it. Every selected run exposes both the profile SHA
  and a SHA binding that profile to the master seed.
- Only calibrated synthetic mode replaces the baseline ladder. Stable baseline
  order IDs move with a deterministic seeded reference path, avoiding stale
  liquidity at prior references. Java remains the single writer and agents
  still receive only the current read-only snapshot.
- The fixed legacy configuration remains selectable as `synthetic` and keeps
  its existing regression behavior.

## Evaluation Contract

Calibration and evaluation dataset IDs must differ. The checksummed
`market_profile_realism_report_v1` pre-registers arrival intensity, order size,
spread, top depth, absolute imbalance, and mid-volatility distances. It compares
the profile-driven simulation with the hardcoded regression control and passes
only when the calibrated median distance is lower. The report also freezes
before/during/after liquidity-evaporation response windows and the deterministic
seed/profile binding.

The tiny committed profile proves the contract only. A real completion report
must be generated locally from licensed, bounded training and held-out ITCH
windows; neither raw sessions nor derived real-market artifacts are committed.

## Consequences

The simulation becomes instrument-conditioned without conflating recorded
history with an interactive counterfactual. A single window can overfit one
regime, so production claims require multiple disjoint dates/regimes and the
same report schema. Zero-sample refill or resilience distributions are retained
explicitly rather than imputed as observations.

## Related Records

- [ARD-0020: Java Arena and Agent Orchestration](ARD-0020-java-arena-websocket-agent-orchestration.md)
- [ARD-0023: Hybrid Historical Replay](ARD-0023-hybrid-historical-replay.md)
- [ARD-0032: Nasdaq ITCH Ingestion](ARD-0032-nasdaq-itch-ingestion.md)
- [ARD-0033: Deterministic Hybrid Injection Scheduling](ARD-0033-deterministic-hybrid-scheduling.md)
