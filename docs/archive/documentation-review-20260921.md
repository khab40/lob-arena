# Documentation review — 2026-09-21

Reviewed all **107 pre-existing Markdown files** under `docs/`, including nested
ARDs and use cases. This extends the [ML architecture review](../architecture/ml-documentation-review-20260921.md).
The review covers roadmap state, implementation ownership, implemented versus
planned workflows, historical/current scope, source references and navigation.
It does not rerun model validation or certify every historical performance claim.

## Architecture ownership and organization

`docs/architecture.md` is the only maintained system overview. Root
`ARCHITECTURE.md` was a navigation page with a duplicated status summary; that
summary was removed. ARD-0001 preserves the original decision and explicitly
points to the current overview and superseding decisions. No decision history
or receipt was merged away.

Sixty Markdown files moved into topic folders. Relative links, images,
repository entry points and the release-packaging prompt reference were updated.
Frozen `evidence/` snapshots and `docs/evidence/` machine receipts were left intact.
The [documentation index](../README.md) is the navigation entry point.

## Roadmap findings

The [dated status snapshot](../roadmap/CURRENT_STATUS.md) links the exact issues,
baseline dates, merged source revision and PR #207 readiness receipts, now
merged into main. It flags September 23 schedule risk. All seven stale milestone
descriptions were subsequently corrected and read back without changing dates,
titles or states; remaining stale issue-body text is explicitly identified.
Active guidance now records completed C0–C4/G0–G7, open G8 and blocked G9.
Transformer/cascade/secure UI remain planned. Historical execution records keep
their original counts, hashes and outcomes with explicit stale/superseded banners.

## Per-file disposition

“Reference” means no roadmap/ownership inconsistency was found in this review;
it does not assert production readiness. Historical records are deliberately
retained, with a warning at the document entry when their prose could mislead.
All links below use the final topic location.

| Document | Disposition | Finding / action |
| --- | --- | --- |
| [archive/CHANGELOG.md](CHANGELOG.md) | Historical / flagged | Dated changes retained; removed paths and old completion statements are not present deployment state. |
| [product/DESIGN-IDEAS.md](../product/DESIGN-IDEAS.md) | Reference / proposals | Theme is implemented; product modes and ABIDES-inspired ideas remain partial/proposed, not roadmap delivery. |
| [DOCUMENTATION_GUIDE.md](../DOCUMENTATION_GUIDE.md) | Corrected | Topic map, canonical ownership, dated status, historical evidence and move/link rules. |
| [product/FUNCTIONAL_OVERVIEW.md](../product/FUNCTIONAL_OVERVIEW.md) | Corrected | Removed 33% corpus/G5-unlocked claims; distinguished C4 research labels, implemented projections and planned cascade/registry. |
| [archive/IMPLEMENTATION_PLAN_GOOGLE_AUTH.md](IMPLEMENTATION_PLAN_GOOGLE_AUTH.md) | Historical / flagged | Removed implementation and routes retained as history; secure restoration is open #91. |
| [roadmap/PHASES.md](../roadmap/PHASES.md) | Corrected / history flagged | Replaced stale board counts and G8 pending-implementation plan; early Python deliverables and spend receipts explicitly historical. |
| [deployment/QUICKSTART.md](../deployment/QUICKSTART.md) | Corrected | Removed unverified five-minute and host-capacity promises; corrected Nginx startup output and scoped local demo versus model Jobs. |
| [roadmap/ROADMAP-MAIN.md](../roadmap/ROADMAP-MAIN.md) | Corrected | Preserved baseline dates, flagged schedule risk, closed corpus steps and replaced obsolete G8 gates. |
| [use-cases/README.md](../use-cases/README.md) | Corrected | Moved to use-cases index; Java live-arena diagram fixed; planned secure UI and ML workflow remain explicit. |
| [architecture.md](../architecture.md) | Current overview | Single canonical overview; added roadmap/index links. ML corrections recorded in the earlier review. |
| [architecture/ARD-0001-overall-architecture.md](../architecture/ARD-0001-overall-architecture.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0002-websocket-state-schema.md](../architecture/ARD-0002-websocket-state-schema.md) | Reference | Java-owned versioned arena_state and WebSocket agree with handlers; formal exported schema remains future. |
| [architecture/ARD-0003-detector-evidence-model.md](../architecture/ARD-0003-detector-evidence-model.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0004-benchmark-artifact-format.md](../architecture/ARD-0004-benchmark-artifact-format.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0005-nebius-endpoint-contract.md](../architecture/ARD-0005-nebius-endpoint-contract.md) | Reference / partial | Endpoint contract and typed fallback implemented; production auth/rate limits remain future. |
| [architecture/ARD-0006-scenario-labeling-and-reproducibility.md](../architecture/ARD-0006-scenario-labeling-and-reproducibility.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0007-nebius-serverless-ai-jobs.md](../architecture/ARD-0007-nebius-serverless-ai-jobs.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0008-nebius-serverless-ai-endpoints.md](../architecture/ARD-0008-nebius-serverless-ai-endpoints.md) | Reference / partial | Endpoint demo integration is not production surveillance; bounded FastAPI evidence boundary retained. |
| [architecture/ARD-0009-judge-mode-investigation-reports.md](../architecture/ARD-0009-judge-mode-investigation-reports.md) | Reference / partial | Full timeline selection/report state machine explicitly future; existing report surfaces do not close #91. |
| [architecture/ARD-0010-agent-runner-execution.md](../architecture/ARD-0010-agent-runner-execution.md) | Reference | Java orchestration, runner protocol and deadlines; remote auth/queues/checkpointing remain future. |
| [architecture/ARD-0011-exchange-liquidity-invariant.md](../architecture/ARD-0011-exchange-liquidity-invariant.md) | Historical config flagged | Java enforces invariant; original Python ARENA_* settings are not live Java controls. |
| [architecture/ARD-0013-ui-shell-preferences.md](../architecture/ARD-0013-ui-shell-preferences.md) | Corrected | Theme diagram now shows Java live state source; accessibility follow-up remains open. |
| [architecture/ARD-0015-nebius-ai-investigation-team.md](../architecture/ARD-0015-nebius-ai-investigation-team.md) | Scope clarified | Done refers to endpoint demo integration; #27/#28/#91 remain open; unauthenticated acceptance is historical. |
| [architecture/ARD-0016-ai-scenario-generator.md](../architecture/ARD-0016-ai-scenario-generator.md) | Corrected | Live scenario injection references Java client; Python engine is offline/serverless only. |
| [architecture/ARD-0017-ai-detector-tournament.md](../architecture/ARD-0017-ai-detector-tournament.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0018-canonical-exchange-event-stream.md](../architecture/ARD-0018-canonical-exchange-event-stream.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0019-python-reference-java-kernel-migration.md](../architecture/ARD-0019-python-reference-java-kernel-migration.md) | Historical sequence flagged | Intermediate Python authority claims belong to migration steps; ARD-0020 owns completed live cutover. |

## Validation

The final tree contains 110 docs Markdown files, including the new index, status
snapshot and this ledger. Static checks covered 1,162 local links and 76 heading
anchors across 120 active documents, with no unresolved targets or moved paths.
All 87 Mermaid diagrams rendered; the four substantively changed diagrams were
visually inspected. Both existing offline release-packaging tests passed.
No training, scoring, cloud mutation or final-test access was performed.
