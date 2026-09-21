# Determinism Contract V1

This contract defines the frozen behavior of the authoritative Java kernel. `contracts/golden/determinism-v1.json` contains language-neutral executable vectors.

The production implementation is under `java/simulation-kernel/src/main/java/ai/lobarena/kernel/determinism`. Python contract tooling still verifies the same vectors independently, but no Python simulation-kernel runtime remains.

## Numeric Representation

- Prices are signed 64-bit integer ticks.
- Quantities are signed 64-bit integer lots and must be non-negative in valid book state.
- Decimal inputs convert through exact base-10 arithmetic: `decimal × 1_000_000_000 / unit_size_nanos` must be integral or the request is rejected.
- A midpoint is stored as `best_bid_ticks + best_ask_ticks`, named `mid_price_ticks_x2`, so half-tick midpoints remain exact.
- Metric values use signed integers plus `decimal_scale`; conversion uses base-10 round-half-even.
- NaN, infinity, locale-specific parsing, and binary floating-point values are outside the deterministic boundary.

## Event Ordering

The scheduler uses this ascending total-order key:

1. logical tick/time;
2. phase;
3. source priority;
4. actor ID as non-empty ASCII byte order;
5. source sequence;
6. insertion sequence.

Frozen phases are agent `10`, scenario `20`, baseline repair `30`, snapshot `40`, and metrics/finalization `50`. No implementation may rely on heap ordering when the comparator returns equality.

## PRNG

- The portable generator is SplitMix64 with unsigned 64-bit overflow after every addition and multiplication.
- Java uses unsigned right shift; Python masks every state/multiply result to 64 bits.
- Bounded integers use rejection sampling, not modulo-only selection.
- Independent stream seeds derive as the first eight big-endian bytes of SHA-256 over `lob-arena-prng-v1\0`, the root seed as eight unsigned big-endian bytes, and the non-empty ASCII stream name.
- Kernel code must use named streams rather than sharing one global generator across components.

## Identifiers And Time

- Canonical sequences begin at 1 and increase contiguously within a stream.
- Simulation event IDs are `venue:lowercase_event_type:sequence`.
- Venue and event type are non-empty ASCII and cannot contain `:`.
- Simulator events use logical ticks. Wall-clock timestamps cannot influence scheduling, identifiers, state, metrics, or hashes.

## Exchange Semantics

The Java implementation of these rules is documented in [Java Integer Order Book](java-order-book.md).

- Same-price quantity modification retains queue position and original priority timestamp.
- Price modification removes the order and appends it behind existing orders at the new price.
- Side and agent ownership cannot change through modify.
- Zero remaining quantity uses cancel rather than modify.
- Matching uses best price, then FIFO order within the price level.
- One execution event is emitted per resting-order fill.
- The tick sequence is agent actions, scenario actions, baseline repair, snapshot, then metric/finalization output.

## Hash Boundary

Raw JSON and raw Protobuf serialization are not canonical hash encodings. Step 4 defines an explicit field encoding and golden digest vectors using these integer, ordering, identifier, and presence rules.

## Related Documentation

- [Java Kernel Migration](java-kernel-migration.md)
- [Java Integer Order Book](java-order-book.md)
- [ARD-0018: Canonical Exchange Event Stream](architecture/ARD-0018-canonical-exchange-event-stream.md)
- [ARD-0019: Python Reference And Java Kernel Migration](architecture/ARD-0019-python-reference-java-kernel-migration.md)
