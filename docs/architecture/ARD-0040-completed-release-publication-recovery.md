# ARD-0040: Completed-Release Publication Recovery

Status: Accepted; recovery primitive and authorized research lifecycle verified

Date: 2026-09-15

Implementation Status: `[publication recovery verified; authorized C4 research G8 complete and G9 signed; production/client qualification unestablished]`

Outcome reconciled 8 October: [G8 independent readback](../operations/g8/g8-final-results-20260923.md)
and [G9 closure](../operations/g8/g9-closure-20260927.md) establish the limited
research outcome. [Current status](../roadmap/CURRENT_STATUS.md) owns remaining work;
dated synthetic/preflight narratives below retain their original scope.

## Context

A final result can be scored and logged successfully but only partly published
to Object Storage. Repeating scoring would violate the frozen-test boundary.
The existing temporary Job workspace cannot guarantee survival after Job loss.

## Decision

Retain and publish a verified completed release through separate operations:

- `retain_completed_release` accepts only a complete `SUCCESS` result with a
  succeeded cloud-run record, verified model/prediction bundle, C4 report and
  recorded MLflow run ID. `RecoveryBinding` binds the execution-package hash,
  request, candidate, report byte hash, MLflow ID and exact final-result URI.
- Copy into a new private directory; reject symlinks, nonregular/unlisted files,
  occupied destinations and transfer-limit violations. Verify and fsync the copy,
  sealing `checkpoint.json` last. Retain its hash independently with the binding.
- Recovery requires both the independent seal hash and binding, rechecks the
  complete inventory and release, and verifies the existing exact-run S3 intent.
  It cannot create an intent, read final inputs, train, score or write MLflow.
- Inspect only the exact result prefix. Verify existing object metadata and
  actual bytes; conditionally create missing objects with `If-None-Match: *`.
  Resolve a lost PUT response by matching readback. Reject unknown/conflicting
  objects, `FAILED`, and incomplete prefixes already marked `SUCCESS`.
- Upload from private verified copies, recheck the checkpoint, publish `SUCCESS`
  last, then read back the complete remote inventory. Preserve partial objects on
  failure. A completed repeat performs zero PUTs; no delete/overwrite fallback exists.

The binding is not an authorization signature or proof of remote MLflow
completion. Publication receipts explicitly leave remote MLflow verification
false; verify that service independently using
[ARD-0039](ARD-0039-same-run-mlflow-recovery.md).

## Storage boundary and qualification

This primitive starts **after MLflow logging**. Pre-logging scored retention is
implemented separately in
[g8_scored_checkpoint.py](../../backend/app/ml/lightgbm/g8_scored_checkpoint.py).
The [signed replacement runner](../operations/g8/g8-live-replacement.md) integrates both
boundaries. Neither can recover a scoring process that failed before sealing
its payload by pretending scoring completed.

The [native storage exception](../operations/g8/g8-persistent-storage-exception.md) has been
exercised by the [two-Job synthetic rehearsal](../evidence/g8-native-recovery-20260917.json).
A second Job recovered after loss of the original workspace; authenticated
MLflow readback and later [independent S3 readback](../evidence/g8-independent-s3-readback-20260917.json)
verified the result. The ordinary no-volume guard and S3/FUSE prohibition remain.
At that historical rehearsal, comparison/registration evidence, storage capacity,
changed transport preflight and replacement-specific authorization were separate
requirements. Synthetic success alone was not G8 completion; the later research
outcome uses the independently verified receipts linked above. See the [production package](../operations/g8/g8-production-package.md).

## Implementation and verification

[g8_publication_recovery.py](../../backend/app/ml/lightgbm/g8_publication_recovery.py)
implements retention and publication.
[recover_lightgbm_g8_publication.py](../../serverless/jobs/recover_lightgbm_g8_publication.py)
defaults to local verification; `--publish` enables remote writes.
The [review-fix receipt](../evidence/g8-publication-recovery-review-fix-20260914.json)
covers payload failure, lost PUT response, marker failure and checkpoint mutation,
with 60 correct objects and no rescoring. That earlier transport was simulated;
the later native rehearsal and 64-object independent readback establish the
additional synthetic Job-storage/publication evidence described above.

## Alternatives and consequences

Deleting partial results or retrying the complete scoring job loses evidence or
reopens test computation. Sealed copies and conditional publication preserve
the original result but need additional disk space and readback I/O. Defaults
bound retention to 10,000 files / 20 GiB; maximum-size transfers may additionally
need up to 10 GiB for an upload snapshot plus readback. Live budgets must cover
these costs without extending the approved runtime ceiling.

## Dependencies and related documentation

- [ARD-0035: Nebius qualification](ARD-0035-nebius-lightgbm-first.md) — execution and authorization boundary.
- [ARD-0038: C4 evaluation](ARD-0038-c4-specific-evaluation.md) — completed report provenance.
- [ARD-0039: Same-run MLflow recovery](ARD-0039-same-run-mlflow-recovery.md) — preceding logging completion.
- [G8 publication recovery](../operations/g8/g8-publication-recovery.md) — detailed CLI, limits and rehearsal history.
- [G8 completion recovery](../operations/g8/g8-completion-recovery.md) — remaining end-to-end gates.
