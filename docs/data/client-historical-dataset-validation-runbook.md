# Client Historical Dataset Validation Runbook

This runbook describes how to ingest a new client-supplied LOBSTER
message/order-book pair, replay the same window as a historical control and as
a hybrid stream with predefined synthetic attacks, produce signed evidence,
and decide whether the dataset passes validation.

Use this workflow for every client dataset and selected time window. The
repository's unit tests verify the implementation; the signed replay workflow
below validates the actual client data.

## Prerequisites

- A paired LOBSTER message and order-book CSV delivery.
- Docker with Compose, or equivalent local Java and Python services.
- `jq`, `openssl`, and `shasum`.
- An Ed25519 signing key held outside the repository. Production keys should be
  organization-managed or hardware-backed.
- An authenticated, independent channel through which recipients can confirm
  the expected public-key fingerprint.

The Data Ingestion UI and API discover files already present on the server.
They do not upload client files. Transfer client data into the configured
`ARENA_LOBSTER_RAW_DIR` using the organization's approved secure transfer
process.

Do not commit licensed client data, private signing keys, or client evidence
bundles to this repository.

## 1. Prepare the client delivery

Place each delivery in its own directory below `data/lobster/` when using the
default Compose configuration:

```text
data/lobster/
└── <client>/<delivery-id>/
    ├── SPY_2012-06-21_34200000_57600000_message_30.csv
    └── SPY_2012-06-21_34200000_57600000_orderbook_30.csv
```

Both filenames must have the same symbol, date, start/end milliseconds, and
depth:

```text
<SYMBOL>_<YYYY-MM-DD>_<START_MS>_<END_MS>_message_<DEPTH>.csv
<SYMBOL>_<YYYY-MM-DD>_<START_MS>_<END_MS>_orderbook_<DEPTH>.csv
```

The message file uses the public six-column LOBSTER layout: seconds since
midnight, event type, source order ID, size, price multiplied by 10,000, and
direction. Each order-book row contains `4 × DEPTH` values in repeating ask
price, ask size, bid price, bid size order.

For a 09:45:00–09:46:00 window:

- start: `35100000` milliseconds since midnight;
- end: `35160000` milliseconds since midnight.

The source filenames may describe a larger session. Select the one-minute
window during import.

## 2. Start the services

From the repository root:

```bash
docker compose up -d --build
```

The relevant endpoints are:

- Data Ingestion API: `http://localhost:8000`
- Java replay API: `http://localhost:8081`
- UI: `http://localhost:5173`

Compose mounts `data/lobster` into the Python ingestion service and
`data/processed/lobster` read-only into the Java exchange.

## 3. Discover and import the selected window

List candidates:

```bash
curl -sS http://localhost:8000/api/data-ingestion/lobster/candidates \
  | jq '.[] | {
      candidate_id,
      symbol,
      trade_date,
      start_time,
      end_time,
      depth,
      status,
      errors
    }'
```

Do not import a candidate whose status is `invalid`. Its `errors` array
identifies missing pairs, duplicate files, invalid names, depth problems, or
session-range problems.

Import the 09:45 one-minute window using the selected `candidate_id`:

```bash
curl -sS -X POST \
  http://localhost:8000/api/data-ingestion/lobster/candidates/<candidate-id>/import \
  -H 'Content-Type: application/json' \
  -d '{"start_time_ms":35100000,"end_time_ms":35160000}' \
  | jq
```

Import runs in the background. Poll until the new dataset appears:

```bash
curl -sS http://localhost:8000/api/data-ingestion/datasets \
  | jq '.[] | select(
      .start_time_ms == 35100000 and
      .end_time_ms == 35160000
    ) | {
      dataset_id,
      symbol,
      trade_date,
      depth,
      row_count,
      path
    }'
```

Record the immutable `dataset_id` and `row_count`.

During import, Python validates:

- message/order-book row synchronization;
- timestamp and trading-session integrity;
- price-level ordering and uncrossed books;
- visible price-level changes and volume conservation where observable;
- tracked order lifecycle operations;
- normalized Parquet alignment;
- output hashes, row counts, and source provenance.

Failed imports are not registered as runnable datasets. Inspect the candidate's
`status` and `errors` again if no dataset appears.

## 4. Confirm Java can see the normalized dataset

```bash
curl -sS http://localhost:8081/api/arena/historical-datasets \
  | jq '.[] | select(.dataset_id == "<dataset-id>")'
```

Java independently verifies the actual `events.parquet` and
`book_snapshots.parquet` files when replay begins. It rejects:

- size or SHA-256 mismatches against the manifest;
- incomplete, duplicate, or physically out-of-order source sequences;
- event/book row-count mismatches;
- timestamp regressions or values outside the selected session; and
- message/book rows that are not positionally aligned on sequence and timestamp.

This check is intentionally repeated at the replay trust boundary; a manifest
alone is not accepted as proof.

## 5. Create or select the production signing key

For a disposable local test key:

```bash
umask 077
openssl genpkey -algorithm Ed25519 \
  -out /secure/lob-validation-key.pem
```

For client delivery, use the approved organization key. Keep the private key
outside the repository and outside the evidence output directory.

## 6. Generate signed evidence

Run one evidence bundle per scenario. The CLI automatically executes:

1. a historical-only control;
2. a hybrid run over the same window;
3. a deterministic repeat of the control; and
4. a deterministic repeat of the hybrid run.

Calculate `max_ticks` from the dataset row count and the Java
`LOB_ARENA_HISTORICAL_ROWS_PER_TICK` setting. The Compose default is `250`:

```bash
ROW_COUNT=<row-count>
ROWS_PER_TICK=250
MAX_TICKS=$(( (ROW_COUNT + ROWS_PER_TICK - 1) / ROWS_PER_TICK + 1 ))
```

