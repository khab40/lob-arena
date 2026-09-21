# ARD-0029: Deterministic LightGBM Binary Training

Status: Accepted and Implemented

Date: 2026-07-29

Implementation Status: `[phase-2 done]`

## Context

Phase 1 admits only hash-compatible, causally ordered and independently
governed train/validation rows. The first trainer must preserve that boundary,
avoid test access and produce a byte-reproducible candidate before calibration
or final evaluation is introduced.

## Decision

`app.ml.lightgbm.training.train_binary_attack_model` is the only Phase 2
training entry point. It:

- accepts a `development` governed dataset containing exactly train and
  validation folds;
- fixes the target to `attack_active`;
- passes raw features and nulls to LightGBM by default;
- accepts the governed 60-column v1 or v2 feature contract and materializes
  each fold once as a bounded float32 memory map;
- derives balanced class weights from training labels only;
- normalizes each base session's contribution within each class while
  preserving equal total class weight;
- evaluates validation loss with training-derived class weights and
  base-session normalization;
- enables deterministic CPU training, a fixed column-building strategy, one
  explicit seed for every LightGBM random source and the configured thread
  count;
- selects the model iteration using validation-only binary-log-loss early
  stopping;
- writes `model.txt` as `lightgbm_text_v1` and `training-run.json` as
  `lightgbm_training_run_v1` in one atomic output directory;
- binds the training manifest explicitly to the governed feature release and
  exact model artifact digest; and
- derives the training-run ID from governed hashes, configuration and the
  resulting model digest.

Scaling is deliberately absent because it is unnecessary for decision trees.
The optional preprocessing boundary accepts only explicitly approved,
deterministic scikit-learn scalers. A scaler is fitted on training rows only,
must preserve the exact governed feature identities and ordering, is applied to
validation rows, and is persisted separately as
`sklearn_transformer_joblib_v1`. Dimensionality reduction, feature mixing and
stochastic preprocessing are not admitted in Phase 2.

The caller supplies an aware `created_at` value instead of allowing the trainer
to read the wall clock. With identical governed inputs, environment, timestamp
and seed, repeated runs must produce identical model bytes, validation
probabilities and training-manifest bytes.

## Consequences

- Phase 2 cannot read or score the frozen test fold.
- Large sessions cannot dominate merely by contributing more labeled windows.
- Missing values retain LightGBM's native semantics on the default path.
- Existing float64 v1 releases remain immutable. New float32 v2 releases bind
  the reduced-width storage explicitly into protocol/config/release hashes and
  still use the same bounded trainer representation.
- The source release retains all 60 features. The later Wave 1 runner supports
  explicit feature ablations through a hashed experiment specification; the
  training manifest/model bind the retained ordered subset. G6 selected 31
  columns after excluding 29 state features. This does not rewrite the source
  feature schema or perform hidden selection inside this trainer.
- The best-iteration booster is saved after fitting. Periodic training-state
  checkpoints and interrupted-training resume are not implemented.
- Calibration, operating points, MLflow logging, final scoring and the Python
  detector adapter subsequently landed under ARD-0031. Live serving is separate.

## Related documentation

- [ARD-0026: Governed LightGBM Release Boundary](ARD-0026-governed-lightgbm-release-boundary.md)
- [ARD-0028: Governed LightGBM Feature Loading](ARD-0028-governed-lightgbm-feature-loading.md)
- [Causal Feature Engineering for LightGBM](../feature-engineering-lightgbm.md)
- [ARD-0030: Float32 Governed Feature Release](ARD-0030-float32-governed-feature-release.md)
