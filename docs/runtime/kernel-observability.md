# Kernel Observability

Kernel observability is implemented around the Java HTTP/gRPC control plane, not inside the deterministic hot loop. Metric and trace failures are isolated from kernel results.

## Java Control Plane

Spring Boot Actuator exposes health, diagnostic metrics, and Prometheus scrape endpoints. The gRPC server can be started as a control-plane-managed boundary:

```bash
LOB_KERNEL_GRPC_ENABLED=true ./gradlew :control-plane:bootRun
```

Relevant endpoints are:

- `/actuator/health`;
- `/actuator/metrics`;
- `/actuator/prometheus`.

The gRPC instrumentation emits:

| Meter | Type | Labels |
| --- | --- | --- |
| `lob.kernel.grpc.requests` | counter | `outcome=completed|invalid_argument|internal_error` |
| `lob.kernel.grpc.duration` | histogram timer | bounded `outcome` |
| `lob.kernel.grpc.events` | distribution summary | none |

Run ids, scenario ids, symbols, event ids, and exception messages are deliberately excluded from labels. They belong in trace/log details, not time-series dimensions.

Each call also creates a `lob.kernel.grpc` Micrometer observation. Spring Boot bridges it to OpenTelemetry, adding bounded `contract.version` and `outcome` attributes. OTLP export is opt-in:

```bash
LOB_KERNEL_OTLP_ENABLED=true \
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://otel-collector:4318/v1/traces \
LOB_KERNEL_TRACE_SAMPLE_PROBABILITY=0.1 \
./gradlew :control-plane:bootRun
```

Trace export uses Spring Boot's `management.tracing.export.otlp.enabled` gate and defaults to disabled. OTLP metric push is separately controlled by `LOB_KERNEL_OTLP_METRICS_ENABLED`; it is off by default because Prometheus scraping is the primary metric path. Local tests and control-plane startup never require a collector.

## Local Prometheus And Grafana

Prometheus and Grafana have separate, complementary roles:

- **Prometheus** is the collector and time-series store. It pulls metrics from
  the application services every 15 seconds and provides raw target health and
  PromQL inspection.
- **Grafana** is the visualization layer. It does not scrape the application
  services directly; it queries the provisioned Prometheus datasource and
  renders the project dashboards.

Start Prometheus without Grafana when raw metrics are enough:

```bash
docker compose --profile prometheus up --build
```

Start the full dashboard stack (Prometheus plus Grafana) with:

```bash
docker compose --profile grafana up --build
```

The older `monitoring` profile is retained as an alias for the full stack:

```bash
docker compose --profile monitoring up --build
```

Open:

- Grafana: http://localhost:3000
- Prometheus: http://localhost:9090

Grafana is provisioned automatically with the Prometheus datasource and five dashboards:

- `LOB Arena E2E Overview`
- `LOB Arena Java Kernel`
- `LOB Arena Components`
- `LOB Arena Bottlenecks`
- `LOB Arena Detector Tournaments`

The profile scrapes:

| Job | Target | Purpose |
| --- | --- | --- |
| `lob-arena-java-kernel` | `java-kernel:8080/actuator/prometheus` | Java HTTP, JVM, GC, and kernel metrics |
| `lob-arena-python-control-plane` | `backend:8000/metrics` | arena state and FastAPI-to-Java proxy metrics |
| `lob-arena-agent-runner` | `agent-runner:9100/metrics` | decision latency, request outcomes, agent mix, and intent output |
| `prometheus` | `prometheus:9090/metrics` | scrape health and Prometheus self-observation |

This is operational telemetry: service availability, throughput, latency,
resource pressure, arena state, and agent-runner behavior. Detector-tournament
precision, recall, F1, false-positive counts, and evidence manifests remain
benchmark artifacts and are not ingested into Prometheus.

### Detector Tournament Telemetry

Detector tournaments use the operational model, but their short-lived local
processes and remote Nebius Jobs are not scrape targets. FastAPI is
the stable bridge: it launches or submits the work, observes status transitions,
and collects artifacts, so its `/metrics` endpoint exposes bounded counters,
gauges, and duration histograms for local, local-mock, and Nebius execution.

The provisioned Grafana `LOB Arena Detector Tournaments` view answers:

- how many tournaments complete or fail by execution mode;
- how long local and Nebius runs take;
- how many tournaments are queued or running;
- how many scenarios complete over time;
- whether Nebius artifact collection succeeds.

No metric label will contain a tournament ID, Nebius Job ID, random seed,
scenario ID, or artifact path. Detailed quality results remain in CSV/JSON
artifacts and benchmark reports. See the
[architecture overview](architecture.md#detector-tournament-observability)
for the metric families and data flow.

Use the bottleneck dashboard first when the arena slows down. If agent decision p95 rises before Java HTTP/kernel latency, the runner is likely saturated. If backend-to-Java latency rises while Java HTTP latency stays flat, the proxy path or network is suspect. If Java heap/GC and Java HTTP latency rise together, inspect Java allocation and scenario load.

The retired Python shadow/authority metrics are intentionally absent. Compatibility drift is a CI failure from exact golden-corpus replay, while production Java health, request outcomes, latency, and event counts remain available through Actuator and Prometheus.

## Prometheus and Grafana Templates

- `monitoring/prometheus/java-kernel.yml` scrapes the Java actuator and existing Python metric endpoints.
- `monitoring/grafana/dashboards/java-kernel.json` provides Java request rate, p95/p99 RPC latency, allocation rate, and canonical event-rate panels. Historical shadow panels may be removed from deployed dashboards.
- `monitoring/grafana/dashboards/lob-arena-detector-tournaments.json` provides tournament outcomes, p95 duration, scenario throughput, in-flight work, and Nebius artifact-collection panels.

These files are mounted by the opt-in Compose services. Starting a Prometheus,
Grafana, or legacy `monitoring` profile adds the corresponding containers and
persistent local volumes; the default Compose path adds neither. Adjust scrape
targets when deployment service names differ.

Recommended alerts are:

- Java error-rate increases;
- failed golden-corpus replay in CI;
- p99 latency above the rollout SLO;
- absence of Java scrape data while the kernel service is deployed.

Grafana is a visualization consumer, never a kernel dependency. Prometheus scraping and OTLP exporting remain outside simulation execution.

## Related Documentation

- [README observability overview](../README.md#role-of-prometheus-and-grafana)
- [Quick Start](QUICKSTART.md)
- [ARD-0021: Local Observability With Prometheus And Grafana](architecture/ARD-0021-local-observability-grafana.md)
