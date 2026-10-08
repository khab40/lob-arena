@/Users/akhabalov-da_1/.codex/RTK.md

# Operator execution preferences

- For future Transformer holdout execution packages, explicitly select
  `RetainingReadbackStore` for independent result collection and verification.
  Retain verified publication bytes and their original version/size/SHA-256
  receipts, plus the exact request verifier-input responses, before returning
  them to the verifier. Use a new private directory per authorized collection
  under root `outputs/` or the approved external evidence store, outside
  disposable worktrees; keep retained payloads out of public publication.
  Recovery uses `OfflineReadbackStore` with separately retained pinned settings.
  Keep the original frozen collector, approved package identities/hashes and
  historical evidence unchanged. This rule grants no additional access, run,
  replacement or spend authorization. See
  `docs/ml/transformer-holdout-execution-package.md`
  (operator instruction, 2026-10-08).

- For new public Job evidence, export a separate non-executable view with
  `scripts/public_job_evidence.py`; preserve the exact approved package and its
  hashes in the authorized evidence store. Keep repository-scoped Gitleaks and
  ggshield publication hooks enabled; never scan private custody with the API or
  bypass a failed scan. See `docs/operations/public-evidence-secret-prevention.md`
  and Bug #341 (operator prevention approval, 2026-10-07).

- Before building, uploading or submitting a Nebius Job image, verify that the
  repository portion is at most 64 characters. Keep the full immutable digest
  in the Job image reference; use separate repository and 64-character digest
  fields for labels. Never fall back to a mutable tag. This failure has recurred
  three times; consult `docs/operations/digest-pinned-jobs.md` and Bug #285.
  The 65-character `.../transformer-research` repository fails; `.../tr` passes
  with the identical digest. Enforce the boundary locally before cloud calls.

- Research priority (operator instruction, 2026-10-02): validate Transformer
  against frozen LightGBM before further platform maintenance. The existing
  MLflow VM may remain running if needed under the operator-managed cost policy.
  Preserve durable experiment artifacts when online tracking is unavailable;
  reconcile MLflow later. This does not authorize final-test access or promotion.

- For transient orchestration failures, use up to three retries with increasing
  per-attempt timeouts, capped at 120 seconds (operator instruction, 2026-10-02).
  Default short-call schedule: initial 30 seconds, then 60, 90 and 120 seconds.
  Preserve overall workload/shutdown budgets and exact access/run scopes.
  Reconcile ambiguous mutations before retrying; do not duplicate completed work
  or retry deterministic configuration, authentication or validation failures.

- Run future agent-initiated model workloads on Nebius Serverless Jobs, including
  synthetic rehearsals, fixture generation that trains models, and pre-production
  tests that exercise training, scoring, or the frozen evaluation runtime.
  The operator requested this on 2026-09-15; see `docs/g8-source-sdk.md`.
- Use the local machine for orchestration, code edits, static checks, and artifact
  inspection. Prepare explicit resource, timeout, Job-count, and spend bounds
  before cloud runs, and retain runtime identities and execution evidence.
- Preserve the frozen candidate and separate authorization gates for final-test
  access and replacement evaluation.
- Start each new PR from updated `main`. Keep each commit at or below 200 changed
  lines. This limit applies per commit, not per PR. Keep one coherent change,
  including its tests and relevant documentation, in one PR with multiple small
  commits as needed. Do not split one change across multiple PRs merely to satisfy
  the commit-size limit. Use isolated worktrees when the root checkout is in
  concurrent use.

# Independent review after each iteration

- Operator instruction (2026-10-06): after every small coherent iteration,
  obtain a review from a separate agent before starting the next iteration,
  publishing changes, building/uploading an execution image or running cloud work.
  An iteration includes its implementation, focused tests and relevant docs,
  configuration or execution packaging; review corrections are iterations too.
- The reviewer must be independent of the author of the changes and review the
  exact commit or captured diff, acceptance criteria and applicable environment
  constraints. Check failure/boundary cases, source/artifact lineage and resource,
  API or permission limits where relevant. Keep the review narrowly scoped.
- Give the reviewer a read-only task. It may inspect code/evidence and run inert
  checks; it must not mutate Git/cloud resources, read credentials/final payloads,
  or execute model training/scoring. Existing Nebius workload rules still apply.
- Retain a review receipt in the project root's `outputs/`: reviewer identity,
  reviewed commit/diff hash, scope, findings, verification and disposition.
  A review with no actionable findings must be recorded explicitly.
- Resolve actionable P0/P1/P2 findings and obtain a separate-agent re-review of the
  correction before proceeding. Record why any reported finding is inapplicable;
  do not silently dismiss it or treat an unreviewed change as approved.
- Require this review in addition to focused tests, CI and human approval gates.
  Keep related iterations and corrections in the same open PR. Do not merge,
  delete resources or expand execution/access authorization through this process.

# Project tickets and hierarchy

