# G8 completed-release publication recovery

Architecture decision: [ARD-0040](architecture/ARD-0040-completed-release-publication-recovery.md).

Status (2026-09-15): post-MLflow recovery primitive merged in PR #175. **Not a G8 exit,
pre-MLflow checkpoint, native-storage durability proof or execution approval.**

## Implemented boundary

`g8_publication_recovery.retain_completed_release` accepts only a complete final
result with `SUCCESS`, a verified model/prediction bundle, C4 report and the already
recorded MLflow run ID. Its cloud-run status must be `succeeded`; schema-valid
`verified` or `failed` records are rejected even with regenerated inventories.
A caller-provided `RecoveryBinding` binds the execution
package SHA-256, request hash, candidate hash, report byte hash, MLflow run ID and
exact final-result URI. The binding must be retained with the reviewed execution
receipt; it is not an authorization signature or proof that remote MLflow finished.
The publication recovery does not recompute the C4 comparison or index new claims.

The helper copies into a new private directory, rejects symlinks/nonregular files,
unlisted payloads and transfer-limit violations, verifies the independent copy,
flushes files/directories, and atomically seals `checkpoint.json` last. It never
overwrites an occupied destination or deletes an interrupted copy. The seal hash
must be recorded separately before any publication. The default bounds are 10,000
files / 20 GiB; live capacity and temporary duplicate-copy cost still require review.
The source must be quiescent and access-controlled during checkpoint creation.

`verify_checkpoint` requires both the independently retained seal hash and binding.
It rejects missing, extra, altered or symlinked payload members and rechecks the
complete model/prediction release. Merely finding a checkpoint on disk cannot
authorize its recovery. This command defaults to **local verification only**:

```text
PYTHONPATH=backend uv run --project backend --extra ml python \
  serverless/jobs/recover_lightgbm_g8_publication.py \
  --checkpoint <retained-checkpoint-directory> \
  --checkpoint-sha256 <independently-retained-seal-hash> \
  --binding <reviewed-recovery-binding.json>
```

Only after the reviewed recovery procedure authorizes remote writes, add
`--publish`. This operation:

- Re-verifies the retained release before remote access and checks the existing
  exact-run S3 intent against the original canonical request bytes and metadata.
  It cannot create an intent, download final inputs, train, score, or write MLflow.
- Lists only the exact bound results prefix, with bounded pagination, rejecting
  unknown objects (including `FAILED`) and incomplete prefixes already marked
  `SUCCESS`. It does not repair a contradictory published success in place.
- Verifies every existing object's metadata **and actual bytes** before writes.
  Creates missing objects with `If-None-Match: *`; conflicting content fails closed.
  A lost PUT success response is resolved only through matching read-back.
- Compares against sealed inventory hashes, not newly computed expectations from
  mutable files. PUT reads a separate private, verified, read-only snapshot, not
  the checkpoint path, so concurrent checkpoint changes cannot poison a reserved
  key before read-back. The snapshot is a copy, not a hard link, and stays alive
  through ambiguous-response verification. Rechecks the checkpoint before
  publishing `SUCCESS` last, then
  independently checks the entire exact remote inventory and all object bytes.
- Preserves all partial objects on failure. It has no delete, overwrite, bucket-wide
  listing or multipart fallback. Repeating a fully verified recovery writes nothing.
  Metadata/list calls to the frozen helper remain positional. PUT and GET use a
  local subprocess adapter with `max(300, ceil(sealed_bytes / 5 MiB) + 120)` seconds,
  reaching 1,144 seconds for a 5 GiB object. No unsupported `timeout_seconds`
  keyword is passed to the frozen helper, and command errors are sanitized.
  These per-transfer limits do not enlarge the approved Job/runtime budget.

Each upload temporarily needs its own verified object copy plus read-back space
(up to 10 GiB combined at the single-object limit); live disk/storage budgeting
must account for this in addition to the retained checkpoint.

The recovery receipt carries the original MLflow ID and reports zero scoring and
MLflow writes. `mlflow_remote_state_verified=false` is intentional: independently
checking the original run's status, metrics and artifact hashes remains required.

## Verified synthetic evidence

Review-fix update: the
[new frozen-runtime receipt](evidence/g8-publication-recovery-review-fix-20260914.json)
and [source scoring receipt](evidence/g8-publication-recovery-review-scoring-20260914.json)
bind the reviewed code changes. They supersede the implementation coverage of the
original receipts below without replacing that history. All four fault scenarios,
including checkpoint mutation during PUT, passed with 60 correct result objects,
one scoring call and one local MLflow run (`49042bcc5e7a43ddbdeea5c18dc10b31`).
The original checkpoint mutation blocks `SUCCESS`, but does not corrupt remote
bytes; restoring the sealed local bytes permits completion without rewriting the
already correct object. Changed bytes during snapshot creation fail before PUT.