The Java API accepts at most `100000` ticks. If the calculated value exceeds
that limit, select a smaller source window or deliberately increase
`LOB_ARENA_HISTORICAL_ROWS_PER_TICK` and restart `java-kernel`.

The replay needs enough ticks to contain the complete attack and at least one
post-attack observation. Use at least seven replay ticks for quote-stuffing.
For small datasets, reduce rows per tick rather than allowing the evidence run
to finish before the scenario lifecycle and post-attack phase are observable.
Record the chosen rows-per-tick value as part of the delivery configuration.

```bash
backend/.venv/bin/python scripts/run_historical_replay_comparison.py \
  --base-url http://localhost:8081 \
  --dataset <dataset-id> \
  --scenario spoofing_like_wall \
  --master-seed 42 \
  --max-ticks "$MAX_TICKS" \
  --signing-key /secure/lob-validation-key.pem \
  --signer "Market Surveillance QA" \
  --output outputs/client-validation/<client>/<dataset-id>/spoofing-seed-42
```

Repeat with separate output directories for:

- `spoofing_like_wall`
- `layering_like`
- `quote_stuffing`

Do not reuse an evidence directory for a different dataset, scenario, seed, or
code revision.

Each directory contains:

- `control.json`
- `hybrid.json`
- `comparison.json`
- `validation-report.json`
- `manifest.json`
- `manifest.sig`
- `signature.json`
- `validation-public-key.pem`
- `checksums.sha256`

The private key is never copied into the bundle.

## 7. Apply the validation gate

The dataset/scenario run passes only when the validation verdict and every
validation check pass:

```bash
jq -e '
  .verdict == "pass" and
  ([.checks[].status] | all(. == "pass"))
' outputs/client-validation/<client>/<dataset-id>/spoofing-seed-42/validation-report.json
```

The report checks:

- verified historical source hashes and complete source-sequence coverage;
- identical control/hybrid historical snapshot streams;
- deterministic repeated streams and traces;
- collision-safe `SYN:` order lifecycles;
- cancellation and execution quantity semantics;
- attack localization to synthetic ground truth;
- absence of label leakage;
- intended book or event-flow impact during injection; and
- exact book equality plus statistical equivalence outside the attack's causal
  neighbourhood.

Quote-stuffing may leave the same end-of-tick book as the control. Its intended
impact is therefore proven through message/add/cancel/execute flow divergence,
while the outside-window equivalence requirement remains unchanged.

A failure is evidence, not something to sign away. Retain the failed bundle,
investigate the named check, and create a new run directory after correcting
the source or configuration.

## 8. Review detector metrics

Validation correctness and detector performance are separate gates. Review TP,
FN, FP, TN, precision, recall, F1, and alert timing:

```bash
jq '.detector_metrics[] | {
  detector,
  true_positive,
  false_negative,
  false_positive,
  true_negative,
  precision,
  recall,
  f1,
  control_alert_ticks,
  hybrid_alert_ticks
}' outputs/client-validation/<client>/<dataset-id>/spoofing-seed-42/comparison.json
```

Apply the client's agreed detector thresholds. A structurally valid hybrid
dataset can still demonstrate a detector miss, which must remain visible in
the commercial report.

## 9. Verify the signed bundle

Run the repository verifier. It verifies the Ed25519 signature over
`manifest.json`, the key ID, and every signed artifact's SHA-256 and byte size:

```bash
backend/.venv/bin/python -c '
from pathlib import Path
from scripts.run_historical_replay_comparison import verify_bundle_signature

verify_bundle_signature(
    Path("outputs/client-validation/<client>/<dataset-id>/spoofing-seed-42")
)
print("signed bundle verified")
'
```

Optionally verify the transport checksum list:

```bash
cd outputs/client-validation/<client>/<dataset-id>/spoofing-seed-42
shasum -a 256 -c checksums.sha256
```

Confirm the public-key fingerprint through the independent client-approved
channel:

```bash
shasum -a 256 validation-public-key.pem
jq -r '.key_id' signature.json
```

The signed manifest is the evidence trust root. `checksums.sha256` is a
convenient transport check and is not a substitute for signature and signed
inventory verification.

## 10. Run implementation regression tests

Run these when the ingestion, replay, detector, metric, or evidence code has
changed. They are not a replacement for the data-specific evidence run:

```bash
uv run --project backend pytest -q
uv run --project backend ruff check backend scripts

cd java
./gradlew test
```

Validate documentation links from the repository root:

```bash
backend/.venv/bin/python scripts/check_markdown_links.py README.md docs data/lobster
```

## Delivery checklist

- [ ] Client files arrived through an approved secure channel.
- [ ] Message and order-book filenames form one unambiguous pair.
- [ ] The intended time window and depth were confirmed with the client.
- [ ] Import completed and produced an immutable dataset ID.
- [ ] Java accepted the actual normalized Parquet files.
- [ ] The entire source row count was replayed.
- [ ] Separate signed bundles were generated for every agreed attack and seed.
- [ ] Every `validation-report.json` check passed.
- [ ] Detector metrics met the client-specific acceptance thresholds.
- [ ] Bundle signature and signed artifact inventory verified.
- [ ] Public-key fingerprint was authenticated independently.
- [ ] Private keys and licensed source data were excluded from the repository.
- [ ] Evidence was archived in the approved immutable client location.

## Related documentation

- [Hybrid Dataset Validation](hybrid-dataset-validation.md)
- [Historical Market Data Ingestion ARD](architecture/ARD-0022-historical-market-data-ingestion.md)
- [Hybrid Historical Replay ARD](architecture/ARD-0023-hybrid-historical-replay.md)
- [Root historical and hybrid replay instructions](../README.md#historical-and-hybrid-replay)
