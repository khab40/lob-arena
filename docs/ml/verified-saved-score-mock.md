# Verified saved-score research mock

Work: [#90](https://github.com/khab40/lob-arena/issues/90), [#91](https://github.com/khab40/lob-arena/issues/91), [Project #3](https://github.com/users/khab40/projects/3). This first integration chunk presents the already independently verified December holdout. It does not complete either story's broader campaign or secure shared-deployment acceptance.

As a research reviewer,
I want to inspect ordered saved predictions from both frozen detectors,
So that I can understand their anomaly evidence without running a model.

Actor: research reviewer. Goal: bounded ordered playback and frozen balanced decisions. Value: an evidence-backed first mock. Out of scope: fresh scoring, order-book reconstruction, shared deployment, model/threshold tuning and production promotion. Verification: inert corruption/access/order tests and mocked UI playback, followed by local inspection of the retained authenticated package.

```gherkin
Feature: Verified saved-score research playback
  Scenario: Inspect an authenticated session
    Given private retained predictions match the independently pinned verification and receipts
    And the operator enabled a direct loopback-only interface
    When the reviewer selects a session and Transformer or LightGBM
    Then bounded pages preserve the original target order
    And scores and alerts retain the detector's frozen balanced threshold
    And source identity and synthetic research-label limitations are visible

  Scenario: Control saved playback
    Given playback is paused at an original row ordinal
    When the reviewer resumes or changes speed
    Then playback continues in order without running a model
    And changing the selected session or detector resets playback to paused

  Scenario: Inspect a mixed replay shard
    Given an authenticated shard contains control and synthetic attack-window rows
    When the reviewer plays its saved predictions
    Then the catalog identifies its observed families
    And each row preserves its original family and target order

  Scenario: Reject invalid custody
    Given retained bytes, receipts, row alignment or verification identity differ
    When saved predictions are requested
    Then no prediction rows are exposed
    And the response omits private filesystem paths

  Scenario: Deny remote or unconfigured access
    Given the mock is disabled or the connection is nonlocal or proxied
    When saved predictions are requested
    Then access is denied
    And the private evidence is outside generic downloadable artifact roots
```

## Private local startup

The API is disabled by default. Use absolute paths. Keep the existing retained package unchanged, including `verification.json`, `result.json`, `predictions.json`, `target-ledger.json` and `receipts/`. Do not copy custody into a worktree or frontend fixture. Configure a fresh generic runtime directory disjoint from private custody; the default `../outputs` overlaps root custody and will be rejected before retention cleanup. A configured private directory remains protected even when playback is disabled ([Bug #359](https://github.com/khab40/lob-arena/issues/359)). The private directory must also be disjoint from `assets/screenshots`. Symlinked private paths are rejected.

From the repository's `backend/` directory, with the project root substituted for `/absolute/project`:

```sh
ARENA_OUTPUT_DIR=/absolute/project/outputs/demo-mock-runtime \
RESEARCH_SAVED_SCORES_ENABLED=true \
RESEARCH_SAVED_SCORES_DIR=/absolute/project/outputs/transformer-holdout-verifier-repair-20261007/offline-replay-r2 \
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-proxy-headers
```

From `frontend/`, use a separate terminal:

```sh
VITE_API_BASE_URL=http://127.0.0.1:8000 pnpm exec vite --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/research-predictions`. Do not use a tunnel, shared proxy, public bind or deploy this local mock as an authentication substitute. Backend denial is authoritative; browser checks supplement it. Shared sensitive-data deployment still needs #91's backend authentication and authorization.

## Evidence and API contract

The reviewed verification SHA-256 is `329158009e8de6b73ff7571acd414cab5cbcfcc760edd8963d61884349a81869`; selected-settings SHA-256 is `2efbed46a82470d86107886041c5eab05265aa89c390f10bce557a9c838b05ab`. These pins come from maintained source, not self-declared local manifests or client input. The verified inventory binds every publication's original version, size and SHA-256, including its local receipt. The loader authenticates all required bytes before exposing any row, checks exact ledger pairing, unique targets and the ordered population digest, and never loads weights or final-input artifacts.

`GET /api/research/saved-scores/campaigns` returns the single allowlisted campaign, opaque session IDs, both detector thresholds and provenance. `GET /api/research/saved-scores/campaigns/{campaign_id}/rows?session_id=…&detector=transformer&offset=0&limit=100` returns at most 100 rows. It preserves original per-shard order and timestamp ties; nanosecond timestamps are decimal strings to avoid browser precision loss. `source_ordinal` and `target_id` trace a row to the original paired file. Invalid evidence returns 503, disabled access 404, nonlocal/proxied access 403 and invalid page bounds 422. Successful responses use `Cache-Control: no-store`.

Catalog `sessions` identifies replay shards, not independent base sessions. Each shard lists its observed `families`; control and attack-window rows can coexist, so its descriptor is `mixed` when needed ([Bug #361](https://github.com/khab40/lob-arena/issues/361)). Per-row families remain visible. The runtime guard uses the same case/trailing-slash route matching as the router ([Bug #360](https://github.com/khab40/lob-arena/issues/360)).

Both detectors' scores come from the same authenticated paired prediction file. The checkpoint hash shown belongs to Transformer; the original frozen G8 LightGBM probabilities were independently paired by the historical verifier. No baseline rescoring occurs. Alert equality uses `probability >= threshold`: Transformer `0.996423148187864`, LightGBM `0.5769230769230769`. Only balanced mode is supported by this first mock.

The UI says **saved research predictions**. Its pacing is rows/second, not simulated exchange time or measured event-to-alert latency. Labels are synthetic research labels, not evidence of real market abuse. Data covers one December date and three base sessions; Transformer uses 60 features plus history versus LightGBM's 31, so attention's independent contribution remains unknown. Fresh inference, broader unseen sessions, operational measurements and MLflow/cost closure follow as separate PRs.
