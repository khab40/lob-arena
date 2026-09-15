# G8 completion recovery — 2026-09-14

Status: G0–G7 complete; G8 open; G9 blocked on a successful, fully evaluated G8.
This is a recovery implementation record, not a final-test approval or G8 exit receipt.

Current follow-up: [live replacement integration and preflight](g8-live-replacement.md)
wires the scored checkpoint, same-run logging and completed-release publisher
into a separate package-bound entrypoint. It preserves four prior submissions
and R4 test access, requires a signed exception and native mount, and leaves the
ordinary no-volume submitter unchanged. Native/remote rehearsal is proposed with
a $2 cap but is not yet approved; no production execution readiness is claimed.

## What is fixed and verified

The R4 request pointed the tabular loader at `projection-artifacts`. C4 actually
publishes `artifacts/tabular/test/...`, with shard URIs relative to `artifacts`.
Preflight now selects `artifacts`, requires all 30 exact frozen test shard keys
(three symbols, each with one control and nine family/seed combinations), rejects
missing, substituted, duplicate/noncanonical entries and packages retaining the old root.
The frozen image and the selected production model are unchanged.

`serverless/jobs/g8_rehearsal.py` executes synthetic C4-shaped train/validation/test
projections through the real loader, training, isotonic calibration, signature
verification, injected runner, scoring, bundle verification and MLflow logger.
It exercises the real conditional publisher with a positional-only simulated S3
transport, reconstructs the published release from those objects and re-verifies it.
It verifies exactly one local MLflow evaluation run, all three logged artifacts
byte-for-byte and the logged row count, alert count and frozen threshold.

The pinned `linux/amd64` image ran the rehearsal with `--network none` on
2026-09-14. Local MLflow run `f8ff022f79404e8fa5c44f3a048ee790` finished;
36 synthetic test rows and 33 published objects passed verification.
Receipt: `outputs/g8-rehearsals/verified-scoring/rehearsal.json` in the recovery
worktree. A portable copy is [recorded here](evidence/g8-synthetic-rehearsal-20260914.json).
These are **synthetic engineering results**, not production detection quality.
The local file-backed MLflow store is explicitly enabled only in the rehearsal;
it does not replace or reconfigure the governed remote tracking server.

The `--wrong-root` negative control and its regression test exercise the actual
loader with R4's erroneous root and must fail before any MLflow evaluation run.
The ordinary `--runtime-compatibility-check` remains only a publication-contract
check: neither it nor this offline rehearsal is sufficient live submission authority.

## Recovery exception — draft, not executable authorization

R4 Job `aijob-e00vtamgkr07mwzt4t`, run `nasdaq-g8-final-r4-20260913`, downloaded
the final release on 2026-09-13 and failed before scoring at the artifact-root check.
Its monitor SHA-256 is
`e6975dcd517dda25b91a0b6bea9a786c87f7d82a451fcb71a8dcc34355016b72`;
the log SHA-256 is
`eadddbdbac943939a9b8243398584ac8866352b30117ef7ea0e3fb9ed9ac2a8c`.
Preserve that failure, result prefix and consumed authorization. It is not a G8 pass.

The user requested preparation of one successful replacement evaluation. The
existing no-retry-after-read rule therefore requires a specific documented
exception, not reuse of an old `APPROVE WAVE1 FINAL TEST` statement. The proposed
exception permits at most one new execution of unchanged candidate
`5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff` after all
readiness gates below pass. No model selection, retraining, feature changes,
recalibration or threshold tuning using test outcomes is permitted.

Before signing/submission, bind the replacement's unique run ID, request/package
hash, runner and evaluation-code hashes, immutable runtime image, final-release
hashes, comparison-evidence inventory, resource/spend limits, R4 incident receipts
and allowed recovery actions. Those bindings are not ready yet. A replacement
preflight must record the prior submission and test access truthfully; the current
first-run v2 fields (`final_jobs_submitted_before=0`, `test_fold_accessed=false`)
must not be repurposed as replacement-history evidence.

## Remaining gates, in execution order

