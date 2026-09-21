# ARD-0002: WebSocket State Schema

Status: Accepted

Date: 2026-06-01

## Implementation Status

Status as of 2026-07-18: `[done; Java owner]`

Implemented:

- Versioned `arena_state` envelope in Spring WebSocket handler and `/ws/arena` route.
- Java-owned complete state payloads for book levels, events, active agents, detector scores, incidents, and runtime flags.
- Frontend WebSocket source hook and UI components that render the latest complete backend state.
- Focused Java WebSocket/runtime tests, including malformed commands and session cleanup.

Follow-up:

- Add formal exported JSON schema and load-test based throttling if message volume grows.

## Context

The React arena needs frequent state updates from the Java live arena. The UI should not reconstruct exchange state from raw events. It needs a compact, stable state envelope that can drive the order book ladder, charts, agent feed, active agents, detector confidence, and incident cards.

Spring owns the live simulation clock and broadcasts messages through `/ws/arena`; FastAPI no longer hosts a WebSocket route.

## Decision

Use a versioned WebSocket message envelope with `type`, `version`, `timestamp`, and `payload`. The primary live message type is `arena_state`.

The payload should include the latest complete UI-ready state, not only a delta.

```json
{
  "type": "arena_state",
  "version": 1,
  "timestamp": "2026-06-01T12:00:00Z",
  "payload": {
    "tick": 42,
    "running": true,
    "book": {
      "bids": [{"price": 99.99, "quantity": 256}],
      "asks": [{"price": 100.01, "quantity": 240}],
      "best_bid": 99.99,
      "best_ask": 100.01,
      "mid": 100.0,
      "spread": 0.02
    },
    "events": [],
    "active_agents": ["MM_01", "NOISE_01", "TAKER_01"],
    "detectors": {"scores": [], "alerts": []},
    "incidents": []
  }
}
```

## Schema Diagram

```mermaid
graph TD
    Message["ArenaMessage - type, version, timestamp"]
    State["ArenaState - tick, running, active agents"]
    Book["BookSnapshot - bids, asks, best levels, mid, spread"]
    Level["BookLevel - price and quantity"]
    Detectors["DetectorState - scores and alerts"]
    Score["DetectorScore - name, confidence, alert"]
    Events["Agent and exchange events"]
    Incidents["Incident list"]

    Message --> State
    State --> Book
    Book --> Level
    State --> Detectors
    Detectors --> Score
    State --> Events
    State --> Incidents
```

## Message Flow

```mermaid
graph TD
    Connect["1. React UI connects to /ws/arena"]
    Initial["2. WebSocket sends initial arena_state"]
    Orders["3. Runtime processes agent orders"]
    Book["4. Matching engine returns book snapshot and events"]
    Scores["5. Detectors score events and book"]
    Publish["6. Runtime publishes arena_state"]
    Render["7. UI renders latest complete state"]

    Connect --> Initial
    Initial --> Orders
    Orders --> Book
    Book --> Scores
    Scores --> Publish
    Publish --> Render
    Render --> Orders
```

## Consequences

Positive:

- UI rendering is simple and robust.
- Late-joining clients receive a complete current state.
- The schema can evolve through `version`.

Tradeoffs:

- Full-state messages are larger than deltas.
- The backend must keep the payload shape stable.
- High-frequency updates may need throttling if the payload grows.

## Related Documentation

- `docs/runtime/runtime-model.md`
- `docs/architecture.md`
- [ARD-0001: Overall Architecture](ARD-0001-overall-architecture.md)
