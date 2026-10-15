# Bug #394: model workload placement

Ticket: [#394](https://github.com/khab40/lob-arena/issues/394), under #91 and
[Project #3](https://github.com/users/khab40/projects/3). Canonical policy:
`AGENTS.md` and `docs/operations/g8/g8-source-sdk.md`.

As a platform operator, I want ordinary local and GitHub checks to run only
reviewed inert tests, so model workloads retain their approved Nebius boundary.

Defect: ordinary backend/LightGBM/G8 targets reach training/scoring through
fixtures when ML dependencies are installed. Dependency absence is insufficient.
The retained independent audit identifies 82 model-reaching test definitions
across 15 modules, including all parametrizations. Original assertions remain
unchanged. Audit: root `outputs/ceo-demo-completion-392-20261013/ci-workload-audit.json`.

The operator-approved 15 October #392 recovery delivers WORKLOAD-AC-01/02/05:
reuse static source/AST inventory generation, externally pinned classification
and pre-fixture pytest selection. Keep mixed-module inert checks. Unknown or
changed sources/classifications refuse before test imports. Every inventory
update requires independent source/classification review before execution.

The optional signed model-runner framework is preserved in the old continuation
and excluded from this recovery. Ordinary pytest cannot enable numerical tests
through an environment flag or supplied authorization object. WORKLOAD-AC-03/04
remain incomplete, requiring their separately reviewed execution package and
actual authorized Nebius results. This bounded increment does not close #394.

```gherkin
Feature: Model workload placement
  Scenario: WORKLOAD-AC-01 Keep default checks inert
    Given reviewed source including a model-reaching fixture
    When ordinary pytest, Make or GitHub CI runs with ML dependencies installed
    Then model-reaching tests are excluded before fixture setup
    And mixed-module inert tests retain their assertions
  Scenario: WORKLOAD-AC-02 Refuse unknown or changed source before collection
    Given a pinned reviewed source inventory
    When a test, helper, application source or classification changes
    Then checks fail before importing test modules
  Scenario: WORKLOAD-AC-03 Require actual admitted Job proof
    Given a proposed numerical test execution
    When exact admitted source, image and actual native Job proof are absent
    Then numerical execution remains unavailable
  Scenario: WORKLOAD-AC-04 Preserve model tests in the bounded Job
    Given a separately approved and verified CPU Job execution package
    When its original numerical assertions run within the approved bounds
    Then exact source, runtime, results and independent readback are retained
  Scenario: WORKLOAD-AC-05 Report separate verification honestly
    Given passing inert CI and incomplete numerical verification
    When acceptance is reported
    Then numerical status remains explicitly incomplete
```

Verification: reuse `test_ci_workload_policy.py` with invented AST/fixture
checks and unchanged model-source conservation. Check default exclusion even
with a model module present, parameter selection, unknown/tampered sources,
classification pins and refusal of authorization overrides. No model runtime
is executed by those checks. Source/classification review and current-head CI
remain separate from the historical audit and any numerical qualification.

| Scenario | Check/evidence under root outputs/ceo-codebase-recovery-20261015 | Status |
| --- | --- | --- |
| WORKLOAD-AC-01/02 | `checks.json`, `source-review.json`: focused policy tests, reviewed inventory and unchanged 82 model definitions | Local pass; CI pending |
| WORKLOAD-AC-03/04 | Preserved separate runner; exact admitted Nebius execution/readback | Excluded from recovery; incomplete |
| WORKLOAD-AC-05 | Workflow names/summary, Make messages and this acceptance mapping; `source-review.json` | Static review pass; CI pending |
