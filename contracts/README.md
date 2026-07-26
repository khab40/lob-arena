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

The schema exposes the unary `SimulationKernel.RunSimulation` process boundary implemented by the Java kernel. See [gRPC Kernel Boundary](../docs/grpc-kernel-boundary.md).

`golden/parity-v1` contains immutable deterministic Protobuf request/result pairs. Replay them against Java with `scripts/run_java_golden_corpus.py`; see [Golden Parity Corpus V1](../docs/golden-parity-corpus-v1.md) for coverage and versioning rules.

The governed ML workflow adds fail-closed JSON contracts for:

- `governed-benchmark-protocol-v1.schema.json`;
- `governed-corpus-v1.schema.json`;
- `clean-window-adjudication-v1.schema.json`;
- `governed-clean-window-equivalence-v1.schema.json`;
- `feature-labels-v2.schema.json`;
- `split-manifest-v1.schema.json`;
- `canonical-java-replay-bundle-v1.schema.json`;
- `feature-streaming-validation-v1.schema.json`;
- `governed-regime-evidence-v1.schema.json`; and
- `benchmark-results-v2.schema.json`.

These schemas bind corpus provenance, independent clean reviews, frozen
session-level splits, canonical Java replay inputs, and signed benchmark
results before any learned-model training.

Run `make check-governed-contracts` to detect drift between generated JSON
contracts and their fail-closed runtime models.
