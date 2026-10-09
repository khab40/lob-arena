# Shared Contracts

`proto/lob/exchange/v1/exchange.proto` is the language-neutral deterministic simulation boundary implemented by the authoritative Java kernel. Checked-in Python bindings support contract tooling and external Python ML/AI integration; they are not a second runtime kernel.

Generate the checked-in Python bindings with:

```bash
uv run --project backend python scripts/generate_protos.py
```

Verify that checked-in bindings match the source schema with:

```bash
uv run --project backend python scripts/generate_protos.py --check
```

Compatibility rules:

- never reuse a field number;
- reserve deleted field numbers and names;
- add fields rather than changing existing field meaning;
- version incompatible contracts in a new Protobuf package;
- do not treat raw Protobuf serialization as the canonical event hash encoding;
- do not add maps to messages used by deterministic hashing.

The repository Gradle build generates Java messages and gRPC service stubs under `build/`. The Python generator checks in both message and gRPC bindings so backend packaging does not require `protoc`.

The schema exposes the unary `SimulationKernel.RunSimulation` process boundary implemented by the Java kernel. See [gRPC Kernel Boundary](../docs/runtime/grpc-kernel-boundary.md).

`golden/parity-v1` contains immutable deterministic Protobuf request/result pairs. Replay them against Java with `scripts/run_java_golden_corpus.py`; see [Golden Parity Corpus V1](../docs/runtime/golden-parity-corpus-v1.md) for coverage and versioning rules.

The governed ML workflow adds fail-closed JSON contracts for:

- `governed-benchmark-protocol-v1.schema.json`;
- `governed-corpus-v1.schema.json`;
- `clean-window-adjudication-v1.schema.json`;
- `governed-clean-window-equivalence-v1.schema.json`;
- `feature-labels-v2.schema.json`;
- `split-manifest-v1.schema.json`;
- `canonical-java-replay-bundle-v1.schema.json`;
- `feature-streaming-validation-v1.schema.json`;
- `governed-regime-evidence-v1.schema.json`;
- `governed-feature-release-v1.schema.json`;
- `benchmark-results-v2.schema.json`;
- `lightgbm-training-run-v1.schema.json`;
- `lightgbm-model-bundle-v1.schema.json`;
- `lightgbm-cloud-job-v1.schema.json`;
- `lightgbm-cloud-run-v1.schema.json`;
- `model-calibration-v1.schema.json`; and
- `detector-predictions-v1.schema.json`.

These schemas bind corpus provenance, independent clean reviews, frozen
session-level splits, canonical Java replay inputs, and signed benchmark
results before any learned-model training. The LightGBM Phase 0 schemas also
bind stable model/training identities, feature and split hashes, validation-only
calibration, frozen operating thresholds, prediction outputs, and the
checksummed model artifact inventory used by the implemented trainer and scorer.
The cloud Job/run contracts bind the execution request and retained run evidence.
See [ARD-0031](../docs/architecture/ARD-0031-complete-lightgbm-v1.md) for completed
implementation and its separate qualification boundary. Runtime
verification additionally checks normalized artifact paths, exact bytes,
sizes, SHA-256 values, canonical manifest contents, schema compatibility, and
the complete checksum inventory.

Run `make check-governed-contracts` to detect drift between generated JSON
contracts and their fail-closed runtime models.

## Artifact inventory

The table retains the originally named artifact paths and their purposes across
legacy/demo and governed workflows; it is not one current publication allowlist.
[ARD-0004](../docs/architecture/ARD-0004-benchmark-artifact-format.md) owns the
legacy benchmark format. [ARD-0026](../docs/architecture/ARD-0026-governed-lightgbm-release-boundary.md),
[ARD-0031](../docs/architecture/ARD-0031-complete-lightgbm-v1.md) and the versioned
schemas above own governed release compatibility and exact checksum inventories.

| Artifact | Purpose |
| --- | --- |
| `events.jsonl` | Append-only stream of simulation events, agent actions, detector signals, and state changes. |
| `history/exchange_events.jsonl` | Canonical add/modify/cancel/execute/snapshot archive, segmented by stream ID for replay. |
| `history/lob_snapshots.jsonl` | Snapshot-only canonical checkpoints for efficient L2 state scans. |
| `data/processed/lobster/<dataset_id>/` | Immutable normalized LOBSTER events, aligned visible-depth snapshots, and registry manifest. |
| `historical-replay/<run>/control.json` / `hybrid.json` | Historical-only and hybrid summaries over the same source window, including source/canonical counts and stream hashes. |
| `historical-replay/<run>/comparison.json` | Detector TP/FN/FP/TN, precision, recall, F1, alert timing, and final-book realism deltas. |
| `historical-replay/<run>/validation-report.json` / `.sig` | Causal-neighbourhood equivalence, lifecycle, provenance, determinism, and detached Ed25519 attestation. |
| `historical-replay/<run>/manifest.json` / `checksums.sha256` | Replay comparison inventory and full-bundle integrity checks. |
| `features/<run>/features.parquet` | Stable typed causal feature rows consumed by the governed LightGBM v1 loader and trainer. |
| `features/<run>/run-metadata.json` / `feature-quality.json` | Feature/config/input hashes, source/session metadata, split policy, missing/distribution/class-balance summaries, and invalid rows. |
| LightGBM Phase 0 manifests | Strict training, calibration, model-bundle, and prediction contracts binding governed inputs, frozen operating points, checksums, and release identity. |
| `experiments/<experiment_id>/experiment.json` | Phase 4.5 experiment manifest with requested scenarios, execution mode, status, artifact paths, optional smart-batch link, and metrics. |
| `experiments/<experiment_id>/attacks.jsonl` | Deterministic attack plan rows with expected labels, detector family, timing, agent profile, and parameters for each planned run. |
| `experiments/<experiment_id>/jobs.jsonl` | Experiment-scoped local and Nebius Job records, including queued, running, completed, failed, and explicitly unconfigured states. |
| `experiments/<experiment_id>/local-batch/` | Local smart-batch outputs for the experiment, including order-book events, trades, labels, alerts, metrics, report, and batch manifest. |
| `experiments/<experiment_id>/artifact_index.json` | Index mapping original local-batch artifact names to canonical experiment-root artifact names. |
| `experiments/<experiment_id>/investigations/` | Per-alert AI Investigator reports as JSON and Markdown, generated from persisted top-confidence batch alerts. |
| `experiments/<experiment_id>/experiment_summary.json` / `leaderboard.json` | Aggregated experiment totals and scenario leaderboard sourced from detector metrics, labels, alerts, and investigations. |
| `experiments/<experiment_id>/benchmark_report.md` | Human-readable synthetic educational benchmark report shown in Reports after aggregation. |
| `snapshots.parquet` | Structured order book and market snapshots optimized for offline analysis. |
| `incidents.json` | Detected incidents with metadata, timestamps, involved agents, scenario labels, and detector evidence. |
| `reports.md` | Human-readable AI Investigator explanations, incident summaries, and benchmark reports. |

The legacy `history/exchange_events.jsonl` / `history/lob_snapshots.jsonl` names
belong to the retained Python implementation record. Current Java cursor replay
uses `history/exchange-events/<stream_id>/segment-*.jsonl`; see the
[durable stream contract](../docs/runtime/exchange-event-stream.md#durable-streams).
The current signed hybrid comparison inventory uses `manifest.sig`,
`validation-public-key.pem` and `signature.json`; see
[ARD-0023](../docs/architecture/ARD-0023-hybrid-historical-replay.md#evaluation-and-artifacts).
Actual filenames and allowed members are taken from each run or release manifest.