The frozen-runtime subprocess-adapter probe verifies 1,144-second timeouts for
both maximum-size PUT and GET without using the frozen transfer helper. This is
a dispatch/timeout probe, **not a real 5 GiB transfer or throughput measurement**.
Local validation passed 154 G8 tests plus Ruff/CLI checks, including regenerated
non-success cloud records at retention and recovery, copy/upload races, size-based
PUT/GET timeouts and sanitized failure handling. The updated local evidence tree is
`/tmp/g8-recovery-review.etfTnJ/rehearsal`; native storage, remote transport and
MLflow-interruption recovery remain unverified.

### Original publication-recovery rehearsal

The [publication recovery receipt](evidence/g8-publication-recovery-rehearsal-20260914.json)
and its [source scoring receipt](evidence/g8-publication-recovery-scoring-20260914.json)
record the exact pinned runtime, injected code hashes and synthetic C4 report hash.
The source rehearsal uses the real C4 evaluator, canonical join and local MLflow,
with synthetic features/rules alerts and simulated remote transport as described
in [G8 recovery](g8-completion-recovery.md).

The original result path was made unavailable after retention. A fresh Python
process verified the checkpoint. Three independent fault scenarios then passed:
The checkpoint also passed verification in a second fresh pinned-image container,
with the evidence directory mounted read-only and network disabled.

| Injected fault | Retained objects verified on recovery | Remaining conditional publications |
| --- | ---: | ---: |
| Failure during payload upload | 2 | 58 |
| Lost successful PUT response | 0 initially | 60, with no repeated PUT for the lost response |
| Failure publishing `SUCCESS` | 59 | 1 |

All three scenarios finish with identical 60-object contents; a subsequent recovery
performs zero PUTs. Across scoring and all recoveries there is one scoring call and
one local MLflow run, `751883c3bd7f450a9b9fb82ab7dded55`, still `FINISHED`.
The harness explicitly prohibits scorer and MLflow `start_run` calls during recovery.
This is not production detection/calibration quality evidence.

Local tests also cover checkpoint corruption, missing/extra members, symlinks,
unsealed interrupted copies, wrong binding/hash, spoofed remote metadata, changed
remote bytes, missing payload behind `SUCCESS`, wrong intent, mutation during PUT,
and nonprogressing listing pagination. They run in `make lightgbm-wave1-g8-check`
and the ML-enabled CI job established in PR #172.
Local validation on 2026-09-14 passed 140 G8 tests plus Ruff/CLI checks and 18
release, canonical-bundle and dataset-lineage regressions. CI status is recorded
in the delivery PR; these counts are not a live execution receipt.

To reproduce the frozen synthetic fault rehearsal, use the exact Docker invocation
and five read-only overlays documented in
[G8 recovery](g8-completion-recovery.md#reproduce-offline), plus
`backend/app/ml/lightgbm/g8_publication_recovery.py` mounted at its matching
`/job/backend/app/ml/lightgbm/` path. Keep `--network none`, mount `serverless/jobs`
at `/rehearsal`, and invoke:

```text
/rehearsal/g8_publication_rehearsal.py --output /evidence/new-unique-directory
```

The retained local artifact tree for this receipt is
`/tmp/g8-publication-recovery.Tjuwyp/rehearsal`. This temporary engineering evidence
is not a durable production archive. A local Docker bind mount is not proof of
Nebius native-filesystem retention or access isolation.

## Still required before the replacement

This helper is **not wired into live submission or the current runner**. It starts
after the completed local result exists; it cannot recover R4, which has no scored
result, or a process loss during scoring/MLflow logging. Do not treat this partial
milestone as the full recovery gate.

Pre-scoring reservation and same-run logging now pass the separate
[MLflow recovery rehearsal](g8-mlflow-recovery.md) with independent C4 provenance
validation. Next retain a durable pre-logging scored checkpoint and prove
fresh-process log-only recovery after workspace loss. Bind those operations and this publisher into the reviewed
replacement package, with mandatory C4 evidence, explicit R4 history and native
storage exception identities. Budget/review/provisioning approval, synthetic native
mount failure tests, authenticated remote MLflow/S3 rehearsal and original C3
availability checks must precede any replacement-specific signed execution approval.
G8 remains open; G9 remains blocked.