- Always link work to its corresponding ticket in
  [GitHub Project #3](https://github.com/users/khab40/projects/3). Identify the
  ticket before implementation and include its URL in the work plan, PR
  description (when applicable), and completion report.
- For a fix, create a new Bug ticket, add it to Project #3, and attach it as a
  sub-issue of the appropriate existing user story or feature. Record the defect
  and observable acceptance criteria, and link the fix to that Bug ticket.
- Organize planned work using **Epic → Feature → User Story**, with actual
  parent/sub-issue relationships. Place each user story under the appropriate
  feature and each feature under the appropriate epic.
- If a new feature or user story is needed, prepare its proposed scope,
  acceptance criteria, and parent placement, then ask for operator approval
  before creating it or implementing that new scope. Existing explicit approval
  for the same scope applies; do not ask again.
- After approval, create the ticket, add it to Project #3, and park it in the
  project's backlog under the approved parent. Approval to create or park a
  ticket does not itself authorize implementation.

# Branch and worktree lifecycle

- Use `main` as the only permanent development branch. Default to one active
  human/agent task branch; additional task branches need a concrete concurrent
  task, with its purpose and owner recorded. Dependabot and explicitly retained
  recovery branches are separate from this active-work limit.
- Before creating a branch or worktree, inspect the root checkout, existing
  branches/worktrees, and the task's PR state. Reuse the existing branch and
  worktree for the same open task. Do not create one per prompt, commit, review
  correction, or CI retry. Never reuse a merged branch for new commits.
- Fetch current `origin/main` before starting a new PR. Use the project-root
  checkout for sequential work when it is clean and unused by another session.
  Create an isolated worktree only for actual concurrent work or to preserve
  another task's edits. Do not switch or modify another session's checkout.
- On first publication, set the task branch's upstream to its matching
  `origin/<task-branch>`, not `origin/main`. Never push task commits to `main`.
- Keep related implementation, tests, and documentation in one PR. Split PRs
  only for independently scoped changes or an explicit operator request, never
  merely to satisfy the 200-changed-lines-per-commit limit.
- Maintain `outputs/workspace-lifecycle.md` in the project root as the shared
  local inventory. Record each task branch/worktree, purpose, owner/session
  (or explicitly unknown), PR/status, retention reason, and next cleanup trigger.
  Refresh it at task start, branch/worktree creation, PR completion, and cleanup.
  Revalidate against Git/GitHub; the inventory is not authoritative live state.
  Preserve other sessions' entries when updating it.
- Store durable run evidence in the project root's `outputs/` or the approved
  external evidence store, not solely inside a disposable worktree. Record the
  source commit and artifact paths. Before removing a worktree, archive valuable
  ignored/untracked evidence and local configuration outside it, then verify
  archive contents and file checksums. Regenerable caches need not be archived.
- Treat cleanup as part of PR completion. After a merge or closure, inspect the
  branch tip, PR outcome, worktree ownership/activity, edits, and ignored files.
  A closed unmerged PR or an ahead count after a squash merge is not sufficient
  deletion evidence. Never delete new commits or another session's active work.
- Honor existing explicit merge/deletion approvals, including their conditions;
  do not ask again for the same authorized targets. Without applicable approval,
  prepare the exact branch/ref/worktree targets and preservation evidence, then
  request cleanup approval in the PR-completion response. Do not silently defer
  cleanup or report it complete while approved removal is still outstanding.
- Automatic deletion after merge is enabled on GitHub; it does not clean local
  branches, remote-tracking refs, or worktrees. After authorization, remove unused
  worktrees, delete reviewed local branches, and prune only approved refs whose
  remote branches are confirmed absent. Revalidate exact targets before acting.
  If only branch deletion is authorized, retain its files/worktree and record any
  detached checkout as pending worktree cleanup rather than forgetting it.
- Keep each recovery/backup branch only with a recorded reason and review trigger.
  Prefer a verified Git bundle and artifact archive for retired work; creating
  backup branches is not a substitute for completing cleanup. R4 and frozen
  evaluation evidence require explicit disposition before retirement.
- At completion, report the actual root branch/status, branch/worktree counts,
  retained exceptions, and pending cleanup. If root `main` is behind, report the
  fast-forward needed; perform it only with applicable authorization, a clean
  unused checkout, and no local-only commits. Never reset away work to synchronize.

# Feature Stories & BDD Rules

Use this format for every new feature or meaningful behavior change.

## 1. User Story or Feature or large change (feat)

```text
As a <role>,
I want <capability>,
So that <value>.
```

Use a precise actor when possible, for example:
- surveillance analyst
- detector developer
- validation engineer
- platform operator
- researcher

## 2. Acceptance Criteria

Define observable behavior with Cucumber/Gherkin:

```gherkin
Feature: <feature name>

  Scenario: <specific behavior>
    Given <initial context>
    When <action or event>
    Then <observable result>
```

Use `And` / `But` only when needed.

Rules:
- Describe **behavior, not implementation**.
- Keep scenarios **testable and specific**.
- Prefer one behavior per scenario.
- Include important failure/boundary cases when relevant.
- Use repository/domain terminology.
- Do not invent ambiguous requirements; record assumptions explicitly.

## 3. Example

```text
As a validation engineer,
I want detector outputs evaluated against labelled LOB scenarios,
So that I can measure detection quality reproducibly.
```

```gherkin
Feature: Detector evaluation

  Scenario: Evaluate a completed labelled run
    Given a completed synthetic run with ground-truth labels
    And a detector has produced alerts
    When evaluation is executed
    Then precision, recall, and F1 are produced
    And results are linked to the run identifier
```

## 4. Required Workflow

```text
User need
→ User story
→ Gherkin scenarios
→ Implementation plan
→ Code
→ Tests
→ Verification
```

Do not treat code completion alone as feature completion.

A feature is done when:
- the story is satisfied;
- applicable scenarios pass;
- automated tests cover the behavior;
- required documentation and execution evidence are updated.

## 5. Definition of Ready

Before substantial implementation, identify:

```text
Actor:
Goal:
Value:
Acceptance scenarios:
Out of scope:
Verification method:
```

For pure refactors with no intended behavior change, a full story is optional. Instead record:

```text
Behavioral change: none.
Invariant: <behavior that must remain unchanged>
Verification: <tests/evidence proving it>
```
