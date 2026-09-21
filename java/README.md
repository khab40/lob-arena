# Java Candidate Kernel

This Gradle build contains the authoritative Java 25 kernel and live arena.
The migration in [ARD-0019](../docs/architecture/ARD-0019-python-reference-java-kernel-migration.md)
and live cutover in [ARD-0020](../docs/architecture/ARD-0020-java-arena-websocket-agent-orchestration.md) are complete; Python runtime fallback is retired.

Modules:

- `exchange-proto` generates Java types directly from `contracts/proto` and reads the shared golden corpus in tests;
- `simulation-kernel` is the framework-free deterministic hot-loop boundary;
- `kernel-benchmarks` owns JMH diagnostics and portable regression gates without adding benchmark libraries to the kernel;
- `kernel-grpc` exposes the candidate kernel through the shared generated gRPC service without adding transport concerns to the hot loop;
- `control-plane` is the separate Spring Boot API boundary and may depend on the kernel, never the reverse.

The kernel currently includes the frozen Java 25 implementations of event ordering, fixed-point conversion, half-even metric quantization, SplitMix64 and named streams, simulation identifiers, canonical event/book bytes, SHA-256 digests, and the rolling event-stream hash.

It also includes the integer-tick/lot order book and matching engine described in [Java Integer Order Book](../docs/runtime/java-order-book.md).

The complete candidate tick runner, normal agents, scenarios, baseline phase, and metric calculation are described in [Java Simulation Kernel](../docs/runtime/java-simulation-kernel.md).

The cross-language service and failure contract are described in [gRPC Kernel Boundary](../docs/runtime/grpc-kernel-boundary.md).

On macOS or Linux, run:

```bash
./gradlew clean check
```

SDKMAN users can pin the repo JDK with the checked-in `.sdkmanrc`:

```bash
sdk env
```

Start the candidate gRPC server for offline shadow replay with:

```bash
./gradlew :kernel-grpc:run --args=50051
```

Start the Spring control plane with the project SDKMAN pin and Java 25 runtime check:

```bash
../scripts/run-java-control-plane.sh --server.port=8081
```

See [Kernel Shadow Mode](../docs/runtime/history/kernel-shadow-mode.md) for the Python replay command and live-mirroring guarantees.

Run forked kernel and matching diagnostics with `./gradlew :kernel-benchmarks:run --args='KernelBenchmarks -prof gc'`; see [Java Kernel Performance](../docs/runtime/java-kernel-performance.md) for gate policy and interpretation.

The Spring control plane exposes Prometheus and opt-in OpenTelemetry around the candidate gRPC boundary. See [Kernel Observability](../docs/runtime/kernel-observability.md) for bounded meters, OTLP settings, and the Grafana template.

The versioned kernel API is now Java-default in Compose. The multi-stage `java/Dockerfile` produces a non-root Java 25 runtime image while permanent CI and sampled runtime replay retain Python as the executable reference; see [Java Kernel Default Cutover](../docs/runtime/history/java-kernel-cutover.md).

The checksum-pinned wrapper owns Gradle 9.6.1. The Foojay resolver auto-provisions a Java 25 toolchain when one is not installed, so a developer-global Gradle or Java 25 installation is not required. Generated Protobuf Java sources stay under `build/` and are not committed.
