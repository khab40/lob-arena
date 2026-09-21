# Canonical Hashing V1

Python and Java compare deterministic simulation output using an explicit SHA-256 encoding. Raw JSON and Protobuf wire bytes are transport formats, not canonical hash inputs.

The reference implementation is `backend/app/contracts/hashing.py`; the Java candidate implementation is `CanonicalHashes` in the framework-free simulation-kernel module. Both test suites verify every payload digest, canonical first-event bytes, book digest, initial digest, each rolling digest, and final stream digest against `contracts/golden/hashing-v1.json`.

## Primitive Encoding

- All integers are fixed-width big-endian.
- `uint8`, `uint32`, `uint64`, and `int64` use 1, 4, 8, and 8 bytes respectively.
- Boolean is one byte: `00` or `01`.
- String is a four-byte UTF-8 byte length followed by UTF-8 bytes.
- Strings must already be Unicode NFC; non-normalized input is rejected.
- Optional values begin with a one-byte presence marker and include their value only when present.
- Repeated values begin with an unsigned four-byte count and retain their declared order.

## Event Encoding

Canonical event bytes begin with the ASCII domain `LOB-EVENT-V1\0`, followed by metadata in Protobuf field-number order and then a one-byte payload discriminator:

| Payload | Discriminator |
| --- | --- |
| Add | `1` |
| Modify | `2` |
| Cancel | `3` |
| Execute | `4` |
| Snapshot | `5` |

Payload fields follow their Protobuf field-number order. Snapshot book levels retain bid/ask list order and optional-field presence. The per-event digest is SHA-256 over these canonical bytes.

## Book Encoding

Standalone book bytes begin with `LOB-BOOK-V1\0`. They contain bid count and ordered bid levels, ask count and ordered ask levels, followed by optional best bid, best ask, twice-price midpoint, and spread.

## Stream Hash Chain

The initial stream digest is SHA-256 over `LOB-STREAM-INIT-V1\0` plus the four-byte contract version. Each step is:

```text
SHA-256("LOB-STREAM-STEP-V1\0" || previous_stream_hash || event_hash)
```

Events must have matching schema version and contiguous sequence beginning at 1. `contracts/golden/hashing-v1.json` freezes canonical bytes and digests for all five payloads.

## Related Documentation

- [Determinism Contract V1](determinism-contract-v1.md)
- [Java Kernel Migration](java-kernel-migration.md)
- [ARD-0019](architecture/ARD-0019-python-reference-java-kernel-migration.md)
