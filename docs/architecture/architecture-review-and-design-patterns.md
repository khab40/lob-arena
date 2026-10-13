# LOB Arena architecture review and design patterns

Review date: 2026-10-13. Source snapshot: `main` at
`4a710e0016110c3d0c22549d04684369b9311b00`.
Documentation owner: [Story #58](https://github.com/khab40/lob-arena/issues/58)
in [Project #3](https://github.com/users/khab40/projects/3); this is maintenance
of its delivered documentation, without reopening its historical acceptance.

This review explains patterns visible in the implementation and the engineering
reason for using each at that boundary. Rationale follows the code and existing
architecture records; it does not reconstruct undocumented personal intent.
The [canonical overview](../architecture.md) owns system responsibilities, and
the [ARD index](README.md) owns decision history. No new design is adopted here.

## Architecture assessment

The strongest architectural choice is separating deterministic market execution
from AI/ML workflows. It makes replay, agent decisions and detector evidence
inspectable without depending on an AI endpoint's availability.

- **Java execution and control plane:** the framework-free simulation kernel
  owns matching; the Spring live arena owns interactive ticks, scenarios,
  deterministic rules, incidents, REST and WebSocket delivery. It is the sole
  live-book writer. See [ARD-0019](ARD-0019-python-reference-java-kernel-migration.md)
  and [ARD-0020](ARD-0020-java-arena-websocket-agent-orchestration.md).
- **Python AI/data plane:** FastAPI composes ingestion, experiments, Nebius
  integration and evidence services. Its live-arena compatibility APIs delegate
  through `JavaArenaClient`; retained Python simulation/scenario code serves
  offline, comparison and test paths, rather than a second live-book authority.
- **React presentation:** arena widgets consume a common source hook; explicit
  demo/mock modes and Java WebSocket mode reuse the same screen. Rendering does
  not mutate the exchange directly.
- **Offline ML and governance:** canonical events become causal features before
  separate labels are joined. Release manifests, checksums and independent
  readback bind results to their inputs. MLflow indexes permitted evidence; it
  does not approve release or promotion.

The explicit transport contracts and event/artifact lineage are strong foundations.
The main pressure points are concentrated control-plane responsibilities,
serialized tick latency and recovery/transport visibility. These are tradeoffs
and follow-up opportunities, rather than evidence of a failed runtime.

## Software design patterns

These names describe specific implementations, not a claim that the entire
repository follows one uniform object-oriented architecture.

| Pattern | Where it is used | Why it is used there |
| --- | --- | --- |
| **Adapter / Ports and Adapters** | Java [`AgentRunnerClient`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/AgentRunnerClient.java) and [`HttpAgentRunnerClient`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/HttpAgentRunnerClient.java); Python [`JavaArenaClient`](../../backend/app/arena/java_client.py). | Translate HTTP responses into application-facing contracts so orchestration and Python compatibility routes can use external services without owning their transport or live exchange. These are selected boundaries, not repository-wide hexagonal architecture. |
| **Facade** | React [`useArenaSource`](../../frontend/src/hooks/useArenaSource.ts), consumed by [`ArenaPage`](../../frontend/src/pages/ArenaPage.tsx). | Give the screen one state/control interface over demo, mock and WebSocket sources, keeping transport and mode selection out of individual widgets. Selection is conditional inside the hook, rather than a hierarchy of Strategy objects. |
| **Strategy** | Retained Python [`RuntimeAgent.decide`](../../backend/app/agents/runtime.py) and its market-maker, noise, taker and heavy/remote implementations. | Vary how an agent decides while the manager retains common collection, deadlines and deterministic intent ordering. This example belongs to the retained Python runtime, not Java live-arena ownership. |
| **Template Method** | Retained Python [`ScenarioBase.apply`](../../backend/app/scenarios/base.py), with `on_stage_enter` and `on_tick` hooks implemented by [`SpoofingLikeScenario`](../../backend/app/scenarios/spoofing_like.py) and peers. | Share lifecycle bookkeeping and one-time stage entry while each scenario supplies its market actions, avoiding copied transition and evidence logic. Subclasses depend on the base lifecycle contract. |
| **Observer / callbacks** | [`IntegerOrderBook`](../../java/simulation-kernel/src/main/java/ai/lobarena/kernel/book/IntegerOrderBook.java) emits `BookMutation`; [`IntegerMatchingEngine`](../../java/simulation-kernel/src/main/java/ai/lobarena/kernel/book/IntegerMatchingEngine.java) records mutations and forwards events to an injected sink. | Capture canonical evidence where book mutations occur without coupling the book to JSONL storage or browser delivery. This is a synchronous callback chain, not a broker-based event bus. |
| **Decorator** | [`ArenaWebSocketHandler.afterConnectionEstablished`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/ArenaWebSocketHandler.java) wraps sessions in Spring's `ConcurrentWebSocketSessionDecorator`. | Add concurrent-send and buffer protection while preserving the WebSocket session interface used by the handler. The implementation uses a framework decorator rather than a custom hierarchy. |
| **Null Object** | [`KernelGrpcTelemetry.noop`](../../java/kernel-grpc/src/main/java/ai/lobarena/grpc/KernelGrpcTelemetry.java), used by [`JavaKernelGrpcService`](../../java/kernel-grpc/src/main/java/ai/lobarena/grpc/JavaKernelGrpcService.java). | Keep telemetry optional without scattering null checks through execution; telemetry failures are isolated from RPC results. Independent monitoring is still needed to notice missing telemetry. |
| **Repository** | [`ExperimentRepository`](../../backend/app/experiments/repository.py), backed by [`LocalStore`](../../backend/app/storage/local_store.py). | Centralize experiment manifest paths, ID validation, serialization and retrieval so lifecycle code does not repeat filesystem rules. This is a filesystem repository, not a transactional database or unit of work. |
| **Dependency Injection / composition root** | Spring [`AgentOrchestrationConfiguration`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/AgentOrchestrationConfiguration.java); FastAPI [`main.py`](../../backend/app/main.py) and `ExperimentRepository(store)`. | Choose shared clients/configuration in wiring code and pass dependencies to components, allowing controlled configurations and test substitutes. FastAPI routes also use `app.state` as a service locator. |
| **Immutable Value Objects and named factories** | Validated Java [`KernelOrder`](../../java/simulation-kernel/src/main/java/ai/lobarena/kernel/book/KernelOrder.java) record with `limit`, `market`, `modify`, `cancel` and `withQuantity`; [`EventOrderKey`](../../java/simulation-kernel/src/main/java/ai/lobarena/kernel/determinism/EventOrderKey.java). | Make valid order requests and total ordering explicit, and return replacement values rather than mutate shared domain records. These are static factories, not the GoF Factory Method or Abstract Factory patterns. |

## Architectural and workflow patterns

These are system/data-processing patterns; they should not be presented as GoF
class structures merely because they have a familiar name.

| Pattern | Where it is used | Why it is used there |
| --- | --- | --- |
| **Single Writer and deterministic event loop** | Synchronized operations in [`LiveArenaService`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/LiveArenaService.java); deterministic ordering in [`JavaSimulationKernel`](../../java/simulation-kernel/src/main/java/ai/lobarena/kernel/simulation/JavaSimulationKernel.java). | Serialize accepted mutations and fix execution order so replay and evidence do not depend on competing writers or runner completion order. This has actor-like ownership, but is not an actor-framework implementation. |
| **Command messages** | Runner intents in [`AgentOrchestrator`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/AgentOrchestrator.java) and kernel [`AgentIntent`](../../java/simulation-kernel/src/main/java/ai/lobarena/kernel/simulation/AgentIntent.java). | Represent requested market actions as data that Java validates, sorts and applies, allowing out-of-process agents to decide without directly mutating the book. These messages do not implement undoable GoF Command objects. |
| **Finite State Machine** | [`ScenarioProgram.advance`](../../java/simulation-kernel/src/main/java/ai/lobarena/kernel/simulation/ScenarioProgram.java), `stageForTick` and `onStageEnter`; interactive [`LiveScenario`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/LiveScenario.java). | Give synthetic attacks repeatable stages and one-time entry effects, making timing, labels and scenario traces interpretable. These are time-driven state machines, not GoF State classes; kernel and interactive implementations are distinct. |
| **Scatter-Gather orchestration** | [`AgentOrchestrator.collect`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/AgentOrchestrator.java), with runner HTTP deadlines. | Collect independent agent responses concurrently, then validate and merge them in deterministic order before one writer acts. One failed runner is omitted while valid peers remain usable. |
| **Pipeline / streaming processing** | [`FeaturePipeline.iter_rows`](../../backend/app/features/pipeline.py) and [`write_streaming_feature_run`](../../backend/app/features/streaming.py). | Transform canonical events into causal rolling features, quality checks and provenance in one processing path, keeping future events and labels out of feature values. The streaming writer uses row groups; `generate` materializes rows, and memory also depends on active orders/windows. |
| **Append-only journal with a bounded hot window** | Bounded event tail in [`IntegerMatchingEngine`](../../java/simulation-kernel/src/main/java/ai/lobarena/kernel/book/IntegerMatchingEngine.java); segmented JSONL and cursor replay in [`CanonicalEventArchive`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/CanonicalEventArchive.java). | Keep live memory bounded while retaining canonical tick evidence for inspection, replay and feature lineage. This is an event-sourcing element, not proof of complete state restoration or whole-system CQRS. |
| **Immutable manifests, checkpoint recovery and idempotent publication** | [`retain_completed_release` / `resume_publication`](../../backend/app/ml/lightgbm/g8_publication_recovery.py); [`RetainingReadbackStore` / `OfflineReadbackStore`](../../backend/app/ml/transformer/holdout_readback_store.py). | Bind recovery to exact artifact hashes and retained receipts so publication can resume without rescoring and verification can replay retained bytes without cloud reads. Conditional writes and completion markers protect release boundaries; ambiguous mutations require reconciliation, not blind retry. |

## Important tradeoffs and recommended follow-up

Recommendations below are review findings, not implemented changes or newly
approved scope. Preserve existing determinism, evidence and authorization contracts
when considering them.

| Observation | Consequence and recommendation |
| --- | --- |
| [`LiveArenaService`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/LiveArenaService.java) combines scheduling, replay, scenarios, rule features, incidents, serialization and persistence in a large synchronized coordinator. | Single-writer safety is clear, but changes have a broad review surface and runner/persistence latency contributes to serialized tick time. Extract cohesive services only while preserving ordering and completed-tick persistence guarantees. |
| [`AgentOrchestrator`](../../java/control-plane/src/main/java/ai/lobarena/controlplane/AgentOrchestrator.java) omits failed/non-object responses and filters malformed intents. Declared agent IDs can remain when a response's intent collection is malformed. | Partial participation preserves valid peers, but returned results lack per-runner failure receipts. Consider separate participation/health telemetry before relying on a complete agent population. |
| WebSocket mode in [`useArenaSource`](../../frontend/src/hooks/useArenaSource.ts) validates only a shallow state shape, starts from mock state and has no automatic reconnect. | Strengthen versioned-envelope validation and explicit connection/last-valid-state behavior; do not assume reliable reconnect or command acknowledgment is delivered. |
| [`ExperimentRepository`](../../backend/app/experiments/repository.py) uses ordinary JSON file writes and skips malformed manifests on read; event archives have per-stream quotas. | Treat this as local artifact persistence. Assess atomic manifest updates, visible corruption handling and retained-stream lifecycle before adding multiuser/concurrent persistence requirements. |
| [`main.py`](../../backend/app/main.py) constructs application services and runs retention cleanup at import time. | This is convenient local wiring but couples imports to filesystem lifecycle. An explicit application lifespan would make resource ownership and test isolation easier to reason about. |

## Evidence and implementation limits

This was a static source/contract review with local documentation checks; it did
not execute model training/scoring or establish deployment, performance or
production qualification. Unmerged task branches are outside the source snapshot.

Existing tests inspected as implementation evidence, not rerun by this review:

- [`AgentOrchestratorTest`](../../java/control-plane/src/test/java/ai/lobarena/controlplane/AgentOrchestratorTest.java): deterministic merging, failed-response isolation and malformed-intent filtering.
- [`CanonicalEventArchiveTest`](../../java/control-plane/src/test/java/ai/lobarena/controlplane/CanonicalEventArchiveTest.java): segment rotation, cursor replay and completed-tick quota rejection.
- [`ArenaWebSocketHandlerTest`](../../java/control-plane/src/test/java/ai/lobarena/controlplane/ArenaWebSocketHandlerTest.java): versioned state/commands and malformed-command errors.
- [`test_streaming_feature_pipeline.py`](../../backend/tests/test_streaming_feature_pipeline.py): feature output invariance across chunk/row-group choices.
- [`test_transformer_holdout_retention.py`](../../backend/tests/test_transformer_holdout_retention.py): retained receipts/bytes and offline readback boundaries.

For current learned-detector serving, Transformer comparison, promotion and access
gates, use the [ML lifecycle](../use-cases/ml-lifecycle.md) and
[current roadmap status](../roadmap/CURRENT_STATUS.md). A verified loader or
research workflow alone does not demonstrate an integrated live serving path.
The Transformer-to-LightGBM cascade remains a conditional design under
[ARD-0037](ARD-0037-transformer-to-lightgbm-cascade.md).
