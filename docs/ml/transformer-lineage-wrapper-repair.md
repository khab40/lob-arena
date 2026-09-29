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
paths fail. After loading the historical credential helper it restores the search
path and validates imports again before calling its credential function.

The proposal must bind both the backend Git tree and operator script SHA-256.
An exclusive per-phase attempt marker is created before runtime checks; a failure
consumes that attempt. An existing abort marker prevents reuse. The retired local
wrapper is disabled and its original bytes are preserved.

Eight inert operator tests cover complete execution with native namespaces,
foreign origins, changed script, expired/missing approval, search-path restoration
and consumed attempts. All 211 focused tests pass. A separate offline probe uses
the actual 321-file pinned backend and actual historical helper imports, with
credential/collector substitutes and network/credential CLI calls blocked. It
reaches the expected substituted transport without object reads or credentials.

The metadata audit and source/window proof remain incomplete. Review this repair
and a new exact one-attempt proposal before any further grant. This PR authorizes
no cloud retry, GPU work or final-test access; G8/G9 stay closed.
