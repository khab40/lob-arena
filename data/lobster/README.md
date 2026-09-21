# Public LOBSTER-compatible replay fixture

`fixture/` contains a small paired message/order-book sample using the public
LOBSTER CSV column layout. It is synthetic test data, not redistributed
commercial market data.

- Message columns: time in seconds since midnight, event type, order ID, size,
  price multiplied by 10,000, direction.
- Order-book columns repeat ask price, ask size, bid price, bid size for each
  requested depth level.
- Filenames follow the LOBSTER convention consumed by the existing ingestion
  API.

Import the fixture with the existing LOBSTER ingestion UI or API. The resulting
`events.parquet`, `book_snapshots.parquet`, and manifest are directly replayable
as either a historical control or a hybrid background stream in the Java
exchange.

See the root [historical and hybrid replay instructions](../../README.md#historical-and-hybrid-replay),
[ARD-0022](../../docs/architecture/ARD-0022-historical-market-data-ingestion.md)
for ingestion, and
[ARD-0023](../../docs/architecture/ARD-0023-hybrid-historical-replay.md) for
ordering, provenance, labels, and evaluation guarantees.

The fixture is internally message/book consistent and is covered by lifecycle,
visible-volume, sequence, timestamp, session, and crossed-book tests. Its
[signed validation bundle](fixture/validation/manifest.json) compares the
historical control with a layering injection, proves exact equivalence outside
the attack window, and demonstrates Ed25519 verification. The sample signer is
not a production organizational identity; see
[Hybrid Dataset Validation](../../docs/data/hybrid-dataset-validation.md).
