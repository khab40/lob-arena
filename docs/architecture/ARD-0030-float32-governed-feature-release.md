# ARD-0030: Float32 Governed Feature Release

Status: Accepted and Implemented

Date: 2026-07-29

Implementation Status: `[done]`

## Context

`lob_features_v1` persisted all 60 numeric model features as Arrow float64.
The Phase 2 trainer immediately converted those columns into bounded float32
memory maps, so the immutable release used twice the numeric matrix width of
the training representation. This was useful while stabilizing formulas, but
is not required by LightGBM and is costly for laptop-scale corpus work.

A paired audit over 1,728 historical/hybrid-style rows found:

- 50% lower uncompressed numeric matrix memory with float32;
- no null-mask changes;
- maximum absolute feature error of `2.4414e-5`;
- maximum relative error of `5.7548e-8` for values with magnitude at least
  `1e-6`;
- maximum LightGBM probability difference of `3.1566e-5`;
- no classification disagreements across thresholds from `0.05` through
  `0.95`; and
- identical validation-selected test decisions and metrics.

The audit is evidence for a versioned migration, not permission to rewrite
existing releases.

## Decision

Introduce `lob_features_v2` with the same ordered 60 feature names and formulas
as v1, but persist numeric feature columns as Arrow float32.

- Feature calculations, rolling statistics, and ratios continue to use
  Python's binary64 `float`. The completed feature row is explicitly rounded
  to float32 before quality reporting, logical hashing, and Arrow writing so
  those artifacts describe the same values.
- Timestamps, sequences, ticks, seeds, labels, booleans, dates, hashes, and
  identity fields retain their exact non-float types.
- v1 remains readable and writable when explicitly selected.
- v2 is the default for new feature-generation and streaming commands.
- v1 and v2 configurations have different canonical hashes.
- A governed release is accepted only when protocol, feature configuration,
  run manifest, row identity, Parquet schema metadata, release manifest, and
  artifact checksum all bind to the same schema version.
- A v2 release requires retraining, recalibration, new operating thresholds,
  new prediction manifests, and a new checksummed model bundle. Existing v1
  models and artifacts are never relabeled as v2.

The equivalence tests require identical null masks, float32 Arrow types, maximum
absolute error at most `5e-5`, and maximum relative error at most `1e-6` for
non-negligible values. Repeated Phase 2 training on v2 must retain byte-identical
models, manifests, and predictions under the existing deterministic boundary.

## Consequences

- New governed feature matrices use half the numeric buffer width and avoid a
  second float64-to-float32 corpus representation before training.
- Compressed Parquet savings vary with entropy and are not promised to be 50%.
- Physical Parquet hashes, configuration hashes, protocol hashes, model hashes,
  and calibrated thresholds differ from v1.
- Float32 does not solve weak detector recall. In the audit, subtle-layering
  recall remained the limiting case under both dtypes.
- A future reduction in feature count or quantized online inference requires a
  separate evidence-backed contract; it is not bundled into this storage
  migration.

## Related documentation

- [ARD-0024: Versioned Causal Feature Engineering](ARD-0024-versioned-causal-feature-engineering.md)
- [ARD-0028: Governed LightGBM Feature Loading](ARD-0028-governed-lightgbm-feature-loading.md)
- [ARD-0029: Deterministic LightGBM Binary Training](ARD-0029-deterministic-lightgbm-binary-training.md)
- [Causal Feature Engineering for LightGBM](../feature-engineering-lightgbm.md)
