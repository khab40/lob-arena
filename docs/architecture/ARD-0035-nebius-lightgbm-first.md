# ARD-0035: Nebius-First Qualification Of Governed LightGBM

Status: Accepted

Date: 2026-08-16

Status reconciled: 2026-08-27

## Implementation Status

Status: `[g0-g4-complete; g5-unlocked; g5-g9-pending]`

Governed LightGBM v1 is implemented locally under ARD-0026 through ARD-0031.
The Wave 1 request/run contracts, CPU Jobs-image profile, hardened transport,
runner, fixture lifecycle, evidence fields and fail-closed tests passed locally
on 2026-08-16. G3 has since established the four Object Storage boundaries,
three service identities, development-to-final denial proof, Container Registry
authentication, and the shared MLflow CPU VM. MLflow is pinned to a Nebius
Container Registry digest and its PostgreSQL/registry/Object Storage round trip
passes. The USD 0 campaign billing baseline and spend controls are recorded.
The approved fixture input was published and read back with canonical hashes,
the temporary staging writer grant was revoked, and the development identity
remains denied both post-staging writes and final-input reads. The extended
Jobs image passed its `linux/amd64` smoke and is pinned to Registry digest
`sha256:bdad8804c52a4b3141101f26f55275937c721997093902c2ea8aa9cc4fd7ab69`.
G3 is complete. The first G4 Job, `aijob-e00zg7n8dsb66xef1c`, was submitted on
`cpu-d3/4vcpu-16gb` and cancelled at the declared 15-minute ceiling after
remaining in platform `STARTING` with no container logs or result objects.
Following explicit Operator authorization, corrected Job
`aijob-e00ytz0nsa2wz6ajb3` removed the Registry secret, used same-project
Registry access, retained the governed `linux/amd64` image digest, and still
attached S3 filesystem volumes. It produced the same result: VM `RUNNING`, Job
`STARTING`, no container logs, and no result objects for 15 minutes, then
`CANCELLED`.

Three later no-volume Jobs did reach the container, but did not reach the
runner: `aijob-e00yhjdjttz772e843` and `aijob-e00a7m37mg0yt5gsgp` used an older
image without the `run-s3` command, and `aijob-e00e0cn0ttvf29g99r` reversed the
command/argument layout so Python tried to open `/job/serverless/jobs/run`.
All five of those attempts count against the fixed 20-Job development ceiling.

Attempt 6, `aijob-e00sa1ejk3qsa13ymw`, proved the bounded short-tag image
workaround and reached the intended runner, but failed before training on the
first Object Storage list call. The packaged AWS CLI is v1.46.0 and the shared
helper still passed the AWS CLI v2-only `--no-cli-pager` option. Attempt 6 is
the sixth consumed development slot.

Attempt 7, `aijob-e00k3nj3402wrdvbnz`, used the AWS CLI v1-compatible image and
completed the governed workload in 38 seconds. Live evidence matched the
reviewed `cpu-d3`, `4vcpu-16gb`, 100 GiB, 3,600-second resource contract and
the governed image digest. Its result prefix contains 25 objects and
`SUCCESS`. The initial monitor correctly failed closed when its local parser
did not recognize Nebius `spec.disk.size_bytes`; the reconciled monitor now
records `COMPLETED`, matched resources, collected logs and no cancellation.
Attempt 7 consumed the seventh slot; 13 of 20 slots remain.

The comparison with successful July Jobs establishes the actionable
root cause: those Jobs passed AWS credentials to the container and used S3 API
staging, with zero volumes. The August Jobs instead mounted whole bucket roots,
while the Wave 1 identity was intentionally allowed to list/read/write only
specific prefixes. Mount startup requires bucket-namespace operations outside
that least-privilege contract, so startup stopped before the container command.
The no-volume correction removes every Wave 1 volume, injects both credential
values from MysteryBox, downloads only the approved release prefix to
ephemeral disk, and uploads the verified result with the terminal marker last.
The attempt-7 correction also removes the v2-only pager flag and disables
paging through `AWS_PAGER`, which is compatible with AWS CLI v1 and v2.
Commit `690a9e9` passed 39 focused Wave 1 tests, all submission/render tests,
Ruff, the `linux/amd64` image/runtime smokes and a container-level integration
list of the exact Nebius prefix with the packaged AWS CLI v1. The corrected
image is pinned to digest
`sha256:3e54fbe1c1ba7e5955a13565dc623cce4542b0df038c5f0b78b0f107e79c95e5`,
and its matching fixture was uploaded and read-back verified. Attempt 7 then
completed successfully at the Nebius Job boundary. Governed result collection
and the final G4 exit record were then verified against a fresh post-run spend
observation. Spend reconciled at USD 8.57 including VAT, all 16 gates passed,
G5 is unlocked and no G4 rerun is authorized or needed.

