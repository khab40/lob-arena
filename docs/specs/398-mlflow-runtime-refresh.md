# MLflow runtime refresh

Ticket: [Bug #398](https://github.com/khab40/lob-arena/issues/398), child of
[Story #19](https://github.com/khab40/lob-arena/issues/19), Project #3.
Existing dependency PR: [#370](https://github.com/khab40/lob-arena/pull/370).

As a platform operator, I want the authentication package to match the declared
MLflow server version, so that routine maintenance builds a consistent image.

Scoped delta: align `mlflow[auth]` with the proposed v3.17.0 base image. Reuse the
existing Dockerfile, deployment version regression and CI image import check.
Behavioral change: none beyond the already proposed dependency release.
Invariant: auth, storage, service isolation, entrypoint and budget policies
remain unchanged. Deployment contracts belong to
[`docs/ml/mlflow-tracking-server.md`](../ml/mlflow-tracking-server.md).
No new dependency, runtime replacement or parallel workflow is introduced.

Assumptions: package and base image versions must agree, as required by existing
tests. In scope: image packaging and inert validation only. Out of scope:
deployment, database migration, model execution, credentials/final-payload
access, promotion, merge and cleanup. This spec grants none of those actions.

```gherkin
Feature: Consistent MLflow runtime dependencies
  Scenario: AC-01 Retain declared server version after auth installation
    Given a base image declaring MLflow 3.17.0
    When its authentication extra is installed
    Then the installed MLflow remains version 3.17.0

  Scenario: AC-02 Preserve existing deployment boundaries
    Given the current authentication and storage configuration
    When the dependency packaging is refreshed
    Then the deployment boundaries and entrypoint remain unchanged
```

Verification reuses the deployment regression and required CI image import
smoke check; no server deployment, authenticated request or numerical inference
is necessary. Exact source/diff/spec pins and independent review are retained
under root `outputs/chore-deps-20261013/`.

| Scenario | Implementation/contract | Test/check | Evidence | Status |
| --- | --- | --- | --- | --- |
| AC-01 | `deployments/mlflow/Dockerfile` | `test_mlflow_metadata_artifacts_auth_and_hardening_are_explicit`; CI Build mlflow image version import | `outputs/chore-deps-20261013/pr370-verification.json`, `pr370-ci.json` | Pass (focused and CI; receipt pins verified head) |
| AC-02 | Existing deployment files and policies | `backend/tests/test_mlflow_deployment.py`; diff against original PR/base | `outputs/chore-deps-20261013/pr370-tests.log`, `pr370-review.json` | Pass (focused) |

CI pass above is pinned to dependency head `aa3f83b6fbf77a71429b9dbe12a4d38299a16025`
in `outputs/chore-deps-20261013/pr370-ci-pre-traceability.json`. This status-only
update changes no dependency or product bytes. Each subsequent publication head
requires fresh CI before merge; its result is retained in `pr370-ci.json`.
