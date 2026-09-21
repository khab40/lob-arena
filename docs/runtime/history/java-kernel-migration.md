# Java Kernel Migration

LOB Arena migrated its versioned deterministic exchange kernel from Python to Java 25 through differential parity. Java now owns the kernel, its public HTTP endpoint, and gRPC service; the duplicate Python kernel and runtime rollout machinery have been retired.

## Frozen Migration Boundary

The first Java authority boundary contains only deterministic hot-loop components:

| Component | Initial authority | Migration condition |
| --- | --- | --- |
| Canonical event contract | Protobuf shared by both languages | Python and Java round-trip the same versioned messages |
| Simulation clock and scheduler | Python reference | Java passes ordering and timing vectors |
| PRNG streams | Python reference | Bit-exact Java/Python vectors pass |
| Order book and matching | Python reference | Events, trades, remainders, priority, and snapshots match |
| Scenario execution | Python reference | Complete scenario event hashes match |
| Market features and deterministic detectors | Python | Move only after kernel parity; metrics must match |
| Live REST, WebSocket, persistence, and orchestration | Java/Spring | Migrated after kernel cut-over under ARD-0020 |
| Frontend | React/TypeScript | No migration planned |
| Java control plane | None initially | Spring Boot is introduced after the plain Java kernel boundary is stable |

Spring objects, dependency injection, HTTP concerns, persistence clients, telemetry exporters, and message brokers must not enter the kernel hot loop.

## Historical Authority Modes

- `python`: Python is authoritative and Java is not invoked.
- `shadow`: both kernels receive an identical Protobuf request; Python publishes results and Java produces a parity report only.
- `java`: Java publishes results, with sampled Python replay retained for rollback and regression detection.

These modes governed migration only. They no longer exist in runtime configuration; Java is the sole kernel authority.

## Completion Gates

Java kernel authority requires all of the following:

1. The Protobuf schema is versioned and compatibility-tested.
2. Numeric units, event ordering, identifiers, PRNG streams, rounding, and hashes are language-neutral specifications.
3. Python is wrapped as a Protobuf reference runner without behavioral drift.
4. The golden corpus covers every exchange event and active scenario.
5. Java passes exact event, trade, snapshot, final-book, and hash parity.
6. Quantized detector inputs and metrics match the frozen tolerance policy.
7. Shadow mode reports no unexplained divergence for the agreed run/seed corpus.
8. Java meets the agreed latency, throughput, allocation, and resource limits.
9. Metrics, traces, health, parity failures, and rollback controls are operational.
10. Permanent CI replay validates Java against an immutable, versioned golden corpus.

## Toolchain Policy

- Target Java version: 25.
- The repository owns a Gradle wrapper and Java toolchain declaration; developer-global Gradle is not required.
- Protobuf and gRPC generation is owned by the build; developer-global `protoc` is not required.
- CI verifies generated-source freshness and builds with the declared Java toolchain.
- A Java 21-only development machine can launch the repository wrapper, which auto-provisions the declared Java 25 compile/test toolchain; no global Gradle or `protoc` is required.

## Explicit Non-Goals During Parity

- No full FastAPI-to-Spring rewrite before kernel parity.
- No Kafka for an individual simulation's internal event queue.
- No Chronicle Queue without a measured durable-journal requirement.
- No Agrona adoption without profiling evidence.
- No ClickHouse or Parquet migration as part of kernel correctness work.
- No removal of the Python reference implementation during the stability period; it was retired only after the final cut-over.

## Implementation Sequence

| Step | Status | Deliverable |
| --- | --- | --- |
| 1 | Done | Scope, authority boundary, gates, toolchain policy, and rollback rules |
| 2 | Done | `lob.exchange.v1` Protobuf messages, checked-in Python bindings, freshness validation, and round-trip tests |
| 3 | Done | Fixed-point units, total ordering, SplitMix64 streams, identifiers, rounding, semantics, and executable vectors |
| 4 | Done | Explicit canonical event/book bytes, SHA-256 digests, stream hash chain, and golden vectors |
| 5 | Done | Authoritative Python Protobuf runner with exact event/book conversion, hashes, and quantized metrics |
| 6 | Done | Immutable deterministic Protobuf parity corpus covering all scenarios, event types, empty-book optionals, checksums, and canonical hashes |
| 7 | Done | Repository-owned Gradle 9.6.1 wrapper, Java 25 toolchains, generated shared Protobuf module, framework-free kernel module, Spring Boot control plane, and CI |
| 8 | Done | Java total ordering, fixed-point/metric rules, SplitMix64 named streams, identifiers, canonical encodings, and SHA-256 event/book/stream hashes with exact golden parity |
| 9 | Done | Integer tick/lot order book, best-price/FIFO matching, modify/cancel rules, executions, owner aggregation, and deterministic Protobuf snapshots/events |
| 10 | Done | Java Protobuf simulation runner with logical clock, ordered normal agents, all active scenarios, baseline repair, per-tick snapshots, deterministic features/detectors, limits, and exact golden outputs |
| 11 | Done | Shared unary gRPC contract, generated Python/Java stubs, Python reference adapter, Java candidate adapter, error mapping, and exact in-process golden-result test |
| 12 | Done | Immutable dual-runner execution, structured event/execution/snapshot/book/hash/metric/termination comparison, first-divergence localization, and full-corpus/mutation tests |
| 13 | Done | Runnable Java gRPC server, deadline-bound Python client, offline corpus replay, bounded live background mirroring, Python-authority failure isolation, and real six-case socket verification |
| 14 | Done | JMH simulation/matching benchmarks, GC allocation profiling, portable p99/throughput/allocation smoke ceilings, and correctness checks inside measured kernel runs |
| 15 | Done | Failure-isolated gRPC metrics/spans, Prometheus actuator, opt-in OpenTelemetry/OTLP, bounded Python shadow metrics, scrape template, and Grafana dashboard |
| 16 | Done | Protobuf kernel API, explicit python/shadow/java router, deterministic percentage cohorts, sampled Python replay, mismatch/error fallback, fail-closed option, persisted decisions, and rollback settings |
| 17 | Done | Java-default Protobuf kernel API, four-service Compose deployment, non-root Java 25 image, 10% runtime Python replay, fallback/rollback, and permanent 100% real-gRPC corpus replay in CI |
| 18 | Done | Java-only Protobuf HTTP/gRPC kernel, retired Python runtime duplicate and rollout paths, immutable Java golden replay, frontend Nginx routing, and documented retained Python ownership |

## Related Documentation

- [ARD-0018: Canonical Exchange Event Stream](architecture/ARD-0018-canonical-exchange-event-stream.md)
- [ARD-0019: Python Reference And Java Kernel Migration](architecture/ARD-0019-python-reference-java-kernel-migration.md)
- [High-Level Architecture](architecture.md)
- [Runtime Model](runtime-model.md)
- [Determinism Contract V1](determinism-contract-v1.md)
- [Canonical Hashing V1](canonical-hashing-v1.md)
- [Golden Parity Corpus V1](golden-parity-corpus-v1.md)
- [Java Integer Order Book](java-order-book.md)
- [Java Simulation Kernel](java-simulation-kernel.md)
- [gRPC Kernel Boundary](grpc-kernel-boundary.md)
- [Differential Parity Harness](differential-parity-harness.md)
- [Kernel Shadow Mode](kernel-shadow-mode.md)
- [Java Kernel Performance](java-kernel-performance.md)
- [Kernel Observability](kernel-observability.md)
- [Kernel Authority Rollout](kernel-authority-rollout.md)
- [Java Kernel Default Cutover](java-kernel-cutover.md)