The 2026-08-21 reconciliation verified project usage at USD 8.03 total and a
USD 1,265.66 credit balance. The latest authoritative pre-attempt-7 observation
was USD 8.55 including VAT; the authoritative post-run value is USD 8.57. The
legacy inline AWS access-key identifier from an old Job no longer resolves in
Nebius IAM (`NotFound`), and the Operator has stopped the shared MLflow VM. No
previous evidence was recopied or archived.

## Context

LOB Arena already has deterministic CPU training, validation-only calibration,
frozen operating modes, explanations, paired evaluation and verified LightGBM
bundles. It also has Nebius Job, Object Storage and MLflow integration surfaces.
The missing step is a production-shaped cloud qualification that measures
model quality together with runtime, throughput, resource use and cost.

Starting with a GPU sequence model would spend the project's limited cloud
credit before establishing the simplest learned-detector baseline. Nebius
Serverless AI Jobs are a better first fit because LightGBM is CPU-efficient,
the work is finite and non-interactive, and completed Jobs release their
compute resources.

## Decision

Qualify the existing governed LightGBM v1 first on Nebius using:

- CPU Serverless AI Jobs for feature verification, training, calibration,
  batch prediction and paired evaluation;
- Standard Object Storage for immutable governed inputs, model bundles,
  reports and cloud-run evidence;
- shared MLflow for searchable run metadata and artifact pointers; and
- repository manifests, hashes, checksums and signatures as the release
authority.

Object Storage is accessed inside the container through prefix-scoped S3 API
calls. Wave 1 must not use S3 filesystem volumes, root `HeadBucket` probes, or
bucket-root list operations. Job credentials are separate MysteryBox-injected
environment values, and input/output bytes live only on ephemeral job disk
during execution.

The first cloud wave freezes one corpus/split/feature identity before tuning.
Development runs may use train and validation only. After thresholds and
operating modes are frozen, one governed evaluation run may inspect the final
test fold.

Every Nebius run must record:

- Job ID, Git SHA and image digest;
- corpus, split, feature, configuration and model hashes;
- resource platform/preset, active runtime, peak memory and CPU utilization;
- processed rows, rows per second and failure/retry state;
- detector and calibration metrics; and
- estimated and, when available, billed cost per run and per million scored
  rows.

## Exit Gates

Transformer work may start only after:

1. three identical repeat runs produce matching governed identities and
   equivalent metrics within declared tolerances;
2. rules and LightGBM are compared on identical immutable inputs;
3. the LightGBM bundle and cloud evidence verify independently;
4. quality, clean-window false-alert, calibration, latency and throughput gates
   are evaluated; and
5. a go/no-go record freezes the LightGBM baseline and the remaining GPU budget.

Passing the software and reproducibility gates does not automatically promote
LightGBM to production champion. A governed official-public-sample evaluation
may produce the research-only `research_baseline_qualified` disposition and
unlock Wave 2 engineering. Production/client acceptance still requires data
rights, independent clean-window review and evaluation evidence appropriate to
that claim.

## Cost And Operations

- Prefer CPU Jobs to an always-on training VM.
- Use small smoke runs before tuning or final evaluation.
- Keep inputs and outputs in one region to avoid unnecessary transfer.
- Keep Standard storage as the default until measured I/O justifies a more
  expensive storage class.
- Bound every Job by resource preset, run count and timeout.
- Do not start the vLLM GPU endpoint for LightGBM work.

## Alternatives Considered

### Train LightGBM and Transformer concurrently

Rejected for the initial roadmap because it obscures the incremental value and
cost of temporal modeling and consumes GPU budget before the CPU baseline is
frozen.

### Use an always-on GPU or CPU VM for all experiments

Rejected as the default because these are finite batch workloads. A persistent
VM may still host shared MLflow metadata when that is cheaper than a managed
service, but it is not the training execution boundary.

### Treat MLflow as the release authority

Rejected. MLflow indexes runs; repository contracts and verified artifact
identities remain authoritative.

## Consequences

The project gains a credible cost/performance baseline early and preserves
credit for work that truly needs GPUs. The sequence is slower than concurrent
model development, but comparisons become interpretable and rollback remains
simple.

## Related Records

- [Wave 1 implementation plan](../nebius-lightgbm-wave1-implementation-plan.md)
- [ARD-0007: Nebius Serverless AI Jobs](ARD-0007-nebius-serverless-ai-jobs.md)
- [ARD-0026: Governed LightGBM Release Boundary](ARD-0026-governed-lightgbm-release-boundary.md)
- [ARD-0027: Shared MLflow Tracking Plane](ARD-0027-shared-mlflow-tracking.md)
- [ARD-0031: Complete Governed LightGBM v1](ARD-0031-complete-lightgbm-v1.md)
- [ARD-0036: Market-Sequence Transformer](ARD-0036-market-sequence-transformer.md)
- [Project phases](../PHASES.md)
