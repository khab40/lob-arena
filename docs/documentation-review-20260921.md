# Documentation review — 2026-09-21

Reviewed all **107 pre-existing Markdown files** under `docs/`, including nested
ARDs and use cases. This extends the [ML architecture review](architecture/ml-documentation-review-20260921.md).
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
The [documentation index](README.md) is the navigation entry point.

## Roadmap findings

The [dated status snapshot](roadmap/CURRENT_STATUS.md) links the exact issues,
baseline dates, merged source revision and separately identified open PR #207
receipts. It flags September 23 schedule risk and stale external milestone text.
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
| [archive/CHANGELOG.md](archive/CHANGELOG.md) | Historical / flagged | Dated changes retained; removed paths and old completion statements are not present deployment state. |
| [product/DESIGN-IDEAS.md](product/DESIGN-IDEAS.md) | Reference / proposals | Theme is implemented; product modes and ABIDES-inspired ideas remain partial/proposed, not roadmap delivery. |
| [DOCUMENTATION_GUIDE.md](DOCUMENTATION_GUIDE.md) | Corrected | Topic map, canonical ownership, dated status, historical evidence and move/link rules. |
| [product/FUNCTIONAL_OVERVIEW.md](product/FUNCTIONAL_OVERVIEW.md) | Corrected | Removed 33% corpus/G5-unlocked claims; distinguished C4 research labels, implemented projections and planned cascade/registry. |
| [archive/IMPLEMENTATION_PLAN_GOOGLE_AUTH.md](archive/IMPLEMENTATION_PLAN_GOOGLE_AUTH.md) | Historical / flagged | Removed implementation and routes retained as history; secure restoration is open #91. |
| [roadmap/PHASES.md](roadmap/PHASES.md) | Corrected / history flagged | Replaced stale board counts and G8 pending-implementation plan; early Python deliverables and spend receipts explicitly historical. |
| [deployment/QUICKSTART.md](deployment/QUICKSTART.md) | Corrected | Removed unverified five-minute and host-capacity promises; corrected Nginx startup output and scoped local demo versus model Jobs. |
| [roadmap/ROADMAP-MAIN.md](roadmap/ROADMAP-MAIN.md) | Corrected | Preserved baseline dates, flagged schedule risk, closed corpus steps and replaced obsolete G8 gates. |
| [use-cases/README.md](use-cases/README.md) | Corrected | Moved to use-cases index; Java live-arena diagram fixed; planned secure UI and ML workflow remain explicit. |
| [architecture.md](architecture.md) | Current overview | Single canonical overview; added roadmap/index links. ML corrections recorded in the earlier review. |
| [architecture/ARD-0001-overall-architecture.md](architecture/ARD-0001-overall-architecture.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0002-websocket-state-schema.md](architecture/ARD-0002-websocket-state-schema.md) | Reference | Java-owned versioned arena_state and WebSocket agree with handlers; formal exported schema remains future. |
| [architecture/ARD-0003-detector-evidence-model.md](architecture/ARD-0003-detector-evidence-model.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0004-benchmark-artifact-format.md](architecture/ARD-0004-benchmark-artifact-format.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0005-nebius-endpoint-contract.md](architecture/ARD-0005-nebius-endpoint-contract.md) | Reference / partial | Endpoint contract and typed fallback implemented; production auth/rate limits remain future. |
| [architecture/ARD-0006-scenario-labeling-and-reproducibility.md](architecture/ARD-0006-scenario-labeling-and-reproducibility.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0007-nebius-serverless-ai-jobs.md](architecture/ARD-0007-nebius-serverless-ai-jobs.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0008-nebius-serverless-ai-endpoints.md](architecture/ARD-0008-nebius-serverless-ai-endpoints.md) | Reference / partial | Endpoint demo integration is not production surveillance; bounded FastAPI evidence boundary retained. |
| [architecture/ARD-0009-judge-mode-investigation-reports.md](architecture/ARD-0009-judge-mode-investigation-reports.md) | Reference / partial | Full timeline selection/report state machine explicitly future; existing report surfaces do not close #91. |
| [architecture/ARD-0010-agent-runner-execution.md](architecture/ARD-0010-agent-runner-execution.md) | Reference | Java orchestration, runner protocol and deadlines; remote auth/queues/checkpointing remain future. |
| [architecture/ARD-0011-exchange-liquidity-invariant.md](architecture/ARD-0011-exchange-liquidity-invariant.md) | Historical config flagged | Java enforces invariant; original Python ARENA_* settings are not live Java controls. |
| [architecture/ARD-0013-ui-shell-preferences.md](architecture/ARD-0013-ui-shell-preferences.md) | Corrected | Theme diagram now shows Java live state source; accessibility follow-up remains open. |
| [architecture/ARD-0015-nebius-ai-investigation-team.md](architecture/ARD-0015-nebius-ai-investigation-team.md) | Scope clarified | Done refers to endpoint demo integration; #27/#28/#91 remain open; unauthenticated acceptance is historical. |
| [architecture/ARD-0016-ai-scenario-generator.md](architecture/ARD-0016-ai-scenario-generator.md) | Corrected | Live scenario injection references Java client; Python engine is offline/serverless only. |
| [architecture/ARD-0017-ai-detector-tournament.md](architecture/ARD-0017-ai-detector-tournament.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0018-canonical-exchange-event-stream.md](architecture/ARD-0018-canonical-exchange-event-stream.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0019-python-reference-java-kernel-migration.md](architecture/ARD-0019-python-reference-java-kernel-migration.md) | Historical sequence flagged | Intermediate Python authority claims belong to migration steps; ARD-0020 owns completed live cutover. |
| [architecture/ARD-0020-java-arena-websocket-agent-orchestration.md](architecture/ARD-0020-java-arena-websocket-agent-orchestration.md) | Corrected | Context now past tense; Java live cutover is complete. |
| [architecture/ARD-0021-local-observability-grafana.md](architecture/ARD-0021-local-observability-grafana.md) | Reference | Operational metrics and dashboards remain distinct from persisted quality evidence. |
| [architecture/ARD-0022-historical-market-data-ingestion.md](architecture/ARD-0022-historical-market-data-ingestion.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0023-hybrid-historical-replay.md](architecture/ARD-0023-hybrid-historical-replay.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0024-versioned-causal-feature-engineering.md](architecture/ARD-0024-versioned-causal-feature-engineering.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0025-governed-corpus-and-ml-benchmark.md](architecture/ARD-0025-governed-corpus-and-ml-benchmark.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0026-governed-lightgbm-release-boundary.md](architecture/ARD-0026-governed-lightgbm-release-boundary.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0027-shared-mlflow-tracking.md](architecture/ARD-0027-shared-mlflow-tracking.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0028-governed-lightgbm-feature-loading.md](architecture/ARD-0028-governed-lightgbm-feature-loading.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0029-deterministic-lightgbm-binary-training.md](architecture/ARD-0029-deterministic-lightgbm-binary-training.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0030-float32-governed-feature-release.md](architecture/ARD-0030-float32-governed-feature-release.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0031-complete-lightgbm-v1.md](architecture/ARD-0031-complete-lightgbm-v1.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0032-nasdaq-itch-ingestion.md](architecture/ARD-0032-nasdaq-itch-ingestion.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0033-deterministic-hybrid-scheduling.md](architecture/ARD-0033-deterministic-hybrid-scheduling.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0034-itch-market-profile-calibration.md](architecture/ARD-0034-itch-market-profile-calibration.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0035-nebius-lightgbm-first.md](architecture/ARD-0035-nebius-lightgbm-first.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0036-market-sequence-transformer.md](architecture/ARD-0036-market-sequence-transformer.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0037-transformer-to-lightgbm-cascade.md](architecture/ARD-0037-transformer-to-lightgbm-cascade.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0038-c4-specific-evaluation.md](architecture/ARD-0038-c4-specific-evaluation.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0039-same-run-mlflow-recovery.md](architecture/ARD-0039-same-run-mlflow-recovery.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/ARD-0040-completed-release-publication-recovery.md](architecture/ARD-0040-completed-release-publication-recovery.md) | ML decision reviewed | See the earlier ML audit for source evidence and corrections; accepted/proposed status and remaining gates retained. |
| [architecture/README.md](architecture/README.md) | Current decision index | Existing ARD catalogue retained; topic links repaired. |
| [architecture/ml-documentation-review-20260921.md](architecture/ml-documentation-review-20260921.md) | Dated review evidence | Earlier 26-ARD review retained; validation counts describe that revision, not this expanded audit. |
| [ml/benchmark-methodology.md](ml/benchmark-methodology.md) | Scope clarified | Legacy synthetic tournament versus client-governed and separate C4 row evaluation. |
| [runtime/calculations-explanations.md](runtime/calculations-explanations.md) | Legacy scope flagged | Rules/tournament formulas describe retained synthetic pipeline, not causal ML features or current Java implementation details. |
| [runtime/canonical-hashing-v1.md](runtime/canonical-hashing-v1.md) | Corrected | Java is authoritative, not candidate; canonical encoding/golden vectors unchanged. |
| [publication/challenge-submission.md](publication/challenge-submission.md) | Historical publication flagged | Original challenge narrative/screenshots retained; ownership/routes/data claims must be revalidated before reuse. |
| [data/client-historical-dataset-validation-runbook.md](data/client-historical-dataset-validation-runbook.md) | Reference | CLI/API and signed validation workflow retained; client data acceptance is not evidence of delivered general BYO adapter product. |
| [publication/demo-script.md](publication/demo-script.md) | Historical publication flagged | Original challenge narrative/screenshots retained; ownership/routes/data claims must be revalidated before reuse. |
| [runtime/determinism-contract-v1.md](runtime/determinism-contract-v1.md) | Reference | Frozen units, ordering and Java authority agree with contract tooling and immutable vectors. |
| [runtime/history/differential-parity-harness.md](runtime/history/differential-parity-harness.md) | Historical / already explicit | Python differential harness removed; retained golden-corpus verification is current. |
| [runtime/exchange-event-stream.md](runtime/exchange-event-stream.md) | Corrected | Completed Java/historical support replaces migrating/future-data language; Python method examples scoped to offline implementation. |
| [ml/feature-engineering-lightgbm.md](ml/feature-engineering-lightgbm.md) | Corrected | Trainer/calibration/logging no longer future; full 60-column schema distinguished from selected 31-column ablation. |
| [operations/g8/g8-c4-evaluation-contract.md](operations/g8/g8-c4-evaluation-contract.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-c4-provenance-fix.md](operations/g8/g8-c4-provenance-fix.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-completion-recovery.md](operations/g8/g8-completion-recovery.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-live-replacement.md](operations/g8/g8-live-replacement.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-mlflow-recovery.md](operations/g8/g8-mlflow-recovery.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-native-context-handoff.md](operations/g8/g8-native-context-handoff.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-native-rehearsal-package.md](operations/g8/g8-native-rehearsal-package.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-persistent-storage-exception.md](operations/g8/g8-persistent-storage-exception.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-prelogging-checkpoint.md](operations/g8/g8-prelogging-checkpoint.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-production-package.md](operations/g8/g8-production-package.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-publication-recovery.md](operations/g8/g8-publication-recovery.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/g8/g8-source-sdk.md](operations/g8/g8-source-sdk.md) | Reconciled / history flagged | Dated current-status/policy link added; original receipts retained; native synthetic recovery is not production G8 qualification. |
| [operations/git-ref-recovery.md](operations/git-ref-recovery.md) | Reference / dated incident | Repair procedure and September 15 receipt retained; no cleanup authorization inferred. |
| [runtime/golden-parity-corpus-v1.md](runtime/golden-parity-corpus-v1.md) | Reference | Immutable Java compatibility corpus and explicit versioning; no regeneration claimed. |
| [data/governed-corpus-benchmark-protocol.md](data/governed-corpus-benchmark-protocol.md) | Corrected | Client gate separated from four-date research exception; embargo is a session-date group. |
| [runtime/grpc-kernel-boundary.md](runtime/grpc-kernel-boundary.md) | Reference | Java-only service boundary and versioned Protobuf contract match current ownership. |
| [data/hybrid-dataset-validation.md](data/hybrid-dataset-validation.md) | Reference | Signed replay/equivalence evidence includes ITCH; causal-locality limitations retained. |
| [runtime/history/java-kernel-cutover.md](runtime/history/java-kernel-cutover.md) | Historical / already explicit | Completed cutover; no remaining Python runtime fallback. |
| [runtime/history/java-kernel-migration.md](runtime/history/java-kernel-migration.md) | Historical / already explicit | Migration steps and retired authority modes retained as history. |
| [runtime/java-kernel-performance.md](runtime/java-kernel-performance.md) | Historical measurement flagged | Step 14 host figures are not current capacity or learned-serving latency. |
| [runtime/java-order-book.md](runtime/java-order-book.md) | Reference | Integer prices/lots, FIFO and canonical event semantics retained. |
| [runtime/java-simulation-kernel.md](runtime/java-simulation-kernel.md) | Corrected | Authoritative runner and permanent golden checks replace candidate/future harness wording. |
| [runtime/history/kernel-authority-rollout.md](runtime/history/kernel-authority-rollout.md) | Historical / final policy current | Java authority and retired Python controls explicitly documented. |
| [runtime/kernel-observability.md](runtime/kernel-observability.md) | Reference | Operational metrics remain separate from detector-quality artifacts; Compose profiles and provisioned dashboards retained. |
| [runtime/history/kernel-shadow-mode.md](runtime/history/kernel-shadow-mode.md) | Historical / already explicit | Removed shadow runtime; immutable Java corpus replay remains. |
| [archive/l40s-migration.md](archive/l40s-migration.md) | Historical / flagged | Old model/endpoint migration commands and resource identities require revalidation. |
| [ml/lightgbm-v1-runbook.md](ml/lightgbm-v1-runbook.md) | Current with historical examples | Earlier ML review distinguishes local command syntax from Nebius execution policy and frozen G8 gates. |
| [publication/linkedin-technical-blog-post-updated.md](publication/linkedin-technical-blog-post-updated.md) | Historical publication flagged | Original challenge narrative/screenshots retained; ownership/routes/data claims must be revalidated before reuse. |
| [publication/linkedin-technical-blog-post.md](publication/linkedin-technical-blog-post.md) | Historical publication flagged | Original challenge narrative/screenshots retained; ownership/routes/data claims must be revalidated before reuse. |
| [product/lob-arena-one-pager.md](product/lob-arena-one-pager.md) | Corrected | Java ownership, existing historical ingestion, actual learned-model sequence and parked live adapters. |
| [ml/mlflow-tracking-server.md](ml/mlflow-tracking-server.md) | Corrected | Repository 3.16.0 pin; artifact logging versus model registration; historical VM/tunnel identities flagged. |
| [ml/model-validation-execution-policy.md](ml/model-validation-execution-policy.md) | Corrected | Replacement schema v3 matches code; old v2 review packages require rebinding. |
| [data/nasdaq-public-sample-v1-data-flow.md](data/nasdaq-public-sample-v1-data-flow.md) | Corrected | Completed preparations/G0–G7; measured-manifest counts; acquisition evidence and identity policies marked historical. |
| [deployment/nebius-deployment.md](deployment/nebius-deployment.md) | Operational scope flagged | Legacy VM/demo examples retained; no current resource-state claim or local model-run authority. |
| [roadmap/nebius-lightgbm-wave1-implementation-plan.md](roadmap/nebius-lightgbm-wave1-implementation-plan.md) | History flagged | Intermediate counts, unopened-test claims and obsolete billing/expiry controls superseded by current status/policy. |
| [roadmap/nebius-public-market-data-lightgbm-plan.md](roadmap/nebius-public-market-data-lightgbm-plan.md) | History flagged | Seven-date/15-Job proposal and intermediate access/cost observations retained as history; four-date C4 complete. |
| [publication/publication-image-plan.md](publication/publication-image-plan.md) | Historical publication flagged | Original challenge narrative/screenshots retained; ownership/routes/data claims must be revalidated before reuse. |
| [research/research-notes.md](research/research-notes.md) | Background reference | Research positioning retained; no claim that referenced techniques are implemented. |
| [runtime/runtime-model.md](runtime/runtime-model.md) | Current reference | Java REST/WebSocket authority and offline ML section agree with implemented boundaries; topic links repaired. |
| [product/safety-and-disclaimers.md](product/safety-and-disclaimers.md) | Reference | Educational/research limits remain applicable; no qualification or compliance claim added. |
| [ml/surveillance-prompting.md](ml/surveillance-prompting.md) | Reference | Bounded Qwen investigation assistant distinct from market-sequence Transformer; schemas and code references resolve. |
| [product/ui-theme.md](product/ui-theme.md) | Reference | UI theme tokens and local preferences; no secure-workspace acceptance implied. |
| [use-cases/ml-data-preparation.md](use-cases/ml-data-preparation.md) | Current use case | C4/generic-loader distinction, partitioning, source labels and tabular/sequence materialization reviewed in ML audit. |
| [use-cases/ml-lifecycle.md](use-cases/ml-lifecycle.md) | Current use-case index | Links implemented versus planned stages and model/data ownership. |
| [use-cases/ml-model-serving.md](use-cases/ml-model-serving.md) | Proposed serving / explicit gaps | Replay/shadow modes and combinations are design requirements; no implemented learned live service claimed. |
| [use-cases/ml-training-selection.md](use-cases/ml-training-selection.md) | Current use case | Training, checkpoints, validation reuse, bounded G6 search and candidate artifact storage reviewed in ML audit. |
| [use-cases/nebius-serverless-use-cases.md](use-cases/nebius-serverless-use-cases.md) | Historical draft flagged | July task boxes do not reflect current endpoint delivery; secure/learned workflows remain planned. |

## Validation

The final tree contains 110 docs Markdown files, including the new index, status
snapshot and this ledger. Static checks covered 1,160 local links and 76 heading
anchors across 120 active documents, with no unresolved targets or moved paths.
All 87 Mermaid diagrams rendered; the four substantively changed diagrams were
visually inspected. Both existing offline release-packaging tests passed.
No training, scoring, cloud mutation or final-test access was performed.
