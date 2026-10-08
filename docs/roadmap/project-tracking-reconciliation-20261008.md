# Project tracking reconciliation — 8 October 2026

Tracking: [Bug #355](https://github.com/khab40/lob-arena/issues/355), under
[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).

The audit cross-checked all 154 existing Project items against 142 repository
issues and all seven milestone descriptions/assignments before adding this Bug.
Current summaries are reconciled with merged [PR #354](https://github.com/khab40/lob-arena/pull/354)
and the [bounded research disposition](../ml/transformer-research-disposition-20261008.md).
Historical entries and complete acceptance criteria remain available.

Behavioral change: none. Frozen settings, model artifacts, research reports,
execution identities and authorization boundaries remain unchanged.

## Completed research and next delivery

Training, seed confirmation, calibration, paired comparison and the authorized
December holdout are independently verified. Scoped [#314](https://github.com/khab40/lob-arena/issues/314)
is closed, including the explicit 64-window derived calibration/decision receipt.
The operator's `continue_research` instruction is recorded; it grants no new
workload, access, spend, promotion or hybrid-study authority.

The next #90/#91 chunk is local-only playback of authenticated private saved
Transformer/LightGBM scores, with frozen thresholds and alert provenance. It is
planned, not implemented. It does not replay an order book or score new events.
The dedicated inference adapter, causal 60-feature/64-row event integration,
separately authorized Nebius rehearsal and MLflow/cost reconciliation follow.

## Existing ticket disposition

| Tickets | Current disposition |
| --- | --- |
| #14/#19/#20/#21 | In Progress; platform, MLflow, infrastructure and observability/FinOps acceptance remain deferred. Research completion does not prove these gates. |
| #15/#16 | In Progress; bounded research decision recorded, first saved-score mock next, full program/demo acceptance open. |
| #24 | In Progress; research verified and #314 closed; MLflow lineage, dedicated serving-path and resource/cost acceptance remain. |
| #25 | Todo; hybrid study unstarted, conditional on separate justification/approval. |
| #88 | Todo; commercial common detector adapter remains parked. Verified Transformer research code exists; the common integration/conformance contract does not. |
| #90/#91 | Todo; saved-score mock planned. Full three-model/LOBSTER campaign and secure guided UI acceptance remain open. |
| #312 | Closed repair; Project status corrected from In Progress to Done. |
| #314/#353 | Closed/Done after PR #354; no reopening or model rerun required. |
| #22/#23 | Closed/Done; corpus and research-only LightGBM G0–G9 completion preserved. |

Other open existing Project tickets retain their applicable scope/status:
#17/#18/#26/#27/#28/#85/#87/#92/#93/#94/#303/#304/#305.
The separate maintenance session completed #352 during this audit; fresh
prepublication readback records it closed, rather than preserving its earlier
In Progress snapshot as current status.
Closed historical tickets require no additional status changes. Full #28 still
depends on the conditional hybrid/investigator-selection work; #305 remains a
separate release/versioning backlog item.

## Milestone acceptance

Counts use actual assigned issues, excluding pull requests and this unassigned
tracking Bug. All seven milestones remain **open** with existing due baselines.
These dates are not refreshed delivery forecasts.

| Milestone | Closed / assigned | Baseline | Remaining acceptance |
| --- | ---: | --- | --- |
| M1 — Governed corpus | 1 / 2 | 11 Sep | #20 repeatability/idempotency, evidence-preserving teardown, grant audit and billing/FOCUS guardrails. #22 is complete. |
| M2 — LightGBM qualification | 1 / 5 | 23 Sep | #14/#18/#19/#21 platform, synthetic campaign, MLflow recovery/registration and observability/FinOps. #23 is research-qualified. |
| M3 — Standalone Transformer | 0 / 1 | 9 Oct | Full #24 MLflow lineage, dedicated serving-path and resource/cost acceptance. Bounded research and scoped #314 are complete. |
| M4 — Hybrid | 0 / 1 | 23 Oct | #25 separately approved study, causal feature release, exact joins, ablations, fallback and disposition. |
| M5 — Integrated evidence | 0 / 1 | 30 Oct | Full #90 Nasdaq/LOBSTER three-model evidence, runtime/cost and rehearsal. The first two-detector saved-score mock is only one increment. |
| M6 — Secure CEO UI | 0 / 5 | 13 Nov | #17/#26/#27/#28/#91 investigator and authenticated guided-workflow acceptance. Shared sensitive deployment needs backend authorization. |
| M7 — Final demo | 0 / 2 | 20 Nov | #15/#16 full program, deployment/security checks, final rehearsal and management acceptance. |

M1/M2 baselines were missed. M3's full-story target remains at risk; research
completion does not establish serving/MLflow/cost completion. Reforecast from
remaining dependencies rather than silently changing dates or reducing scope.

## Verification

Before/after issue, Project and milestone snapshots, exact reviewed update
payloads and independent review receipts are retained in project-root
`outputs/project-tracking-reconcile-20261008/`. Verify Markdown links, unchanged
acceptance/due/state boundaries and exact live readbacks. No model or cloud
resource operation is part of this reconciliation.
