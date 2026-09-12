# ARD-0035: Nebius-First Qualification Of Governed LightGBM

Status: Accepted

Date: 2026-08-16

Status reconciled: 2026-09-10

## Implementation Status

Status: `[g0-g6-complete; g7-g9-pending]`

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

### G5 closure — 2026-09-07

G5 passed. Three sequential successful Jobs
`aijob-e00qe81x3p8td0sgmj`, `aijob-e00nq0t5p6j8jk88z3`, and
`aijob-e00aw1zyvs4nf931ef` are bound respectively to MLflow runs
`e3dd3db46d9741d89b3ed230df109c09`,
`36589c337eb343a6bfe826ac3fb347dd`, and
`ce34abdaf5014224b636f9a83354e67a`. The strict comparator passed all nine
gates and all 21 deterministic fields. The runs share reproducibility hash
`cb76261299dd010d4d482d920e7cbece60140f6f5a24ffaefedcc9b57cadf9e2`,
best iteration 22, validation binary log loss `0.42910155734851124`, and no
test-fold access.

The immutable comparison receipt is
`outputs/lightgbm-wave1/nasdaq-g5-repro-20260906/g5-repeat-comparison.json`
(SHA-256
`d6209d45027f376ac67d55fd8f1cdf7428b0e635d6f5fc011e45600051aedcb1`).
The execution receipt is
`outputs/lightgbm-wave1/nasdaq-g5-repro-20260906/g5-execution-evidence.json`
(SHA-256
`ac51f8d3a40210e40ab66c0bb5b766c7807176a5a497b2f1992c4a27f5b0bd38`).
The governed C4 evidence supplied through `--c4-mlflow-evidence` is
`outputs/market-data/nasdaq-c4-four-date-5c85182-20260905/c4-mlflow-dataset-release.json`
(SHA-256
`c5818eb6c836cc7693d025422553c36ed0c2981fd0c39af03f1f483cada8af7b`),
which binds the release hashes to MLflow run
`dc119d708cc4464e8fe1b82ba976bf3e`. The G5 execution receipt verifies 240
metadata-only dataset inputs and no raw-row upload.
Formal closure review corrected its summary count from 22 to the 21 canonical
comparison fields; no governed run or result bytes changed.

One earlier G5 Job, `aijob-e00dwzjr9g2zck6me2`, trained and logged to MLflow
run `94d5b9c9d22d44d6a6cb50d6e8390daf` but failed before result publication
because the results-bucket policy omitted the new campaign prefix. It produced
zero result objects and was excluded from the repeat comparison. Results access
was corrected only for the exact development campaign prefix and remains in
place. The temporary publisher permissions were removed, its key is inactive,
and the development bucket policy was restored. The failed attempt consumed a
development slot: 11 of 20 are now used, and the unstarted G6 matrix is reduced
from ten to nine Jobs by removing one hyperparameter configuration. MLflow is
again independently `STOPPED`.

### G6 closure — 2026-09-10

G6 passed its fixed nine-Job validation-only campaign. The four-run search
selected the `ablate-state` experiment. Its seed-42 result and the mechanically
derived seed-7 and seed-2027 confirmations produced identical balanced F1
`0.6931407942`, minimum attack-family recall `0.5333333333`, and validation
binary log loss `0.3449773248`, passing all three stability gates.

Raw, Platt, and isotonic calibration reproduced the same model and raw
validation predictions. Isotonic was selected by the frozen ordering with
calibrated Brier `0.0068910983` and validation ECE `1.4586e-18`; Platt produced
`0.0080377169` and `0.0042177037`, and raw produced `0.0209358031` and
`0.0816111663`. Balanced precision `0.6760563380`, recall `0.7111111111`, and
F1 `0.6931407942` were unchanged. These are governed validation-only research
results, not final-test or production-performance claims.

All nine collection receipts verified, all nine MLflow run IDs are distinct,
dataset lineage is metadata-only, and `test_fold_accessed=false`. The campaign
used the same pinned runtime image and input identity throughout. Seven input
packages record control-plane Git SHA `fb93abf`; the two final calibration
packages record receipt-reliability SHA `2fdc29f`. The image, input identity,
planned experiment specifications, calibration model, and raw predictions did
not change. The comparator now records both SHAs while correctly treating the
immutable image digest as runtime code identity and continues to reject runtime
image or input drift.

The selected candidate hash is
`5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff`;
the reproducibility hash is
`6afed0cc408791156b8ea801791ff1afc7ea2838d7f5978bda90ca145ef62e06`.
The final comparison receipt is
`outputs/lightgbm-wave1/nasdaq-g6-development-20260907/g6-comparison-final.json`
with SHA-256
`8baa904c5c8ccad4406d62b383999d0c294c9830869e1633aef71d3989b1aa40`.
All 12 gates passed, every rejected trial remains in the receipt, project spend
reconciled to USD 28.65, and the development ceiling is fully consumed at
20/20. The temporary publisher grant was removed, the replacement publisher
key is inactive, the previous key is expired, and the shared MLflow VM is
`STOPPED`.

G7 completed on 2026-09-12 without test access. Candidate
`5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff`
is bound to freeze receipt SHA-256
`232f1a88e39caf2591df5ee135bb25b6ce2fb080688dc197cd96676840f8d7fc`.
The exact-hash operator statement is recorded in outer authorization receipt
SHA-256
`b0b6cee7fce8db3618cdaeb905ec7588d57a94985ef3823215664da4ce8ceed6`,
binding signed-content SHA-256
`dcf056eba18cd95169f3caade2f7d1c2285e1b49b94e2a9ab353bb74f1233db0`,
signature SHA-256
`a012abb5948b3cf058c77fd9336f5a81eaaa0b2c2782aab653d9ba3dbf3005ea`,
and trusted public-key SHA-256
`a433d622c153a47df472a703d549f180c43ab5d467ae35606667d29ef24e06ab`.
Independent verification reports `authorized`, `signature_verified=true`, and
`final_identity_available=true`. G8's one final evaluation is next; MLflow
remains stopped until that verified experiment window.

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

For G8, the signed request, authorization, public key, metadata-only C4 lineage
receipt, and a checksum-bound orchestration runner are injected as small
read-only Job files. The authorized, unchanged image first verifies those
files, MLflow health, and an empty result prefix; it then downloads the selected
candidate from the development-results lane and reads the sealed C4 final
release exactly once. The join exists only on ephemeral Job disk. This avoids a
second mutable final-data package and does not rebuild the image authorized in
G7.

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
