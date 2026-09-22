# Java Simulation Kernel

`JavaSimulationKernel` is the framework-free Java 25 authoritative runner for the version 1 `SimulationRequest`/`SimulationResult` contract. It executes requests rather than replaying fixture outputs.

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

The migration-era differential harness is retired. Permanent regression checks
compare this implementation with the immutable [golden corpus](golden-parity-corpus-v1.md).


## Java diagnostic maintenance

Use supported Jackson 3 string accessors (`stringValue`, `asString`, `isString`)
and Spring's `UNPROCESSABLE_CONTENT` / `CONTENT_TOO_LARGE` constants. The old
Jackson accessors delegate to these replacements; preserve default arguments
and avoid changing coercion or missing-value behavior during API cleanup.

The Java null-analysis review uses these collection contracts:

- matching executions and book queues contain constructed records, never null entries;
- comparator receivers are actual event keys/intents and retain their existing ordering;
- visible levels are constructed from protobuf levels, and lifetimes are boxed primitives;
- string splitting, successful profile loading, incident creation, fixture lists, and
  path construction produce the non-null receivers used by their stream operations;
- `Map.merge` invokes its remapping function only with non-null existing/new values.

Explicit lambdas let Eclipse analyze those receiver calls without the unchecked
method-reference conversion warnings. No null-analysis suppression is required.
Test loops initialize their result with the first step and still execute three steps.

Resource ownership remains explicit: Spring closes its gRPC bean using
`destroyMethod = "close"`; the standalone server has a shutdown hook. Construct
these instances before calling their fluent `start()` method so analysis can
follow the same object. Successful archive tests and rejected historical-source
tests use try-with-resources. The archive quota-rejection test has the sole local
`resource` suppression: it holds no open file handle, and `close()` would retry
the deliberately rejected pending flush. Do not broaden this suppression.

Validate with `./java/gradlew -p java clean check`. Gradle compilation and Eclipse
null/resource analysis are separate checks; a passing Gradle build alone does
not establish a warning-free IDE.
