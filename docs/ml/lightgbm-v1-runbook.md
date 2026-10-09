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

See [digest-pinned Jobs](../operations/digest-pinned-jobs.md) and immutable approved
G8 records for concrete package/runtime identities. Current execution policy
supersedes the old `WAVE1_SPEND_TO_DATE_USD` and fixed-slot examples; it does not
change their recorded hashes or create permission for a new run.

## G5 reproducibility comparison

The completed gate uses exactly three governed development runs with distinct
run, provider Job and MLflow identities. It is a verification contract, not a
request to repeat the cost-bearing sequence. Each request binds its own immutable
`releases/<run_id>/staging` input URI and C4 MLflow dataset-release receipt;
reusing the corpus-release prefix would collide and is forbidden. Verify receipt,
frozen root and development projection identity before execution. MLflow train/
validation Dataset inputs carry complete Parquet SHA-256 in `artifact_sha256`
tags and bounded digest prefixes.

The retained comparator interface is:

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

Require verified collections/test isolation and exact request inputs, model and
validation-prediction hashes, best iteration, metrics, calibration, operating
points, feature order/importance, schemas, reliability and governed identities.
Only timestamps, external IDs, runtime, peak memory, cost, request hash and
timestamp-bearing package hash may differ. `--allow-fixture-preflight` emits
`local_fixture_comparator_preflight_only`, never a G5 pass. A future real repeat
requires C0–C4 prerequisites and separate exact operator authorization.
