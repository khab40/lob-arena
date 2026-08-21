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
They do not establish client performance. A performance release requires the
licensed 30-session corpus, two-reviewer clean labels, frozen test split and
signed governed evaluation.

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
NEBIUS_WAVE1_INPUT_URI=s3://aimada-wave1-dev-e00g6zvxpr00/releases/RELEASE_ID/staging \
NEBIUS_OBJECT_STORAGE_ENDPOINT_URL=https://storage.eu-north1.nebius.cloud \
NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID=ACCESS_ID_SECRET_SELECTOR \
NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID=SECRET_KEY_SELECTOR \
python scripts/submit_nebius_job.py \
  --workload lightgbm-wave1 \
  --image cr.eu-north1.nebius.cloud/REGISTRY/jobs@sha256:DIGEST \
  --dry-run
```

All five failed attempts count against the fixed 20-Job development ceiling;
15 slots remain. The next cloud action remains one explicitly authorized,
15-minute G4 development smoke after the image contents, command contract,
input package, and dry run verify together. Mutable tags, inline credentials,
filesystem mounts, broad bucket probes, and unbounded prefixes are rejected.
