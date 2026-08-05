# Hybrid Dataset Validation

The hybrid validation bundle is the commercial handoff for a historical
control run and an attack-injected run over the same LOBSTER window. It proves
source integrity, replay determinism, injected-order lifecycle correctness,
attack localisation, and the absence of unintended changes outside the
attack's causal neighbourhood.

The same validation applies to `itch_parquet_v1`. A scheduled comparison binds
the selected source sequence or timestamp, resolved scenario parameters,
master seed, and dataset in `historical_injection_schedule_v1`. Control and
hybrid use the identical schedule partition. When multiple historical rows
share the trigger timestamp, every tied row is applied before the synthetic
mutation and later rows remain deferred.

The validator reuses the authoritative Java replay and canonical book hashes.
Before replay, Java independently verifies both normalized Parquet files
against the manifest, checks their row counts, unique sequences, monotonic
timestamps, session bounds, and exact sequence/timestamp pairing. The compact
validation trace is emitted only as an evaluation artifact. It is not detector
input and contains no ground-truth fields.

## Validation layers

### LOBSTER ingestion

The importer validates:

- one-to-one message/order-book row synchronization;
- monotonic source timestamps and the filename trading-session bounds;
- ask/bid ordering, unique price levels, positive quantities, and uncrossed
  books;
- visible price-level deltas for add, partial-cancel, delete, and visible
  execution messages;
- tracked source-order adds, reductions, deletions, and executions;
- unchanged visible depth for hidden execution, cross-trade, and halt records;
- normalized Parquet sequence/timestamp alignment; and
- manifest row counts, output hashes, and source provenance.

Order-level validation reports how many lifecycle events could be tracked from
an observed add. An order first seen after the selected window began is counted
as untracked rather than assigned invented queue history.

### Hybrid replay

The comparison endpoint executes each control and hybrid run twice. It records
full stream hashes, historical snapshot-stream hashes, synthetic event audits,
and a compact per-tick book and event-flow trace. Validation requires:

- identical repeat-run hashes and traces;
- the same Java-verified immutable Parquet hashes, complete source sequence
  count, row count, and historical snapshot-stream hash in both runs;
- ITCH compressed-stream and parser/config hashes, message counts, filters,
  quota limits, and output hashes when the source is `nasdaq_itch`;
- identical requested/actual trigger coordinates, schedule parameters, and
  schedule hash in control and hybrid runs;
- valid `SYN:` order lifecycles, including cancellation and execution
  quantities;
- synthetic events contained by the separate ground-truth attack window;
- intended book or add/cancel/execute flow divergence during the causal
  neighbourhood; and
- equivalence outside the causal neighbourhood.

The causal neighbourhood is the inclusive synthetic ground-truth interval.
Before and after it, every paired combined-book hash must match exactly. The
validator also runs a paired 95% mean-difference equivalence interval for
spread, top-depth, imbalance, level count, and message/add/cancel/execute
counts. The equivalence margin is 1% of the control scale, with an absolute
0.01 floor for imbalance. Exact book equality outside the attack window is
stronger than the statistical test and is required for a passing commercial
report. During the window, event-flow divergence is sufficient for
quote-stuffing because its add/cancel burst can intentionally reconverge to the
same end-of-tick book.

## Create a signed report

Keep the Ed25519 private key outside the repository, ideally in an
organization-managed signing service or hardware-backed keystore.

```bash
umask 077
openssl genpkey -algorithm Ed25519 -out /secure/lob-validation-key.pem

backend/.venv/bin/python scripts/run_historical_replay_comparison.py \
  --base-url http://localhost:8081 \
  --dataset <dataset-id> \
  --scenario layering_like \
  --master-seed 42 \
  --max-ticks 10000 \
  --signing-key /secure/lob-validation-key.pem \
  --signer "Market Surveillance QA" \
  --output outputs/historical-replay/<run-id>
```

The signed bundle contains:

- `control.json` and `hybrid.json`;
- `comparison.json`;
- `validation-report.json`;
- `manifest.sig`;
- `validation-public-key.pem`;
- `signature.json`;
- `manifest.json`; and
- `checksums.sha256`.

Verify both bundle integrity and the detached signature:

```bash
cd outputs/historical-replay/<run-id>
shasum -a 256 -c checksums.sha256
openssl pkeyutl -verify -pubin \
  -inkey validation-public-key.pem \
  -sigfile manifest.sig \
  -rawin -in manifest.json
```

`manifest.json` contains the SHA-256 digest and byte size of every evidence
artifact. Verifying its signature and then its inventory binds the control,
hybrid, metrics, validation report, signature metadata, and public key as one
evidence bundle. `checksums.sha256` is a convenient transport check; the signed
manifest is the trust root. The public key proves which private key signed the
bundle, but commercial trust still requires the recipient to authenticate that
public-key fingerprint through an independent organizational channel.

## Sample report

The public fixture includes a
[signed sample validation bundle](../data/lobster/fixture/validation/manifest.json).
It is signed by a disposable sample key whose private half is not retained.
The signature demonstrates the artifact format and verification flow; it does
not represent an organizational production attestation.

## Known limits

- LOBSTER visible depth does not expose participant identity or full queue
  priority.
- Price-level conservation can be proven only where the affected price is
  visible in consecutive supplied snapshots.
- Statistical power depends on the number of replay ticks outside the attack
  window. Exact book-hash equality remains mandatory even for small fixtures.
- A genuine market reaction caused by an executed injected order may require a
  wider, explicitly approved causal-neighbourhood policy. The current report
  uses the synthetic ground-truth window and fails if effects persist beyond
  it.
