# ARD-0032: Nasdaq TotalView-ITCH Ingestion

Status: Phase 1 Accepted and Implemented

Date: 2026-08-04

## Context

The historical Parquet replay contract was already stable, but ingestion and
Java provenance still assumed LOBSTER. The arena needs one bounded Nasdaq
TotalView-ITCH 5.x adapter without creating a second replay path or committing
licensed market sessions.

## Decision

- FastAPI treats `lobster` and `nasdaq_itch` as peer source adapters. Existing
  LOBSTER routes and manifest defaults remain valid.
- The ITCH adapter accepts local length-prefixed plain or gzip streams. It
  parses System Event and Stock Directory messages and reconstructs visible
  `A`, `F`, `E`, `C`, `X`, `D`, and `U` order lifecycles for one selected
  symbol. Other message types are counted and ignored as book mutations.
- Stock Locate values are resolved from the current session's Stock Directory.
  Source sequence counts every feed message, including unsupported messages,
  and timestamps remain integer nanoseconds since midnight.
- Validation rejects timestamp regressions, missing or reused order references,
  invalid reductions/replacements, negative depth, crossed books, malformed
  message lengths, and symbol/locate inconsistencies.
- Output remains aligned `events.parquet` and `book_snapshots.parquet`. Core
  columns are unchanged; ITCH adds raw message type, locate, tracking number,
  match number, MPID, printable flag, and replacement reference columns.
- Java reads `source_type`, `format`, and `venue` from the manifest and ignores
  additive Parquet columns. Legacy manifests default to `lobster`,
  `lobster_parquet_v1`, and `LOBSTER`.
- Local normalization defaults to one symbol, a 30-minute UI window, depth 10,
  a 12 GiB working-set cap, and a 20 GiB free-disk reserve. Import writes to a
  temporary sibling and atomically publishes only completed datasets.

## Provenance Contract

An ITCH manifest records `source_type=nasdaq_itch`,
`format=itch_parquet_v1`, `venue=XNAS`, parser version, source name,
compressed-stream SHA-256, parser/config SHA-256, symbol/window/depth filters,
all message-type counts, output file hashes, and quota limits. Dataset identity
is derived from source and parser configuration hashes.
The legacy-required `imported_at` field is normalized to feed-date midnight UTC
for ITCH so repeated conversion in separate registries produces an identical
manifest; operational job timing belongs in logs rather than dataset identity.

## Data and Licensing Boundary

The repository contains only a tiny generated binary fixture. Real sessions
must be obtained and handled under the user's Nasdaq or data-vendor agreement.
The adapter does not download data and does not materialize an uncompressed
full-session file.

## Consequences

Historical ITCH replay remains immutable: recorded participants cannot respond
to a counterfactual overlay. Controlled hybrid injection reuses the normalized
stream, while fully interactive causal response remains a synthetic-simulation
property. Cloud partitioning and multi-session ingestion remain future scaling
work and must retain this manifest and Parquet contract.

## References

- [Nasdaq TotalView-ITCH 5.0 specification](https://www.nasdaqtrader.com/content/technicalsupport/specifications/dataproducts/NQTVITCHSpecification.pdf)
- [Synthetic ITCH fixture](../../data/nasdaq-itch/README.md)
- [ARD-0022: Historical Market Data Ingestion](ARD-0022-historical-market-data-ingestion.md)
- [ARD-0023: Hybrid Historical Replay](ARD-0023-hybrid-historical-replay.md)
