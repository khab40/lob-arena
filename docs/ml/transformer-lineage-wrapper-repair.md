# Transformer metadata operator repair — 2026-09-29

Parent: [Story #24](https://github.com/khab40/lob-arena/issues/24), Feature #16 / Epic #15, Project #3. Continuation after merged PR #261.

The local replacement-audit orchestration wrapper checks Path(app.__file__) against backend/app/__init__.py. The repository uses a native namespace package, so app.__file__ is None. The wrapper raised TypeError before credential lookup or any S3 GET. Phase-one grant at version 137 requires approved abort removal; no automatic retry.

As a platform operator,
I want the complete audit wrapper preflight exercised without credentials or network,
So that package-layout failures are caught before temporary access is granted.

```gherkin
Feature: Pinned audit runtime preflight
  Scenario: Accept the pinned namespace package
    Given the approved backend snapshot uses a native namespace package
    When the complete operator wrapper is exercised with inert credentials and transport
    Then runtime validation succeeds and calls only the substituted transport
  Scenario: Reject a foreign package origin
    Given an app package or imported app module outside the approved snapshot
    When the operator wrapper checks its runtime
    Then it fails before credential lookup or transport
  Scenario: Do not reuse an aborted approval
    Given the replacement attempt has an abort record
    When the operator wrapper is invoked again
    Then it fails before credential lookup or transport
```

Plan: preserve failed wrapper and zero-GET evidence; complete approved grant removal; validate namespace/module paths instead of assuming __init__.py; run the entire wrapper with inert injected credential and collector substitutes; keep the abort interlock so a new exact authorization is required. No cloud retry, payload read or model execution.

## Verified outcome

The approved replacement failed in local orchestration, before credential lookup
or the pinned collector. `app.__file__` is `None` for this repository's native
namespace package. No metadata GET occurred. The abort rule was honored; no retry
was attempted. Operator removal was independently verified by Nebius MCP at
bucket version 138: the original two rules and all other settings were restored
within 400.130141 seconds. [Evidence](../evidence/transformer-lineage-operator-repair-20260929.json).

The versioned `scripts/collect_transformer_lineage_metadata.py` checks package
search paths and imported module origins under the pinned snapshot, including
native namespaces. Duplicate paths to that same snapshot are harmless; foreign
paths fail. The credential lookup routine now resides in the SHA-bound operator;
its client factory comes from the verified backend. The ignored historical helper
is never loaded or executed.

The proposal must bind both the backend Git tree and operator script SHA-256.
An exclusive per-phase attempt marker is created before runtime checks; a failure
consumes that attempt. An existing abort marker prevents reuse. The retired local
wrapper is disabled and its original bytes are preserved.

Sixteen inert operator tests cover complete execution with native namespaces,
foreign origins, changed script, expired grants or changed approval, malicious
ignored helpers, fixed credential selectors, failed lookups, ambiguous responses,
wrong reader identity and consumed attempts. All 219 focused tests pass. A separate
blocked-network probe validates all 321 backend files and completes the operator
path using a fresh main-history checkout, with credentials and collection replaced
by inert substitutes. No real credentials or objects are read.

The metadata audit and source/window proof remain incomplete. Review this repair
and a new exact one-attempt proposal before any further grant. This PR authorizes
no cloud retry, GPU work or final-test access; G8/G9 stay closed.

The [r2 proposal](../evidence/transformer-lineage-replacement-r2-proposal-20260929.json)
binds the repaired operator script and unchanged collector backend. It requests
115 new GETs; the cumulative bound remains 116 because this wrapper abort read
zero objects. Its fresh output root preserves both aborted attempts. The original r2 approval is retained with a review-hold marker; it was never
executed. The amended proposal changes executable bindings and requires exact
approval before any grant, credential lookup or collection.

## P1 review corrections — Bug #265

[Bug #265](https://github.com/khab40/lob-arena/issues/265) is a child of Story #24
in Project #3. The mutable ignored helper could execute arbitrary top-level code
or return a substituted client before origin checks. Both inert attack cases
reproduced before the patch and pass after the helper execution path was removed.
A third inert reproduction confirmed cached bytecode could override verified source.
Preflight now rejects extra runtime files, and imports neither write caches nor
use an external cache prefix. The credential routine preserves the already tracked MysteryBox version selectors,
45-second lookup timeout, reader identity check and pinned S3 client settings.

As a platform operator,
I want every executed audit component bound to durable approved source,
So that review and approval cover the actual code used for collection.

```gherkin
Feature: Complete audit executable binding
  Scenario: Ignore an altered historical helper
    Given a historical helper contains executable code or a substituted client
    When the approved metadata operator runs
    Then the historical helper never executes
    And credentials use only the bound routine and pinned client
  Scenario: Reject invalid development credentials
    Given credential lookup fails or returns an ambiguous or wrong identity
    When the operator prepares collection
    Then no collection occurs and the phase cannot retry
  Scenario: Resolve the approved backend from main history
    Given a fresh checkout containing merged main history
    When the backend pin is resolved and its files are verified
    Then the approved backend tree is available and matches every runtime file
```

Plan and verification: remove ignored-code execution, exercise both attacks and
legitimate credential behavior with inert substitutes, then bind the same backend
tree to merged `8d93e3d`. A fresh single-branch clone confirms that `4b5b511` is absent
while `8d93e3d` resolves to the identical tree. Script SHA-256, rather than a temporary
PR commit, binds operator bytes. [P1 evidence](../evidence/transformer-lineage-p1-review-20260929.json).

The commit-size finding is not reproduced: published commits `98939fa`, `fbccb4b`
and `0e6dc19` changed 170, 178 and 92 lines respectively, each within the 200-line
limit. Their history is retained. No new cloud attempt has started.
