# Governed LightGBM v1 Runbook

LightGBM v1 is a binary `attack_active` challenger. It never trains on frozen
test data or converts unreviewed history into label zero. Updated 8 October 2026;
[Bug #357](https://github.com/khab40/lob-arena/issues/357),
[Story #23](https://github.com/khab40/lob-arena/issues/23),
[Project #3](https://github.com/users/khab40/projects/3).

## Execution policy and current workflow

G0–G9 are complete as `research_baseline_qualified`; see
[G9 closure](../operations/g8/g9-closure-20260927.md) and
[current status](../roadmap/CURRENT_STATUS.md). No rerun is needed or authorized.
Agent-initiated training, scoring, synthetic training fixtures and frozen-runtime
rehearsals run on Nebius Serverless Jobs. Local work is orchestration, static
checks and artifact inspection. Apply the
[validation policy](model-validation-execution-policy.md) and
[ML lifecycle](../use-cases/ml-lifecycle.md). The interfaces below describe how
an approved package is prepared; they do not grant access, execution or spend.

## Required inputs

Require a passing verified corpus/validation, frozen chronological split,
externally SHA-256-anchored governed feature release and `lob_features_v2`
configuration. Keep the feature release and model outputs under one shared
artifact root: manifest URIs are root-relative and verification resolves every
referenced byte from that namespace.

## Commands

Install optional dependencies for orchestration/static inspection:

```bash
cd backend
uv sync --extra ml
cd ..
```

The phase interfaces are deliberately separate. Execute model phases only
inside an exactly approved bounded Job package, including model-runtime tests:

```text
make lightgbm-v1-test
make lightgbm-train-dev
make lightgbm-calibrate
make lightgbm-evaluate-test
make lightgbm-build-bundle
make lightgbm-verify-release
```

Supply governed paths using each Make recipe's environment variables.
`LIGHTGBM_CREATED_AT` must be explicit timezone-aware ISO-8601;
`LIGHTGBM_GIT_COMMIT` the exact 40-character commit. Test scoring requires frozen
calibration/operating modes and separate final-access authorization. Generic
calibration defaults to Platt; the completed research release selected isotonic.
The direct CLI also supports isotonic/raw and configurable precision/recall floors:

```bash
backend/.venv/bin/python scripts/lightgbm_v1.py calibrate --help
```

## Outputs

Training writes `model.txt`/`training-run.json`. Calibration writes raw validation
predictions, calibration manifest/metrics, feature importance, reliability and
ordered schema. Frozen scoring writes predictions, alert contributions and
prediction manifest. Assembly writes `model-bundle.json`/`checksums.sha256`, then
runs the Phase 0 byte verifier. A complete release supplies all five fields:

```json
{
  "detector_training_manifest": "path/to/training-run.json",
  "detector_calibration_manifest": "path/to/calibration-manifest.json",
  "detector_model_bundle": "path/to/model-bundle.json",
  "detector_predictions_manifest": "path/to/prediction-manifest.json",
  "detector_artifact_root": "path/to/shared-artifact-root"
}
```

`governed_evaluation_plan_v1` rejects partial fields and verifies the complete
release before using frozen LightGBM candidate alerts. Canonical deterministic
rules remain the paired session baseline. Detection-before-benefit, false alerts
per million events, regime/uncertainty/family reports retain the canonical
benchmark contract. The runtime adapter pins the evaluated operating mode.

## MLflow

Calibration accepts `--mlflow-tracking-uri`; bundle logging follows byte
verification. MLflow indexes permitted manifests, metrics, diagrams, importance,
model and metadata-only Dataset lineage. It receives no raw licensed records
and is not the approval authority. The VM may remain running under the recorded
operator-managed policy; historical start/stop instructions are superseded.

## Current evidence boundary

Fixtures establish determinism/compatibility/orchestration, not client quality.
The completed public Nasdaq/LOBSTER research package supports the signed
research-baseline disposition and Wave 2 engineering. Production/client claims
still need appropriate licensed data, independently reviewed clean labels, a
frozen test protocol and signed evaluation suitable for that claim.

## Wave 1 local gate

This heading preserves links to the original implementation workflow. Its local
training/e2e examples are historical interfaces, superseded for agent execution
by the policy above. The [immutable Wave 1 narrative](https://github.com/khab40/lob-arena/blob/d896efe8ca501c1ef8e6c63442f3433948a6405e/docs/ml/lightgbm-v1-runbook.md#wave-1-local-gate)
retains commands, failed attempts, seven consumed slots, old budget/VM rules and
alias exceptions. Those receipts cannot authorize new submissions or collections.

The retained transport contract uses no filesystem/S3 volumes: separate
MysteryBox selectors supply credentials, the Job downloads the exact development
prefix to `/job/wave1`, then conditionally publishes verified results with SUCCESS
last. MLflow selectors must be `governed-writer`, never bootstrap administrator
or read-only `prometheus`. Reject inline credentials, mounts, broad probes,
unbounded prefixes and mismatched request/runtime identity.

For any newly approved package:

1. Bind exact source/input/output identities, finite resources/timeouts/Job count,
   dependencies and authorization in staging/request evidence.
2. Verify image repository length ≤64 characters **before** build/upload/submission;
   retain the full `@sha256:` digest. Mutable tags, distinct deployment images and
   the historical short/digest-derived alias exception are rejected for new Jobs.
3. Generate the exact dry-run; independent review and operator approval bind its
   SHA-256. Never reuse consumed approval or infer budget from historical slots.
4. Submit once and read back provider Job/project/image/resources/timeout. Missing
   or mismatched identity fails admission; reconcile ambiguous creation before retry.
5. Monitor within the package's bounds; independently verify version/size/hash,
   publication bytes and SUCCESS before accepting completion. Final evaluation
   additionally needs a trusted signing-key fingerprint outside the package.

```bash
cd backend
UV_CACHE_DIR=/tmp/lob-arena-uv-cache uv run --extra ml \
  python ../scripts/lightgbm_wave1.py local-e2e \
  --output ../outputs/lightgbm-wave1/local-fixture
```

G3 supplied the real image digest, least-privilege identities, approved buckets
and MysteryBox secret references on 2026-08-16. After two failed mounted-S3
attempts and three no-volume image/entrypoint failures, the Wave 1 boundary is:
there are no `--volume` arguments. The Job receives `AWS_ACCESS_KEY_ID` and
`AWS_SECRET_ACCESS_KEY` through separate MysteryBox selectors, downloads the
exact development release prefix to `/job/wave1`, runs there, and uploads the
verified result to the exact campaign/run prefix with `SUCCESS` last.

Prepare the dry run with:

```bash
python scripts/lightgbm_wave1.py stage-fixture \
  --release-id RELEASE_ID \
  --run-id RUN_ID \
  --image cr.eu-north1.nebius.cloud/REGISTRY/jobs@sha256:DIGEST \
  --mlflow-tracking-uri http://PRIVATE_MLFLOW_HOST:5500 \
  --output outputs/lightgbm-wave1/RELEASE_ID-request-evidence.json

export NEBIUS_WAVE1_INPUT_URI=s3://aimada-wave1-dev-e00g6zvxpr00/releases/RELEASE_ID/staging
export NEBIUS_WAVE1_REQUEST_EVIDENCE=outputs/lightgbm-wave1/RELEASE_ID-request-evidence.json
export NEBIUS_OBJECT_STORAGE_ENDPOINT_URL=https://storage.eu-north1.nebius.cloud
export NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID=ACCESS_ID_SECRET_SELECTOR
export NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID=SECRET_KEY_SELECTOR
export NEBIUS_MLFLOW_USERNAME_SECRET_ID=MLFLOW_USERNAME_SECRET_SELECTOR
export NEBIUS_MLFLOW_PASSWORD_SECRET_ID=MLFLOW_PASSWORD_SECRET_SELECTOR
export WAVE1_SPEND_TO_DATE_USD=RECONCILED_SPEND_BELOW_40
export WAVE1_DEVELOPMENT_JOBS_CONSUMED=5

python scripts/submit_nebius_job.py \
  --workload lightgbm-wave1 \
  --image cr.eu-north1.nebius.cloud/REGISTRY/jobs@sha256:DIGEST \
  --evidence-output outputs/lightgbm-wave1/g4-dry-run.json \
  --dry-run
```

The two MLflow selectors must contain the `governed-writer` identity created by
the MLflow initializer. They must not contain the bootstrap administrator or
the read-only `prometheus` identity.

New G4 Jobs use the exact approved digest in both commands above and below.
The short-tag workaround for [#84](https://github.com/khab40/lob-arena/issues/84)
is retired: a distinct deployment image or the workaround flag is rejected
before dry-run generation and submission. After creation, the submitter reads
back the exact Job ID and `spec.image`; missing or mismatched readback records a
failed submission and requests cancellation. Historical short-tag receipts
remain available for monitoring and existing-Job recovery, but cannot satisfy
new digest-only collection. See [digest-pinned Jobs](../operations/digest-pinned-jobs.md)
for the retained provider evidence and G8 migration requirements.

Do not submit until the Operator has reviewed `g4-dry-run.json`. Confirm that
review by passing its SHA-256; the submitter refuses a different request,
command, spend baseline, Job count, or dry-run hash:

```bash
DRY_RUN_SHA256=$(shasum -a 256 outputs/lightgbm-wave1/g4-dry-run.json | awk '{print $1}')

python scripts/submit_nebius_job.py \
  --workload lightgbm-wave1 \
  --image cr.eu-north1.nebius.cloud/REGISTRY/jobs@sha256:DIGEST \
  --reviewed-dry-run outputs/lightgbm-wave1/g4-dry-run.json \
  --reviewed-dry-run-sha256 "${DRY_RUN_SHA256}" \
  --evidence-output outputs/lightgbm-wave1/g4-submission.json

python scripts/lightgbm_wave1.py monitor-g4 \
  --submission outputs/lightgbm-wave1/g4-submission.json \
  --output outputs/lightgbm-wave1/g4-monitor.json
```

The monitor queries `nebius ai job get`, verifies the actual project, image,
platform, preset, disk and timeout, collects redacted logs, and cancels a Job
that has not completed within 15 minutes. After a completed Job, download and
verify the immutable S3 result and assemble the exit gate:

```bash
python scripts/lightgbm_wave1.py collect-s3 \
  --result-uri s3://aimada-wave1-results-e00g6zvxpr00/campaigns/wave1-research-20260816/development/RUN_ID \
  --result outputs/lightgbm-wave1/g4-result \
  --submission outputs/lightgbm-wave1/g4-submission.json \
  --monitor outputs/lightgbm-wave1/g4-monitor.json \
  --estimated-cost-usd JOB_COST_ESTIMATE \
  --campaign-spend-to-date-usd RECONCILED_POST_JOB_SPEND \
  --output outputs/lightgbm-wave1/g4-collection.json

python scripts/lightgbm_wave1.py g4-exit \
  --stage-evidence outputs/lightgbm-wave1/RELEASE_ID-request-evidence.json \
  --dry-run-evidence outputs/lightgbm-wave1/g4-dry-run.json \
  --submission outputs/lightgbm-wave1/g4-submission.json \
  --monitor outputs/lightgbm-wave1/g4-monitor.json \
  --collection outputs/lightgbm-wave1/g4-collection.json \
  --result outputs/lightgbm-wave1/g4-result \
  --output outputs/lightgbm-wave1/g4-exit.json
```

Run `make lightgbm-wave1-g4-check` before building the immutable cloud image.
The shared MLflow VM remains stopped until immediately before an explicitly
authorized submission and should be stopped again after evidence collection.

The first six attempts failed before training. Attempt 7 completed the governed
workload, matched `cpu-d3`, `4vcpu-16gb`, 100 GiB and the one-hour timeout, and
published 25 result objects plus `SUCCESS`. Seven of the fixed 20 development
slots are consumed and 13 remain. No rerun is authorized or needed. Governed
collection completed, spend reconciled at USD 8.57 including VAT, all 16 G4
gates passed and G5 is unlocked. The submitter verifies the canonical request
evidence and rejects inline credentials, filesystem mounts, broad bucket
probes, unbounded prefixes and request/runtime mismatches. The temporary
digest-derived deployment alias is permitted only by the recorded bounded
exception and must resolve to the full governed digest before and after Job
creation. Final evaluation also requires the trusted signing-key SHA-256 from
outside the candidate package.

## G5 reproducibility comparison

After C4 publishes the frozen Nasdaq development projection, submit exactly
three separately identified development Jobs using equivalent requests.

The C4 gate must include a successful `make mlflow-log-dataset-release`
receipt. Pass it to projection staging as `--c4-mlflow-evidence`; the package
and request hash-bind the receipt, and the runner rejects a release, frozen
root, or development projection mismatch. Each prepared G5 request must bind
`input_release_uri` to its unique, immutable
`releases/<run_id>/staging` package URI. Reusing the C4 dataset release prefix
would collide with the already-published corpus and is forbidden. The transport
rejects missing or different lineage URIs, and each successful run must expose
metadata-only MLflow Dataset inputs for train and validation with complete
governed Parquet SHA-256 values in `artifact_sha256` tags (and MLflow-bounded
digest prefixes). Do not start the three paid Jobs if any of those
preconditions is absent.

After each result is downloaded and collected, enforce G5 with:

```bash
python scripts/lightgbm_wave1.py g5-compare \
  outputs/lightgbm-wave1/g5-repeat-1/result \
  outputs/lightgbm-wave1/g5-repeat-2/result \
  outputs/lightgbm-wave1/g5-repeat-3/result \
  --collections \
  outputs/lightgbm-wave1/g5-repeat-1/collection.json \
  outputs/lightgbm-wave1/g5-repeat-2/collection.json \
  outputs/lightgbm-wave1/g5-repeat-3/collection.json \
  --output outputs/lightgbm-wave1/g5-repeat-comparison.json
```

The command requires exactly three governed development projections, three
distinct run, Nebius Job and MLflow identities, verified collection receipts,
test-fold isolation and exact agreement across request inputs, model and
validation-prediction hashes, best iteration, metrics, calibration parameters,
operating points, feature order/importance, schemas, reliability artifacts and
governed identities. Only timestamps, external execution IDs, runtime, peak
memory, cost, request hash and timestamp-bearing candidate-package hash may
differ.

`--allow-fixture-preflight` is available only to test the comparison mechanism.
It emits `local_fixture_comparator_preflight_only` and cannot produce a G5 pass.
The real three-Job G5 sequence remains cost-bearing and requires the C0-C4
Nasdaq foundation plus explicit Operator authorization.
