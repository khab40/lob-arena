# Nebius LightGBM Wave 1 Implementation Plan

Status: G0-G3 complete; approved digest-verified short-tag workaround implemented; refreshed G4 dry run awaits current spend reconciliation

Date: 2026-08-26

## Outcome

Qualify the already-implemented governed LightGBM v1 on Nebius and produce one
independently verifiable package binding immutable inputs, source/image hashes,
Nebius Job IDs, MLflow runs, rules-versus-LightGBM results, runtime, throughput,
memory, cost and a Wave 2 go/no-go decision.

Fixture/synthetic completion proves the cloud pipeline only. Official public
samples may support the research qualification defined below. Production or
client model-performance acceptance additionally requires appropriately
permitted data and predeclared business gates.

## 2026-08-16 Public-Sample Amendment

Waiting for a separately licensed corpus is no longer a Wave 1 or Wave 2
engineering prerequisite. G4 remains a fixture-only cloud smoke. After an
explicitly authorized G4 runtime-recovery attempt passes, G5-G8 will use the
official public Nasdaq ITCH samples and the repository's LOBSTER sample
according to the
[Nebius public market data plan](nebius-public-market-data-lightgbm-plan.md).

The new `research_baseline_qualified` disposition may unlock Wave 2 engineering
when the public-sample quality, reproducibility, isolation, cost and operational
gates pass. It does not authorize a production-quality, commercial/client, or
licensed-corpus claim. Such claims still require data rights and evaluation
evidence appropriate to that use.

## 2026-08-21 Baseline Reconciliation

- Project billing for `project-e00g6zvxpr00waz8t3y51k` was verified in the
  Nebius console at 11:57 UTC: USD 6.64 subtotal, USD 1.39 VAT, USD 8.03 total,
  and USD 1,265.66 remaining credit. This is below the USD 25 reporting trigger
  and leaves USD 41.97 inside the fixed USD 50 Wave 1 ceiling.
- The shared MLflow VM is stopped by the Operator. It must remain stopped until
  tracking is required for an explicitly authorized run.
- The legacy AWS access-key identifier recovered from an old redacted Job
  configuration no longer resolves through Nebius IAM (`NotFound`). No live
  inline credential was recovered, copied, or retained.
- Five failed G4 Jobs have consumed five places in the fixed 20-Job development
  ceiling. Fifteen development Jobs remain; the ceiling is not increased.
- Prior Job specifications, logs, and results are not copied into a new archive
  during this reconciliation. Existing governed records remain in place.

## 2026-08-22 G4 Preflight Reconciliation

- Live Serverless AI Job inventory still contains exactly the five bounded G4
  attempts recorded above; no sixth Job was submitted. All five are terminal:
  four `CANCELLED` and one `FAILED`. The last three attempts used 250 GiB disks
  rather than the reviewed 100 GiB G4 contract, so they cannot be reused as
  evidence for the next submission.
- The MLflow VM `computeinstance-e00xq8hqrzks2pf3gn` is live-verified as
  `STOPPED`. Its private address remains `10.4.0.54`, and the Job subnet that
  can reach it is `vpcsubnet-e00ppzc4353dxv210j`. It was not started during
  this preflight.
- A fresh `linux/amd64` Jobs image was built from commit `9b12be9`, passed the
  import smoke plus the exact `run-s3 --input-uri` entry-point check, and was
  pushed as the immutable reference
  `cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/lob-arena-jobs@sha256:760142ec89750025314d5376c2b2c8e8fe7827ab5d7c2dc7bc9a9065b7d0a7c3`.
- The matching fixture request is staged at
  `s3://aimada-wave1-dev-e00g6zvxpr00/releases/wave1-g4-9b12be9-20260822/staging`.
  Five objects were read-back verified; request SHA-256 is
  `66db37b624519ab89873fdc4636b1078ad0a73eb1d9e7fdf7eade698c198cc4d`,
  inventory SHA-256 is
  `994bd1a24f817cf52a51de18aa808425bd044502cc3f019fa955349683058733`,
  and `SUCCESS` was published last. The temporary exact-prefix publisher key
  was deleted and the bucket policy was independently verified back at its
  read-only `releases/*` baseline.
- The development Object Storage MysteryBox selectors are active. No
  MysteryBox selectors currently exist for `MLFLOW_TRACKING_USERNAME` and
  `MLFLOW_TRACKING_PASSWORD`; the submit adapter correctly refuses to render a
  G4 dry run without both.
- USD 8.03 remains the latest authoritative console billing observation, from
  2026-08-21 11:57 UTC. The CLI profile exposes no billing contract ID and the
  authenticated browser bridge is unavailable in this workspace, so current
  spend has not been reconciled. The submit adapter correctly refuses to use
  the stale value as current spend.
- `make check-submit` passes all 12 submit/render adapter tests. No Job was
  created, no prior evidence was re-archived, and the reviewed G4 dry-run
  artifact remains intentionally ungenerated until both blockers above are
  resolved.

### 2026-08-26 Operator Update

- Current project spend was reconciled by the Operator at USD 8.12 including
  VAT. This remains below both the USD 25 reporting trigger and USD 40 stop-new-
  submissions threshold.
- The initial live MysteryBox metadata-only listing confirmed that no selectors
  existed for `MLFLOW_TRACKING_USERNAME` or `MLFLOW_TRACKING_PASSWORD`; creating
  those two value secrets from the existing private MLflow administrator
  credentials was the final dry-run blocker.
