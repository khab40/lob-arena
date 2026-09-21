# gRPC Kernel Boundary

The versioned `lob.exchange.v1.SimulationKernel` service is the integration boundary for the authoritative Java kernel:

```protobuf
rpc RunSimulation(SimulationRequest) returns (SimulationResult);
```

Requests and results use the deterministic Protobuf contract directly. No JSON conversion, floating-point value, Spring object, FastAPI model, persistence handle, or telemetry object enters the hot loop.

## Implementation

- `java/kernel-grpc` adapts the framework-free `JavaSimulationKernel` to generated Java gRPC types.
- `java/control-plane` owns the gRPC server lifecycle and the public Spring HTTP adapter.
- `exchange-proto` owns Java message and service generation.
- `scripts/generate_protos.py` owns checked-in Python client bindings used by ML/AI integrations and compatibility tooling.

There is no Python gRPC kernel service.

## Failure Contract

- Invalid contract versions, malformed deterministic inputs, and unsupported scenario parameters return gRPC `INVALID_ARGUMENT` or HTTP 400.
- Unexpected Java failures return gRPC `INTERNAL` or the corresponding Spring server error.
- Transport deadlines, authentication, retries, and deployment policy remain outside the deterministic kernel.

Java integration tests and the permanent CI replay execute the checked-in corpus and compare complete byte-exact results.
