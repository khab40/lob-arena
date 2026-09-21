# ARD-0005: Nebius Endpoint Contract

Status: Accepted

Date: 2026-06-01

## Implementation Status

Status as of 2026-07-13: `[partial]`

Implemented:

- Serverless endpoint app exposes health, explanation, scenario generation, smart scenario, order-book alert, and investigation-report routes.
- Backend `NebiusClient` shapes typed requests, handles environment-based URLs, and falls back to deterministic typed mock responses.
- UI and backend routes support incident explanation, smart detection, investigation report generation, and scenario drafting without exposing endpoint credentials to the browser.
- Endpoint contract tests cover the local serverless app.
- Real Endpoint investigations, response evidence, latency, fallback state, and S3 upload state are archived in the frozen [benchmark bundle](../../evidence/deployment-2026-07-14-1412/benchmarks/outputs/benchmark/EXP-390EFAC2/README.md).

Before final submission:

- Keep consolidated latency and sanitized screenshot references in the submission index.

Future work:

- Production authentication, rate limiting, and broader endpoint observability.

## Context

The backend needs AI-generated explanations for detected synthetic incidents,
simulation summaries, smart order-book alert scoring, and investigation-style
reports. The UI should not call Nebius directly. The backend should pass
structured detector evidence to the serverless endpoint and receive structured
response fields that can be stored and rendered.

## Decision

Expose Nebius Serverless AI Endpoints with explicit health, smart detection,
investigation report, event explanation, simulation explanation,
report-generation, and bounded scenario-generation routes.

Endpoint roles:

```mermaid
graph TD
    Endpoints["Nebius Serverless AI Endpoints"]
    Judge["Real-time AI judge"]
    Explain["Explanation generation"]
    Narrator["Scenario narrator"]

    Endpoints --> Judge
    Endpoints --> Explain
    Endpoints --> Narrator
```

Routes:

- `GET /health`
- `POST /orderbook-alert`
- `POST /investigation-report`
- `POST /explain-event`
- `POST /explain-simulation`
- `POST /generate-report`
- `POST /generate-scenario`
- `POST /generate-smart-scenario`

The endpoint accepts structured JSON evidence and returns structured JSON explanation output.

## Endpoint Flow

```mermaid
graph TD
    UI["1. React UI requests incident explanation"]
    Backend["2. FastAPI backend receives request"]
    StoreLoad["3. Backend loads incident evidence"]
    Endpoint["4. Backend posts to Nebius endpoint"]
    Response["5. Endpoint returns structured explanation"]
    StoreReport["6. Backend persists generated report"]
    UIResponse["7. UI renders title, risk, summary, evidence, action"]

    UI --> Backend
    Backend --> StoreLoad
    StoreLoad --> Endpoint
    Endpoint --> Response
    Response --> StoreReport
    StoreReport --> UIResponse
```

## Contract Diagram

```mermaid
graph TD
    IncidentRequest["ExplainIncidentRequest - id, type, confidence, severity, evidence, features"]
    SimulationRequest["ExplainSimulationRequest - simulation id, tick window, detector summary, incidents"]
    Explanation["ExplanationResponse - title, risk, summary, evidence, action, disclaimer"]
    AlertRequest["OrderBookAlertRequest - L2 window, events, features, scenario hint"]
    AlertResponse["OrderBookAlertResponse - suspicion score, detected pattern, reasons"]
    ReportRequest["InvestigationReportRequest - trace, alerts, metrics"]
    ReportResponse["InvestigationReportResponse - case report, timeline, findings"]
    ScenarioRequest["ScenarioGenerationRequest - prompt and constraints"]
    ScenarioResponse["ScenarioGenerationResponse - type, title, description, parameters, risk, safety note"]

    IncidentRequest --> Explanation
    SimulationRequest --> Explanation
    AlertRequest --> AlertResponse
    ReportRequest --> ReportResponse
    ScenarioRequest --> ScenarioResponse
```

## Response Requirements

Explanation responses must include:

- `title`
- `risk_level`
- `plain_english_summary`
- `evidence`
- `recommended_action`
- `disclaimer`

Order-book alert responses must include:

- `suspicion_score`
- `detected_pattern`
- `confidence`
- `reasons`
- `recommended_action`

Investigation report responses must include:

- `title`
- `summary`
- `timeline`
- `detector_findings`
- `limitations`
- `recommended_next_steps`

The disclaimer must preserve the project framing: educational simulation only, no real manipulation detection, no trading signals, and no compliance decisions.

## Environment Variables

The backend reads endpoint wiring from:

- `NEBIUS_INCIDENT_EXPLAINER_URL`
- `NEBIUS_SCENARIO_GENERATOR_URL`
- `NEBIUS_ENDPOINT_BASE_URL`
- `ENDPOINT_TOKEN` optional
- `NEBIUS_TENANT_ID` optional metadata/status field

## Consequences

Positive:

- UI remains decoupled from Nebius credentials and endpoint details.
- Explanations are grounded in deterministic detector evidence.
- Reports can be persisted with clear schema.

Tradeoffs:

- Backend must handle endpoint failures gracefully.
- Endpoint contract changes require backend and UI updates.
- Generated summaries still require safety framing and review.

## Related Documentation

- `docs/deployment/nebius-deployment.md`
- `serverless/endpoint/README.md`
- [ARD-0003: Detector Evidence Model](ARD-0003-detector-evidence-model.md)
- [ARD-0008: Nebius Serverless AI Endpoints](ARD-0008-nebius-serverless-ai-endpoints.md)
- [ARD-0009: Judge Mode Investigation Reports](ARD-0009-judge-mode-investigation-reports.md)
