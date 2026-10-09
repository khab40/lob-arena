# ARD-0035: Nebius-First Qualification Of Governed LightGBM

Status: Accepted

Date: 2026-08-16

Status reconciled: 2026-10-08.

Tracking: [Bug #357](https://github.com/khab40/lob-arena/issues/357),
[LightGBM Story #23](https://github.com/khab40/lob-arena/issues/23),
[Project #3](https://github.com/users/khab40/projects/3).

## Implementation Status

G0–G9 are complete. The signed 27 September exit is
`research_baseline_qualified`; production/client qualification is not established.
The operator accepted the verified package and unknown-cost disposition and
delegated signing. See [G9 closure](../operations/g8/g9-closure-20260927.md).
Transformer development and its separately authorized holdout are verified;
[current status](../roadmap/CURRENT_STATUS.md) owns the remaining work.

The approved G8 replacement completed one frozen evaluation. Independent readback
verified 176 S3 objects, four MLflow artifacts, 30 dataset identities and 24 metrics.
Precision 85.58%, recall 65.93% and F1 74.48% cover three symbol sessions on one
research date, with synthetic positives and assumed research-control negatives.
The final fold was downloaded by failed R4 before the successful replacement;
it must not be described as globally unopened. Candidate, features, calibration
and thresholds remain frozen. No completed authorization may be replayed.

## Validation execution policy — 2026-09-16

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
`final_identity_available=true`. At that G7 checkpoint the final fold was unopened;
R4 subsequently downloaded it and failed before scoring (see current status above).

The first two separately authorized G8 Jobs failed closed before candidate or
final-release download. The second, `aijob-e00rwzexvwb11rmt4c`, is bound to
authorization receipt SHA-256
`99c0660231ec0584c38ba85f0d2d6c25e155b22162014a00b6b9f60eab733d60`,
preflight SHA-256
`18384b38c840fd903f3ee02824d98248b3704f885225c38a35a572c533379bea`,
recovered submission receipt SHA-256
`1a41e50036da77febeb0d8e609c2f0e3febbd0ee9aee9ce09ebf8b0c9450136f`,
terminal monitor receipt SHA-256
`8a2d21a435e15f19b8e8f62e99fabbd77e888542ebfcff2103263e5523eb66f8`,
and redacted log SHA-256
`53c70aae73acf70488552a569ec6b7db49296e14d4609f3080fbcfc59fb8be80`.
The log terminates at the exactly-once intent claim, which precedes both S3
downloads and evaluation. An authenticated query of MLflow experiment `3`
found zero runs after submission, so no test result or success claim was
recorded.

The decisive live read-back was results-bucket policy version 3: the active G6
campaign had its development writer but neither the final identity's
development-candidate viewer nor final-results writer. Version 5 now adds only
those two exact G6 prefixes and preserves the five prior rules. The identity
provisioner is changed to append missing rules only when every existing rule
matches a recognized Wave 1 lane, to use resource-version concurrency control,
and to verify the resulting policy by read-back. The final key is `INACTIVE`
and MLflow is `STOPPED`. The policy-remediation and MLflow absence-verification
receipt SHA-256 values are respectively
`5a9bbc2f998f8cc3621e2039b06428272ed19b2628b7f4c0a9fc5ce10fe680fd`
and
`1d3457e241e726ff2ecc210f7ce33b0ddb69b9447c6cd7e4561edb3a59dce950`;
the idempotent provisioner state receipt SHA-256 is
`7a1d3a7be81c4d526eed2479273adc2be76c74be2adc607c04a55eaaabca26c1`.
Another Job requires a fresh signed authorization.

The third authorization was consumed by exactly one Job,
`aijob-e00gw2jh294yqa39pd`. The container failed before authorization
verification because the newly injected runner imported
`S3PublicationIntent` from an older frozen runtime image that did not contain
it. The submission, monitor, redacted-log and verified-outcome SHA-256 values
are `26a57b160b3abfd9fd5769076294c67c945056d5da02f07ce07705d62d558207`,
`c69f11bce6d77a15cba4bce8fe9f6f7564ce2c37d057a049bb6772c5695c4d68`,
`af12942515c13f6d270979a744d19cdc57018c065009cd271f36bd497be9d46f`,
and `db743ebd216066feecec8d743246d2a6652558e25b2f1eef6409a3d3388ec9a7`.
No candidate or final object was downloaded, and an authenticated MLflow query
found zero matching governed-evaluation runs.

The decision is to keep the authorized model runtime immutable and make the
small injected control plane explicitly backwards compatible. Its private
publication implementation performs only conditional `PutObject` operations,
checksum read-back, marker-last publication and bounded rollback of objects it
created. Each successful conditional create enters rollback ownership before
metadata or read-back verification can fail. Preflight v2 now runs the exact
injected runner's conditional-
publication compatibility probe inside the exact digest-pinned image with
networking disabled and binds both identities in its receipt; the previously
failing image passes with runner SHA-256
`b5c3e6c5c918ff7b219e497ab735249c5bfdc083874f7c68d9b7b59a3a6ebe2a`.
The image build independently runs the same packaged G8 probe. This closes
the compatibility class of failure before authorization or cloud spend without
changing the frozen model or its dependency environment. No fourth Job is
authorized by this remediation.

## Evaluation and Recovery Decision Dependencies — 2026-09-15

The following records extend this execution decision and preserve its frozen
candidate and release-authority boundary:

- [ARD-0038: C4-Specific Frozen Evaluation](ARD-0038-c4-specific-evaluation.md)
- [ARD-0039: Same-Run MLflow Evaluation Recovery](ARD-0039-same-run-mlflow-recovery.md)
- [ARD-0040: Completed-Release Publication Recovery](ARD-0040-completed-release-publication-recovery.md)

The signed replacement runner now binds C4 evidence, scored retention,
reservation/recovery and completed-release publication. Native synthetic storage
and remote recovery have been exercised; production qualification remains open.
Every replacement must preserve R4's consumed authorization and test-access
history and require its own reviewed, signed execution binding. See the current
status above and [production package](../operations/g8/g8-production-package.md). Earlier
G7/R1–R3 paragraphs are historical checkpoints, not current authorization.

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
files and MLflow health, then atomically creates an exact-run intent object with
`If-None-Match: *`; it then downloads the selected candidate from the
development-results lane and reads the sealed C4 final release exactly once.
The intent lives outside the checksum-bound result prefix, and the candidate /
final join exists only on ephemeral Job disk. This avoids a second mutable
final-data package and does not rebuild the image authorized in G7.

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

- [Wave 1 implementation plan](../roadmap/nebius-lightgbm-wave1-implementation-plan.md)
- [ARD-0007: Nebius Serverless AI Jobs](ARD-0007-nebius-serverless-ai-jobs.md)
- [ARD-0026: Governed LightGBM Release Boundary](ARD-0026-governed-lightgbm-release-boundary.md)
- [ARD-0027: Shared MLflow Tracking Plane](ARD-0027-shared-mlflow-tracking.md)
- [ARD-0031: Complete Governed LightGBM v1](ARD-0031-complete-lightgbm-v1.md)
- [ARD-0036: Market-Sequence Transformer](ARD-0036-market-sequence-transformer.md)
- [Project phases](../roadmap/PHASES.md)
