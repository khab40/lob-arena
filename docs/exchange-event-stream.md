# Exchange Event Stream

LOB Arena is migrating from direct synthetic order-book mutation to a canonical exchange event stream that can carry simulation events now and historical market data later.

## Canonical Event Contract

Schema version 1 supports five event types:

| Type | Meaning | Required event payload |
|------|---------|------------------------|
| `add` | A new resting order entered the book | order, agent, side, price, quantity, owner |
| `modify` | A resting order changed | previous/new price and quantity, priority result |
| `cancel` | Remaining resting quantity was removed | order, agent, side, price, canceled quantity |
| `execute` | Aggressor and resting orders traded | execution/order/agent IDs, aggressor side, price, quantity, remainders |
| `snapshot` | An L2 view of the book at a stream position | requested depth and book levels/derived prices |

Every event has an event ID, schema version, source (`simulation` or `historical`), symbol, venue, optional canonical and source sequences, optional simulation tick, nanosecond exchange/receive timestamps, and optional scenario lineage.

Canonical `sequence` belongs to the normalized LOB Arena stream. `source_sequence` preserves an upstream historical feed sequence without assuming different feeds use compatible numbering. Events may be created without a canonical sequence; the event log assigns one before publication or persistence.

## Implementation Progress

| Step | Status | Scope |
|------|--------|-------|
| 1 | Done | Typed and validated canonical event schemas plus stable dictionary serialization |
| 2 | Done | Sequenced event log, bounded tail/cursor replay, duplicate protection, and JSONL round trips |
| 3 | Done | Explicit modify requests with ownership checks and deterministic price-time priority rules |
| 4 | Done | Matching engine emits and logs canonical add, modify, cancel, and execute events |
| 5 | Done | Configurable-depth typed book snapshots and sequenced snapshot checkpoints |
| 6 | Done | Agent, scenario, and baseline book mutations feed one canonical simulation stream with one snapshot per tick |
| 7 | Done | Bounded canonical events in arena/WebSocket state plus cursor-based HTTP replay |
| 8 | Done | Discriminated TypeScript event union, mock stream, and compact exchange tape |
| 9 | Done | Common source reader, live simulation adapter, canonical JSONL replay, and historical record-normalizer boundary |
| 10 | Done | Append-only canonical and snapshot history streams with stream-scoped replay and end-to-end coverage |

See [ARD-0018](architecture/ARD-0018-canonical-exchange-event-stream.md) for the architecture decision and compatibility rules.

## Event Log And Replay

`EventLog` owns the canonical sequence. It assigns contiguous sequences beginning at 1, preserves correctly pre-sequenced imports, and rejects gaps, out-of-order events, and duplicate event IDs. Consumers can request a bounded tail or replay strictly after a sequence cursor.

JSONL contains one complete canonical event per line. Loading JSONL reconstructs the typed event and revalidates both its payload and the stream's ordering; errors identify the failing line.

## Modify Semantics

- A same-price quantity modification retains the order's queue position and original priority timestamp.
- A price change removes the order from its old level and appends it behind existing orders at the new price, using the modification timestamp.
- Side and agent ownership cannot change through modify.
- Quantity must remain positive. Removing all remaining quantity uses an explicit cancel event.
- Modifying an unknown order is a no-op result so a historical adapter can apply venue-specific missing-order policy outside the book.

## Matching Output

`MatchingEngine.submit()` returns typed, already-sequenced canonical events and appends the same objects to its event log. A crossing limit order can produce multiple `execute` events in price-time order and then one `add` event if quantity remains. Execute payloads include both order and agent IDs plus post-trade remaining quantities.

Unfilled market orders and unknown cancel/modify commands do not change exchange state, so they emit no canonical state event. Command rejection telemetry can be added as a separate operational stream without polluting deterministic book replay.

## Snapshot Checkpoints

The order book creates a typed `OrderBookSnapshot` before any JSON conversion. `MatchingEngine.record_snapshot()` appends that state as a canonical `snapshot` event with a positive requested depth and the current stream sequence. The snapshot includes bid/ask levels, best prices, midpoint, and spread. Simulation integration records one checkpoint after all mutations for each tick.

## Simulation Integration

The simulation owns one `MatchingEngine`, one order book, and one canonical log per run. Runtime agent limit/market/cancel commands use the matching engine. Synthetic level operations used by market makers, scenarios, and the baseline liquidity guard are observed at the order-book mutation boundary, so rapid place/cancel activity is retained even when its net L2 change is zero.

Each tick is ordered as agent actions, scenario actions, baseline-liquidity repair, then one L2 snapshot. Scenario mutation contexts add scenario ID/name/family to their canonical events. Existing `AgentEvent` objects remain a derived UI/detector view during migration and are not the source of canonical book replay.

## Delivery Contract

Arena state and each versioned `arena_state` WebSocket message include `exchange_events`, an ascending bounded tail of canonical records. The default in-memory window is 100 and is configurable when constructing the simulation engine.

`GET /api/arena/exchange-events?after_sequence=N&limit=M` provides gap-free cursor replay. The response includes `next_after_sequence`, the stream's `latest_sequence`, and `has_more`; clients pass the returned cursor into the next request. Limits are constrained to 1–1000 events.

The authoritative Java control plane retains at most
`LOB_ARENA_EVENT_HISTORY_CAPACITY` canonical events in the JVM (50,000 by
default). Older cursor pages are served from the segmented archive, so memory
rotation does not create replay gaps. Responses also include `stream_id`,
`first_available_sequence`, and `retained_from_sequence`. Supplying
`streamId=<id>` reads a completed stream after a reset.

## Frontend Projection

The frontend models the five event payloads as a discriminated `ExchangeEvent` union. Arena's secondary detection drawer includes an Exchange Tape showing the newest 18 events with canonical sequence, type, concise state change, venue, symbol, and simulation tick. Snapshot rows show depth and level counts rather than rendering their complete nested book.

Local mock/demo mode generates the same add/modify/snapshot contract, keeping the component independent of delivery mode.

## Event Sources

Consumers depend on the `ExchangeEventSource.read(after_sequence, limit)` contract and receive the same cursor batch regardless of origin.

- `SimulationEventSource` is a live view over the current simulation log.
- `CanonicalJsonlEventSource` replays an already-normalized and validated JSONL stream.
- `HistoricalRecordEventSource` accepts raw records plus a venue/vendor normalizer. The normalizer must emit `source="historical"` events and preserve source sequence/timestamps; the source assigns independent contiguous canonical sequences.

ARD-0018 is complete without selecting a vendor CSV layout. When a historical dataset is selected, its integration supplies a small `HistoricalRecordNormalizer` without changing matching, replay, API, detectors, or frontend consumers.

## Durable Streams

Each completed Java arena tick appends every canonical event to
`history/exchange-events/<stream_id>/segment-*.jsonl` before publishing the
completed tick. Segment manifests retain sequence ranges and archive byte
counts. Rows retain the canonical payload and add `stream_id` archive
metadata.

Canonical sequences are scoped to `stream_id`. Reset starts a new stream with
sequence 1 while preserving prior append-only history. The active-stream
archive is bounded by `LOB_ARENA_EVENT_ARCHIVE_MAX_STREAM_BYTES`; a replay
whose conservative estimate exceeds that quota is rejected before it starts.

End-to-end coverage runs an eight-tick spoofing-like scenario and verifies all five event types, exact sequence continuity, one snapshot per tick, persisted/in-memory event equality, and equality between the final persisted checkpoint and live book.