- The two tracking selectors were subsequently created from the existing
  private deployment environment without printing either payload:
  `mbsec-e00dmydkcge9t3b31v` for `MLFLOW_TRACKING_USERNAME` and
  `mbsec-e00fjt8vg2q7n7t0fb` for `MLFLOW_TRACKING_PASSWORD`. Both are `ACTIVE`.
  Access used a temporary port-22 rule restricted to the current operator
  `/32`; that rule was deleted, the original `185.115.4.0/32` rule remains
  unchanged, and the MLflow VM was verified `STOPPED` afterward.
- The reviewed dry run is
  `outputs/lightgbm-wave1/g4-dry-run-20260826.json`, with SHA-256
  `35f4bd6de37eb3e6ef5303626388149b4f46a7bcd76328fc8cb02acdedba02de`.
  It binds spend USD 8.12, development Job count 5, the staged request hash,
  immutable image, fixed resources, private subnet and all four redacted
  MysteryBox injections. It declares `cloud_resources_created: false`; no Job
  was submitted.

### 2026-08-26 G4 Submission Reconciliation

- Two submissions of the original reviewed command were rejected before Job
  creation with `Labels: label value length (131) exceeds maximum value (64)`.
  Updating the Nebius CLI from `0.12.245` to `0.12.265` did not change the
  server response. Neither call consumed a development Job.
- Commit `725279d` split the runtime image evidence into label-safe repository
  and SHA-256 environment fields, while reconstructing and enforcing the exact
  immutable image reference inside the workload. The focused Wave 1 suite
  passed 22 tests, `make check-submit` passed 12 tests, and Ruff passed. The
  commit is on `main` and `origin/main`.
- A replacement `linux/amd64` image passed its import and exact `run-s3` CLI
  smoke checks and was pushed as
  `cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/lob-arena-jobs@sha256:97a6f9a40ab2286eae5f82cd4f61fa478a4e0d050fc71070c8a1468ae9bf601b`.
- The replacement fixture is staged at
  `s3://aimada-wave1-dev-e00g6zvxpr00/releases/wave1-g4-725279d-20260826/staging`.
  Its five objects passed read-back verification, request SHA-256 is
  `0ab054c163e1c1cd11cff3b76f061868bd3493e65329b35b54c06507590ba82b`,
  inventory SHA-256 is
  `569ee6f7b531283eff5ff85d266029bb1594e0332c46d031e0c862ec41071d9e`,
  and `SUCCESS` was published last. The temporary publisher key was deleted and
  the development bucket policy was independently verified back at its single
  read-only `releases/*` rule.
- The replacement dry run is
  `outputs/lightgbm-wave1/g4-dry-run-725279d-20260826.json`, with SHA-256
  `cb1a6c0422aa3e48187f1463fd0499076a2c178e4c1b91c98e0613fad0006aaf`.
  It preserves the immutable image, fixed project/resources, spend USD 8.12,
  development count 5, exact staged request and four redacted MysteryBox
  selectors. It contains no volume or legacy full-image environment value; the
  longest plain environment value is exactly 64 characters.
- The authorized replacement submission was nevertheless rejected with the
  same 131-character label error before Job creation. This rules out the
  environment variable as the source: 131 is the length of the full immutable
  `--image` reference, which the AI Job service is passing through a Compute
  label limited to 64 characters. The current CLI and official command
  reference advertise `registry/path@digest`, but the live service cannot
  create this Job with that documented form.
- The governed development count therefore remains 5/20. MLflow was started
  only for the authorized submission window and is independently verified
  `STOPPED` after the rejection. No monitoring or result collection applies
  because no Job ID exists.

The Operator explicitly approved the bounded short-tag exception on 2026-08-26.
The governed request and runtime contract continue to bind the complete image
digest. Deployment uses the 63-character, digest-derived reference
`cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/g:97a6f9a40ab2286e`, which resolves
to the reviewed `sha256:97a6f9a40ab2286eae5f82cd4f61fa478a4e0d050fc71070c8a1468ae9bf601b`.
The submitter now requires the explicit exception flag, verifies this mapping
when producing the dry run and immediately before submission, reads back the
created Job image, verifies the mapping again, and requests cancellation if the
post-creation check fails. The monitor compares the Job against the reviewed
deployment reference while collection retains the full governed digest.

