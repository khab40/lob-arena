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
- retains the governed 60-column `lob_features_v1` input contract while
  materializing each fold once as a bounded float32 memory map;
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
- Float64 remains the immutable feature-release interchange format; float32 is
  the governed trainer representation. This halves matrix storage without
  silently changing the feature contract.
- All 60 governed features remain available for the v1 baseline and paired
  evaluation. Feature selection is deferred to a separately versioned,
  evidence-backed schema rather than being embedded in this trainer.
- Model calibration, operating-point selection, MLflow logging, final test
  evaluation and detector integration remain later phases.

## Related documentation

- [ARD-0026: Governed LightGBM Release Boundary](ARD-0026-governed-lightgbm-release-boundary.md)
- [ARD-0028: Governed LightGBM Feature Loading](ARD-0028-governed-lightgbm-feature-loading.md)
- [Causal Feature Engineering for LightGBM](../feature-engineering-lightgbm.md)
