# G8 replacement: persistent-storage exception proposal

Architecture decision: [ARD-0040](architecture/ARD-0040-completed-release-publication-recovery.md).

Status (2026-09-14): **preparation approved; not provisioned or executable**.
The user approved preparing a narrowly scoped persistent-storage exception for
the single G8 replacement, with review and budgeting before live provisioning.
That approval does not approve a resource purchase, a mount, final-read credential
activation, the retry-rule exception, or another final evaluation.

## Reason and scope

The current runner uses `TemporaryDirectory`; a Job loss can destroy scored
predictions before S3 publication. Its existing publication rollback and fresh-run
MLflow logger are not resumable. Exactly-once submission alone cannot recover
those outputs. No successful G8 may rely on rescoring after that loss.

The [G3 runbook](lightgbm-v1-runbook.md) forbids volumes in governed Wave 1 Jobs.
Keep that default, the existing submission guard, and the S3 filesystem-mount
prohibition unchanged. Propose one exception for **one native Nebius Compute
shared filesystem**, one dedicated writable mount (`/g8-durable`), and one
replacement run. This is not a bucket/FUSE mount or permission to mount existing
project data. No general-purpose `--volume` bypass is proposed.

Nebius documents native shared-filesystem Job mounts and retention of mounted
volumes after cancellation/deletion, unlike container disk:
[Manage Jobs](https://docs.nebius.com/serverless/jobs/manage).
Mounted storage is billed separately:
[AI Jobs pricing](https://docs.nebius.com/serverless/pricing-quotas).
These capabilities motivate the proposal; they do not prove mount permissions,
crash durability, encryption configuration, or recovery for this project.
The read-only MCP `compute filesystem list` returned `{}` in the configured
default scope on 2026-09-14. No existing filesystem was selected or created.

## Bindings required before provisioning or submission

All entries below are unresolved. They must be populated, independently reviewed,
and hashed into a new execution package; placeholders must fail validation.

- Replacement run ID, package/request hashes, exact approved image digest,
  runner/evaluator/recovery code hashes, and immutable candidate/release/profile/
  original-comparison identities. Preserve candidate
  `5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff`.
- Original R4 submission, test-read and pre-scoring failure receipts; an explicit
  replacement exception acknowledging that history, not first-run status fields
  or reuse of R4's consumed signature.
- Exact project and region, dedicated filesystem resource ID, storage type and
  capacity, mount path/mode, unique run directory, and authorized execution and
  recovery identities. Bind a reviewed creation specification before provisioning
  and bind the returned resource ID before execution approval.
- Verified encryption/access isolation and least-privilege attachment permissions;
  no unrelated Jobs may read the directory. Keep credentials out of persisted
  outputs and evidence; use runtime credential delivery only.
- Fresh cumulative campaign spend, current storage/compute prices, maximum
  retention and recovery duration, and worst-case incremental USD cost including
  MLflow uptime. Apply the existing USD 40 stop-new-work / USD 50 total ceiling.
  The old USD 28.65 observation is stale and is not a funding decision. No capacity,
  retention duration or dollar allowance is approved by this draft.
- Named cleanup owner and deadline/escalation policy. Do not automatically delete
  the sole verified scored copy on a timer; reconcile retention against the approved
  budget and obtain direction if safe recovery exceeds that allowance.

## Implementation and proof required

1. Create a dedicated replacement-only validation path. Reject unbound filesystem
   IDs, extra mounts, changed candidate/image/package identities, or re-use of an
   occupied run directory. General Wave 1 Jobs must continue rejecting volumes.
2. Reserve one MLflow run identity before scoring and persist it with the execution
   intent. If creation has an ambiguous response, reconcile the reserved identity;
   never blindly create another run. Concurrent/repeated starts must fail closed.
3. Put outputs on the mounted filesystem. Flush prediction shards, model bundle,
   inventories and identities, then write a checksum-bound scored checkpoint with
   atomic rename and directory synchronization. Treat an interrupted, incomplete
   scoring checkpoint as an incident requiring direction, not permission to score
   again. File presence alone is not completion proof.
4. Add a separate publish/log-only recovery command that cannot invoke scoring,
   training or final-input download. It verifies the complete checkpoint, computes
   or verifies C4 comparison evidence from retained predictions, and resumes only
   the reserved MLflow run. Retain the original comparison evidence as well as
   predictions; the shared logger must still independently verify provenance.
5. Preserve partially published S3 objects. Resume only after matching existing
   bytes against the checkpoint; conflicting bytes fail closed. Resolve lost PUT
   responses by read-back, publish `SUCCESS` last, and verify independently. Do not
   reuse the current rollback publisher as a durable recovery implementation.
6. Rehearse the reviewed package in the exact frozen runtime with synthetic data:
   failure after scoring, during MLflow writes, after a successful PUT with a lost
   response, and during marker publication. Assert one scoring invocation and one
   MLflow run after recovery, with identical artifact hashes and metrics.
7. Before final access, prove the approved native mount survives synthetic Job
   cancellation/recreation and reattachment by the recovery identity. Perform
   authenticated remote MLflow and S3 round trips, using no real test inputs.
   A local Docker bind mount does not establish this remote guarantee.
8. After independent S3/MLflow verification, archive the checkpoint/execution
   receipts, revoke temporary attachment and final-read access, and remove temporary
   compute/storage only through the approved cleanup procedure. Retain R4 history.

## Current disposition

Only the design preparation is approved. No submission validator was relaxed,
no resource was provisioned, and full durable recovery is not claimed. The
[completed-release publication primitive](g8-publication-recovery.md) now verifies
local retention and publish-only fault recovery after MLflow has finished. It is
not a pre-logging scored checkpoint, native-mount proof or live runner integration.
Review/budget approval precedes live provisioning; successful synthetic durability
and authenticated transport proofs precede the separately signed replacement
execution. G8 remains open and G9 remains blocked.
