# Secure CEO demo: playback and fresh detection

## Approved main recovery — 15 October 2026

Ticket: [#392](https://github.com/khab40/lob-arena/issues/392), under #91 in
[Project #3](https://github.com/users/khab40/projects/3). The operator explicitly
approved point 1 of the codebase recovery proposal on 15 October. This bounded
increment restores the secure saved-playback application to current `main`.
Fresh detection, source generation, model execution, deployment and full parent
acceptance remain outside this increment and tracked by #392/#90/#91.

As an authorized demo operator, I want the existing secure Arena and verified
saved evidence available from main, so I can run a reproducible interim demo
while the original fresh-detection backlog remains explicit.

Reuse the 42 reviewed secure-demo commits through `f3f6f20`, already rebased on
main `393ba47`: CEOAuth, CEOJourney/JourneyStore, the original React routes and
controllers, shared request transport, Java proxy, verified saved-score loader,
ITCH validation and loopback release configuration. Preserve current main's
dependency updates, original model packages, historical tags and evidence.
The former continuation and its uncommitted work are preserved in a verified
Git bundle and checksum-verified archives under root
`outputs/ceo-codebase-recovery-20261015/`; their source worktrees remain intact.

Apply the retained fixture corrections for [#393](https://github.com/khab40/lob-arena/issues/393)
and [#396](https://github.com/khab40/lob-arena/issues/396): await actual session
teardown and completed theme transitions before assertions. Product behavior,
assertions and retry policy are unchanged. Use the existing static inventory
and pytest selection for [#394](394-model-workload-placement.md), with numerical
execution kept outside ordinary CI. The separate model-runner implementation
is preserved with the old continuation; this recovery does not qualify it.

Acceptance reuses the scenario IDs below. No historical receipt establishes a
new exact-head pass. Final review checks the recovered source, preservation,
current dependencies, scoped test results and authentic browser evidence.

| Scenario IDs | Recovery verification | Root receipt | Status |
| --- | --- | --- | --- |
| CEO-AC-01–04/08/09 | Auth/backend boundary tests; allowed/denied entry, logout, expiry and workspace isolation | `checks.json`, `browser-rehearsal.json` | Pass for saved increment |
| CEO-AC-05–07 | Verified saved playback, capture, model switch, explanation, save/reopen and canonical browser export equality | `checks.json`, `browser-rehearsal.json` | Pass |
| CEO-AC-11; ITCH-AC-01–04 | Existing ordinary/authenticated screens, Java proxy and source readiness checks | `checks.json`, `browser-rehearsal.json` | Pass; no new ITCH import claimed |
| CEO-AC-10/12 (saved increment only) | Browser suite without retries, actual saved-flow rehearsal, independent review and final-head CI | `source-review.json`, `final-review.json`, `publication.json`; [PR #401](https://github.com/khab40/lob-arena/pull/401) | Local verification/review pass; final-head CI and tag indexed by publication receipt |
| WORKLOAD-AC-01/02/05 | Reviewed source inventory, excluded numerical fixtures and explicit CI status | `portable-review.json`, `checks.json`, `publication.json` | Local verification/review pass; final-head CI indexed by publication receipt |
| CEO-FRESH-01–04; WORKLOAD-AC-03/04 | Broader fresh journey and authorized numerical execution | Preserved continuation; #392/#394 | Excluded from approved recovery; incomplete |

Merge and cleanup require their exact-target operator approvals. Completion of
this bounded recovery must not close #392, #90 or #91 as fully delivered.

Receipts above are retained under root `outputs/ceo-codebase-recovery-20261015/`.
Verification: 267 focused inert backend tests, 69 frontend unit tests, lint/build,
and all 36 browser tests with zero retries passed. The authentic Google journey
saved/reopened original evidence and exported JSON equal to the server record.
The source review pins `f3f6f20` plus patch `958f740e8fe8a163fcaf753b2860d5a6366d2160b1adb8c6e0f747f0a0b8a908`.
The portable inventory correction preserves all prior hashes under Python
3.11/3.12/3.14; its 15 focused policy checks and independent review passed.
No model workload or new cloud deployment ran. `publication.json` records the
final reviewed head, CI run, immutable recovery tag and merge state. Publication
evidence remains distinct from local checks and does not qualify fresh detection.

Tickets: [#91](https://github.com/khab40/lob-arena/issues/91) and
[#90](https://github.com/khab40/lob-arena/issues/90), in
[Project #3](https://github.com/users/khab40/projects/3).

The [fresh-detection successor](#fresh-detection-successor--13-october-2026)
records the operator's clarified release target. The saved-playback increment
below remains a delivered interim capability, with its original scope preserved.

## Saved-playback increment — 12 October 2026

Operator decision, 12 October 2026: deliver saved Transformer/LightGBM playback
first for this week's CEO demo; fresh scoring follows later. Start on localhost
with the existing Google configuration, then deploy to a Nebius VM separately.
This specification
owns that bounded increment. [PHASES Wave 4/5](../roadmap/PHASES.md) retains the
full story acceptance. [Verified playback](../ml/verified-saved-score-mock.md)
owns original score verification and ordering; its loopback interface remains
unchanged. [Investigator design](../architecture/ARD-0015-nebius-ai-investigation-team.md)
owns the existing explanation contract. Historical research packages stay frozen.

As an authorized CEO demo reviewer,
I want to inspect one verified research campaign, explain a captured anomaly and
save its evidence,
So that I can follow the product outcome without assembling private artifacts.

Actor: allowlisted Google user in one configured demo workspace.
Goal: Google sign-in → prepared campaign → saved predictions → captured anomaly
→ explanation → durable report and evidence export.
Value: one understandable, repeatable, evidence-backed demonstration.

In scope: preserve the existing application screens, controllers, backend services
and deployment stack; add backend-verified Google identity and application sessions,
one prepared campaign, existing Transformer/LightGBM saved decisions, a bounded
anomaly snapshot, evidence-grounded explanation, durable save/readback and protected
export to those existing surfaces. Existing capabilities retain their contracts
and configuration requirements. Disabled or unconfigured cloud services retain
their existing visible states; this increment grants no new execution or spend.
Out of scope: implementing fresh model scoring, new training, #25 cascade, new live
feeds, new ingestion or tournament capabilities, multiworkspace administration,
production qualification and #24's original MLflow reconciliation.

Dependencies: approved private saved-score custody; Google web client configuration,
allowed identities and the exact local or shared origin; existing explanation configuration
when an LLM is used. Missing configuration must produce a visible unavailable state.
No demo fallback may grant access to a shared deployment.

Assumptions: the demo preserves the existing full application behind the session
boundary, including its REST and WebSocket transport. Private prepared evidence
does not become generic Arena artifacts. The existing local research interface
remains usable under its original direct-loopback guard. A deterministic explanation fallback is
acceptable when explicitly labelled; it must not be described as a real LLM result.

Local-first refinement: an explicit local demo mode permits a configured HTTP
loopback origin with direct loopback backend access only. It rejects forwarded
headers and remote peers, still requires Google and application sessions, and
uses separate local cookies. The shared mode requires HTTPS and secure cookies;
the local exception cannot enable remote access. Local frontend API requests use
the same origin through a loopback development proxy. This refinement follows
the operator's local-first instruction and adds no cloud execution authorization.

Cookie compatibility correction ([Bug #377](https://github.com/khab40/lob-arena/issues/377)):
unrelated browser cookies must not invalidate an otherwise authorized application
session after Google login. Authentication paths use consistent cookie parsing;
duplicate or malformed application cookies remain refused. This restores intended
CEO-AC-01/02/09 behavior and does not change authorization or session duration.

Account replacement correction ([Bug #378](https://github.com/khab40/lob-arena/issues/378)):
when session polling changes the authenticated subject or workspace, the journey
must discard the previous account's captured evidence, explanation, saved records
and pending work before displaying the replacement account. Same-subject polling
preserves the current snapshot. This restores CEO-AC-02/09 isolation within the
approved demo workspace; it does not add identity or administration scope.

Frontend image packaging correction ([Bug #381](https://github.com/khab40/lob-arena/issues/381)):
the image build must retain the existing `dev/ceoLoopbackProxy.ts` dependency
imported by `vite.config.ts`. The frontend context currently excludes that file,
causing the production image build to fail while a full-checkout build passes.
Admit only that directory and exact file through the existing build-input allowlist.
The first correction's `!dev/` also admitted descendants under Docker's parent
matching semantics; its custom static checker incorrectly reported them excluded
(finding `CEO-PACKAGING-I1-01`). Preserve that packet as failed exclusion evidence.
Order the rules as `!dev/`, `dev/**`, then `!dev/ceoLoopbackProxy.ts` so the exact
dependency is admitted after descendants are excluded. Verify invented sibling,
dotfile and nested paths using pinned official `moby/patternmatcher` v0.6.0,
including both parent-matching APIs; do not use the incompatible custom parser.
Docker's [context syntax](https://docs.docker.com/build/concepts/context/#syntax)
and [matcher source](https://github.com/moby/patternmatcher/blob/v0.6.0/patternmatcher.go)
own those matching semantics.
Preserve CEO-AC-02b's local access guard and CEO-AC-10's reviewed-build prerequisite;
this changes packaging only, with no proxy, authentication or inference behavior
change. Verify context selection and the existing proxy tests, lint and build;
independent correction review precedes any image build or CI rerun. Original-custody
end-to-end rehearsal and full story acceptance are tracked separately below.

Existing-interface correction ([Bug #383](https://github.com/khab40/lob-arena/issues/383)),
operator instruction 12 October: use the existing Arena interface, not a separate
CEO screen. Keep the application sidebar, account/theme controls, Arena cockpit
and Control Panel investigation presentation. The standalone route must not
replace the application shell. Its historical functional rehearsal is retained;
it does not accept the rejected presentation.

Further operator correction, 12 October: preserve the developed and tested UI and
backend capabilities. Merely reusing the shell while replacing its pages or
disabling backend initialization does not satisfy this request. The earlier
prepared-page override and its functional receipts remain historical, unaccepted
for this full-product release. Reuse the same separate task branch/PR; issue the
verified build through an immutable release tag, with isolated release configuration.

Keep one existing route table, actual Arena/Data Ingestion/Scenario Generator/
Control Panel controllers and normal backend initialization. Add prepared playback
as a source in Saved Research, and a saved-anomaly input in the existing
Investigation Team section. Reuse protected capture/explain/save/readback/export
contracts; do not construct order-book features, trades, heuristic confidence or
synthetic incident timelines from saved score rows. A custody failure affects
only that source. It must not block the other working screens.

Key protected frontend state by workspace and Google subject; logout, expiry and
account replacement clear it and abort pending work. Session protection covers
existing FastAPI and direct Java API/WebSocket alternatives, including frames and
commands after revocation. Preserve existing route methods and request limits.
Validate private roots before generic store initialization or retention. Keep
Java/agent internal ports private in release configuration. Reuse the existing
four-service Compose stack and dependencies; correct only demonstrated packaging
gaps. Local-first verification uses inert fixtures and mock external services.
Fresh scoring and Nebius deployment remain separately gated.

Browser-runner correction for Bug #383 (finding `CEO-ARENA-I1-01`): the standard
frontend `test:e2e` command must exercise both ordinary Arena behavior and the
explicit prepared mode. A single server cannot enable both after the standalone
route stopped choosing the runtime. Use separate test projects and strict-port
fixture servers with explicit false/true demo flags; refuse reuse of an existing
server whose mode is unverified. This changes test orchestration only. The website
has its own browser configuration and is unaffected. Retain the initial CLEAR
review and supplemental P2; correction re-review is required before publication.

Fixture correction ([Bug #384](https://github.com/khab40/lob-arena/issues/384)):
the unchanged ordinary ingestion test still mocks retired discovery/import paths.
Align only its invented fixture with the maintained source-scoped client contract,
including both discovery sources, candidate source metadata and import depth 10.
Keep the exact 17-minute window, confirmed dataset deletion and unhandled-route
refusal. This restores ordinary-mode verification without changing ingestion,
authentication, model or cloud behavior. The default browser command must pass
all 33 cases (22 ordinary and 11 prepared); retain earlier failed attempts.

## Acceptance

```gherkin
Feature: Secure research playback demonstration
  Scenario: CEO-AC-01 Enter the demo through Google
    Given the operator configured Google and an allowed identity
    When that identity completes sign-in
    Then the backend verifies the identity before creating an application session
    And the reviewer enters the configured demo workspace

  Scenario: CEO-AC-02 Deny access outside an authorized session
    Given a missing, expired, revoked or disallowed application session
    When a client requests campaign rows, anomalies, explanations or exports
    Then the backend denies access before reading or exposing private evidence
    And alternate REST and WebSocket routes do not grant access

  Scenario: CEO-AC-02b Keep local demo access on loopback
    Given the operator enabled the explicit local Google demo mode
    When a remote peer, forwarded request or different origin requests access
    Then access is denied before private evidence is read
    And disabling Google does not create a fallback session

  Scenario: CEO-AC-03 Inspect authentic saved decisions
    Given the prepared campaign passes the existing pinned custody verifier
    When the reviewer selects a supported detector and plays its saved rows
    Then ordering, scores and frozen threshold decisions remain unchanged
    And the display identifies saved research predictions and synthetic labels
    And changing speed does not run a model

  Scenario: CEO-AC-04 Reject unavailable or changed evidence
    Given campaign custody is missing or fails verification
    When the reviewer opens the campaign or captures an anomaly
    Then no unverified rows or invented result are exposed
    And an actionable unavailable state omits private paths

  Scenario: CEO-AC-05 Capture an anomaly from original evidence
    Given an authenticated campaign contains a saved threshold alert
    When the reviewer selects that alert
    Then the backend captures its original bounded context and provenance
    And later playback or detector selection cannot change that snapshot

  Scenario: CEO-AC-06 Explain the captured evidence honestly
    Given the reviewer selected a captured anomaly
    When an explanation is requested
    Then the explanation uses that snapshot rather than the latest Arena state
    And the exact bounded input, output and actual LLM or fallback mode are retained
    And failure produces a visible failed or labelled fallback result

  Scenario: CEO-AC-07 Save and reopen a complete result
    Given an anomaly and its explanation are available
    When the reviewer saves the result and later reopens or exports it
    Then its original snapshot, explanation and identities are unchanged
    And the retained bundle is verified before reporting save success
    And exports require the authorized workspace session

  Scenario: CEO-AC-08 Refuse incomplete saves and unsafe requests
    Given a write failure, unsupported row, altered identifier or cross-site mutation
    When capture, explanation, save or export is requested
    Then the operation does not report success or expose another artifact
    And the reviewer can see the failure without credential or private-path leakage

  Scenario: CEO-AC-09 End application access
    Given an active application session
    When the reviewer logs out or its configured lifetime ends
    Then that session cannot read or mutate the demo afterward

  Scenario: CEO-AC-11 Preserve the existing product capabilities
    Given the operator enabled the authenticated demo release
    When the authorized reviewer uses existing application screens
    Then the existing navigation, theme, controllers and backend contracts remain available
    And prepared playback is additive in Saved Research and Investigation Team
    And unavailable prepared custody does not block other working screens
    And saved scores do not become invented order-book or incident features

  Scenario: CEO-AC-12 Release the existing full stack reproducibly
    Given a reviewed commit with passing focused checks and CI
    When the operator starts its isolated local release configuration
    Then the existing frontend, backend, Java kernel and agent services are used
    And an immutable release tag identifies that exact verified commit
    And writable runtime outputs are separate from retained private evidence
    And internal service ports cannot bypass the configured session boundary

  Scenario: CEO-AC-10 Rehearse the complete journey
    Given the reviewed build, approved deployment and prepared private campaign
    When the operator completes sign-in, playback, capture, explanation and save
    Then a reopened evidence bundle proves the demonstrated result
    And the retained receipt records the source build and actual explanation mode
```

## Delivery plan and verification

### Prepared journey contract (12 October refinement)

The first prepared window contains at most 64 original rows from one replay shard,
centred on its first Transformer threshold alert (up to 16 preceding rows).
Selection is a demonstration choice, not a new evaluation population. Both models
use that same window; original ordinals, target IDs, timestamps and decisions stay
unchanged. If no original Transformer alert is available, the campaign is unavailable.
The operator configures custody; browser requests cannot choose filesystem paths.
Every campaign read or capture verifies original custody again.

All following endpoints are below `/api/ceo-demo/`, require the application session,
use no-store responses and reject mutations without the exact configured origin:

| Endpoint | Behavior |
| --- | --- |
| `GET campaign` | Original catalog plus `prepared_window: {session_id, offset, limit}`. |
| `GET rows?detector=transformer` | Existing page contract for the fixed window; only the two supported detector IDs. |
| `POST anomalies` | Accept only `{detector, target_id}` for an original alert in that window; return an immutable snapshot. |
| `POST anomalies/{id}/explanation` | Retain and return a deterministic factual explanation of that snapshot, explicitly labelled `deterministic_fallback`. |
| `POST anomalies/{id}/save` | Verify the complete snapshot and explanation bundle on disk before returning the saved record. |
| `GET evidence` | List this user's saved record summaries. |
| `GET evidence/{id}` | Verify and reopen this user's complete saved record. |
| `GET evidence/{id}/export` | Download the same verified saved record as JSON. |

Snapshot schema: opaque `id`, `campaign_id`, selected `detector`, `threshold`,
original selected `row`, `paired_scores` (probability, threshold and alert for
each model), preceding original `context` (at most 16 rows), original `provenance`,
`workspace_id`, creation time and `snapshot_sha256`. Paired context contains only
saved scores and synthetic labels; it cannot imply order-book or trade evidence.
Explanation schema: `mode`, `input_sha256`, exact `input` snapshot, bounded `text`,
creation time and `explanation_sha256`. The explanation describes recorded scores,
thresholds and synthetic labels, and states the absence of fresh inference or
adjudicated market abuse. It makes no invented order, trade or market-abuse claim.
Saved record schema: `id`, `snapshot`, `explanation`, `saved_at` and
`record_sha256`; list summaries expose only `id`, `symbol`, `detector`, `saved_at`.
Hashes use the existing canonical JSON encoding with the hash field omitted.

Private durable files belong to the authenticated Google subject and configured
workspace. Identifiers are server-created opaque values; another user cannot read
or overwrite them. Exclusive creation, bounded reads, regular-file checks and
durable atomic writes protect both intermediate artifacts and saved records.
Readback verifies canonical bytes and embedded hashes; corruption or incomplete
writes fail without save success. Repeated explain/save returns the same verified
artifact. No browser-provided snapshot or explanation is accepted as evidence.

The guided UI offers play/pause and presentation speed, a model selector, alert
selection, capture, explanation, save, reopen and JSON download. Changing selection
cannot change an already captured snapshot. It always identifies saved research
predictions, synthetic labels and the actual explanation mode. This refinement
implements the existing bounded scope and does not authorize a remote LLM call.

1. Preserve existing routes/controllers behind the account-keyed Google/session gate.
2. Reuse Saved Research with a protected fixed-window source adapter; preserve the
   ordinary reader's local custody guard and original paging behavior.
3. Add saved-snapshot input and existing evidence actions to Investigation Team.
4. Restore normal backend services and protect all HTTP/Java/WebSocket alternatives;
   use existing transport libraries and preserve route contracts and private roots.
5. Independently review each coherent iteration, run focused tests and CI, then
   prepare the concrete deployment and end-to-end rehearsal.

Use inert identity, evidence and explanation fixtures locally; no local model
execution is needed for this increment. Real Google sign-in and any remote LLM call
are separate integration checks. Declare exact remote call/resource bounds before
execution and use applicable Nebius CLI skills for Nebius operations. This document
grants no cloud mutation, data-access expansion, spend, merge or cleanup approval.

The [local CEO runbook](../operations/local-ceo-playback-demo.md) describes the
approved local surface and rehearsal procedure. It does not replace this contract.
### Historical predecessor verification

The following mapping records the rejected prepared-page/backend predecessor.
Its passing functional checks remain historical evidence, not acceptance of the
current full-product release. The current mapping follows the validation correction.

Test references: **A** is [`backend/tests/test_ceo_auth.py`](../../backend/tests/test_ceo_auth.py);
**J** is [`backend/tests/test_ceo_journey.py`](../../backend/tests/test_ceo_journey.py).
**Auth browser** is [`frontend/e2e/ceo-auth.spec.ts`](../../frontend/e2e/ceo-auth.spec.ts);
**Journey browser** is [`frontend/e2e/ceo-journey.spec.ts`](../../frontend/e2e/ceo-journey.spec.ts).
**Journey flow** is its exact test `CEO-AC-03/05/06/07 play, capture, explain, save, reopen and export one fixed result`.

Evidence references are retained privately under root
`outputs/ceo-playback-demo-20261012/`, outside the disposable worktree:

- **B**: `journey-cookie-correction1/checks.json` records 168 inert backend cases
  and Ruff passing. Fixtures contain no original campaign payloads or real Google tokens.
- **F**: `journey-correction1-checks/node.log`, `browser-approved.log`, `lint.log`
  and `build.log` record 61 Node cases, 10 mocked browser cases, lint and build passing.
  `browser.log` retains a superseded sandbox failure; it is not passing evidence.
- **R**: `journey-iteration1-review-classifier_author.json` and
  `journey-correction1-review-runtime_review.json` retain independent review and
  resolution of both P2 findings, Bugs [#377](https://github.com/khab40/lob-arena/issues/377)
  and [#378](https://github.com/khab40/lob-arena/issues/378). The correction is CLEAR
  with no actionable P0/P1/P2 findings; its SHA-256 is
  `8f7294a1aa33c67f63123b387665afec849ae2cf3baa0f0b9b0e7ddd65dc66ab`.
- **P**: `frontend-image-packaging-correction1/checks.json` records the official
  matcher check (20 paths, 80 assertions), five proxy tests and lint passing. The
  unchanged production build carries forward from the original iteration. Its custom parser
  exclusion claim is invalidated by `frontend-image-packaging-iteration1-review-classifier_author.json`
  (P2 `CEO-PACKAGING-I1-01`); its five proxy tests, lint and production build remain
  passing evidence. Correction review is CLEAR; the fixed frontend image and all
  25 PR checks passed at predecessor commit `5214a74b670defb0a0571591213ac488fed8676a`
  ([CI run](https://github.com/khab40/lob-arena/actions/runs/38268949603)).
- **U**: `existing-arena-iteration1/checks.json` records the corrected existing
  interface's 61 Node checks, 11 mocked browser cases, lint and production build.
  The first browser attempt retains its compile/HMR-test failures; the corrected
  run passes. The HMR exception permits only the configured development server's
  exact root socket; market sockets and other API calls remain failures.
- **D**: `existing-arena-iteration1/browser-rehearsal.json` and
  `export-verification.json` record actual Google access, authentic original-score
  playback, capture, Control Panel navigation, labelled fallback, save, reload,
  reopen, export, detector comparison and logout/re-entry. The browser export equals
  the retained saved object and all three canonical hashes verify. This uses the
  recovered version-1 publications and runs no model. Temporary recovery access
  was selectively removed and independently read back before UI rehearsal.
  The rejected standalone UI's earlier functional receipt remains historical.
- **UR**: `existing-arena-iteration1-review-classifier_author.json` is the exact
  diff/spec independent review receipt. The current correction requires CLEAR
  review and fresh head CI before publication readiness is claimed.
- **U2**: `existing-arena-correction1/checks.json` owns verification of the default
  frontend browser command across both modes. The initial UI review is superseded
  for publication by `existing-arena-iteration1-ci-supplement-review-classifier_author.json`;
  `existing-arena-correction1-review-classifier_author.json` records correction review.

| Scenario | Contract or implementation | Check | Retained evidence | Status |
| --- | --- | --- | --- | --- |
| CEO-AC-01 | `CEOAuth`; Google verification and opaque session | A: `test_http_login_cookie_session_and_logout`, `test_official_google_verifier_signature_and_claims_without_network`, `test_unrelated_unquoted_json_cookie_preserves_login_poll_expiry_and_logout`; Auth browser: `Google callback enters the workspace and logout removes its contents` | B, F, R, U, D | Actual local Google integration and inert checks pass |
| CEO-AC-02 | `CEOAccessBoundary`; session and user isolation | A: `test_session_expiry_and_current_allowlist_removal`, `test_alternative_routes_denied_even_after_login`, `test_cross_site_mutation_and_websocket_refusal`; J: `test_missing_session_denies_before_any_original_or_artifact_reads`, `test_another_authenticated_subject_cannot_read_explain_save_or_export`; Journey browser: `CEO-AC-02/09 replacement account clears captured and saved evidence` | B, F, R, U, D | Inert/mock denial and isolation pass; local session integration pass |
| CEO-AC-02b | Local backend and development/preview proxy guards | A: `test_local_forwarded_origin_and_host_refusal_before_reads`, `test_direct_remote_peer_denied`, `test_missing_google_config_visible_and_denies`; [`frontend/test/ceo-loopback-proxy.test.mjs`](../../frontend/test/ceo-loopback-proxy.test.mjs): `denies remote or unknown original peers despite forged local headers`, `guards the preview server before its inherited demo proxies`; P: `config_dependency_included`, `unrelated_inputs_excluded` | B, F, R, P, U, D | Boundary checks and packaging review pass; predecessor image CI pass; fresh head CI pending |
| CEO-AC-03 | Pinned saved-score verifier and fixed paired window | J: `test_fixed_original_window_preserves_ordinals_targets_timestamps_and_both_scores`, `test_existing_pinned_verifier_reads_only_invented_custody_and_refuses_later_change`; Journey flow | B, F, R, U, D | Authentic original-custody playback and detector comparison pass |
| CEO-AC-04 | Reverification and safe unavailable response | J: `test_changed_custody_refuses_fresh_reads_and_capture_without_private_path_leak`, `test_missing_journey_configuration_is_visible_unavailable`, `test_no_original_transformer_alert_means_unavailable_campaign`; Journey browser: `CEO-AC-04 unavailable custody shows a safe operator action` | B, F, R, U, D | Inert refusal and authentic custody integration pass; original bytes preserved |
| CEO-AC-05 | Immutable captured snapshot and paired context | J: `test_capture_keeps_exact_selected_row_paired_context_and_immutable_hash`, `test_lightgbm_alert_capture_uses_same_original_window`; Journey browser: `CEO-AC-05 same-account polling preserves its immutable captured snapshot`; Journey flow | B, F, R, U, D | Original-custody immutable capture and detector-change preservation pass |
| CEO-AC-06 | Snapshot-bound factual `deterministic_fallback` | J: `test_explicit_factual_fallback_and_repeated_explain_save_reopen_export_are_durable`; [`frontend/test/ceo-journey.test.mjs`](../../frontend/test/ceo-journey.test.mjs): `explanation and reopened evidence keep exact snapshot binding and actual fallback mode`; Journey flow | B, F, R, U, D | Actual snapshot-bound labelled fallback and exact input binding pass |
| CEO-AC-07 | Durable verified user/workspace-owned saved bundle | J: `test_explicit_factual_fallback_and_repeated_explain_save_reopen_export_are_durable`, `test_another_authenticated_subject_cannot_read_explain_save_or_export`; Journey flow | B, F, R, U, D | Actual save, reload, reopen and browser export verification pass |
| CEO-AC-08 | Bounded requests and durable failure handling | J: `test_save_before_explanation_is_refused`, `test_fsync_failure_retains_partial_and_never_reports_save_success`, `test_corrupt_intermediate_or_saved_bytes_refused_without_save_success`, `test_unsafe_mutation_refused_before_original_capture`, `test_count_and_byte_budgets_fail_before_another_artifact`; Journey browser: `CEO-AC-08 failed save cannot enable download or claim retained evidence` | B, F, R, U | Inert/mock failure boundaries pass; no deliberate original-custody damage |
| CEO-AC-09 | Durable session revocation and expiration | A: `test_google_session_opaque_durable_logout`, `test_session_expiry_and_current_allowlist_removal`, `test_unrelated_unquoted_json_cookie_preserves_login_poll_expiry_and_logout`; Auth browser: `server expiration clears the workspace without a browser session fallback` | B, F, R, U, D | Inert expiry/revocation checks and actual logout/re-entry pass |
| CEO-AC-11 | Existing App shell, Arena and Control Panel; account-keyed controller above routes | Journey browser: `CEO-AC-11 existing Arena shell and Control Panel preserve original evidence without legacy work`; actual dark/light theme and route rehearsal | U, D, UR | Existing interface and navigation pass; exact correction review pending |
| CEO-AC-10 | Reviewed local journey and separately approved deployment | Fixed frontend image CI build and actual sign-in/playback/capture/explain/save/reopen/export receipt with source build and explanation mode | P, U, D, UR | Local journey pass; exact correction review and fresh head CI pending; shared deployment deferred |

The table above records predecessor verification only. The operator rejected its
prepared-page/backend override as insufficient preservation of the product.
The full-product correction requires new frontend, backend/transport and packaging
checks, independent review, fresh CI and an authentic rehearsal before release.

### Validation-only correction, 2026-10-13

Bug [#386](https://github.com/khab40/lob-arena/issues/386), under #91 in Project #3,
owns two stale backend checks exposed by CI run `38340617695` at `de524b08`.
Behavioral change: none. The invariant is the existing Java proxy metrics contract
and a Java-authoritative minimal image with the required Google authentication
import, without the retired Python engine/routes/contracts, gRPC or protobuf.
Reuse the shared `JavaTransport` test seam and existing runtime smoke command;
add no dependency, provider request, model execution or deployment scope.

```gherkin
Scenario: CEO-AC-11v Verify existing proxy metrics through the current transport
  Given an invented Java transport response or failure
  When the existing typed client completes its request
  Then the original response and outcome-labelled proxy metrics are verified
  And no external request is made

Scenario: CEO-AC-12v Validate the authenticated minimal application image
  Given the existing application with its required Google token verifier
  When minimal-image validation runs
  Then the verifier import succeeds without contacting Google
  And retired Python runtime components, gRPC and protobuf remain absent
```

Focused inert tests and independent exact-diff review precede publication.
Fresh backend test and image-smoke CI passed for corrected source `f168c305` in
[run 38342831278](https://github.com/khab40/lob-arena/actions/runs/38342831278).
All 25 PR checks passed. The backend failed-job retry addressed a pre-existing
watchdog race, not a product change; [Bug #387](https://github.com/khab40/lob-arena/issues/387)
remains open and must be fixed before #24's live MLflow VM work.

| Scenario | Implementation | Focused check | Evidence | Status |
| --- | --- | --- | --- | --- |
| CEO-AC-11v | Existing `JavaArenaClient` metrics, invented shared transport response | `test_java_arena_client_records_proxy_metrics` (completed, HTTP 404/422/503, unavailable) | Root `outputs/ceo-playback-demo-20261012/full-product-ci-validation1/checks.json` and `review-full_product_review.json`; CI above | Pass: 42 focused checks, independent CLEAR review and backend CI |
| CEO-AC-12v | `app.runtime_smoke --minimal-image` | `test_minimal_smoke_accepts_google_auth_without_verifier_invocation`, rejection/import/callability/engine-authority cases in `test_runtime_smoke.py` | Same correction receipts; original failing CI retained | Pass: inert checks, independent CLEAR review and actual backend image-smoke CI |

### Initial full-product draft, 13 October 2026

The original frontend, normal FastAPI backend, Java kernel and agent ran
locally from `f168c305ce865e3b0c91d11968079f28dbacf18a`. Runtime and image identities
are retained in root `outputs/ceo-playback-demo-20261012/release-local-20261013/`.
`rehearsal-v2.json` records actual Google access, original Data Ingestion and Arena,
64 original saved rows, capture, labelled deterministic explanation, durable save
and reload/reopen. `server-saved-verification.json` verifies the retained 3,636-byte
canonical bundle and all three hashes. It does not prove browser download.

Full-product CLEAR reviews are retained as `full-product-backend2-review-full_product_review.json`,
`full-product-frontend1-review-publication_review.json`,
`full-product-packaging2-review-full_product_review.json`,
`full-product-ci1-review-full_product_review.json`,
`full-product-fixture1-review-full_product_review.json`,
`full-product-proxy2-review-publication_review.json` and the validation review above.
The local topology's separate CLEAR preparation review is
`release-local-20261013/review-v2-full_product_review.json`.

Browser export, post-capture detector switching and logout/re-entry remain pending:
the download attempt timed out and the computer-use connection became unavailable.
Existing mocked browser and inert boundary tests pass but do not complete those
authentic steps. No model, LLM, import, deletion or new cloud workload was run.

The operator requested a running draft today. An immutable **draft** release tag
may identify this reviewed, CI-passing local increment while these steps remain
explicitly pending. This refines the full-rehearsal tag prerequisite for draft
delivery only; CEO-AC-10/12 and full story acceptance remain incomplete. Retain the
partial receipt, exact source/image identities and independent disposition before
tagging. Any documentation-only release commit requires fresh CI and proof that
the running application/build inputs are unchanged from the rehearsed source.

| Scenario | Full-product correction verification | Evidence | Status |
| --- | --- | --- | --- |
| CEO-AC-01/02/02b/09 | A: `test_existing_routes_are_session_protected_and_preserved`; `test_full_product_boundary.py`; account replacement and expiry browser cases | `full-product-backend2/checks.json` (299 inert checks), CLEAR backend/proxy reviews, 35-case browser CI and `rehearsal-v2.json` | Inert checks and actual Google/live no-cookie denial pass; actual logout/re-entry pending |
| CEO-AC-03/04/05 | J: fixed-window/capture tests; Journey browser fixed-window and source-only failure cases | CLEAR frontend review, 35-case browser CI and `rehearsal-v2.json` | Authentic 64-row playback, paired scores and capture pass; post-capture detector switching pending |
| CEO-AC-06/07/08 | J: durable explain/save/export and failed-write cases; existing Investigation Team saved input | Same browser CI; `rehearsal-v2.json`, `server-saved-verification.json` | Actual fallback, save, reload/reopen and server hashes pass; actual browser export pending |
| CEO-AC-11 | Journey browser: `CEO-AC-11 authenticated full product keeps its controllers alongside saved evidence`, `CEO-AC-04/11 unavailable prepared custody leaves ordinary screens working` | CLEAR backend/frontend/fixture reviews, 22 ordinary + 13 authenticated browser cases, actual original-screen observations | Pass for preserved capabilities under their existing configuration contracts |
| CEO-AC-10/12 | Full existing four-service release, isolated outputs/ports, exact images and immutable draft tag | CLEAR packaging/preparation reviews, 25-check CI, `runtime-identities.json`, `rehearsal-v2.json`; final release receipt required | Draft running locally; final documentation review/CI/tag pending; full rehearsal acceptance pending |

The original three saved publications were recovered under bounded approval;
the temporary exact-key viewer rule was removed with the original nine rules
preserved. Historical failed attempts remain retained. Shared Nebius deployment,
full #90/#91 acceptance and #24 MLflow closure stay open.
A passing narrow demo does not establish fresh scoring, LOBSTER robustness,
cascade value, production
latency or completed story acceptance.

### ITCH source readiness correction — Bug #389

Ticket: [#389](https://github.com/khab40/lob-arena/issues/389), child of #91 in
[Project #3](https://github.com/users/khab40/projects/3); existing PR #380.

As a demo reviewer, I want directory-only ITCH symbols identified before import,
so that I can select usable data without an avoidable failed job.

The bundled synthetic fixture has MSFT directory metadata but only AAPL order
events. Before the fix, discovery called both ready. Reuse `iter_records`, the existing
candidate invalid/errors contract, service refusal and Data Ingestion controls.
Do not add another UI or replay path or alter the original fixture's bytes.
Small-source event availability is checked only within explicit input/record
bounds. Incomplete checks never establish that a symbol has no events. Large
sessions keep their existing directory discovery path and import validation.
The additional scan accepts files up to 1 MiB and inspects at most 10,000
records, stopping after 1 MiB of framed payload (one final record may cross
that boundary). A budget stop means unknown availability, never empty.
ARD-0032 owns parsing/provenance; existing empty-window validation remains.

Assumptions/dependencies: locally configured source roots, approved source data,
existing adapter and session authorization. Also audit configured roots and
safe local/campaign metadata to explain the missing real Nasdaq data. Acquisition,
final-data recovery, cloud/model workloads and shared deployment are out of scope.

```gherkin
Feature: ITCH source readiness
  Scenario: ITCH-AC-01 Refuse a directory-only small source
    Given the bundled fixture contains MSFT directory metadata without MSFT order events
    When available sources are discovered
    Then MSFT has an invalid status and a reason identifying its missing events
    And the existing screen disables Import and the backend refuses an import job

  Scenario: ITCH-AC-02 Preserve usable source conversion
    Given the bundled fixture contains eight AAPL lifecycle events at 09:30
    When AAPL is imported for 09:30 through 09:31
    Then the existing aligned event and book outputs contain eight rows
    And empty windows and cross-symbol substitution remain rejected

  Scenario: ITCH-AC-03 Preserve bounded discovery
    Given a source exceeds the small-source size or inspection budget
    When its directory is discovered
    Then discovery does not finish a full-session event scan
    And an incomplete inspection does not mark any symbol empty

  Scenario: ITCH-AC-04 Refuse a truncated gzip source
    Given a small source has a truncated gzip trailer
    When discovery inspects its events
    Then the source is invalid with its validation error and no import job starts
```

| Scenario | Implementation/check | Evidence | Status |
| --- | --- | --- | --- |
| ITCH-AC-01 | `test_directory_only_symbol_is_refused_before_import_job`; browser `ITCH-AC-01 directory-only MSFT cannot import while AAPL remains usable` | Root `outputs/ceo-playback-demo-20261012/itch-readiness-389/iteration1/checks.json` | Focused checks, independent review and CI pass |
| ITCH-AC-02 | `test_fixture_normalizes_every_visible_lifecycle_transition`, `test_selected_symbol_never_reads_other_symbol_orders`; LOBSTER checks | Same retained iteration receipt | Focused checks, independent review and CI pass |
| ITCH-AC-03 | `test_large_source_skips_event_inspection`, `test_incomplete_event_inspection_does_not_mark_symbols_empty` (record/payload budgets) | Same retained iteration receipt | Focused checks, independent review and CI pass |
| ITCH-AC-04 | `test_truncated_gzip_is_invalid_instead_of_failing_discovery` | Correction receipt in `itch-readiness-389/iteration2/` | Focused check, correction re-review and CI pass |

Fix commit `4d183ac` passed all 25 checks in
[CI 38363316055](https://github.com/khab40/lob-arena/actions/runs/38363316055).
The independent correction review is retained in `iteration2/review-full_product_review.json`.
The local backend was restarted from that commit; direct fixture discovery shows
AAPL ready and MSFT invalid. Actual authenticated browser reinspection is pending.

The bounded source audit found only the 229-byte generated fixture in the root
and demo worktree's `data/nasdaq-itch`; their default roots contain no 2019 raw
session. The configured defaults are checkout-relative, and the thin local
release adds no research-corpus mount. C0–C4 prepared the 2019 research corpus
in cloud storage; C4 model-feature projections are not UI replay books. See
root `outputs/ceo-playback-demo-20261012/nasdaq-local-source-audit-20261013.json`
and the maintained [four-date data flow](../data/nasdaq-public-sample-v1-data-flow.md).
Actual private environment overrides and current cloud object availability were
not inspected. Any development replay recovery requires exact artifact/access
bounds; December final data remains governed separately.

## Fresh-detection successor — 13 October 2026

Operator clarification: the CEO release must attach the selected, trained,
calibrated and tested LightGBM and Transformer to the existing UI and backend.
The reviewer chooses one model per run; the result must come from that model's
fresh execution. Saved playback does not satisfy this successor. LLM explanation
is later work. This is an increment of existing #90/#91, not full story closure.

As an authorized CEO reviewer, I want to load a supported source, choose a frozen
detector and inspect its measured result, so that I can assess what it catches,
misses and falsely flags through the existing application.

Actor: allowlisted Google user; operator configures approved data and execution.
Goal: Google → data/mode → selected model → run → quality and detection evidence.
Value: a reproducible product demonstration with honest strengths and limitations.
Technical acceptance and metric definitions belong to
[frozen detector flow §6](../frozen-detector-release-and-demo-flow.md#6-observable-acceptance-for-implementation).
This section owns the corresponding existing-screen journey and presentation.

| Data choice | Evaluation meaning |
| --- | --- |
| Real historical | Unlabelled unless independent truth is provided; show alerts and evidence without invented FP/FN/F1. |
| Clean synthetic | Evaluator knows the generated control population; show false alarms and its denominator. |
| Synthetic with known attacks | Executed attack truth stays outside detector inputs; evaluate against the retained ledger. |
| Supported combination | Score all admitted compatible causal inputs; retain provenance, ordering and label coverage; compute quality metrics only on the supported labelled population. |
| Future source | Extend existing adapters when implemented and authorized; unavailable sources remain unavailable. |

Reuse plan: `DataIngestionPage` and existing source adapters/Java replay for data;
existing Arena controls, `FeaturePipeline` and causal Transformer windows for
events/features; governed `LightGbmV1Detector` and the reviewed #24 classifier
work for frozen model admission; existing evaluation, results and evidence
services for outcomes. Extend shared result components and existing navigation.
The #24 classifier currently accepts governed development batches and requires
CUDA; an adapter and independently verified parity are still required for this
journey. Preserve the frozen research package while adding that adapter.

In scope: the two selected models, bounded supported data modes, fresh causal
scoring, visible readiness/progress/failure, labelled metrics, retained evidence,
and a separate immutable release tag with an authentic end-to-end rehearsal.
Out of scope: retraining/retuning, #25 cascade, new feed acquisition, arbitrary
uploads, future connectors, production qualification and real LLM explanation.
Shared deployment follows the existing separately configured deployment gate.

Dependencies: exact frozen release custody, compatible features and causal history,
approved bounded execution and retained evaluator-only truth. Agent-initiated
model execution remains on Nebius Serverless Jobs under the existing resource,
timeout, access and spend rules. This specification is not execution approval.
Verification: inert API/UI contract tests; separately bounded numerical/parity
checks; independent review; CI; Google-to-result/export browser rehearsal.

```gherkin
Feature: Existing application with selected frozen detectors
  Scenario: CEO-FRESH-01 Choose a supported source and mode
    Given the reviewer has entered the existing workspace through Google
    When the reviewer selects historical, clean synthetic, attack synthetic or a supported combination
    Then the existing controls show its identity, availability and label coverage
    And unavailable choices explain what is missing before a run starts

  Scenario: CEO-FRESH-02 Run the selected frozen model
    Given a compatible source and a verified LightGBM or Transformer release
    When the reviewer starts a bounded run with the selected model
    Then the application displays that run's model identity and actual progress
    And warm-up, unavailable execution and failures cannot appear as successful detection

  Scenario: CEO-FRESH-03 Understand the measured result
    Given a completed run and its retained evaluation coverage
    When the reviewer opens its result in the existing application
    Then source, selected model, alerts and supported quality metrics appear together
    And counts, denominators, units and unavailable metrics are explicit
    And detailed provenance remains available without preceding the main outcome

  Scenario: CEO-FRESH-04 Rehearse and retain the tagged result
    Given the reviewed release preserves the existing screens and backend capabilities
    When Google entry, data selection, each model run, result, save, reopen, export and logout are rehearsed
    Then retained evidence binds those observations to the exact immutable release
    And the exported result matches the saved run and its selected model
```

| Scenario | Reused implementation / remaining work | Verification and evidence | Status |
| --- | --- | --- | --- |
| CEO-FRESH-01 | Existing ingestion/replay/scenario controls; common run binding pending | Source/mode and unavailable-path API/browser checks planned; no fresh-run receipt | Pending |
| CEO-FRESH-02 | Existing frozen loaders/features; model adapter and runtime bridge pending | Selected-model identity, causal parity and bounded numerical rehearsal planned | Pending |
| CEO-FRESH-03 | Existing evaluation/results/evidence components; common result presentation pending | Label-aware result fixtures and actual retained run readback planned | Pending |
| CEO-FRESH-04 | Existing auth, full stack, evidence save/export and release tooling | Authentic two-model rehearsal, independent review, exact-source CI and new tag pending | Pending |

The delivered `ceo-demo-20261012-r1` tag is the saved-playback draft. Its historical
research metrics do not describe a newly selected input or a newly executed run.
