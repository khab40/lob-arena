# Shared dependency refresh

Ticket: [Bug #397](https://github.com/khab40/lob-arena/issues/397), child of
[Story #58](https://github.com/khab40/lob-arena/issues/58), Project #3.
Existing dependency PR: [#372](https://github.com/khab40/lob-arena/pull/372).

As a platform operator, I want a shared frontend/website dependency refresh to
keep both products reproducibly buildable, so that maintenance preserves their
existing capabilities.

Scoped delta: synchronize the five website specifiers already updated by #372.
No intended application behavior change. The frontend lockfile remains shared;
security patches and overrides, product routes and deployment policies remain
the existing owners' contracts. No dependency is added.

Reuse: `frontend/package.json`, `website/package.json`, the symlinked website
lockfile, `frontend/test/shared-lockfile.test.mjs`, existing pnpm 10.30.3 scripts,
frontend CI and public-website CI. Do not weaken frozen installation.

Assumptions: both manifests intentionally share dependency definitions, as
enforced by the existing regression. Package release compatibility is verified
by the existing tests/builds. No product rewrite, cloud/model execution,
deployment, merge or cleanup authorization is granted.

```gherkin
Feature: Reproducible shared dependency refresh
  Scenario: AC-01 Both consumers accept the shared lockfile
    Given the five dependency updates in PR #372
    When frontend and website install with their frozen shared lockfile
    Then both installs succeed
    And both manifests use matching dependency specifiers

  Scenario: AC-02 Preserve existing security dependency controls
    Given the reviewed dependency patches and overrides
    When the website manifest is synchronized
    Then those patches and overrides remain unchanged

  Scenario: AC-03 Preserve both application builds
    Given the synchronized manifests and locked dependency versions
    When existing frontend and website verification runs
    Then their tests, lint and builds pass
```

Verification uses existing unit/build/browser workflows; no model runtime or
gated data is required. Exact reviewed commit/diff and focused results are
retained under root `outputs/chore-deps-20261013/`.

| Scenario | Implementation/contract | Test/check | Evidence | Status |
| --- | --- | --- | --- | --- |
| AC-01 | Both manifests and shared lockfile | `frontend/test/shared-lockfile.test.mjs`: shared frontend and website lockfile uses matching dependency specifiers; both frozen installs | `outputs/chore-deps-20261013/pr372-verification.json` (pins baseline, diff and spec hashes) | Pass (focused) |
| AC-02 | Existing `pnpm` controls | Compare both `pnpm` definitions with pre-repair head | `outputs/chore-deps-20261013/pr372-verification.json` (pins baseline, diff and spec hashes) | Pass (focused) |
| AC-03 | Existing product build/test scripts | Frontend/website unit, lint, build, browser CI | `outputs/chore-deps-20261013/pr372-*-tests.log`, `pr372-*-lint.log`, `pr372-*-build.log`; `pr372-ci.json` after publication | Pass (focused and CI; receipt pins verified head) |

CI pass above is pinned to dependency head `7c9bc2e126d52fa856e8648bbdc13985f6a132d1`
in `outputs/chore-deps-20261013/pr372-ci-pre-traceability.json`. This status-only
update changes no dependency or product bytes. Each subsequent publication head
requires fresh CI before merge; its result is retained in `pr372-ci.json`.
