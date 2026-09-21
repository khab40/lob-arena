# G8 same-run MLflow recovery — 2026-09-14

Current execution policy (2026-09-16): the
[LightGBM/Transformers validation policy](model-validation-execution-policy.md)
supersedes older billing, dollar-ceiling and package/VM/retention windows below.
No billing queries or balance refreshes. Identity/integrity checks and separate
final-test authorization remain; historical receipts keep their original context.

Architecture decision: [ARD-0039](architecture/ARD-0039-same-run-mlflow-recovery.md).

Engineering milestone only. G8 remains open and G9 blocked. This extends the
merged [post-MLflow publication recovery](g8-publication-recovery.md); it does not
authorize a replacement, provision storage, or change the production runner.

## Contract

`g8_mlflow_recovery.py` adds two separate operations:

1. `reserve_run(ResumeTarget(...))`, called **before scoring**, binds one run to
   the reviewed execution-package, request, candidate, C4 profile, request run ID
   and tracking URI. The experiment must already exist. An exclusive ledger lock,
   atomic records and file/directory `fsync` precede the create-run request. The
   caller must explicitly configure `MLFLOW_HTTP_REQUEST_MAX_RETRIES=0`; otherwise
   the operation stops before creating a run. A lost creation response leaves an
   intent that can only be reconciled by search. Exactly one matching active run
   can be adopted; zero matches after an intent, duplicates, deleted runs,
   contradictory identities, FAILED or KILLED status all stop recovery. A saved
   run ID is never silently replaced.
2. `log_governed_evaluation_run(..., resume_target=...)` verifies the complete
   release and independently re-evaluates original C4 checkpoint/comparison
   evidence before entering the recovery sink. It cannot reserve or create a run.
   It binds the verified candidate/profile to the reservation, seals a logging
   plan, snapshots the four artifact files and hashes, and checks all existing
   run tags, metric histories, dataset lineage and artifact bytes before writes.
   Only missing evidence is written. Conflicts are errors, never overwritten.
   Completion requires full readback and `FINISHED`; repeating a completed
   operation verifies it again with zero MLflow writes.

The logging plan contains stable dataset source URIs and cloud metric values;
recovery must not substitute a temporary checkpoint path or new recovery timings.
The original model/candidate, calibration, features and thresholds stay frozen.
Metadata-only dataset inputs carry full artifact SHA-256 values; raw rows are not
uploaded to MLflow. Partially logged runs intentionally remain RUNNING until the
same evidence verifies; a run ID or a RUNNING status is not an evaluation receipt.

The identity ledger is not a scoring-once guard or signed execution approval.
Its at-most-one-create property requires the **same intact ledger and exclusive
writer**. Do not discard/recreate it or use a second ledger to bypass ambiguity.
There is no server-side uniqueness transaction across independent ledgers.
Native filesystem locking, durability and mount-presence checks still need
review and failure testing. The API requires an existing, non-symlink ledger root;
this alone is not proof that the approved native mount is present.

## Verified evidence

The exact pinned `linux/amd64` image, with `--network none`, ran
`serverless/jobs/g8_mlflow_rehearsal.py` using synthetic fixtures and real
file-backed MLflow. The original scoring, full C4 evaluator, independent logger
verification and release/publication checks run unchanged. Only external
readiness, intent and S3 transport are simulated. The fault wrapper lets real
MLflow writes complete and then loses their responses.

- One run created and reserved before one final scoring invocation.
- Lost create, metric, artifact and FINISHED responses recovered into the same
  run over four **logging-only** attempts; scoring was not repeated.
- Local run `dd146b2e4007473ea0963899c110f1f0` is FINISHED.
- 24 metrics verified with exactly one history value each; 30 exact dataset
  inputs; all four artifact files verified byte-for-byte.
- The complete synthetic comparison still covers 27 checkpoints and 198 paired
  observations. This is not production model quality or Java execution evidence.
- Repeating completed logging performed zero writes.

Portable [recovery receipt](evidence/g8-mlflow-recovery-rehearsal-20260914.json)
and [underlying scoring/publication receipt](evidence/g8-mlflow-recovery-scoring-20260914.json)
bind the imported code, report, reservation and completion record hashes. The
full local tree is `/tmp/g8-mlflow-resume.xgP2xd/rehearsal`; it is temporary
engineering evidence, not a durable production archive. Remote authentication,
native storage and pre-logging payload retention are explicitly unverified.

Regression tests additionally exercise remote conflicts, duplicate reservations,
missing ledgers, concurrent ledger use, source-file mutation, partial lineage
logging, immutable logging plans, and zero second create POSTs through the actual
MLflow HTTP SDK when a loopback test server disconnects or returns HTTP 503.
Forged C4 reports remain rejected before either the legacy or recovery sink.

### PR #176 tag-order review follow-up

The reviewed local and frozen MLflow 3.15.2 SDK already serializes dataset tags
as a mapping; the reported ordering failure was not reproduced in that runtime.
Normalization is now explicit from raw key/value entries, independent of the
SDK's serialized container, with duplicate keys rejected before normalization.
The canonical identity stays compatible with existing mapping-based ledgers.
Five regression cases cover all tag permutations with mapping/list serializers,
identical/conflicting duplicate keys, and reordered backend lineage after a lost
input-log response (no duplicate input write and zero completed-recovery writes).

The pinned-image rehearsal was repeated with reversed tag lists on remote
readback: 210 dataset-input readbacks exercised the ordering boundary. Synthetic
run `6c945617cba74a4695fd74a86c237481` finished with one creation, one scoring
call, 24 metrics, 30 inputs, four verified artifacts and zero completed-recovery
writes. The [review-fix receipt](evidence/g8-mlflow-tag-review-20260914.json) and
[source receipt](evidence/g8-mlflow-tag-review-scoring-20260914.json) bind the
updated code. The original receipts above are preserved as history. Full local
outputs: `/tmp/g8-mlflow-tag-review.zL7Z46/rehearsal`. This remains an offline
file-store rehearsal with reordered responses, not a live PostgreSQL test.

## Reproduce

`make lightgbm-wave1-g8-check` includes the recovery tests and lint. The two SDK
transport tests require permission to bind a temporary **loopback-only** port;
they make no requests to Nebius or the governed tracking service.

For the frozen-image rehearsal use the Docker command and five read-only module
overlays in [the completion record](g8-completion-recovery.md#reproduce-offline),
plus `g8_mlflow_recovery.py` mounted read-only at
`/job/backend/app/ml/lightgbm/g8_mlflow_recovery.py`. Replace the script/arguments
with `/rehearsal/g8_mlflow_rehearsal.py --output /evidence/<new-directory>`.
Keep the same pinned digest and `--network none`. No credentials are needed.

## Next gate

The [pre-logging checkpoint milestone](g8-prelogging-checkpoint.md) now retains
the scored payload, original C4 provenance, reservation identity and original
logging context and proves fresh-process recovery after synthetic workspace loss.
Next finalize the execution result truthfully and integrate the already-reviewed
marker-last publisher with the reviewed durable execution package.
The existing production runner still uses a temporary workspace and its legacy
logger; this API is deliberately not wired into submission yet.

Only after the durable integration, native storage exception/budget/review,
authenticated remote rehearsal, original production C3 availability and fresh
preflight pass should a replacement-specific package be signed. Preserve R4's
consumed authorization; no new final-test execution occurred in this milestone.
