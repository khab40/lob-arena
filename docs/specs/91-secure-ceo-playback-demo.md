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

