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
  -d '{"start_time_ms":35100000,"end_time_ms":35160000}' | jq
```

Import is asynchronous. Poll until registered; record immutable dataset ID and
row count. Failed imports are not runnable; recheck candidate status/errors.

```bash
curl -sS http://localhost:8000/api/data-ingestion/datasets \
  | jq '.[] | select(.start_time_ms == 35100000 and .end_time_ms == 35160000) |
    {dataset_id,symbol,trade_date,depth,row_count,path}'
```

Python validates paired rows, timestamps/session, ordered uncrossed price levels,
observable volume/level changes, tracked order lifecycles, normalized Parquet
alignment, hashes/counts and provenance.

## 4. Confirm Java can see the normalized dataset

```bash
curl -sS http://localhost:8081/api/arena/historical-datasets \
  | jq '.[] | select(.dataset_id == "<dataset-id>")'
```

At replay, Java independently checks actual `events.parquet`/`book_snapshots.parquet`
size/hash, complete unique physically ordered source sequences, matching row
counts, monotone in-session timestamps and positional sequence/time alignment.
The manifest alone is insufficient at this replay trust boundary.

## 5. Create or select the production signing key

A disposable local key can be created outside repository/evidence directories:

```bash
umask 077
openssl genpkey -algorithm Ed25519 -out /secure/lob-validation-key.pem
```

Client delivery uses the approved organization key, never this disposable key
unless explicitly accepted for that delivery. The private key stays outside bundles.

## 6. Generate signed evidence

For each scenario the CLI runs historical control, hybrid, and one deterministic
repeat of each. Calculate full-window ticks with Java's configured rows per tick
(Compose default 250):

```bash
ROW_COUNT=<row-count>
ROWS_PER_TICK=250
MAX_TICKS=$(( (ROW_COUNT + ROWS_PER_TICK - 1) / ROWS_PER_TICK + 1 ))
```

Java accepts at most 100,000 ticks. Exceeding that requires a smaller window or
a deliberately increased rows-per-tick setting and `java-kernel` restart. Cover
the complete attack plus at least one post-attack observation; quote stuffing
needs at least seven replay ticks. For small datasets reduce rows per tick so
the lifecycle remains observable. Record the chosen configuration.

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

Repeat `spoofing_like_wall`, `layering_like`, `quote_stuffing` with separate
output directories. Never reuse a directory across dataset/scenario/seed/code
revision. Each bundle contains control/hybrid/comparison/validation JSON,
`manifest.json`, `manifest.sig`, `signature.json`, `validation-public-key.pem`
and `checksums.sha256`; never a private key. This replay command runs the existing
canonical comparison. Agent-initiated learned-model training/scoring/runtime
rehearsals, including synthetic fixtures, require authorized Nebius Jobs under
[the execution policy](../ml/model-validation-execution-policy.md).

## 7. Apply the validation gate

Pass requires the verdict and **every** check to pass:

```bash
jq -e '.verdict == "pass" and ([.checks[].status] | all(. == "pass"))' \
  outputs/client-validation/<client>/<dataset-id>/spoofing-seed-42/validation-report.json
```

Checks cover source hashes/complete sequences, identical historical snapshots,
deterministic repeats/traces, collision-safe `SYN:` lifecycle and quantity
semantics, synthetic-ground-truth localization/no label leakage, intended
book/event-flow impact, and exact books plus statistical equivalence outside
the causal neighborhood. Quote stuffing may leave identical end-of-tick books;
message/add/cancel/execute-flow divergence establishes its intended impact.
See [validation details](hybrid-dataset-validation.md).

Retain failures, investigate the named check, then use a fresh output directory
for corrected source/configuration; signing does not turn a failure into a pass.

## 8. Review detector metrics

Validation correctness and detector quality are separate gates:

```bash
jq '.detector_metrics[] | {detector,true_positive,false_negative,false_positive,
  true_negative,precision,recall,f1,control_alert_ticks,hybrid_alert_ticks}' \
  outputs/client-validation/<client>/<dataset-id>/spoofing-seed-42/comparison.json
```

Apply agreed client thresholds; a valid hybrid dataset can expose detector misses.
Report them. Unreviewed historical controls are not independently proven clean
labels; qualify quality claims to the supported synthetic/reference population.

## 9. Verify the signed bundle

The verifier checks Ed25519 over `manifest.json`, key ID, and every signed
artifact's SHA-256/byte size:

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

Check transport and independently authenticate the public-key fingerprint:

```bash
cd outputs/client-validation/<client>/<dataset-id>/spoofing-seed-42
shasum -a 256 -c checksums.sha256
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
