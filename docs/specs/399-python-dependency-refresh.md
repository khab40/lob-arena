# Locked Python dependency refresh

Ticket: [Bug #399](https://github.com/khab40/lob-arena/issues/399), child of
[Story #19](https://github.com/khab40/lob-arena/issues/19), Project #3.
Existing dependency PR: [#373](https://github.com/khab40/lob-arena/pull/373).

As a platform operator, I want locked packages to match declared requirements,
so that tested and packaged runtimes use the proposed dependency releases.

Scoped delta: refresh the backend lock for MLflow skinny 3.17.0, retaining the
existing PR's MLflow and Jobs google-auth updates. No application behavior is
intentionally changed beyond those releases. Reuse `backend/uv.lock`, existing
uv tooling, requirement consumers, security-floor/build-context tests, and
required image CI. No new framework, dependency or workflow is introduced.

Invariants: retain Jobs `databricks-sdk==0.67.0`, patched Protobuf 7 floors with
the `<8.0.0` ceiling, and existing endpoint/security floors. Historical frozen
execution packages and archived runtime proof remain unchanged. Deployment and
MLflow lineage contracts remain owned by existing documentation, including
[`docs/ml/mlflow-tracking-server.md`](../ml/mlflow-tracking-server.md).

Assumptions: a frozen install consumes the checked-in lock; package resolution
and image compatibility must be verified, not inferred from a green stale lock.
Out of scope: model scoring/training, cloud Job/image submission or upload,
live deployment, credentials/final-payload access, promotion, merge and cleanup.

```gherkin
Feature: Consistent locked dependency refresh
  Scenario: AC-01 Locked client agrees with its declared release
    Given the backend declares MLflow skinny 3.17.0
    When the lock is checked against the manifest
    Then the check passes
    And the lock resolves MLflow skinny 3.17.0

  Scenario: AC-02 Preserve compatible runtime boundaries
    Given the intentional Databricks and Protobuf constraints
    When the proposed dependency releases are resolved
    Then those constraints and existing security floors remain intact

  Scenario: AC-03 Build the updated runtime consumers
    Given the refreshed lock and updated Jobs requirements
    When the existing required ML imports and Jobs image checks run
    Then the locked ML client and Jobs runtime import successfully
```

Exact diff/spec/source hashes, checks and independent review are retained under
root `outputs/chore-deps-20261013/`; no numerical model execution is needed.

| Scenario | Implementation/contract | Test/check | Evidence | Status |
| --- | --- | --- | --- | --- |
| AC-01 | `backend/pyproject.toml`, `backend/uv.lock` | `uv lock --project backend --check`; lock metadata inspection | `outputs/chore-deps-20261013/pr373-verification.json` | Pass (inert) |
| AC-02 | Existing requirements/security constraints | `test_dependency_security_floors.py`, `test_serverless_docker_build_contexts.py`; inert Jobs resolver | `outputs/chore-deps-20261013/pr373-tests.log`, `pr373-verification.json` | Pass (inert) |
| AC-03 | Existing backend/Jobs image consumers | CI LightGBM governed data boundary: Verify ML dependency imports (`--extra ml`); Build jobs image | `outputs/chore-deps-20261013/pr373-ci.json` | CI gate pending |

Both Jobs requirement sets are resolved for Linux x86_64/Python 3.11, matching
their Dockerfiles. The market-preparation image is outside the existing CI
matrix: metadata compatibility is verified here; its runtime build is not
claimed. AC-03 covers the locked ML client and the existing Jobs image check.
