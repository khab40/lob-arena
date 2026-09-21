# ARD-0001: Overall Architecture

Status: Superseded in part by [ARD-0020](ARD-0020-java-arena-websocket-agent-orchestration.md)

Date: 2026-05-31

## Scope and successors

This records the original separation of the UI, simulation, detectors, AI
explanations and batch jobs. Its FastAPI-owned live runtime was superseded by
Java ownership in ARD-0020. Current design lives in the
[system overview](../architecture.md), progress in [current status](../roadmap/CURRENT_STATUS.md),
and product positioning in the [one-pager](../product/lob-arena-one-pager.md).

The original component diagrams and delivery checklists are retained in
[the pre-compaction revision](https://github.com/khab40/lob-arena/blob/63fe41d277732875628d0e72449a1f8e992ae07b/docs/architecture/ARD-0001-overall-architecture.md).
They are historical, not a second current architecture.

## Context

The initial educational simulator needed interactive replay/investigation and
offline labeled benchmarks, with reproducible artifacts and a UI independent
of AI services. It was not a production surveillance or compliance system.

## Decision

Separate presentation, exchange execution, deterministic detection, AI
explanation and offline benchmarking. The original implementation selected
React and a FastAPI simulator; ARD-0020 later transferred live authority to Java.
The rationale and consequences below retain their original decision scope.

## Key Decisions

### Decision 1: Keep UI And Simulation Separate

The UI will not directly own exchange logic. It sends commands to the backend and receives state updates.

Rationale:

- keeps simulation testable outside the browser
- avoids duplicating state logic across frontend and backend
- allows batch jobs to reuse simulation concepts without UI dependencies

### Decision 2: Use Deterministic Detectors Before AI Explanations

The detector engine will calculate confidence and evidence deterministically. AI explanations summarize evidence but do not determine incidents.

Rationale:

- makes benchmark metrics meaningful
- improves reviewability
- avoids overstating AI-generated conclusions
- supports the educational safety framing

### Decision 3: Keep Nebius Endpoint And Job Separate

The Serverless AI Endpoint and Serverless AI Job serve different runtime needs.

Rationale:

- endpoint is latency-sensitive and interaction-driven
- job is throughput-oriented and benchmark-driven
- separation makes deployment and observability clearer

### Decision 4: Persist Artifacts Locally

The system writes local event, snapshot, incident, benchmark, and report artifacts under `outputs/`.

Rationale:

- supports replay and debugging
- supports benchmark reproducibility
- gives reviewers concrete artifacts
- avoids treating transient UI state as the only source of truth

### Decision 5: Use Explicit Safety Language

README, UI, docs, and generated reports must state that this is an educational simulation.

Rationale:

- scenarios are synthetic abuse-like patterns
- detectors are simplified and deterministic
- output must not be interpreted as real surveillance, trading advice, or compliance guidance

## Alternatives Considered

### Browser-Only Simulation

Rejected for the primary architecture.

Reason:

It would simplify the demo but make backend APIs, batch benchmarks, artifact persistence, and serverless integration less realistic.

### AI-First Detection

Rejected.

Reason:

AI-generated text is not a stable detector. The project needs deterministic detector outputs before explanation generation.

### Single Monolithic Service For UI, Simulation, Benchmark, And Explanation

Rejected.

Reason:

It would reduce deployment boundaries but obscure the distinction between live demo, offline benchmark, and AI explanation workloads.

## Consequences

Positive consequences:

- clear runtime boundaries
- testable simulation and detector logic
- UI can remain responsive and visual
- Nebius components have focused responsibilities
- benchmark outputs can be reproduced and reviewed

Tradeoffs:

- more modules and documentation to maintain
- WebSocket state contract needs to stay synchronized with UI needs
- benchmark and live runtime may diverge if shared logic is not kept aligned
- serverless deployment requires separate configuration and observability artifacts

## Related decisions

Use the [ARD index](README.md) for schema, detector, artifact, agent, data and
ML decisions. [ARD-0020](ARD-0020-java-arena-websocket-agent-orchestration.md)
### Future Ideas Inspired By Modeling Notes

The broader modeling direction is to treat the exchange as one example of a multidimensional time-series process. The same architecture could model not only quotes, trades, spreads, depth, and order-flow events, but also synchronized external context such as news, macro events, political statements, social signals, or other exogenous shocks.

This opens several future research and product directions:

- digital twin of a market process: run the real or historical process and a virtual mathematical version side by side, using differences between them to improve models and predictions
- adversarial behavior modeling: represent market participants as agents or groups of agents with conflicting goals, strategies, and observable consequences
- semantic attack simulation: model not only order-book abuse, but also misinformation, data poisoning, fake signals, deepfake-driven market narratives, and other context-level attacks
- online learning loop: continuously validate predictions, detector outputs, and decisions against the simulated or replayed process, then refine the model
- Boyd-cycle framing: model both attacker and defender loops of observe, orient, decide, and act, making the arena a conflict simulation rather than a passive dashboard
- cross-domain extension: use the same simulation pattern for other complex adversarial systems where multiple entities interact over time, such as competitive markets, information operations, supply chains, or social tension modeling

The exchange domain is a strong first case study because it has rich public data, clear event streams, measurable outcomes, visible agent behavior, and well-known market microstructure indicators. A convincing prototype here can become the foundation for a broader platform for simulation, prediction, and decision support in adversarial multidimensional systems.
