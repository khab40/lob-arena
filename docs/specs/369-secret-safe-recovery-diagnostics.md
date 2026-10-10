# Secret-safe recovery diagnostics

Canonical specification for [Bug #369](https://github.com/khab40/lob-arena/issues/369),
a child of [Story #24](https://github.com/khab40/lob-arena/issues/24) in
[Project #3](https://github.com/users/khab40/projects/3). Related implementation
and evidence remain in [PR #368](https://github.com/khab40/lob-arena/pull/368).

As a validation engineer,
I want fixed, secret-safe failure provenance from metadata recovery,
So that I can diagnose a failed collection without repeating unknown requests.

Actor: validation engineer. Goal: preserve observable failure stage and counts.
Value: bounded, reviewable diagnosis while protecting private custody.
Reason: the first recovery attempt retained no stage after its subprocess wrapper
replaced fixed errors and its entry point discarded their provenance. Its exact
credential and HEAD attempt counts remain unknown. No body GET can have begun
because validated HEAD receipt persistence precedes every body destination.

In scope: a distinct diagnostic successor package, fixed stage/reason receipts,
subprocess cleanup, inert boundary tests and an exact reviewed read-only proposal.
Out of scope: body recovery, numerical execution, final-data access, new credentials,
permissions, retries, resource mutation, promotion, merge or deletion.
Dependencies: existing selector and selected-checkpoint identity pins, installed
Nebius CLI and skills, private root evidence custody, independent review.
Assumptions: original full recovery packages and failed custody remain byte-identical.
The [#24 specification](24-governed-transformer.md), frozen execution package and
existing metadata collector retain their subjects; this specification grants no
additional execution or access authorization.

```gherkin
Feature: Secret-safe recovery diagnosis

  Scenario: AC-01 Retain stage and request counts
    Given a reviewed diagnostic package and exclusive private custody
    When an allowed CLI operation is attempted
    Then an immutable stage intent precedes launch
    And result or terminal failure records its ordinal and intended, started, responded and validated counts

  Scenario: AC-02 Protect secrets and preserve failure provenance
    Given cancellation, timeout, CLI failure or invalid metadata
    When subprocess cleanup completes
    Then an allowlisted stage and fixed reason identify the failure
    And no raw output, exception text, credentials, headers, arguments, selectors or URLs are retained

  Scenario: AC-03 Enforce a diagnostic-only scope
    Given a separately pinned diagnostic plan
    When diagnosis is requested
    Then at most two original selector reads and one original pinned checkpoint HEAD occur
    And no GET, body file, mutation, retry or verified artifact collection occurs
    And local grounding and all calls obey finite declared deadlines

  Scenario: AC-04 Fail closed on custody failure
    Given failed intent, result or terminal receipt persistence
    When diagnosis terminates
    Then success is not returned
    And original packages and prior evidence remain unchanged
```

The proposed successor uses a 360-second orchestration bound and at most 60 seconds
per call, including the existing one-second cleanup reserve. These are request
execution bounds, not a monetary cap. Known authentication/permission signatures
may be classified in memory; all other command failures use a fixed unclassified
reason. Raw output remains unavailable to public publication and diagnostic files.

Verification uses invented credential sentinels, CLI responses and inert processes.
Cover both selectors, reader identity drift, malformed responses, wrong HEAD
version/size, missing credentials, permissions, timeout/cancellation, unexpected
exceptions and receipt-write failure. No fixture executes a model or live request.
Exact independent review must pin this file, runner, plan, tests and preserved
historical packages before any diagnostic execution is proposed.

| Scenario | Implementation | Test/check | Evidence | Status |
| --- | --- | --- | --- | --- |
| AC-01 | Distinct private diagnostic runner | Stage ordering and exact-count fixtures | Root outputs/governed-transformer-closure-20261009; successor receipt pending | Pending |
| AC-02 | Allowlisted failure journal and cleanup | Sentinel absence and failure-code fixtures | Same successor receipt; no raw outputs published | Pending |
| AC-03 | Externally pinned diagnostic plan | Zero GET/body/mutation/retry and deadline assertions | Exact reviewed plan and execution receipt pending | Gated |
| AC-04 | Exclusive private custody | Persistence failure and unchanged-original checks | Preservation hashes and independent review pending | Pending |