Update 2026-09-14: the user approved the separate
[C4 evaluation contract](g8-c4-evaluation-contract.md). Its metadata audit confirms
that the four-date frozen protocol cannot use the seven-date benchmark unchanged.
The new implementation adds paired observation metrics, calibration assessment,
session-cluster uncertainty, original-checkpoint/replay verification and MLflow
report support. Following merged PR #171, the injected runner now accepts
`--c4-evaluation-inputs`, checks its frozen metadata before remote operations,
evaluates its actual scored output, and sends the report through the shared
logger's independent provenance verification. This option is not yet required or
bound by a replacement-specific submission package; the legacy no-report path is
retained only for compatibility. Neither the production candidate nor the existing
seven-date benchmark was changed.

The full synthetic C4 contract rehearsal now passes in the pinned image with five
read-only module overlays: 27 original-format checkpoint releases, 30 canonical
replay domains, 198 paired observations, one final scoring invocation and one local
MLflow run. It verifies detection metrics, calibration assessment, session-cluster
uncertainty, rules comparison, conditional publication of 60 objects and artifact/
metric read-back. Local run `a221a294cf0847eabb80fc2a602c7b59` is `FINISHED`;
the [portable receipt](evidence/g8-complete-c4-rehearsal-20260914.json) binds the
runner, rehearsal, all five overlays and report bytes. The matching
[synthetic report](evidence/g8-complete-c4-synthetic-report-20260914.json) is retained
byte-for-byte, not as a production quality claim. The complete local artifact
tree was retained at `/tmp/g8-complete-c4-final.oTEwDb/rehearsal`; it is temporary
engineering evidence, not a durable production archive.

The original-checkpoint verification, canonical stream/observation join and shared
logger's re-evaluation are real, not substituted. Features and Java-format rules
alerts are synthetic fixtures; no Java process or real test data was used. Remote
readiness, unique intent and S3 transport are simulated; local MLflow is file-backed.
The receipt explicitly records remote authentication/storage as unverified and
production G8 as incomplete. Negative tests reject altered profile bindings before
remote access and corrupt checkpoint payloads before creating an MLflow run.

The user approved **preparing** the
[persistent-storage exception](g8-persistent-storage-exception.md). This is not
permission to provision or submit. Durable recovery, original production checkpoint
availability, remote rehearsal and replacement-specific authorization remain open.

Follow-up after merged PR #172: a
[completed-release publication recovery primitive](g8-publication-recovery.md)
now retains an independently checksum-bound copy and resumes exact-prefix S3
publication without deleting partial objects, rescoring, or writing MLflow. The
frozen synthetic fault rehearsal passed for payload failure, lost PUT response
and marker failure; a fresh process verified the retained copy after the original
path became unavailable. This covers **post-MLflow publication only**. It is not
wired into live execution; pre-logging retention, same-run MLflow recovery and
native-storage durability remain outstanding. No new execution is authorized.

Follow-up after merged PR #175: [same-run MLflow recovery](g8-mlflow-recovery.md)
now reserves an identity before scoring and resumes interrupted logging after
independent C4 verification. The pinned-image synthetic rehearsal creates one
run, scores once, recovers four lost-response cases, verifies 24 metrics, 30
dataset inputs and all four artifacts, then repeats completed logging with zero
writes. This does not retain scored payloads before logging or survive Job loss
yet, and is not wired into live execution. Those integration and native-storage
gates remain open, as do remote rehearsal and replacement-specific approval.

Follow-up after merged PR #176: [pre-logging checkpoints](g8-prelogging-checkpoint.md)
now retain the scored release, original C4 comparison evidence and unchanged
logging context before any evaluation evidence is logged. The synthetic proof
abruptly exits after sealing, removes the original workspace, then runs the
actual log-only CLI in fresh processes. Recovery also survives a second abrupt
exit after an artifact upload and finishes the same run without rescoring.
Native storage durability, full execution-result finalization/publication
integration, remote rehearsal and replacement-specific approval remain gates.

