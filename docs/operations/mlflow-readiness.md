# MLflow readiness operation — 2026-10-02

Status: the approved first attempt aborted before staging; independent Nebius
readback verified STOPPED at resource version 108. No application mutation or
artifact transfer occurred. The [attempt receipt](../evidence/mlflow-readiness-attempt-20261002.json)
preserves that consumed authorization. The
[replacement proposal](../evidence/mlflow-readiness-replacement-proposal-20261002.json)
requires fresh approval of its [execution manifest](../evidence/mlflow-readiness-r2-execution-manifest-20261002.json)
before another start. Manifest SHA-256:
`4ef479bc2d5f98e9a9d5054ebe8beef7caaabc3151f50d02c26a89e60b5694bc`.
Its five exact operator/helper files are retained in root
`outputs/transformer-mlflow-readiness-r2-20261002/` for inspection.
Ticket: [#19](https://github.com/khab40/lob-arena/issues/19), consumer
[#24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).

Read the [design](../ml/mlflow-readiness-design.md) and
[ARD-0041](../architecture/ARD-0041-mlflow-readiness-before-transformer-execution.md).
This operation supersedes the unapproved September 28 four-grant/single-smoke
proposal by adding application recovery, frozen research registration and two
retained probe runs. It does not authorize the CPU audit.

## Resources and mutations

- Existing VM `computeinstance-e00xq8hqrzks2pf3gn`, `cpu-e2/2vcpu-8gb`, existing
  32 GiB disk. One start, 600-second shutdown target, independent watchdog armed
  before start, early stop on completion or abort. This is not a provider billing
  cap. Unknown costs retain the operator-managed disposition; no new billing gate.
- Host operation has a 330-second work budget plus 20 seconds cleanup. Restore
  has 210 seconds work plus 30 seconds cleanup within that ceiling. After restore,
  at least 220 seconds must remain before live work begins: 180 seconds live work,
  20 seconds cleanup and 20 seconds for preservation/configuration checks.
  Both phases cannot consume their maxima in one window. Completion is
  unbenchmarked; insufficient reserve aborts before live writes. No automatic retry.
- Guest readiness allows at most 90 seconds, constrained by the absolute VM
  deadline. Every poll retains sanitized SSH/sudo/Docker/container states.
  Authentication, host-key and sudo denial stop immediately. Before execution,
  435 seconds must remain: 370 seconds SSH execution, 40 independent readback,
  20 evidence collection and 5 stop signaling. Remote inspection and application
  execution share one 360-second deadline inside the SSH bound.
- Restore: two temporary containers from the existing deployed images. PostgreSQL
  1 CPU/1 GiB with 512 MiB database tmpfs; MLflow 1 CPU/2 GiB with 256 MiB tmpfs.
  Both use network `none`, a private Unix socket and no ports or cloud credentials.
- Live verification: one temporary client container from the deployed MLflow
  image, 1 CPU/512 MiB, 64 MiB tmpfs. It reaches only the existing private MLflow
  endpoint through the VM network; it receives application credentials, no AWS
  credentials. No image pull/build/upgrade occurs.
- Restore creates one experiment/run/user, one inert registry namespace with two
  versions, and its probe metadata: ten API mutations. These exist only in the
  disposable restored database. Original frozen metadata is not modified.
- Live state: at most two absent Transformer namespaces, four exact additive
  permissions, one LightGBM research version/alias, two retained metadata-only
  runs, one parameter/metric, one inert artifact and two run terminations. The
  exporter attempts one denied tag write against the same child. Existing
  namespace/version conflicts stop the operation rather than being overwritten.
  Namespace creation may also establish MLflow's usual admin creator ownership.
- Seven frozen artifact GETs (90,458 expected bytes), one 49-byte inert PUT and
  its GET: eight GETs total 90,507 expected bytes. Each reader allows one guard
  byte to detect excess, giving a conservative aggregate ceiling of 90,515
  bytes read. Downloads reject excess bytes and redirects and retain the exact
  response bytes privately for independent offline checking. No event/sequence
  payload, final bucket, model training/scoring or Serverless Job is accessed.
- Append the Transformer names to the existing deployment's two allowlists;
  preserve all other bytes. No initializer, credential rotation, permission
  removal, deployment restart, model promotion or permanent-resource deletion.
- Cleanup authorization covers only the three temporary containers created by
  this attempt, guarded by ownership labels and immutable IDs. Keep their private
  evidence/journals. No Git cleanup is included.

## Preparation before start

1. Obtain exact replacement execution-manifest approval. The manifest binds the
   proposal, implementation commit, orchestrator, guest helper, watchdog,
   independent readback and verifier. Record its hash in `authorization.json`;
   the execution gate checks approval and all bytes before reserving the attempt.
   Use the listed package/input hashes; stage only those files from the reviewed
   commit. The seven model artifacts are downloaded by the operation, not loaded
   into a model. Do not copy the private database dump into a PR.
2. Read Nebius skills, MCP service documentation and current VM/security rules.
   Recheck STOPPED, preset, private/public addresses and operator SSH `/32`.
   October 2 readback matched `94.43.12.97/32`; no new network grant is proposed.
   If this differs, stop and prepare the exact missing access separately.
3. Preserve an exclusive VM/registry/configuration window. Arm the existing
   `scripts/nebius_mlflow_watchdog.py` 600-second watchdog before start. Retain its
   handshake, provider reads and stop result. Do not adopt an already-running VM.
4. After SSH is available, inspect the existing Compose environment-file label
   and require one canonical owned `0600` file. Do not guess or search for another
   secret file if the expected deployment binding is absent. Verify retained
   backup hash and package bytes before the mutation attempt.

## Execution inside the VM

Launch the reviewed wrapper with bytecode writes disabled and `PYTHONPATH` equal
to the staged package root, using its exact bound source, inputs, output,
environment-file path, proposal hash and commit. The entry point is
`scripts/mlflow_readiness_window.py`; `--help` documents the arguments.
Never print the environment file, Docker environment, auth configuration or raw
exception text. Persisted public receipts contain no credentials or password hashes.

The wrapper validates all package/input files and the environment syntax before
creating temporary containers. It performs actual-image preflight before the
isolated restore, requires verified cleanup, then performs the live phase. The
preflight requires MLflow 3.13.0, its auth dependencies and required method
signatures, zero SDK retries, synchronous logging, 10-second HTTP timeout, disabled
telemetry, exact private URI and no active-model state. Any mismatch stops before
application grants. Repository 3.16.1 is not an authorized runtime upgrade.

Live requests use separate scoped identities. The grant helper checks both users
before its first grant and rejects broader inherited access. The registry helper
checks the frozen manifest, run, full dataset identities and seven artifact bytes
before writes. Journals are bound to this proposal/commit and retained on the VM;
lost responses do not authorize another create/probe POST.

The wrapper privately compares all live user rows and authentication defaults
before/after, then checks the exact additive environment update. REST user hashes
are redacted and cannot replace this comparison. The final application receipt
still says independent readback and VM stop are pending.

## Independent readback and completion

Copy only the evidence, journals and eight retained artifact files into root
`outputs/transformer-mlflow-readiness-r2-20261002/`; keep private files private.
Independently recompute each artifact size/hash against the committed seven-file
manifest and inert probe payload. Check proposal/source/image identities, restored
table equality and allocated IDs, namespace IDs, four permissions, parent/child
links, FINISHED states, strict HTTP 403 denial, registry source/tags/alias, private
credential/default preservation booleans, persisted allowlists and empty cleanup
failure lists. Verify STOPPED through fresh Nebius MCP readback and bind the
watchdog evidence before publishing an overall verified readiness receipt.

On any failure retain the intent and partial evidence, stop the VM, report which
phase changed state, and reconcile read-only. Do not revoke earlier permissions,
overwrite artifacts/aliases, recreate runs, or silently issue a replacement.

Then prepare the sealed CPU image, exact request and campaign journal bindings,
provider admission and actual orchestration dependencies. The installed CLI
0.12.274 meets the compute skill floor but is below the Serverless skill floor
0.12.277; resolve that compatibility check before CPU submission. Ask for exact
one-Job authorization only after readiness passes. The two readiness runs are
probes, not campaign runs or CPU execution evidence.
