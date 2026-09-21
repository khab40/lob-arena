# Java Kernel Performance

The `kernel-benchmarks` module separates diagnostic measurement from portable regression gates. It uses [OpenJDK JMH](https://openjdk.org/projects/code-tools/jmh/) 1.37 for forked JVM benchmarks and Java thread-allocation accounting for broad CI smoke ceilings.

## JMH Benchmarks

`KernelBenchmarks` measures:

- complete deterministic simulation runs for the normal-market, quote-stuffing, and liquidity-evaporation golden requests;
- one crossing market order against a freshly prepared 12-level integer order book.

Run the configured warmup and measurement suite on macOS or Linux:

```bash
cd java
./gradlew :kernel-benchmarks:run --args='KernelBenchmarks -prof gc'
```

Use filters and shorter iterations for a development sanity check:

```bash
./gradlew :kernel-benchmarks:run \
  --args='KernelBenchmarks.runSimulation -p caseId=normal-market-seed-42 -wi 1 -i 1 -w 500ms -r 500ms -f 1 -bm avgt -tu us -prof gc'
```

JMH execution is not part of ordinary `check`: benchmark timings depend on CPU, power state, background load, JVM warmup, and profiler choice.

## Portable Regression Gates

`KernelPerformanceGateTest` runs during the normal Gradle `check` lifecycle. It checks the largest golden simulation and a complete crossing-match setup against deliberately broad ceilings:

| Path | p99 ceiling | Throughput floor | Allocation ceiling |
| --- | ---: | ---: | ---: |
| 10-tick liquidity-evaporation simulation | 1 second/run | 5 runs/second | 32 MiB/run |
| Fresh 12-level book plus crossing match | 50 ms/match | 100 matches/second | 1 MiB/match |

These are portability gates, not performance objectives. They catch order-of-magnitude regressions, runaway allocation, or accidentally blocking code without making CI depend on workstation-class timing. Tightening a gate requires repeated measurements on the CI runner and an ARD update.

The gate also verifies the largest scenario's event count and canonical stream hash on every measured run, so a faster but behaviorally different implementation cannot pass.

## Step 14 Local Sanity Baseline

A short single-fork, single-measurement run on the current macOS/aarch64 Java 25 environment reported:

| Benchmark | Average time | Normalized allocation |
| --- | ---: | ---: |
| Normal-market golden simulation | 327.707 µs/run | 763,830.948 B/run |
| Crossing market order | 0.226 µs/op | 22,536.067 B/op |

These readings only prove that benchmark generation, forking, execution, and GC allocation profiling work end to end. They are not a publishable baseline and are not used as CI thresholds. Full measurements require the default multi-iteration configuration, controlled hardware, saved raw output, and comparison against the same environment.

No Agrona or alternative data structure is introduced by this step. The allocation profile establishes evidence for later targeted optimization.

## Long-running Control-plane Memory Budget

The Compose Java service uses an explicit 4 GiB container limit rather than
deriving its heap from all Docker Desktop memory:

| Consumer | Default budget |
| --- | ---: |
| Java heap | 2 GiB |
| Java direct buffers | 256 MiB |
| Embedded DuckDB | 1 GiB |
| Metaspace, threads, native libraries, and headroom | approximately 768 MiB |

DuckDB uses two threads, spills to the disk-backed
`/tmp/lob-arena-duckdb` directory, and may use at most 8 GiB of spill space.
Normalized event and book files must be physically aligned and ordered by
`source_sequence`; replay reads them in 4,096-row JDBC result pages so the
driver cannot materialize a complete session in native memory. The final page
closes its result set, statement, and connection immediately at EOF.
The effective application limits are available from
`GET /api/arena/runtime-limits`.

The live matching engine retains 50,000 canonical events. Complete event
history is written to stream-scoped JSONL segments under
`outputs/history/exchange-events/`; cursor replay transparently reads older
events from those segments. A reset creates a new stream instead of deleting
completed stream history.

Relevant overrides are:

```text
JAVA_KERNEL_MEMORY_LIMIT
JAVA_KERNEL_JAVA_TOOL_OPTIONS
LOB_ARENA_EVENT_HISTORY_CAPACITY
LOB_ARENA_EVENT_ARCHIVE_SEGMENT_EVENTS
LOB_ARENA_EVENT_ARCHIVE_MAX_STREAM_BYTES
LOB_ARENA_DUCKDB_MEMORY_LIMIT
LOB_ARENA_DUCKDB_THREADS
LOB_ARENA_DUCKDB_TEMP_DIRECTORY
LOB_ARENA_DUCKDB_MAX_TEMP_DIRECTORY_SIZE
```

Raise the heap, DuckDB memory, or archive quota only with corresponding
container-memory and disk-capacity changes. Large full-session datasets can
produce tens of millions of canonical mutations; insufficient archive
capacity produces a `422 archive_capacity_insufficient` response rather than
an OOM kill.
