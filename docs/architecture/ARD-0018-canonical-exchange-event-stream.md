# ARD-0018: Canonical Exchange Event Stream

Status: Accepted and Implemented

Date: 2026-07-18

Implementation Status: `[done]`

Completion: The original ten implementation steps completed in commit `32dc799`.

## Ownership update

[ARD-0020](ARD-0020-java-arena-websocket-agent-orchestration.md) made Java the sole
live exchange and REST/WebSocket owner. Retained Python schemas/readers consume
artifacts for offline simulation, causal features and ML; they do not establish
a second live exchange. The
[original Python implementation record](https://github.com/khab40/lob-arena/blob/d896efe8ca501c1ef8e6c63442f3433948a6405e/docs/architecture/ARD-0018-canonical-exchange-event-stream.md#step-1-implementation-record)
retains the ten-step migration history and former persistence paths.

## Context

Loose order-book dictionaries did not provide a stable source contract for
replay or historical adapters. Simulation and historical data need one ordered
vocabulary for adds, modifications, cancellations, executions and L2 snapshots.
Venue timestamps and upstream sequences must survive without forcing logical
simulator ticks to imitate exchange wall-clock time.

## Decision

Publish version 1 canonical events with `add | modify | cancel | execute | snapshot`
discriminators, identity, normalized source, venue, symbol, canonical/source
sequences, optional tick/timestamps and optional scenario lineage.

- Canonical sequence is contiguous within a stream and distinct from upstream `source_sequence`.
- Validate required identifiers, positive price/quantity state, non-negative remainders, snapshot depth and modification-priority claims.
- Same-price quantity changes retain FIFO position/timestamp; price changes cancel/reinsert at the new price. Side and agent ownership cannot change.
- A crossing order emits one execution per resting fill and then any resting limit remainder; non-mutating commands emit no canonical state event.
- One combined-book checkpoint follows all mutations in each completed simulation tick.
- Preserve the derived UI event projection while delivering typed canonical events to consumers.

The Java integer/Protobuf boundary and outward JSON records represent the same
canonical lifecycle. Raw JSON/Protobuf wire bytes are not the canonical hash
encoding; [hashing v1](../runtime/canonical-hashing-v1.md) owns that specification.

## Architecture

```mermaid
flowchart LR
    Simulation[Simulation source]
    Historical[Historical source]
    Canonical[Canonical event schema v1]
    Log[Sequenced event log]
    Book[Order book]
    Consumers[Detectors, API, persistence]

    Simulation --> Canonical
    Historical --> Canonical
    Canonical --> Log
    Log --> Book
    Log --> Consumers
```

This is the source/consumer relationship, not permission for a consumer to
mutate the authoritative Java exchange.

## Durable Replay Boundary

The current Java archive extends the original append-only design:

- A completed tick's canonical rows are flushed before completed state is published.
- `history/exchange-events/<stream_id>/segment-*.jsonl` and segment manifests retain sequence ranges and byte counts.
- The bounded JVM window is not the replay boundary: older cursor pages come from the archive.
- Reset starts a new stream at sequence 1 and preserves completed streams.
- `GET /api/arena/exchange-events` returns the exclusive next cursor, latest sequence, `has_more`, `stream_id`, `first_available_sequence` and `retained_from_sequence`; `streamId` selects a completed stream.
- Replay estimates above the configured archive quota are rejected before starting; a persistence failure must not be reported as a completed canonical tick.

This reconciles implemented behavior, not a new storage or deletion policy.
[Exchange Event Stream](../runtime/exchange-event-stream.md#delivery-contract)
owns the exact cursor/retention controls, and
[Java memory/archive limits](../runtime/java-kernel-performance.md#long-running-control-plane-memory-budget)
owns resource defaults and capacity responses. Implementation lives in
`CanonicalEventArchive` and `LiveArenaService`; archive and replay tests cover
rotation, stream reset and publication boundaries.

## Historical Replay Evolution

[ARD-0023](ARD-0023-hybrid-historical-replay.md) uses the same versioned vocabulary:

- strict canonical CSV maps actual source lifecycle events into kernel mutations;
- normalized LOBSTER reconstructs deterministic aggregate visible levels and retains the immutable source L2 snapshot;
- Nasdaq ITCH normalization is defined in [ARD-0032](ARD-0032-nasdaq-itch-ingestion.md);
- synthetic overlays share the kernel but retain separate IDs, source, seeds and ground truth.

Historical-only records do not establish benign labels. Combined-book prediction
checkpoints and historical-source validation snapshots remain distinct.

## Alternatives And Consequences

A loosely shaped UI event feed cannot reconstruct order-level lifecycle or
preserve source timing. L2 snapshots remain observational checkpoints and cannot
replace canonical mutations. The versioned contract makes validation and replay
portable, but adds identifiers/timing fields and requires explicit adapters or
migrations for incompatible schema changes.

## Related Documentation

- [Exchange Event Stream](../runtime/exchange-event-stream.md)
- [Determinism v1](../runtime/determinism-contract-v1.md)
- [WebSocket state](ARD-0002-websocket-state-schema.md)
- [Liquidity and quote ownership](ARD-0011-exchange-liquidity-invariant.md)
- [Java kernel migration](ARD-0019-python-reference-java-kernel-migration.md)
- [Historical ingestion](ARD-0022-historical-market-data-ingestion.md)
- [Hybrid replay](ARD-0023-hybrid-historical-replay.md)
