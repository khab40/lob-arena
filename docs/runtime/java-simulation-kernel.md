# Java Simulation Kernel

`JavaSimulationKernel` is the framework-free Java 25 candidate runner for the version 1 `SimulationRequest`/`SimulationResult` contract. It executes requests rather than replaying fixture outputs.

## Tick Lifecycle

Each logical tick runs these phases in order:

1. all configured normal agents decide from the same pre-action depth snapshot and their intents are totally ordered;
2. set-level and market intents mutate the integer book through the matching engine;
3. the active scenario advances through armed, wall placed, pressure, cancellation, confirmation, and done stages;
4. baseline liquidity repairs the configured levels without displacing non-baseline quantity;
5. one depth-limited L2 snapshot event is appended;
6. market features and detector confidences are calculated and quantized for the result.

The implementation includes the reference market maker, deterministic noise trader, periodic taker, spoofing-like wall, layering-like, quote-stuffing, and liquidity-evaporation programs. Logical ticks—not wall-clock time—control all state and output.

## Contract Behavior

- Requests with unsupported versions, unfrozen scenario parameters, invalid required configuration, or event-limit overflow are rejected.
- Initial baseline construction occurs before event-listener attachment and therefore emits no stream events.
- Every completed tick emits exactly one snapshot.
- Result events are contiguous and canonically hashed; the final book has its independent canonical hash.
- Metrics are sorted, represented as integer values at decimal scale six, and use the frozen half-even policy.
- Java is authoritative and must continue to match every checked-in golden request for ordered events, books, hashes, and metrics.

Reusable arbitrary-result divergence diagnostics are added in the differential parity harness step; the simulation tests in this step establish deterministic execution and golden-envelope acceptance.
