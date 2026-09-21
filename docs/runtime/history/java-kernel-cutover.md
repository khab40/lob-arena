# Java Kernel Cut-over

Java 25 is the sole implementation and runtime authority for the versioned `SimulationRequest`/`SimulationResult` kernel.

## Runtime Boundary

- `POST /api/kernel/run` accepts `application/x-protobuf` or `application/octet-stream` and returns `application/x-protobuf`.
- `GET /api/kernel/status` reports the Java implementation and contract version.
- gRPC `SimulationKernel.RunSimulation` remains available on port 50051 for service integration and verification.
- The frontend Nginx service sends same-origin `/api/kernel/` requests directly to the Java control plane.
- The Python backend does not proxy, replay, shadow, or fall back for kernel requests.

ARD-0020 subsequently moved the interactive arena, scenarios, deterministic detectors/incidents, persistence, WebSocket delivery, and agent orchestration to Java. FastAPI now retains AI/ML, experiments, evidence, Nebius integration, and serverless jobs.

## Deployment

Compose runs Java kernel, Python backend, agent runner, and frontend. The Java service exposes HTTP/Actuator on host port 8081 and gRPC on 50051. The frontend reaches Java through the Compose service name; the Python backend no longer depends on Java startup.

The Java image remains a multi-stage, non-root Java 25 image. Its runtime contains the application JAR and Java runtime, not Gradle, the build JDK, tests, documentation, outputs, credentials, or platform-specific launchers.

## Compatibility And Rollback

The immutable `contracts/golden/parity-v1` corpus is the compatibility oracle. CI starts the production Spring Boot JAR and requires exact Java output bytes for every case. Intentional deterministic changes require a new versioned corpus and an ARD update.

There is no Python kernel fallback. Operational rollback deploys the previous verified Java image or release.