The permanent Nebius correction is tracked by GitHub issue
[#84](https://github.com/khab40/lob-arena/issues/84), under cloud-platform
Feature #14 and blocking LightGBM Story #23. The exception must be retired when
Nebius accepts the documented digest-form image. A fresh spend observation is
still required before generating and authorizing the replacement dry run; USD
8.12 is the pre-attempt baseline, not a fabricated post-attempt observation.

## Prior Decisions Preserved

The earlier Codex/OpenAI discussions established the architecture used here:

- Nebius Serverless AI Jobs for bounded experiments;
- Standard Object Storage for durable inputs/results and MLflow artifacts;
- Nebius Container Registry for cloud images;
- the repository's existing self-hosted MLflow stack on a modest CPU VM;
- Nebius Job logs/metrics plus existing Prometheus/Grafana/MLflow exporters;
- no Kubernetes, Managed MLflow or Managed PostgreSQL under the current credit
  budget; and
- no GPU or vLLM dependency for LightGBM.

Wave 1 extends the existing integration. A second Job, storage, tracking,
registry or observability architecture is forbidden.

## Ownership

- **Codex:** all repository code, tests, generated JSON/YAML, commands,
  validation, evidence collection/analysis and documentation.
- **Operator (Alexey):** Nebius account/IAM/billing/quota actions, permitted-data
  decisions, execution of credentialed commands supplied by Codex, and explicit
  authorization of the one final-test run.

The Operator will not edit code/configuration, calculate hashes, interpret raw
logs, choose retry validity or change model settings after final authorization.

## Fixed Controls

| Control | Fixed value |
| --- | --- |
| Region | `eu-north1` |
| Compute | Serverless AI Jobs, `cpu-d3`, initial `4vcpu-16gb` |
| Concurrency | One Job until reproducibility passes; maximum four afterward |
| Image | Existing `lob-arena-jobs`, extended for ML and pinned by digest; no `latest` |
| Development ceiling | 20 Jobs total, including smoke and repeats |
| Final evaluation | One Job, no automatic retry |
| Timeouts | Smoke uses the 1h platform minimum with a 15m cancellation watchdog; development 60m; final 120m |
| Approved all-in spend ceiling | USD 50, including Jobs, the new MLflow VM, Object Storage and other Wave 1 resources |
| Storage | Standard class, same region |
| Test isolation | Development identity cannot read final-test objects |
| Release authority | Repository schemas, hashes, checksums and signatures; not MLflow |

The Operator may lower ceilings. Raising one requires a recorded plan amendment
before submission.

## Approved G0 Baseline

Approved by the Operator on 2026-08-16:

| Input | Approved value |
| --- | --- |
| Nebius project | `project-e00g6zvxpr00waz8t3y51k` |
| Region | `eu-north1` |
| Credit balance | USD 1,273, Operator-reported on 2026-08-16 |
| Credit expiration | 2026-12-31 |
| Wave 1 ceiling | USD 50 all-in |
| CPU allowance | 12 non-GPU VMs and 200 non-GPU vCPUs; zero in use when checked |
| Current Object Storage | No buckets; approved Wave 1 buckets are listed below |
| Shared MLflow | Running on `aimada-wave1-mlflow`; private URL `http://10.4.0.54:5500`; Nebius Object Storage artifact round-trip verified |
| Corpus status | `APPROVED` for research-only, non-commercial use of the current fixture/synthetic corpus |
| Derived features in Nebius | Permitted for that approved research-only corpus |
| Release signer | `Alexey Khabalov — Wave 1 Release Approver` using the repository-supported Ed25519 flow |
| Prior Object Storage key | Revoked; historical inline Job credentials are forbidden |

The USD 50 ceiling is enforced as a campaign control rather than assumed to be
a native billing hard stop. At USD 25, report spend; at USD 40, stop new
submissions and reconcile; at USD 50, hard-stop the campaign. The signing
private key remains outside the repository, MLflow and Job environment; only
the public key and its SHA-256 identity enter the release.

The approved absolute final quality gates are:

- clean-window false alerts: at most 5 clustered alerts per million evaluable
  events, with the 95% session-cluster bootstrap upper bound at most 10, and no
  regression from the rules baseline;
- attack-family recall: at least 0.90 for every supported family, with the 95%
  session-cluster bootstrap lower bound at least 0.80, and no family below the
  rules baseline; and
- detection delay: p90 at most 1 second, maximum at most 5 seconds, and
  detection-before-benefit rate at least 0.90.

The Operator approves the current fixture/synthetic corpus for research-only,
non-commercial Wave 1 work. This approval does not establish a governed
licensed-corpus benchmark or authorize commercial/client use, so the gates
exercise the pipeline but cannot support a production-quality or
licensed-corpus claim. The highest possible Wave 1 disposition under this G0 baseline is
`cloud_pipeline_qualified_performance_pending`; `qualified_for_wave2` remains
blocked until a permitted governed licensed corpus is frozen and evaluated.
This original G0 disposition rule is superseded for engineering progression by
the public-sample amendment above, while its production/client claim boundary
remains in force.

## Existing Components To Reuse

| Existing component | Wave 1 extension |
| --- | --- |
| `serverless/jobs/Dockerfile` | Add pinned backend ML dependencies while preserving synthetic Job commands |
| `serverless/jobs/render_job_config.py` and `nebius_job_config.yaml` | Add a governed LightGBM workload profile |
| `scripts/build-serverless-images.sh` | Build/smoke/push the same Jobs image to Nebius Container Registry |
| `scripts/create-nebius-ai-job.sh` and `submit_nebius_job.py` | Add validated LightGBM mode; no second submitter |
| `NebiusExperimentOrchestrator` | Reuse submit/status/log/artifact command templates and Job records |
| `NebiusEvidenceArchive` | Index LightGBM evidence and S3 metadata |
| `run_batch_experiments.py` S3 path | Extract and harden shared artifact transport instead of adding another uploader |
| `app.ml.lightgbm.*` and `scripts/lightgbm_v1.py` | Reuse governed loading, training, calibration, prediction, bundling and verification |
| `app.ml.lightgbm.tracking` | Add Nebius resource/throughput/cost metadata to existing experiments |
| Existing MLflow Compose stack | Run on the small CPU VM with Nebius Object Storage artifacts; no second tracker |
| Existing Prometheus/Grafana/exporter | Add Wave 1 run status and metrics alongside Nebius Job telemetry |

## New Code That Is Actually Required

Codex will implement only the missing workload-specific pieces:

- `contracts/lightgbm-cloud-job-v1.schema.json`;
- `contracts/lightgbm-cloud-run-v1.schema.json`;
- typed canonical models under `backend/app/ml/lightgbm/`;
- `serverless/jobs/run_lightgbm_wave1.py` with `preflight`, `development`,
  `final-evaluation` and `verify` modes;
- shared bounded/checksummed S3 transport extracted from the current Job path;
- reusable resource evidence: wall/CPU time, peak RSS, rows/second and resource
  identity;
- frozen request specifications under
  `configs/experiments/lightgbm-wave1/`;
- helper scripts for local input-package construction, collection, repeat
  comparison, candidate freeze and exit-record assembly; the cloud upload
  command remains a G3 deliverable; and
- focused unit, integration, container and failure-path tests plus Make targets.

## Cloud Boundaries

The Operator approved four private Standard buckets in `eu-north1`:

```text
aimada-wave1-dev-e00g6zvxpr00/releases/<release_id>/
aimada-wave1-final-e00g6zvxpr00/releases/<release_id>/
aimada-wave1-results-e00g6zvxpr00/campaigns/<campaign_id>/
aimada-mlflow-e00g6zvxpr00/artifacts/
```

Required principals:

1. **Operator:** push image, submit/cancel Jobs, read status/logs.
2. **Development Job:** read development inputs; write its result prefix; must
   be denied access to final inputs.
3. **Final Job:** read frozen candidate and final inputs; write final result;
   unavailable before final authorization.
4. **MLflow VM:** read/write only the MLflow artifact prefix and attach to the
   shared MLflow VM.

The Operator is the existing human principal; the other three are generated
service accounts. No generated identity joins a default editors group.
Credentials must be supplied through Nebius MysteryBox-backed Job secret
references and must never appear as inline Job environment values. Raw licensed
records are not needed by the model Job and are not uploaded unless separately
permitted.

## Per-Job Evidence

A successful result contains:

```text
request.json
input-inventory.json
environment.json
cloud-run.json
metrics.json
artifacts/<governed LightGBM outputs>
checksums.sha256
SUCCESS
```

Uploads use `staging/`; `SUCCESS` is written last. Incomplete prefixes are
invalid. Failed Jobs publish `failure.json` and `FAILED` when storage is
reachable. Secrets, complete environment dumps and raw licensed rows are
forbidden in logs/artifacts.

## Strict Execution Gates

### G0 — Operator Inputs

Operator confirms:

- Nebius project ID, actual credit balance/expiration and USD 50 ceiling;
- bucket names and `eu-north1`;
- CPU Job quota;
- shared MLflow VM status/private URL;
- fixture/synthetic versus licensed-corpus status;
- permission to store derived train/validation/test features;
- signing identity; and
- numeric final gates for clean-window false alerts, attack-family recall and
  detection delay.

Codex generates the redacted input template. No credential is committed or
pasted into chat.

**Gate:** local implementation may proceed with fixtures, but no cloud command
runs before all G0 fields are resolved.

**Status:** passed on 2026-08-16. All operator inputs are recorded. The shared
MLflow VM and storage/IAM boundaries exist, and G3 closed on 2026-08-16 with
the spend baseline, operator CPU admissibility confirmation, governed input
hashes and immutable Jobs-image digest verified.

### G1 — Reuse-First Code Implementation

**Status:** implemented locally on 2026-08-16. G3 subsequently passed; the next
submission boundary is the single G4 Cloud Smoke.

Codex:

1. adds strict request/run schemas and canonical IDs;
2. extends the existing Jobs image, renderer and submitter;
3. adds the LightGBM runner using existing model functions;
4. extracts/hardens shared S3 transport;
5. extends the existing orchestrator, evidence archive, MLflow tracking and
   monitoring;
6. adds dry-run, collection, freeze and comparison helpers; and
7. writes all tests and runbook commands.

Fail-closed tests cover unknown fields, mutable images, missing hashes, path
escape, secret serialization, development test access, partial uploads,
duplicate run IDs and final execution without authorization.

**Gate:** existing synthetic/LightGBM tests and new Wave 1 tests all pass;
current Nebius Job behavior remains backward compatible.

### G2 — Local End-To-End Gate

**Status:** passed locally on 2026-08-16. The governed LightGBM regression
suite, Wave 1 failure-path suite, clean-directory fixture lifecycle, submit
checks and CPU-only Jobs-image smoke all passed. No Nebius resource was
created and no cloud credential was used.

Codex runs, with fixture data only:

```text
make lightgbm-v1-test
make lightgbm-wave1-test
make lightgbm-wave1-container-smoke
make check-submit
```

The local flow must stage inputs, preflight, train, calibrate, freeze, authorize
a fixture test, evaluate, bundle, verify, collect and generate an exit record.
The extended Jobs image must contain no GPU/vLLM dependency.

**Gate:** a clean directory can independently verify the complete fixture
package. No Nebius resource is created before this passes.

### G3 — Existing Nebius Foundation

G3 has nine independently evidenced controls:

| # | Control | Owner | Status |
| ---: | --- | --- | --- |
| 1 | Record the Billing start baseline, enable notifications, and enforce the USD 25 report, USD 40 submission stop/reconciliation and USD 50 hard stop | Operator | Complete, 2026-08-16; baseline USD 0 at `2026-08-16T08:22:00Z` |
| 2 | Verify live availability of `cpu-d3 4vcpu-16gb` for one bounded Job | Operator | Complete by operator confirmation, 2026-08-16; no further quota polling |
| 3 | Configure the four Standard Object Storage boundaries with versioning and incomplete-upload cleanup | Codex/operator execution | Complete, 2026-08-16 |
| 4 | Create the three least-privilege service identities | Codex/operator execution | Complete, 2026-08-16 |
| 5 | Prove the development identity is denied final-input access | Codex | Complete, 2026-08-16 |
| 6 | Authenticate the existing build script to Nebius Container Registry | Codex | Complete, 2026-08-16 |
| 7 | Deploy the existing self-hosted MLflow stack on the CPU VM with Nebius Object Storage and run its registry/artifact smoke | Codex | Complete, 2026-08-16 |
| 8 | Construct, hash, upload and read back the permitted derived fixture input package under the development release prefix | Codex; no additional Operator approval because research-only derived storage is already approved | Complete, 2026-08-16 |
| 9 | Build, smoke, push the existing extended Jobs image and resolve its immutable registry digest | Codex | Complete, 2026-08-16 |

Operator returns redacted outputs, IDs, digest and access-test results only.

**Gate:** passed. IAM isolation, input hashes, image digest and MLflow
round-trip verify in `outputs/nebius/evidence/wave1-g3-exit-20260816.json`.

**Partial status (2026-08-16):** the live development credential passed its
positive control on `aimada-wave1-dev-e00g6zvxpr00/releases/` and received
`AccessDenied` for the same operation and prefix on
`aimada-wave1-final-e00g6zvxpr00`. The final bucket policy names only the final
group. The redacted local evidence is
`outputs/nebius/evidence/wave1-development-denied-final-20260816.json`. G3
remains open for billing/quota evidence, governed input staging and the
immutable Jobs-image digest.

**Container Registry authentication status (2026-08-16):** passed. Registry
`registry-e00jaawvmwdhya5z2w` (`aimada-wave1`) is active in the approved
project. Docker uses the Nebius credential helper for
`cr.eu-north1.nebius.cloud`; a redacted helper probe returned username `iam`
and a non-empty credential, and an authenticated lookup under the exact
registry path returned `no such manifest` rather than an authorization error.
The existing build script is therefore addressed with:

```bash
IMAGE_NAMESPACE=cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w \
TAG=<immutable-wave1-tag> \
PLATFORM=linux/amd64 \
SMOKE=true \
PUSH=true \
./scripts/build-serverless-images.sh
```

Do not run the push until the image tag is frozen. The redacted authentication
evidence is `outputs/nebius/evidence/wave1-registry-auth-20260816.json`.

**Shared MLflow status (2026-08-16):** passed. The existing MLflow 3.13,
PostgreSQL 16 and read-only exporter services run on VM
`computeinstance-e00xq8hqrzks2pf3gn` (`cpu-e2`, `2vcpu-8gb`) at private URL
`http://10.4.0.54:5500`. Security group
`vpcsecuritygroup-e00yz1akcnmb6zrk1h` permits port 5500 only from the selected
`10.0.0.0/13` subnet and SSH only from the recorded operator `/32`; a public
port-5500 probe failed as required. The VM attaches only
`serviceaccount-e00cs5gpgzah6zxzny`.

MinIO is not deployed on Nebius. MLflow uses
`s3://aimada-mlflow-e00g6zvxpr00/artifacts` through the dedicated bucket key.
The running MLflow container is pinned to Nebius Container Registry digest
`sha256:2845ef39ff83f79748cda1aa507b2dcc0de6d379b7683e75d27d01ca9a020076`.
Post-cutover smoke run `aa91baa2acba40dbbd005a197fa7ffa6` finished and its
45-byte probe was uploaded and downloaded at
`artifacts/2/aa91baa2acba40dbbd005a197fa7ffa6/artifacts/deployment/probe.txt`
(ETag `0adb1320d78be884bea777301fcd2dc5`). The exporter was healthy. The
short-lived operator Registry login was removed after the pull; no MLflow
Registry static key remains. Registry-scoped `viewer` permit
`accesspermit-e00mqgt54phkyntg78` remains, while the broader project-viewer
fallback attempted during diagnosis was removed.

Billing evidence is recorded in
`outputs/nebius/evidence/wave1-billing-baseline-20260816.json`. The redacted MLflow evidence is
`outputs/nebius/evidence/wave1-mlflow-roundtrip-20260816.json`.

**G3 completion (2026-08-16):** the approved research fixture is published at
`s3://aimada-wave1-dev-e00g6zvxpr00/releases/wave1-g3-42f6b88a4f8f/staging`
with five verified objects, canonical inventory SHA-256
`6d5834ed96a354ca83144597aeddd467fc11fe900f50746062220124108acf22`,
and `SUCCESS` published last. The temporary single-prefix staging writer grant
was revoked; development reads remain allowed, development writes and final
reads are denied. The Jobs image passed its `linux/amd64` smoke and is frozen as
`cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/lob-arena-jobs@sha256:bdad8804c52a4b3141101f26f55275937c721997093902c2ea8aa9cc4fd7ab69`.
G3 is closed; no AI Job was submitted during G3.

At published Compute prices, the running `2vcpu-8gb` VM is approximately
USD 0.0496/hour for compute and its 32 GiB network SSD approximately USD
0.0031/hour, before static-IP, network and Object Storage charges. This is a
campaign estimate, not a billing record. Stop the VM through the Nebius API
when shared tracking is not needed; a guest `poweroff` is unsafe while the VM
uses the `RECOVER` policy.

#### G3 IAM and storage bootstrap

The three generated identities are service accounts for development Job S3
access, final Job S3 access and the shared MLflow VM. The Operator is the
existing human account and is not issued another credential. Each service
account is the only member of its own custom IAM group; no generated identity
joins `editors` or another default group.

Use the fixed first campaign ID `wave1-research-20260816`. Changing it after
objects are staged requires a new reviewed bucket policy, so do not use a run
ID or Job ID here.

From the repository root, first authenticate and run the local-only plan:

```bash
nebius iam get-access-token >/dev/null
./scripts/provision-nebius-wave1-identities.sh \
  --campaign-id wave1-research-20260816
```

Review the printed matrix. It must show that development has no policy on the
final bucket. Then apply it once:

```bash
./scripts/provision-nebius-wave1-identities.sh \
  --campaign-id wave1-research-20260816 \
  --apply
```

The apply is idempotent for the exact declared resources. It creates missing
service accounts, custom groups, memberships, MysteryBox-backed access keys and
buckets. If an approved bucket already exists with a different policy,
versioning setting or lifecycle rule, it stops instead of overwriting that
bucket. The generated non-secret resource inventory is written with mode 0600
to:

```text
outputs/nebius/wave1-iam-wave1-research-20260816.json
```

Do not retrieve an access-key payload or copy it to `.env`. AI Jobs consume the
two MysteryBox selectors in `access_keys.<lane>` as `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY`. `job_s3_api` supplies the exact endpoint and governed
prefixes. Wave 1 must not pass `--volume`: it stages input and output through
prefix-scoped S3 API calls on ephemeral job disk. Attach the MLflow service account ID from
`service_accounts.mlflow` to the MLflow VM with the VM create command's
`--service-account-id` option; its S3 access key is already stored in
SecretStash.

The final S3 key is created inactive. Only after the repository verifies the
signed final authorization, run the exact activation command printed by the
script. Submit the one final Job, then immediately run the printed deactivation
command. A second final submission requires a new authorization decision.

The expected storage grants are:

| Identity | Read | Write | Explicitly absent |
| --- | --- | --- | --- |
| Development Job | development `releases/*` | this campaign's `development/*` results | every final-input object and final-result prefix |
| Final Job | final `releases/*`; this campaign's development candidate | this campaign's `final/*` results | every other campaign prefix |
| MLflow VM | MLflow `artifacts/*` | MLflow `artifacts/*` | development, final and result buckets |

After apply, return only the generated resource IDs and access-test outcomes.
Never return SecretStash payloads. IAM denial and the MLflow artifact round
trip passed and were rebound into the completed G3 exit record.

#### Completed G3 execution slice

1. **Operator — billing evidence: complete.** The USD 0 baseline and USD
   25/40/50 controls are recorded.

   ```text
   BILLING_BASELINE_AT=<ISO-8601 UTC timestamp>
   WAVE1_SPEND_TO_DATE_USD=<number>
   ALERT_25_CONFIGURED=YES
   STOP_40_ACKNOWLEDGED=YES
   HARD_STOP_50_ACKNOWLEDGED=YES
   ```

2. **Operator — CPU admissibility:** confirmed. Do not poll quota again.
3. **Codex — close the staging gap: complete.** The command constructs
   the fixture-derived development package, writes its canonical inventory and
   checksums, uploads through the development identity to
   `s3://aimada-wave1-dev-e00g6zvxpr00/releases/<release_id>/staging/`, verifies
   every object by size/hash, publishes `SUCCESS` last, and reads the completed
   package back. It must refuse final-bucket URIs, mutable inputs, duplicate
   release IDs and inline credentials.
4. **Codex — regress locally: complete.** `make lightgbm-wave1-test`,
   `make lightgbm-wave1-local-e2e`, `make lightgbm-wave1-container-smoke` and
   `make check-submit` after the staging command is added.
5. **Codex — stage once: complete.** The approved research-only fixture package
   was uploaded, redacted input hashes/object metadata were retained, and the
   development-to-final denial proof was repeated after staging.
6. **Codex — publish the Jobs image: complete.** An immutable tag was derived
   from the verified source/input contract, built for `linux/amd64`, smoke-run,
   pushed with `scripts/build-serverless-images.sh`, and resolved to the
   Registry digest. Only `<repository>@sha256:<digest>` is used afterward.
7. **Codex — G3 exit check: complete.** The redacted G3 record binds bucket IDs,
   identity IDs, denial evidence, input inventory hash, Jobs-image digest,
   MLflow run `aa91baa2acba40dbbd005a197fa7ffa6`, and the spend baseline. Only a
   passing record unlocks G4.
8. **Operator — G4 manual action:** after reviewing the generated dry run,
   submit exactly one `cpu-d3 4vcpu-16gb` smoke Job with the minimum one-hour
   Nebius timeout and a 15-minute operator cancellation watchdog, and return only
   its Job ID and status. Codex performs all collection and interpretation.

### G4 — Cloud Smoke

Codex generates the dry run; Operator submits it exactly once and returns the
Job ID/status; Codex collects and verifies the result.

Limits: one `4vcpu-16gb` Job, one-hour platform timeout, 15-minute operator
watchdog, smallest permitted release, no test access, no parallelism, no
automatic retry.

**Gate:** `SUCCESS`, checksums, MLflow development record, Job identity, runtime
and resource evidence verify; no secret appears in config/logs/artifacts.

**Implementation status (2026-08-22): complete locally.** The G4 chain now
binds an immutable staged request to a selector-redacted dry run, requires the
Operator-confirmed dry-run SHA-256 before submission, records the returned Job
ID, enforces the USD 40 pre-submit and 20-Job campaign stops, monitors actual
Job status/resources with a 15-minute cancellation watchdog, collects redacted
logs, downloads and checksum-verifies the result prefix, requires a bound
MLflow run and post-Job cost reconciliation, and emits one fail-closed G4 exit
record. `make lightgbm-wave1-g4-check` exercises this flow without cloud access.
The VM remains stopped and no sixth Job has been submitted by this implementation
step; runtime completion still requires the separately authorized cloud action.

**Attempt status (2026-08-16 through 2026-08-17): failed.** Job
`aijob-e00zg7n8dsb66xef1c` remained `STARTING` for the entire 15-minute policy
window while its CPU VM was `RUNNING`; it emitted no container logs and
published no result objects. Codex cancelled it at `2026-08-16T09:22:21Z`.
The temporary Registry pull secret was deleted. The one-use short image alias
resolved to the governed digest both before and after the attempt. Evidence is recorded in
`outputs/nebius/evidence/wave1-g4-attempt-20260816.json`.

After explicit Operator authorization to repeat G4, second Job
`aijob-e00ytz0nsa2wz6ajb3` was submitted without Registry credentials, using
same-project Registry access but still using S3 filesystem mounts. It also
remained `STARTING` for the full 15-minute window while its VM was `RUNNING`,
with no container logs or result objects. Codex requested cancellation at
`2026-08-16T10:15:19Z`; final state was `CANCELLED`. The image alias still
resolved to the governed `linux/amd64` digest after cancellation. Evidence is
recorded in `outputs/nebius/evidence/wave1-g4-retry-20260816.json`.

Three explicitly authorized no-volume attempts followed on 2026-08-17:

- `aijob-e00yhjdjttz772e843` and `aijob-e00a7m37mg0yt5gsgp` reached the
  container but used an older image that did not contain the `run-s3` command;
  both exited on CLI validation and were cancelled.
- `aijob-e00e0cn0ttvf29g99r` used a reversed command/argument layout and failed
  because Python tried to open `/job/serverless/jobs/run` as a file.

None reached LightGBM training or published a result. These three attempts and
the two mount-startup attempts all count against the development ceiling.

The S3 API correction is implemented locally. Successful July Jobs used no
volumes: the container received credentials and staged data with S3 APIs. Both
August attempts mounted whole bucket roots, but Wave 1 IAM intentionally grants
only release/result prefixes; the mount agent requires bucket-namespace access
before starting the container. The corrected runner lists only the exact input
prefix, downloads and checksum-verifies it to ephemeral disk, executes the
unchanged local-path model runner, verifies output, uploads non-terminal objects
and publishes `SUCCESS` last. Submission now rejects `NEBIUS_VOLUME` and
requires two MysteryBox credential selectors. The no-volume design has reached
the container, but the deployed image/entrypoint has not yet executed the S3
runner successfully. G4 remains locked until the image contents, command
contract, input package, and dry run are verified together and the Operator
explicitly authorizes one bounded attempt.

Corrected G4 sequence:

1. Codex builds and locally smokes a new `linux/amd64` image containing the
   exact S3 API CLI entrypoint, then pushes it through the existing Nebius
   Registry path and resolves the immutable digest.
2. Codex stages a new immutable development release whose canonical request names
   the exact S3 result prefix, experiment specification, approved project/image/
   resource envelope, and private MLflow URI. The resulting request-evidence
   file and its canonical hash are mandatory submitter inputs.
3. Codex renders a dry run with no `--volume`, the fixed eu-north1 endpoint,
   exact `cpu-d3` / `4vcpu-16gb` / 100 GiB / one-hour resources, separate
   MysteryBox selectors for AWS and MLflow credentials, and the out-of-band
   trusted public-key fingerprint for final evaluation; local policy tests pass.
4. Operator reviews the redacted dry run and explicitly authorizes exactly one
   15-minute G4 submission. No authorization means no Job.
5. After submission, Codex collects Job/log/result evidence, verifies the
   downloaded result and MLflow record, binds the returned Job ID, actual
   project/image/resources and nonnegative cost estimate, reconciles spend, and
   either closes G4 or stops with one bounded failure record.

The stopped VM remains stopped during this baseline reconciliation. No prior
evidence is re-archived; archive upload is opt-in and supports the standard AWS
ambient credential chain when explicitly enabled.

### G5 — Reproducibility

Operator submits the same development request three times sequentially. Codex
compares them.

Must match exactly: model/prediction hashes, best iteration, calibration,
thresholds, metrics, feature importance/order and all governed identities.

May differ: Job/run/MLflow IDs, timestamps, runtime, peak memory and cost.

**Gate:** any unexplained model, prediction or metric difference blocks tuning
and Wave 2.

### G6 — Bounded Development Campaign

The campaign remains capped at 20 total development Jobs. Five failed G4 Jobs
have consumed five slots, so the remaining matrix is capped at 15 Jobs:

| Group | Jobs |
| --- | ---: |
| Corrected smoke plus three repeats | 4 |
| Predeclared hyperparameters | 4 |
| Feature-family ablations | 2 |
| Selected-candidate seed stability | 2 |
| Raw/Platt/isotonic calibration | 3 |

No exploratory replacement is permitted. Any additional failure consumes one
of these 15 slots and requires the unstarted portion of the matrix to shrink;
raising the 20-Job ceiling requires a recorded amendment before submission.

Operator runs only Codex-generated commands. Codex ranks candidates using
validation only. Failed Jobs count toward the ceiling. No adaptive trial is
added after viewing results. Stop submissions at 80% of the spend ceiling and
reconcile before continuing.

**Gate:** one candidate is selected by the predeclared validation policy; all
rejected candidates remain in the report.

### G7 — Candidate Freeze And Manual Authorization

Codex generates a verified frozen package with the selected hashes, operating
mode/threshold, validation-only report, image digest, predicted final cost/time
and proof that test data has not been accessed.

Operator performs the sole governance transition:

```text
APPROVE WAVE1 FINAL TEST <candidate_hash> <timestamp>
```

Codex stores it as a signed authorization artifact. Different hash, silence or
informal approval is invalid.

**Gate:** final identity remains unavailable until authorization verifies.

### G8 — One Final Evaluation

Operator uses the final identity to submit the digest-pinned command exactly
once. Codex collects and verifies predictions, model bundle, rules comparison,
benchmark, uncertainty and cloud-run evidence. Operator disables the final
identity afterward.

If a failure occurs before any test read, Codex may prove that and prepare a new
authorization. If test bytes were read, there is no retry or further tuning.

**Gate:** complete release verification passes; rules and LightGBM used the
same observations; no post-test change occurs; MLflow governed-evaluation is
logged only after verification.

### G9 — Cost Reconciliation And Exit

Operator exports the campaign's Nebius Billing usage with sensitive tenant
fields redacted. Codex assembles:

- estimated versus billed cost;
- total/per-Job active time, rows/second and cost per million rows;
- memory/right-sizing recommendation;
- quality/operational gate results;
- claim boundary and accepted/rollback identities; and
- signed JSON and Markdown exit records.

The disposition is exactly one of:

- `qualified_for_wave2`;
- `research_baseline_qualified`;
- `cloud_pipeline_qualified_performance_pending`; or
- `not_qualified`.

`qualified_for_wave2` or `research_baseline_qualified` permits Transformer
implementation. The latter permits engineering only and cannot support a
production/client performance claim.

## Default Acceptance Rules

- 100% schema/checksum verification and zero secret findings.
- Zero final-prefix reads before G8.
- Three exact deterministic development repeats.
- One authorized final-test access.
- Current validation floors start at 0.90 precision and 0.90 recall; they may be
  raised at G0 but not lowered after G6.
- Calibration must not worsen both Brier score and expected calibration error
  versus raw probabilities.
- All Jobs stay within timeout/memory/disk and the approved spend ceiling.
- Final release verifies without MLflow; MLflow round-trip then succeeds.
- No production-quality conclusion without the G0 business gates and governed
  licensed corpus.

## Failure Rules

| Failure | Action |
| --- | --- |
| Schema/checksum/path failure | Stop; correct locally and rerun tests before a new Job |
| Secret exposure | Revoke/rotate, quarantine evidence and restart foundation verification |
| Development identity reads final input | Revoke immediately; repair IAM and repeat G3 |
| Mutable image/input changed | Invalidate affected runs; create a new campaign ID |
| Reproducibility mismatch | Block tuning and Wave 2 |
| Incomplete upload | Reject prefix; publish only after source bytes verify |
| MLflow unavailable | Preserve governed files; gate remains blocked until logged exactly once |
| Spend reaches 80% | Stop submissions and reconcile |
| Final Job read test data then failed | No automatic retry or tuning |

## Completion Checklist

- [x] G0 operator decisions recorded (2026-08-16).
- [x] G1 reuse-first code and tests pass locally (2026-08-16).
- [x] G2 local fixture package verifies (2026-08-16).
- [x] G3 existing Nebius components, IAM boundaries, governed input and immutable image verify (2026-08-16).
- [ ] G4 cloud smoke passes (two mounted-S3 attempts cancelled after 15 minutes in `STARTING`; S3 API correction is local-only and awaits an authorized attempt).
- [ ] G5 three-run reproducibility passes.
- [ ] G6 development campaign completes within ceilings.
- [ ] G7 candidate and final authorization are signed.
- [ ] G8 one final evaluation verifies.
- [ ] G9 billing reconciliation and exit records are signed.
- [ ] Issue #23 and ARD-0035 receive evidence links and final status.
- [ ] Issue #24 remains Todo unless disposition is `qualified_for_wave2` or
  `research_baseline_qualified`; the latter unlocks engineering only.

## Completed Implementation Through G3

G1-G3 are complete. They extended the existing Jobs image, renderer, submitter,
orchestrator, evidence archive, MLflow tracking and monitoring; added the
LightGBM runner, contracts, shared storage hardening and tests; and passed
without changing the LightGBM algorithm. G3 reused the existing Nebius
Registry, four governed buckets, three identities and shared MLflow VM. The
second mounted G4 Cloud Smoke also failed before container start. The July-style
S3 API correction is implemented and locally tested. Work stops at G4 pending
a new immutable image/input package, reviewed dry run, and explicit submission
authorization; G5 is not unlocked.

## Related Documentation

- [Nebius Public Market Data Plan for LightGBM Wave 1](nebius-public-market-data-lightgbm-plan.md)
- [ARD-0035: Nebius-First Qualification Of Governed LightGBM](architecture/ARD-0035-nebius-lightgbm-first.md)
- [Governed LightGBM v1 Runbook](lightgbm-v1-runbook.md)
- [Shared MLflow Tracking](mlflow-tracking-server.md)
- [Nebius Deployment](nebius-deployment.md)
- [Project phases](PHASES.md)
