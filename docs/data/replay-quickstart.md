# Historical replay and market-profile quickstart

Run commands from the repository root after the [application quickstart](../deployment/QUICKSTART.md).
Agent-initiated model workloads follow the [execution policy](../ml/model-validation-execution-policy.md).

### Historical and hybrid replay

The Java exchange replays existing `canonical_csv_v1` order events, LOBSTER
message/order-book imports, and normalized Nasdaq TotalView-ITCH 5.x streams
through the same integer matching engine used by synthetic runs. LOBSTER
ingestion remains the existing paired-file workflow:
the Python adapter validates the public six-column message and `4 × depth`
order-book formats, writes aligned Parquet plus a checksummed manifest, and the
Java exchange reconstructs each contemporaneous book state from that immutable
stream.

The peer `nasdaq_itch` adapter streams length-prefixed plain or gzip ITCH input
without materializing an uncompressed session. It resolves daily Stock Locate
mappings and reconstructs `A`, `F`, `E`, `C`, `X`, `D`, and `U` visible-order
lifecycles for one symbol and bounded time window. The adapter emits the same
aligned Parquet columns plus additive ITCH provenance, while its manifest binds
`source_type=nasdaq_itch`, `format=itch_parquet_v1`, `venue=XNAS`, parser/config
versions, compressed-stream SHA-256, filters, message counts, output hashes, and
disk limits. Unsupported non-book messages are counted but never interpreted as
book mutations.

The small public [LOBSTER-compatible fixture](../../data/lobster/README.md) contains
synthetic test records covering add, partial cancel, delete, visible/hidden
execution, cross trade, and halt messages. It can be imported from **Data
Ingestion** without redistributing licensed market data. The older
[canonical CSV fixture](../../data/historical/README.md) remains supported.
The [synthetic ITCH fixture](../../data/nasdaq-itch/README.md) covers every supported
transition and contains no real Nasdaq session data.

In the Arena UI:

1. Import a LOBSTER pair or a bounded Nasdaq ITCH symbol window in **Data Ingestion**.
2. Select **Historical control**, choose the imported dataset, load it, and
   start replay for an unlabeled control run.
3. Select **Hybrid + attacks**, load the same dataset, then launch the existing
   spoofing-like or layering-like attack from **Scenario Setup**. Attacks are
   intentionally launched from the UI/API after the replay source is loaded;
   the historical importer never creates attacks or labels.

Historical records are immutable and never become benign ground truth. Only the synthetic overlay supplies attack labels, and detector features do not contain scenario labels or synthetic-only metadata. Historical and synthetic participant/order IDs use separate `HIST:` and `SYN:` namespaces.

At each replay step, records are ordered by exchange timestamp, historical
phase, source priority, actor ID, source sequence, and insertion sequence.
Historical records therefore win equal-timestamp ties; the attack generator
then reads only the reconstructed live book. It never reads a future Parquet
row. Batch comparisons may specify exactly one `trigger_source_sequence` or
`trigger_timestamp_ns`. Control and hybrid runs split at the same point, all
historical rows tied at that exchange timestamp are applied first, and later
rows are deferred. The attack seed is derived from the configured master seed,
dataset, scenario family, deterministic scenario number, and schedule hash.
The schedule hash also binds bounded parameters for the existing scenario
family. Synthetic-only and manually launched runs keep their previous defaults.

Example request bodies are committed as
[historical-control.json](../../configs/replay/historical-control.json) and
[hybrid-with-ui-attack.json](../../configs/replay/hybrid-with-ui-attack.json). Load
one with:

```bash
curl -sS -X POST http://localhost:8081/api/arena/data-source \
  -H 'Content-Type: application/json' \
  --data @configs/replay/historical-control.json
```

The Java comparison endpoint executes both modes over the same source:

```bash
curl -sS -X POST http://localhost:8081/api/arena/replay-comparison \
  -H 'Content-Type: application/json' \
  -d '{"dataset_id":"itch-aapl-window","scenario_family":"spoofing_like_wall","master_seed":42,"trigger_source_sequence":125000,"scenario_parameters":{"quantity_lots":30000},"max_ticks":10000}'
```

To reuse the tournament precision/recall/F1 calculation and create a
checksummed, signed validation bundle:

```bash
backend/.venv/bin/python scripts/run_historical_replay_comparison.py \
  --base-url http://localhost:8081 \
  --dataset sample-btcusdt-0945 \
  --scenario spoofing_like_wall \
  --master-seed 42 \
  --trigger-source-sequence 125000 \
  --scenario-parameters '{"quantity_lots":30000}' \
  --signing-key /secure/lob-validation-key.pem \
  --signer "Market Surveillance QA" \
  --output outputs/historical-replay/sample-btcusdt-0945
```

The bundle contains the control, hybrid, metrics, validation, signed manifest,
checksum, Ed25519 signature, and public-key artifacts. The signed manifest
binds every evidence payload by SHA-256 and byte size. It records Java-verified
Parquet hashes, repeat-run determinism, full-stream/historical/synthetic
hashes, source/event counts, injected-order lifecycle, detector metrics, and
before/during/after causal locality. Outside the labelled attack
neighbourhood, paired books must match exactly and book/event-flow metrics must
pass the documented statistical equivalence bounds. See
[Hybrid Dataset Validation](hybrid-dataset-validation.md) for the
methodology, signing trust boundary, verification commands, and limitations.
For repeatable client deliveries, use the
[Client Historical Dataset Validation Runbook](client-historical-dataset-validation-runbook.md).
The public fixture includes a
[signed sample report](../../data/lobster/fixture/validation/validation-report.json).

Known limitation: LOBSTER exposes aggregate depth snapshots but not participant
identity, and selected windows can begin after orders were originally entered.
The replay therefore represents historical liquidity as deterministic
per-price `HIST:` level orders while preserving every source message sequence
and its aligned post-event snapshot. Synthetic orders remain separate and
retain their own lifecycle. This is deterministic and faithful at the visible
depth supplied by LOBSTER, but it cannot recover queue priority or participant
identity absent from the source files.
The configured replay batch (`LOB_ARENA_HISTORICAL_ROWS_PER_TICK`, default
`250`) controls throughput, not injection precision. Scheduled comparisons
partition a prefetched batch at the resolved source row, include all
equal-timestamp historical rows, and defer the remainder.

Architecture decisions are recorded in
[ARD-0022](../architecture/ARD-0022-historical-market-data-ingestion.md) for
ingestion/storage and
[ARD-0032](../architecture/ARD-0032-nasdaq-itch-ingestion.md) for the ITCH
adapter and source-neutral manifest contract, and
[ARD-0033](../architecture/ARD-0033-deterministic-hybrid-scheduling.md) for
exact in-window scheduling and evidence bindings, and
[ARD-0023](../architecture/ARD-0023-hybrid-historical-replay.md) for hybrid
ordering, provenance, seed derivation, label isolation, metrics, and artifacts.

### ITCH-calibrated interactive simulation

