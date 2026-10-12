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

In scope: backend-verified Google identity, application sessions, one prepared
campaign, existing Transformer/LightGBM saved decisions, a bounded anomaly snapshot,
evidence-grounded explanation, durable save/readback and protected export.
Out of scope: fresh model scoring, new training, #25 cascade, live feeds, arbitrary
uploads, broad source catalogue, tournaments, resumable event replay, multiworkspace
administration, production qualification and #24's original MLflow reconciliation.

Dependencies: approved private saved-score custody; Google web client configuration,
allowed identities and the exact local or shared origin; existing explanation configuration
when an LLM is used. Missing configuration must produce a visible unavailable state.
No demo fallback may grant access to a shared deployment.

Assumptions: the shared deployment exposes only this bounded demo surface. Other
Arena controls and WebSockets may be unavailable there; they must not expose an
unauthenticated alternative. The existing local research interface remains usable
under its original direct-loopback guard. A deterministic explanation fallback is
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

1. Restore a narrow backend identity/session boundary and deny alternative access.
2. Reuse the pinned saved-score loader through the protected demo contract.
3. Capture one anomaly and connect explanation to that immutable snapshot.
4. Persist and verify a bounded result bundle; add the guided UI and export.
5. Independently review each coherent iteration, run focused tests and CI, then
   prepare the concrete deployment and end-to-end rehearsal.

Use inert identity, evidence and explanation fixtures locally; no local model
execution is needed for this increment. Real Google sign-in and any remote LLM call
are separate integration checks. Declare exact remote call/resource bounds before
execution and use applicable Nebius CLI skills for Nebius operations. This document
grants no cloud mutation, data-access expansion, spend, merge or cleanup approval.

The [local CEO runbook](../operations/local-ceo-playback-demo.md) describes the
approved local surface and rehearsal procedure. It does not replace this contract.
The following mapping records verification of the implemented increment, not full
scenario acceptance with actual Google identity and original campaign custody.

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

| Scenario | Contract or implementation | Check | Retained evidence | Status |
| --- | --- | --- | --- | --- |
| CEO-AC-01 | `CEOAuth`; Google verification and opaque session | A: `test_http_login_cookie_session_and_logout`, `test_official_google_verifier_signature_and_claims_without_network`, `test_unrelated_unquoted_json_cookie_preserves_login_poll_expiry_and_logout`; Auth browser: `Google callback enters the workspace and logout removes its contents` | B, F, R | Inert/mock pass; actual Google integration pending |
| CEO-AC-02 | `CEOAccessBoundary`; session and user isolation | A: `test_session_expiry_and_current_allowlist_removal`, `test_alternative_routes_denied_even_after_login`, `test_cross_site_mutation_and_websocket_refusal`; J: `test_missing_session_denies_before_any_original_or_artifact_reads`, `test_another_authenticated_subject_cannot_read_explain_save_or_export`; Journey browser: `CEO-AC-02/09 replacement account clears captured and saved evidence` | B, F, R | Inert/mock denial and isolation pass; actual rehearsal pending |
| CEO-AC-02b | Local backend and development/preview proxy guards | A: `test_local_forwarded_origin_and_host_refusal_before_reads`, `test_direct_remote_peer_denied`, `test_missing_google_config_visible_and_denies`; [`frontend/test/ceo-loopback-proxy.test.mjs`](../../frontend/test/ceo-loopback-proxy.test.mjs): `denies remote or unknown original peers despite forged local headers`, `guards the preview server before its inherited demo proxies` | B, F, R | Inert local/shared boundary pass; actual local integration pending |
| CEO-AC-03 | Pinned saved-score verifier and fixed paired window | J: `test_fixed_original_window_preserves_ordinals_targets_timestamps_and_both_scores`, `test_existing_pinned_verifier_reads_only_invented_custody_and_refuses_later_change`; Journey flow | B, F, R | Invented custody/mock pass; original-custody playback pending |
| CEO-AC-04 | Reverification and safe unavailable response | J: `test_changed_custody_refuses_fresh_reads_and_capture_without_private_path_leak`, `test_missing_journey_configuration_is_visible_unavailable`, `test_no_original_transformer_alert_means_unavailable_campaign`; Journey browser: `CEO-AC-04 unavailable custody shows a safe operator action` | B, F, R | Inert/mock refusal pass; original-custody integration pending |
| CEO-AC-05 | Immutable captured snapshot and paired context | J: `test_capture_keeps_exact_selected_row_paired_context_and_immutable_hash`, `test_lightgbm_alert_capture_uses_same_original_window`; Journey browser: `CEO-AC-05 same-account polling preserves its immutable captured snapshot`; Journey flow | B, F, R | Inert/mock pass; original-custody rehearsal pending |
| CEO-AC-06 | Snapshot-bound factual `deterministic_fallback` | J: `test_explicit_factual_fallback_and_repeated_explain_save_reopen_export_are_durable`; [`frontend/test/ceo-journey.test.mjs`](../../frontend/test/ceo-journey.test.mjs): `explanation and reopened evidence keep exact snapshot binding and actual fallback mode`; Journey flow | B, F, R | Labelled fallback verified with fixtures; actual rehearsal pending |
| CEO-AC-07 | Durable verified user/workspace-owned saved bundle | J: `test_explicit_factual_fallback_and_repeated_explain_save_reopen_export_are_durable`, `test_another_authenticated_subject_cannot_read_explain_save_or_export`; Journey flow | B, F, R | Fixture save/readback/export pass; actual rehearsal pending |
| CEO-AC-08 | Bounded requests and durable failure handling | J: `test_save_before_explanation_is_refused`, `test_fsync_failure_retains_partial_and_never_reports_save_success`, `test_corrupt_intermediate_or_saved_bytes_refused_without_save_success`, `test_unsafe_mutation_refused_before_original_capture`, `test_count_and_byte_budgets_fail_before_another_artifact`; Journey browser: `CEO-AC-08 failed save cannot enable download or claim retained evidence` | B, F, R | Inert/mock failure boundaries pass; actual rehearsal pending |
| CEO-AC-09 | Durable session revocation and expiration | A: `test_google_session_opaque_durable_logout`, `test_session_expiry_and_current_allowlist_removal`, `test_unrelated_unquoted_json_cookie_preserves_login_poll_expiry_and_logout`; Auth browser: `server expiration clears the workspace without a browser session fallback` | B, F, R | Inert/mock pass; actual Google lifecycle pending |
| CEO-AC-10 | Reviewed local journey and separately approved deployment | Actual sign-in/playback/capture/explain/save/reopen/export receipt with source build and explanation mode | Actual receipt not yet retained | Pending/gated; no actual original-custody end-to-end receipt |

Actual Google integration, original-custody end-to-end rehearsal, CI/publication
and deployment remain pending. The first original-data S3 HEAD failure has no
established cause in this increment; it does not establish that original custody
is missing or invalid. Full #90/#91 acceptance and #24 MLflow closure stay open.
A passing narrow demo does not establish fresh scoring, LOBSTER robustness,
cascade value, production
latency or completed story acceptance.
