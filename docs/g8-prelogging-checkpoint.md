# G8 pre-logging checkpoint and workspace-loss recovery

Current execution policy (2026-09-16): the
[LightGBM/Transformers validation policy](model-validation-execution-policy.md)
supersedes older billing, dollar-ceiling and package/VM/retention windows below.
No billing queries or balance refreshes. Identity/integrity checks and separate
final-test authorization remain; historical receipts keep their original context.

Status: synthetic engineering milestone, not a live G8 exit receipt. Built on
merged PR #176 from main `157eacb`. G8 remains open and G9 blocked.

## What is retained

`retain_scored_checkpoint` copies the already-scored artifact tree, frozen
candidate, request, C4 root/projection/profile, original comparison manifest,
preparation and its 27 declared checkpoint trees. Unrelated comparison-directory
files are not copied. The sealed context preserves original dataset source URIs,
cloud logging metadata and manifest locations; recovery never substitutes a
temporary snapshot URI or recomputes cloud timings.

The caller must have reserved the MLflow run before scoring and retain the
original reservation ledger outside the workspace. The caller supplies an
explicit canonical workspace root containing the
scored artifacts; the checkpoint must be disjoint from that whole workspace,
not merely a sibling of its artifact subdirectory. Retention holds the ledger's
exclusive lock and refuses if logging has already started. It checks the request, candidate
and C4 profile against that reservation, verifies copied release artifacts and
independently re-evaluates original C4 comparison evidence. Source manifest objects
must match the retained manifests.

Copies are private, size-bounded and independently checksum-verified. Files and
directories are fsynced; `checkpoint.json` is atomically installed **last**.
The returned checkpoint SHA must be independently retained and fsynced before
the workspace can be discarded. Existing destinations cannot be overwritten.
Interrupted retention remains unsealed for diagnosis and is never treated as
recoverable success. The seal is **not** a final-result `SUCCESS` marker.

## Log-only recovery

`serverless/jobs/recover_lightgbm_g8_scored.py` defaults to local verification.
`--log` enables logging into the original reserved run:

1. Require the independently retained checkpoint hash, reservation specification
   and intact original ledger; reject rebinding to another run.
2. Rehash the exact inventory and verify the complete release and C4 provenance.
3. Make a private, independently rehashed copy so mutable checkpoint files cannot
   change the bytes supplied to the logger.
4. Invoke the shared logger's independent verification and same-run recovery.
   Verify the remote metrics, lineage, artifact bytes and FINISHED status.

There is no final-input download, dataset loader, model scoring, training,
calibration fitting or run-creation operation in this recovery path. It **does**
read retained feature/prediction rows and original replay evidence to verify the
comparison; that is postprocessing, not rescoring. Credentials stay outside the
checkpoint and are supplied through the existing MLflow environment.

Example (paths must be canonical absolute paths, on the reviewed storage):

```text
python serverless/jobs/recover_lightgbm_g8_scored.py \
  --checkpoint /retained/checkpoint \
  --checkpoint-sha256 <independently-retained-sha256> \
  --reservation /retained/execution/reservation.json \
  --ledger-root /retained/ledger
```

Add `--log` only for authorized tracking recovery and set
`MLFLOW_HTTP_REQUEST_MAX_RETRIES=0`. Do not create a new reservation, delete the
ledger, or derive an authoritative SHA from an untrusted checkpoint to bypass a
conflict. The CLI prints a logging-recovery receipt, not a production acceptance
decision or a published cloud result.

## Workspace-loss proof

`g8_checkpoint_rehearsal.py` runs the real full synthetic C4 scoring path in a
child process. It reserves one run, scores once, retains and verifies the
checkpoint, fsyncs its independent receipt, then exits abruptly with code 73
before any evaluation evidence is logged. The parent verifies that the reserved
run is RUNNING with no metrics, inputs or artifacts.

Only then does it remove the synthetic workspace it created. The retained
checkpoint, ledger, independent receipts and file-backed tracking store are
separate siblings. Recovery invokes the actual CLI in a fresh process from an
empty working directory. An additional abrupt exit (74) follows a successful
artifact upload. Another new process finishes the same run; a final new process
verifies it again with all MLflow write methods forbidden.

Recovery workers also forbid the dataset loader, scorer, trainer, execution
runner, final-input download, fluent start-run and client create-run methods.
The proof checks one run, one scoring call, one metric-history value per metric,
30 original dataset inputs and byte-verified artifacts. It asserts that the
original workspace is absent and the recovery process differs from the scorer.
No Java execution, production test data, Nebius resource or remote authentication
is involved.

## Reproduce and remaining gates

Pinned-image execution receipt:
[workspace-loss proof](evidence/g8-prelogging-checkpoint-rehearsal-20260914.json)
and [verified logging completion](evidence/g8-prelogging-checkpoint-logging-20260914.json).
Local synthetic MLflow run `390b4074515741f899ee0dcfb21266c8` is FINISHED:
one scoring call, 24 metrics, 30 dataset inputs, four byte-verified artifacts,
and zero writes on completed replay. The checkpoint retains 348 files
(2,730,329 bytes of synthetic payload); this is not a production capacity estimate.
Its SHA-256 is
`f0673ee6d8b72fa0c421bba56d0d56a69332ac20a36b627bf6006c72c9716944`.
The full retained local tree is `/tmp/g8-prelogging-frozen.mPZcjW/verified`;
the original synthetic workspace was deliberately removed, while the checkpoint,
ledger and tracking store were preserved. These temporary local outputs are
engineering evidence, not a production archive. The receipt binds all eight
module overlays, the actual recovery CLI, rehearsal and C4 report.

`make lightgbm-wave1-g8-check` includes checkpoint corruption, forged/resealed
reports, changed original comparison payloads, resource limits, symlinks,
nonregular markers, wrong run bindings, retention after logging, interrupted
copies, concurrent source changes and the fresh-process proof.

For the exact-image proof use the pinned digest and base Docker invocation from
[the G8 completion record](g8-completion-recovery.md#reproduce-offline). Mount
these eight files read-only from `backend/app/ml/lightgbm/` at matching
`/job/backend/app/ml/lightgbm/` paths:

- `tracking.py`, `c4_evaluation.py`, `c4_replay_evidence.py`
- `g8_benchmark_readiness.py`, `g8_c4_fixture.py`
- `g8_mlflow_recovery.py`, `g8_publication_recovery.py`, `g8_scored_checkpoint.py`

Mount `serverless/jobs/` at `/rehearsal` and an empty host directory at
`/evidence`. Execute
`/rehearsal/g8_checkpoint_rehearsal.py --output /evidence/new-directory`
with `--network none`. A Docker bind mount and local fsync/process-loss proof
**do not establish Nebius native-filesystem durability**.

Next integrate the verified logging recovery with truthful execution-result
finalization and the reviewed marker-last publisher. The production runner is
not changed here; it still requires a replacement-specific durable execution
package and native-mount checks. Native storage exception/budget/provisioning
approval, mount/locking failure tests, authenticated remote MLflow/S3 rehearsal,
original production C3 availability and fresh live preflight remain required.

The workspace must live on approved storage from the start to cover failures
**before** the checkpoint is sealed (including scoring, bundle/report generation
and retention itself). This proof covers loss after a verified seal and retained
receipt, not arbitrary earlier loss, storage destruction, or a second permission
to score. Preserve R4's consumed authorization; only a newly reviewed and signed
replacement package can authorize the one live replacement evaluation.
