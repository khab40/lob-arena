# Golden Parity Corpus V1

The version 1 golden corpus is the immutable, byte-exact compatibility oracle for the Java kernel. It lives in `contracts/golden/parity-v1` and contains deterministic Protobuf request/result pairs plus a checksum manifest.

## Coverage

The corpus includes normal market, empty book, spoofing-like wall, layering-like, quote-stuffing, and liquidity-evaporation runs. Together they cover add, modify, cancel, execute, and L2 snapshot payloads, multiple seeds, absent optional book fields, hashes, and quantized metrics.

Each manifest entry records raw request/result SHA-256 checksums, canonical stream and book hashes, event-type counts, and metric count. Consumers parse the `.pb` files with `lob.exchange.v1`, while canonical event and book identity continues to use the explicit hashing contract rather than raw Protobuf bytes.

## Verification

Start the Java gRPC service, then replay every immutable case:

```bash
uv run --project backend python scripts/run_java_golden_corpus.py --target 127.0.0.1:50051
```

The Python command is a gRPC verification client, not a Python kernel implementation. The Java Gradle tests also consume the same request and expected-result files directly.

## Maintenance Policy

Version 1 files are immutable evidence. A behavioral or schema change that intentionally changes these bytes must create `parity-vN` and document the compatibility decision in an ARD. Correcting a proven fixture defect also requires an explicit ARD amendment. The retired Python generator must not be recreated merely to mutate version 1 fixtures.
