# Java Integer Order Book

The authoritative Java order book and matching engine live in the framework-free `simulation-kernel` module. They represent all prices as signed 64-bit ticks and all quantities as non-negative signed 64-bit lots; binary floating-point values do not enter book state.

## Frozen Behavior

- Bids are visited from highest to lowest price; asks are visited from lowest to highest.
- Resting orders at one price remain in insertion order and match FIFO.
- A same-price quantity modification replaces the order in place and retains its original timestamp.
- A price-changing modification removes the order from its old queue and appends it to the destination queue with the request timestamp.
- Side and agent ownership cannot change through modify; zero quantity requires cancel.
- A market or crossing limit order emits one execute event per resting-order fill.
- The unfilled quantity of a limit order rests only after all execution events are emitted.
- Cancel events use the actual resting order state rather than fields supplied by the cancel request.
- Snapshots aggregate quantities by price, retain deterministic bid/ask ordering, expose the first non-normal owner, and preserve optional-field absence for one-sided or empty books.

The matching engine emits version 1 Protobuf events with contiguous sequences and deterministic `venue:type:sequence` identifiers. Initial book construction is event-free when performed before the matching listener is attached; explicit reinitialization through an active engine emits baseline add events, preserving the frozen version 1 behavior.

## Validation

Java tests cover both aggressor sides, limit constraints, price/FIFO order, partial fills, residual resting orders, modify/cancel rules, owner aggregation, baseline IDs and quantities, empty optional fields, all five event payloads, snapshot depth, sequence continuity, and canonical stream hashing.
