# ARD-0041: MLflow readiness before Transformer execution

Status: Proposed; implementation prepared, operational verification pending.

Date: 2026-10-02

Tickets: [Story #19](https://github.com/khab40/lob-arena/issues/19), consumed by
[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).

## Context

Merged [PR #275](https://github.com/khab40/lob-arena/pull/275) implements the CPU
role-audit package. Its campaign requires a working governed MLflow plane before
execution. The earlier restore proved 60 tables and 19,521 rows, but did not prove
application writes or restored sequence allocation. The frozen LightGBM package
has seven verified artifacts, but its registry version and research alias remain
to be established. Transformer namespaces need four narrowly scoped permissions.

The existing deployment initializer rotates service passwords and reconciles
permissions by removal/replacement. That behavior cannot implement the approved
additive design. Repository MLflow versions also do not establish the deployed
version; an upgrade must not be hidden in a readiness check.

## Decision

1. Reuse the existing stopped MLflow VM and its actual deployed images. Validate
   imports, API signatures, synchronous logging, finite HTTP timeouts and zero
   SDK retries in that image before application mutations. Do not use the Mac's
   incomplete auth environment as runtime evidence.
2. Restore the retained backup into isolated PostgreSQL and MLflow containers.
   Neither container has network access or published ports; they communicate
   through a private Unix socket. Compare original table fingerprints before and
   after application startup, then verify authenticated metadata operations and
   increasing experiment/user IDs. No live database is replaced.
3. Verify the frozen LightGBM run, all dataset lineage and seven exact artifact
   hashes before creating one research lineage version and `research-baseline`
   alias. A reference to `governed/model.txt` is not a deployable MLflow flavor,
   production promotion, model reload or evaluation.
4. Add only missing exact Transformer grants: `governed-writer` EDIT and
   `prometheus` READ on the experiment and registered model. Inspect inherited
   roles and effective permissions first; conflicts stop the operation. Preserve
   prior grants, identities, passwords and defaults. REST hides password hashes,
   so credential preservation requires private database comparison.
5. Retain a metadata-only parent and child with durable creation intents. Verify
   writer logging and inert artifact roundtrip, exporter reads and HTTP 403 on
   its tag-write attempt against the same child. No second run is used to test
   denial. Ambiguous writes retain intent and stop automatic retries.
6. Persist both namespaces in repository bootstrap defaults and append them to
   existing VM allowlists without rewriting other values. Do not invoke the
   existing initializer or deploy/restart upgraded images for this operation.
7. Readiness requires independent application evidence, preserved state and
   verified VM shutdown. Unit tests and a model registry version alone cannot
   satisfy it. Exact CPU authorization follows readiness; GPU authorization
   follows a successful CPU role audit and its separate reviewed package.

## Alternatives and consequences

Reusing the initializer would violate password/grant preservation. Registering a
version without downloading its artifacts would bind names without verifying
content. Database row equality alone misses broken sequence allocation and API
authentication. Retrying mutation POSTs after timeouts can duplicate records.

The chosen design adds explicit probes and retained journals. It depends on
exclusive operator custody: MLflow aliases have no compare-and-set operation,
and an independent writer could invalidate a read-before-write check. The local
shutdown watchdog is not a provider billing cap; loss of the operator machine or
network still requires operator intervention.

G8/G9 remain closed. Unknown costs retain the existing operator-managed
disposition. Full closure of #19–#21, future campaign logging, deployment upgrade,
and serving qualification remain separate work.

## Related documents

- [Readiness design and acceptance](../ml/mlflow-readiness-design.md)
- [Readiness operation](../operations/mlflow-readiness.md)
- [Shared tracking plane](ARD-0027-shared-mlflow-tracking.md)
- [Same-run recovery](ARD-0039-same-run-mlflow-recovery.md)
- [Transformer CPU package](../ml/transformer-role-audit-package.md)
