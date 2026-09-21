# Differential Parity Harness

The Python/Java differential harness was a migration tool used to establish parity before cut-over. It compared contract identity, ordered events, executions, snapshots, final books, hashes, metrics, and termination, and localized the first divergent sequence.

After Java became the sole kernel implementation, the executable Python reference and differential harness were removed. Permanent regression protection now uses the immutable versioned golden corpus:

```bash
uv run --project backend python scripts/run_java_golden_corpus.py --target 127.0.0.1:50051
```

This client compares the Java result bytes with checked-in expected bytes. Intentional behavioral changes require a new corpus version and ARD decision.
