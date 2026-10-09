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

Apply the [operator-managed validation policy](../ml/model-validation-execution-policy.md)
instead of historical billing, package-expiry or fixed VM/spend limits. Retain
finite resources, Job counts/timeouts, actual identities, integrity evidence and
separate final-access/replacement authorization. Later exact approved packages
retain their own bounds; this record grants no new run, access or spend.

## Evaluation and Recovery Decision Dependencies — 2026-09-15

[ARD-0038](ARD-0038-c4-specific-evaluation.md) defines the separately hashed C4
research evaluation; [ARD-0039](ARD-0039-same-run-mlflow-recovery.md) reserves and
recovers the same MLflow run; [ARD-0040](ARD-0040-completed-release-publication-recovery.md)
recovers completed publication without rescoring. The signed runner combines C4
verification, durable pre-logging scored retention, same-run recovery and marker-last
publication. Synthetic rehearsals and the accepted research outcome do not establish
client qualification. Frozen model runtime and reviewed orchestration overlays
retain separate bindings and must pass exact-image compatibility preflight.

## Historical execution record

The [immutable pre-compaction record](https://github.com/khab40/lob-arena/blob/d896efe8ca501c1ef8e6c63442f3433948a6405e/docs/architecture/ARD-0035-nebius-lightgbm-first.md#implementation-status)
retains G3–G8 attempts, receipt hashes, consumed slots, policy corrections and
then-current resource/cost observations. [G8 results](../operations/g8/g8-final-results-20260923.md)
and [G9 closure](../operations/g8/g9-closure-20260927.md) record the final outcome.
Those snapshots are evidence, not executable instructions or current resource state.

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
