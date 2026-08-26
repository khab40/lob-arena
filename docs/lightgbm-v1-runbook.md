# Governed LightGBM v1 Runbook

LightGBM v1 is a binary `attack_active` challenger. It never trains on the
frozen test fold and never converts unreviewed history into label zero.

## Required inputs

- passing locally verified corpus manifest and validation;
- frozen chronological split;
- externally SHA-256-anchored governed feature release;
- `lob_features_v2` configuration; and
- one shared artifact root containing the feature release and all model output.

The shared root is mandatory because every manifest URI is root-relative and
the final verifier resolves every referenced byte from that namespace.

## Commands

Install the optional ML dependencies and run the focused gate:

```bash
cd backend
uv sync --extra ml
cd ..
make lightgbm-v1-test
```

The delivery commands are deliberately separate:

```text
make lightgbm-train-dev
make lightgbm-calibrate
make lightgbm-evaluate-test
make lightgbm-build-bundle
make lightgbm-verify-release
```

Provide the governed input paths through the environment variables named in
the corresponding Make recipes. `LIGHTGBM_CREATED_AT` must be an explicit
timezone-aware ISO-8601 timestamp and `LIGHTGBM_GIT_COMMIT` must be the exact
40-character commit ID. The test command must be invoked only after validation
calibration and operating modes are frozen.

Calibration defaults to Platt scaling. The direct CLI can select isotonic or
raw calibration and configure precision/recall floors:

```bash
backend/.venv/bin/python scripts/lightgbm_v1.py calibrate --help
```

## Outputs

Training produces `model.txt` and `training-run.json`. Calibration produces
raw validation predictions, the calibration manifest, metrics, global feature
importance, reliability evidence and the ordered feature schema. Frozen-test
scoring produces predictions, alert-level contributions and a prediction
manifest. Bundle assembly writes `model-bundle.json` and `checksums.sha256`,
then runs the Phase 0 byte verifier immediately.

The complete verified release can be supplied to the existing governed
benchmark by adding these fields to `governed_evaluation_plan_v1`:

```json
{
  "detector_training_manifest": "path/to/training-run.json",
  "detector_calibration_manifest": "path/to/calibration-manifest.json",
  "detector_model_bundle": "path/to/model-bundle.json",
  "detector_predictions_manifest": "path/to/prediction-manifest.json",
  "detector_artifact_root": "path/to/shared-artifact-root"
}
```

All five fields are required together. The evaluator reruns complete release
verification before replacing canonical rule alerts with the frozen LightGBM
alerts for the candidate side. Deterministic-rule session metrics remain the
paired baseline. Detection-before-benefit, false alerts per million events,
regime matrices, uncertainty and challenge-family results continue to come
from the governed canonical benchmark. The runtime adapter is locked to the
operating mode evaluated by that release.

## MLflow

Pass `--mlflow-tracking-uri` to calibration to record the development run.
Bundle logging is permitted only after local verification. MLflow stores
permitted manifests, metrics, diagrams, feature importance and the model; it
does not receive raw LOBSTER records or become the approval authority.

## Current evidence boundary

Fixture and synthetic runs prove determinism, compatibility and orchestration.
They do not establish client performance. Official public Nasdaq ITCH samples
plus the repository LOBSTER sample may support the research-only
`research_baseline_qualified` disposition and unlock Wave 2 engineering. A
production/client performance release still requires appropriately licensed
data, two-reviewer clean labels, a frozen test split and signed governed
evaluation suitable for that claim.

## Wave 1 local gate

The Nebius Wave 1 shell reuses this implementation without submitting a cloud
job. Run the local gates from the repository root:

```bash
make lightgbm-v1-test
make lightgbm-wave1-test
make lightgbm-wave1-local-e2e
make lightgbm-wave1-container-smoke
make check-submit
```

`lightgbm-wave1-local-e2e` creates a clean temporary package, trains and
calibrates on the approved research fixture, freezes the candidate, creates an
ephemeral Ed25519 fixture authorization, opens the fixture test fold once,
builds and verifies the bundle, collects checksums, and writes the exit record.
It does not create a Nebius resource or use cloud credentials.

For manual inspection in a retained directory:

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

While Nebius issue #84 remains open, the Operator-approved workaround may be
used by adding both of the following arguments to the dry-run and submission
commands:

```bash
  --deployment-image cr.eu-north1.nebius.cloud/REGISTRY/g:FIRST_16_DIGEST_HEX \
  --allow-short-tag-workaround
```

The complete deployment reference must be at most 64 characters and remain in
the same registry namespace. The submitter resolves it to the governed digest
during dry-run creation and immediately before submission. After creation it
reads back the Job image, resolves the tag again, and requests cancellation on
any mismatch. The full immutable digest remains in the staged request and
runtime equality contract. This exception is temporary because tags remain
mutable; remove it when Nebius accepts the documented digest image reference.

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
collection and the final G4 exit record remain locked until a fresh post-run
spend observation is supplied. The submitter verifies the canonical request
evidence and rejects inline credentials, filesystem mounts, broad bucket
probes, unbounded prefixes and request/runtime mismatches. The temporary
digest-derived deployment alias is permitted only by the recorded bounded
exception and must resolve to the full governed digest before and after Job
creation. Final evaluation also requires the trusted signing-key SHA-256 from
outside the candidate package.
