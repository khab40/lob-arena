# Transformer integration: five separate PRs (2026-10-08)

Operator instruction: implement the five listed workstreams in at least five PRs. This approves their engineering scope. It does not supply exact authorization for additional model workloads, access grants, spending, merges or deletion.

## PR 1 — verified saved-score backend/GUI mock

Tickets: [#90](https://github.com/khab40/lob-arena/issues/90), [#91](https://github.com/khab40/lob-arena/issues/91), [Project #3](https://github.com/users/khab40/projects/3).

As a research reviewer,
I want to replay independently verified saved Transformer and LightGBM predictions,
So that I can inspect their anomaly evidence without rerunning either model.

Actor: research reviewer. Goal: selectable calibrated scores, original row order and frozen balanced thresholds. Value: a reproducible first mock. Out of scope: fresh inference, order-book reconstruction, model selection, threshold tuning, shared deployment, live trading and production promotion.

```gherkin
Feature: Verified saved-score research playback

  Scenario: Inspect an authenticated saved session
    Given the operator enabled the loopback-only mock with private retained evidence
    And the evidence matches the independently pinned verification and publication receipts
    When a reviewer selects a session and detector
    Then bounded pages preserve the original target order
    And alerts use that detector's frozen balanced threshold
    And the page identifies saved research predictions and their limitations

  Scenario: Resume a saved session
    Given playback is paused at an original row ordinal
    When the reviewer resumes or changes playback speed
    Then playback continues from that ordinal without scoring a model
    And selecting another detector resets playback to a paused state

  Scenario: Refuse invalid evidence
    Given a publication, receipt, ordered ledger or verification pin differs
    When the reviewer requests saved predictions
    Then no prediction rows are exposed
    And the API reports evidence unavailable without private paths

  Scenario: Keep the mock local and private
    Given the mock is disabled or the request is nonlocal or proxied
    When a client requests saved predictions
    Then access is denied
    And private evidence outside the generic artifact root is not downloadable there
```

Implementation: stdlib-only authenticated loader for the retained paired JSON and ledger; one fixed allowlisted holdout identity, opaque session IDs, decimal-string nanosecond timestamps, GET-only bounded API. Explicitly disabled by default. Evidence and generic artifact roots must be disjoint; reject symlinks. Loopback peer/host/origin enforcement and rejection of forwarding headers supplement a required loopback bind with proxy headers disabled. This is a local research interface, not completion of #91's shared-deployment authentication.

Frontend: separate research page/client; begin paused, bounded page requests, small rows/second speed whitelist, stale-request cancellation, no Nebius status/model/tournament/websocket requests. Do not reuse heuristic detector confidence or create invented market events. Show source hashes, calibrated score, threshold, alert, symbol/family and synthetic research-label context. No retained private rows in fixtures, Git or public exports.

Verification: invented inert metadata fixtures, corruption/schema/path/nonlocal/page boundary tests; focused backend tests; frontend helper tests, typecheck/build/lint and mocked Playwright interactions. Independently review each coherent implementation/correction and retain exact patch receipts under root outputs. Locally inspect the existing authenticated retained package after the loader passes; no cloud read or model execution is necessary.

## PR 2 — fresh causal inference adapter

Tickets: [#24](https://github.com/khab40/lob-arena/issues/24), #90. Connect the governed 60-feature order plus missingness and 64-row causal history to the immutable selected checkpoint, train-only normalization, temperature and operating point. Preserve shard resets, cutoffs, masks and exact target identities. Export alerts into the canonical runtime contract. Test boundary handling with inert structures; prepare an exact Nebius parity/streaming package using RetainingReadbackStore. Execute model verification only after exact Job/access/spend approval. Do not count saved-score playback as fresh inference.

## PR 3 — operational measurements

Tickets: #24, #90 and relevant infrastructure acceptance under [#21](https://github.com/khab40/lob-arena/issues/21). Measure complete event ingestion → feature/history construction → inference → calibrated decision → backend delivery → visible alert latency. Report p50/p95/p99, throughput, warmup, batching, hardware, resource use and actual comparable cost. Compare both detectors on identical rows and declared runtime conditions; include preprocessing and idle costs. Prepare separate bounded measurement authorization; do not infer event-to-alert latency from historic GPU inference time.

## PR 4 — additional unseen-data research and controlled ablations

Ticket: #24; propose any new child stories and their Gherkin acceptance before creation if scope is not already covered. Inventory available Nasdaq sessions and distinguish already-exposed dates from unseen dates. Freeze broader-session and realistic-negative labeling/split protocol before looking at outcomes. Compare matched features/history, with attention versus a non-attention temporal control, under comparable search/seed budgets. The current Transformer has 60 features plus history versus LightGBM's 31: existing results do not isolate attention gains. Prepare exact bounded Nebius execution and spend proposals; require approvals before data access/model runs. Persist every attempt and limitations, including unsuccessful results.

## PR 5 — research closure and lineage/cost reconciliation

Tickets: #24 and relevant MLflow acceptance under [#19](https://github.com/khab40/lob-arena/issues/19)–[#21](https://github.com/khab40/lob-arena/issues/21). Bind selected checkpoint, full hyperparameters, ordered features, normalization, calibration, decisions, datasets, images and code to verified MLflow artifacts without refitting. Reconcile actual spend against commitments and operator policy, distinguishing estimates and unknown costs. Resolve remaining #24 acceptance explicitly; record continue/stop/promotion disposition and remaining limitations. No production promotion is implied.

Dependency order: PR 1 can ship now; PR 2 precedes PR 3; PR 4 needs a frozen research protocol and new authorization; PR 5 closes only the acceptance actually verified. Each remains independently reviewable and starts from updated main after the preceding required merge. Independent review and CI supplement human approval; they do not authorize merges or cloud expansion.
