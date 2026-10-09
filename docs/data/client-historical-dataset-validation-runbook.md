# Client Historical Dataset Validation Runbook

Ingest a client LOBSTER message/book pair, replay the same window as historical
control and with predefined attacks, produce signed evidence, and assess data
validation separately from detector quality. Repeat for each dataset/window.
Implementation tests do not replace data-specific signed evidence.
Tracking: [Bug #357](https://github.com/khab40/lob-arena/issues/357),
[Project #3](https://github.com/users/khab40/projects/3).

## Prerequisites

Require a paired delivery, Docker Compose or Java/Python services, `jq`,
`openssl`, `shasum`, and an externally held Ed25519 key. Client keys must be
organization-approved, preferably managed/hardware-backed, with public-key
fingerprint authentication through an independent channel. UI/API discover
server files; they do not upload data. Transfer securely into configured
`ARENA_LOBSTER_RAW_DIR`. Never commit licensed data, private keys or client bundles.
This workflow grants no new client access or model-execution authorization.

## 1. Prepare the client delivery

Default Compose deliveries live under `data/lobster/<client>/<delivery-id>/`:

```text
<SYMBOL>_<YYYY-MM-DD>_<START_MS>_<END_MS>_message_<DEPTH>.csv
<SYMBOL>_<YYYY-MM-DD>_<START_MS>_<END_MS>_orderbook_<DEPTH>.csv
```

Both names must agree on symbol/date/session/depth. Messages have six columns:
seconds since midnight, event type, source order ID, size, price ×10,000,
direction. Book rows have `4 × DEPTH` repeating ask price/size, bid price/size.
A 09:45–09:46 window is `35100000`–`35160000` ms; filenames may cover a larger
session, with the selected minute bounded during import.

## 2. Start the services

```bash
docker compose up -d --build
```

| Surface | Address |
| --- | --- |
| Ingestion API | `http://localhost:8000` |
| Java replay API | `http://localhost:8081` |
| UI | `http://localhost:5173` |

Compose mounts `data/lobster` into ingestion and `data/processed/lobster`
read-only into Java. These are local services; shared access requires its own
approved authentication/authorization configuration.

## 3. Discover and import the selected window

```bash
curl -sS http://localhost:8000/api/data-ingestion/lobster/candidates \
  | jq '.[] | {candidate_id,symbol,trade_date,start_time,end_time,depth,status,errors}'
```

Reject `invalid` candidates: `errors` names pairing, duplicates, filename, depth
or session problems. Import the selected valid candidate:

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
- [Historical Market Data Ingestion ARD](../architecture/ARD-0022-historical-market-data-ingestion.md)
- [Hybrid Historical Replay ARD](../architecture/ARD-0023-hybrid-historical-replay.md)
- [Root historical and hybrid replay instructions](../../README.md#historical-and-hybrid-replay)
