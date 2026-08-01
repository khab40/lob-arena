# ARD-0031: Complete Governed LightGBM v1

Status: Accepted and Implemented

Date: 2026-07-31

Implementation Status: `[lightgbm-v1 done]`

## Context

Phase 2 produced a deterministic binary `attack_active` model but deliberately
stopped before calibration, threshold selection, frozen-test scoring,
explanations, detector loading, paired evaluation, or release assembly. Those
steps must preserve the Phase 0 binding and must not turn MLflow into an
alternative approval path.

## Decision

Complete LightGBM v1 with one shared artifact-root namespace and the following
ordered state transition:

```text
governed train + validation
  -> deterministic training
  -> validation-only calibration
  -> frozen operating points
  -> isolated test access
  -> prediction and contribution artifacts
  -> checksummed verified model bundle
  -> governed paired evaluation
  -> optional MLflow indexing
```

Calibration supports raw probabilities, Platt scaling, and isotonic
regression. Platt scaling is the default. It fits only validation predictions
and records raw/calibrated Brier score, expected calibration error, reliability
bins, and a deterministic reliability diagram. Threshold selection freezes:

- high precision: maximum recall satisfying the configured precision floor;
- balanced: maximum F1; and
- high recall: maximum precision satisfying the configured recall floor.

Deterministic secondary ordering resolves metric ties. An unattainable floor
fails rather than silently changing the requested operating contract.

The test scorer accepts only a separately loaded `final_test` governed feature
dataset. It writes schema-locked Parquet containing raw probability,
calibrated probability, frozen threshold and alert decision. LightGBM tree
contributions are emitted for the top absolute features of every alert. The
runtime detector adapter accepts exactly the ordered governed columns, retains
native missing values, verifies every release artifact before loading, and
returns calibrated probability plus signed feature contributions.

The existing governed benchmark may consume a complete verified LightGBM
release as an external detector alert source. It requires the training,
calibration, model-bundle and prediction manifests together and reruns the
complete release verifier before accepting an alert. A prediction manifest by
itself is insufficient. The benchmark continues to use canonical replay ground
truth, reviewed clean windows, session-cluster statistics, regime evidence and
deterministic-rule session metrics for the paired baseline. Liquidity
evaporation and layering-like results are reported as challenge cases.

The runtime adapter may use only the operating mode recorded by the verified
test prediction manifest. Releasing a different mode requires its own frozen
test prediction and bundle. Prediction validation uses bounded Parquet batches
and a disk-backed exact uniqueness index. Alert loading retains only sparse
alerts and run identities rather than materialising full prediction columns.

Bundle verification parses the feature schema, validation metrics, global
importance and contribution artifacts. It checks their model/calibration
bindings and requires every alert to have a consistent ranked contribution set
using governed feature names.

MLflow receives explicit parameters, metrics, hashes and permitted artifacts
only after local contract checks. Development runs use
`lob-arena/lightgbm-development`; a verified frozen-test bundle uses
`lob-arena/governed-evaluation`. Registry state and aliases remain deployment
pointers, never release proof.

## Artifact-root rule

Feature shards, model output, calibration output, prediction output and bundle
metadata must resolve under one configured artifact root. Every manifest URI is
relative to that root. This makes the Phase 0 verifier usable against real
outputs and prevents a release from depending on ambiguous per-command roots.

## Operational interface

`scripts/lightgbm_v1.py` and the corresponding Make targets expose distinct
training, calibration, frozen-test prediction, bundle and verification steps.
The separation is intentional: the test loader cannot be reached by training
or calibration.

## Consequences

- LightGBM v1 is complete as a governed binary challenger.
- Real performance claims remain blocked until a licensed, reviewed corpus is
  frozen and its test evaluation is signed.
- Full-session inference and evaluation remain bounded by Parquet batch size,
  sparse alert state and disk-backed exact identity checks;
  calibration retains only probability, label and family vectors.
- The first sequence challenger can reuse the same corpus, split, evaluation,
  artifact and MLflow boundaries.

## Related documentation

- [ARD-0026: Governed LightGBM Release Boundary](ARD-0026-governed-lightgbm-release-boundary.md)
- [ARD-0028: Governed LightGBM Feature Loading](ARD-0028-governed-lightgbm-feature-loading.md)
- [ARD-0029: Deterministic LightGBM Binary Training](ARD-0029-deterministic-lightgbm-binary-training.md)
- [ARD-0030: Float32 Governed Feature Release](ARD-0030-float32-governed-feature-release.md)
- [Shared MLflow Tracking](../mlflow-tracking-server.md)
