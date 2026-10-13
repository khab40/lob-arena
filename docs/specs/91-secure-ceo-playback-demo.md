# Secure CEO playback demo

Tickets: [#91](https://github.com/khab40/lob-arena/issues/91) and
[#90](https://github.com/khab40/lob-arena/issues/90), in
[Project #3](https://github.com/users/khab40/projects/3).

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
The following mapping records the local saved-playback increment. It distinguishes
inert failure checks, authentic browser integration and the remaining review/CI gates.

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
Fresh backend test and image-smoke CI results are required; both scenarios are
pending until those checks pass for the corrected source.

| Scenario | Implementation | Focused check | Evidence | Status |
| --- | --- | --- | --- | --- |
| CEO-AC-11v | Existing `JavaArenaClient` metrics, invented shared transport response | `test_java_arena_client_records_proxy_metrics` (completed, HTTP 404/422/503, unavailable) | Root `outputs/ceo-playback-demo-20261012/full-product-ci-validation1/checks.json` | 42 focused inert checks pass; independent review and fresh CI pending |
| CEO-AC-12v | `app.runtime_smoke --minimal-image` | `test_minimal_smoke_accepts_google_auth_without_verifier_invocation`, rejection/import/callability/engine-authority cases in `test_runtime_smoke.py` | Same correction receipt; original failing CI retained | Inert inventory checks pass; actual minimal-image CI pending |

| Scenario | Full-product correction verification | Evidence | Status |
| --- | --- | --- | --- |
| CEO-AC-01/02/02b/09 | Session denial, existing HTTP methods, Java and active WebSocket expiry/revocation; account-state reset | New exact-diff checks and review receipt required | Pending |
| CEO-AC-03/04/05 | Existing Saved Research with authentic fixed window, original offsets and thresholds; source-only failure | New browser and original-custody rehearsal receipt required | Pending |
| CEO-AC-06/07/08 | Saved snapshot input in existing Investigation Team; same exact retained evidence contracts | New browser and export verification receipt required | Pending |
| CEO-AC-11 | All original screens/controllers and normal backend initialization; ordinary and authenticated browser suites | New full-product browser/backend receipts required | Pending |
| CEO-AC-10/12 | Full existing four-service release, isolated outputs/ports, exact images and immutable tag | Reviewed packaging, fresh CI and local release rehearsal required | Pending |

The original three saved publications were recovered under bounded approval;
the temporary exact-key viewer rule was removed with the original nine rules
preserved. Historical failed attempts remain retained. Shared Nebius deployment,
full #90/#91 acceptance and #24 MLflow closure stay open.
A passing narrow demo does not establish fresh scoring, LOBSTER robustness,
cascade value, production
latency or completed story acceptance.
