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
