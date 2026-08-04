# ARD-0033: Deterministic Hybrid Injection Scheduling

Status: Phase 2 Accepted and Implemented

Date: 2026-08-04

## Context

Manual hybrid launch is useful for demonstrations, but batch evidence needs an
attack to begin at an exact reproducible point inside a normalized ITCH window.
A replay batch can span that point and can contain several rows with the same
exchange timestamp, so a tick-only trigger is insufficient.

## Decision

- A comparison accepts at most one positive `trigger_source_sequence` or valid
  nanoseconds-since-midnight `trigger_timestamp_ns`.
- Source-sequence triggers must identify a normalized visible-book row.
  Timestamp triggers resolve to the first row at or after the request.
- Control and hybrid runs use the same partition. Every historical row with the
  resolved trigger timestamp is applied before synthetic mutations; subsequent
  rows are deferred until the next replay tick. Prefetch state is never exposed
  to the scenario generator.
- If the source reaches EOF during the attack, both runs continue through the
  declared attack end and one post-attack observation. This preserves aligned
  traces and complete injected-order lifecycles.
- Existing scenario families expose bounded integer parameters only. Defaults
  preserve previous behavior. Dataset, family, master seed, requested trigger,
  and resolved parameters form a SHA-256 schedule identity that also enters the
  synthetic seed derivation.
- `scenario_ground_truth_v1` remains backward compatible and gains trigger
  source sequence/timestamp, exchange-time start/end, schedule hash, and
  parameters. Only `SYN:` simulation events may carry this truth.

## Evidence

Comparison summaries and signed bundles record identical control/hybrid source
integrity, ITCH source/parser/config/output hashes, source counts, requested and
actual trigger coordinates, schedule parameters/hash, deterministic repeats,
synthetic lifecycle, and before/during/after causal-locality results.

## Consequences

Historical participants remain immutable and non-interactive. The schedule is a
controlled counterfactual overlay, not a claim about how recorded participants
would have reacted. Fully interactive causal response remains the synthetic
mode addressed by calibrated market profiles.

## Related Records

- [ARD-0023: Hybrid Historical Replay](ARD-0023-hybrid-historical-replay.md)
- [ARD-0032: Nasdaq ITCH Ingestion](ARD-0032-nasdaq-itch-ingestion.md)
