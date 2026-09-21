# Professional surveillance prompting

LOB Arena uses Qwen2.5-14B-Instruct as a bounded investigation assistant, not as
the detector. Deterministic detectors first produce structured episode evidence;
the model explains that evidence, compares hypotheses, and recommends review
steps. It receives summaries only—never raw order-book streams.

## Contracts and implementation

- System prompt, request builder, invocation policy, and strict parser:
  [`serverless/endpoint/surveillance.py`](../serverless/endpoint/surveillance.py)
- Request schema:
  [`surveillance-request.schema.json`](../serverless/endpoint/schemas/surveillance-request.schema.json)
- Response schema:
  [`surveillance-response.schema.json`](../serverless/endpoint/schemas/surveillance-response.schema.json)
- Examples: [spoofing](../serverless/endpoint/examples/spoofing.json),
  [layering](../serverless/endpoint/examples/layering.json),
  [benign market making](../serverless/endpoint/examples/benign-market-making.json),
  and [uncertain](../serverless/endpoint/examples/uncertain.json).

The request contract covers simulation metadata, regime, instrument, episode
duration, suspected participant, order/trade statistics, derived features,
detector scores, a compact timeline, before/during/after LOB summaries,
cancellation/execution metrics, price movement, optional ground truth, and
previous participant behaviour. Missing fields are listed explicitly rather
than inferred.

The response contract is strict JSON with classification, confidence, severity,
market context, evidence, counter-evidence, alternatives, episode timeline,
detector disagreement, recommended actions, regulatory assessment, and an
executive summary. Extra or missing fields fail validation and activate the
existing deterministic endpoint fallback.

The user prompt template is a compact JSON envelope:

```json
{
  "task": "Assess the summarized synthetic market episode and return the required professional surveillance JSON.",
  "episode_summary": "<validated summarized request>",
  "required_response_schema": "<strict response JSON Schema>"
}
```

The system prompt supplies the investigator role, evidence rules, uncertainty
and safety constraints, hidden-reasoning rule, and deterministic output rules.
The user envelope supplies only the episode-specific facts and output contract.

## Prompt budget and summarization

The builder caps the user payload at 24,000 serialized characters (roughly
6,000 tokens), the event timeline at 32 observations, detector results at 16,
and previous-behaviour entries at 12. LOB snapshots contain only touch, spread,
depth, imbalance, and summarized-level counts. This leaves room for the system
prompt within the 6–8k input-token target and remains comfortably below the
16,384-token vLLM context configured for one `gpu-l40s-d` GPU.

The model is instructed to reason internally without exposing chain-of-thought,
separate observation from inference, compare manipulation and benign hypotheses,
explain detector disagreement, report uncertainty, and never invent unavailable
market data. Temperature is `0.0`, the default seed is `42`, and output must be
one JSON object. Interesting episodes receive a 1,200-token output budget;
benign or low-score summaries receive 500 tokens.

## Invocation policy

Model inference occurs only for:

| Trigger | Purpose |
| --- | --- |
| High anomaly score (at least `0.75`) | Investigate materially anomalous evidence |
| Detector disagreement (score gap at least `0.30` or conflicting votes) | Reconcile competing detector interpretations |
| Completed manipulation episode | Assess the full bounded episode |
| Simulation summary | Narrate aggregate synthetic results |
| Benchmark generation | Produce a concise benchmark report |

Ordinary low-score events do not invoke vLLM. Existing HTTP request and response
shapes remain unchanged: route adapters translate the professional assessment
back into `/orderbook-alert`, investigation, report, and explanation contracts.
Scenario-generation routes remain separately bounded because they generate
synthetic workloads rather than surveillance assessments.

## Safety boundary

This prompting layer handles synthetic educational evidence only. It has no
real trading data, produces no trading signals, makes no claim of detecting
real market manipulation, and is not suitable for compliance decisions.