1. **Resolve canonical benchmark inputs.** The C4 final projection publication
   contains feature/sequence shards and projection manifests, not the canonical
   replay streams, rules alerts, adjudications, regime evidence, streaming evidence
   and baseline session metrics required by `scripts/evaluate_governed_benchmark.py`.
   `projection_freeze.py` binds projected rows to C3 checkpoint event-stream hashes;
   `replay_export.py` produces the canonical replay manifests and rules alerts in
   C3. Bind a narrowly scoped immutable comparison-evidence package from those
   existing checkpoints to the same sessions/observations. Do not regenerate or
   substitute a different rules baseline, and do not inspect final rows while
   preparing this metadata-only authorization. If the required evidence was not
   retained, record that as a blocker and obtain a protocol decision; do not silently
   replace event/campaign metrics with row-classification metrics.
   Following the explicit C4-contract approval, evaluate the approved row-level
   scope under its own metric names; retain the seven-date incompatibility and
   exclusions rather than claiming equivalence. Original rules checkpoint
   availability still requires verification before an execution package is ready.
2. **Wire and rehearse the complete evaluator.** The frozen `_run_final` currently
   builds predictions and a bundle but does not call the canonical benchmark or
   pass `benchmark_results_path` to MLflow. Add frozen-threshold detection metrics,
   held-out calibration assessment, rules comparison and session-cluster uncertainty.
   Verify the same-observation join and report limited test-session support honestly.
   Repeat the full synthetic rehearsal with this exact reviewed evaluation package.
   The new injected-runner C4 path and full offline synthetic rehearsal satisfy
   this engineering milestone; production package binding and remote validation
   are still required. The unchanged image alone does not include these overlays.
3. **Make publication recovery independent of scoring.** Prove verified predictions,
   manifests and the MLflow run ID survive publication failure on durable governed
   storage. The current temporary workspace is not durable across Job destruction.
   Add a checksum-bound publish/log-only recovery operation that cannot load or score
   test inputs and cannot create duplicate evaluation runs. Inject failures after
   scoring, during MLflow logging, after a successful PUT with a lost response, and
   during marker publication; verify recovery without re-execution.
4. **Review/merge, bind the exception and run live preflight.** Use a fresh PR from
   current main for subsequent delivery. Verify fresh billing, exact image digest,
   scoped credentials, private authenticated MLflow and a synthetic remote artifact
   round-trip. No final-read credential activation or cloud Job occurs in this PR.
   Obtain the replacement-specific signed authorization only for the completed,
   reviewed package; never use the consumed R4 statement.
5. **Execute once and independently verify.** Claim the unique intent, score once,
   verify the complete benchmark/release, index exactly one governed MLflow run,
   publish marker last, then independently compare S3 bytes and MLflow artifacts,
   metrics, lineage and run status. Report measured quality, even if below target;
   successful execution is not a guarantee of model qualification.
6. **Close only on evidence.** Update roadmap/checklist, Issue #23 and ARD-0035 with
   the verified production receipts and measured rules/LightGBM comparison. Disable
   the final identity, stop temporary resources, reconcile cost, then proceed to G9.

## Reproduce offline

Create an empty host evidence directory, mount it at `/evidence`, and mount
`serverless/jobs` read-only at `/rehearsal`. Run the following arguments with Docker:

```text
run --rm --platform linux/amd64 --network none --entrypoint python
--mount type=bind,source=<absolute-jobs-directory>,target=/rehearsal,readonly
--mount type=bind,source=<absolute-evidence-directory>,target=/evidence
cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/lob-arena-jobs@sha256:dc32b12d7216bfeef8e5d95c50363f34bb76f34159ef9343ff3d6996983a89b2
/rehearsal/g8_rehearsal.py --output /evidence/new-unique-directory
```

Add `--wrong-root` and use another output directory for the expected-failure
negative control. `make lightgbm-wave1-g8-check` includes these regression tests
against the checkout; the pinned-image command separately verifies frozen-runtime
compatibility. Neither command accesses real test data or starts a Nebius Job.

For the **complete C4 comparison**, additionally mount these five files from
`backend/app/ml/lightgbm/` read-only at the corresponding
`/job/backend/app/ml/lightgbm/<filename>` paths before the image argument:

- `tracking.py`
- `c4_evaluation.py`
- `c4_replay_evidence.py`
- `g8_benchmark_readiness.py`
- `g8_c4_fixture.py` (synthetic rehearsal only; not a production overlay)

Add `--c4` to the rehearsal arguments and use a new empty output path. Keep
`--network none`. The receipt records the actual imported module hashes, one
scoring call, and the limited synthetic comparison scope. This command does not
prove native Nebius mount durability or duplicate-safe MLflow recovery.
