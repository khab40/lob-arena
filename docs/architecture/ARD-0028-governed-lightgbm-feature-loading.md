# ARD-0028: Governed LightGBM Feature Loading

Status: Accepted and Implemented

Date: 2026-07-29

Implementation Status: `[phase-1 done]`

## Context

Phase 0 defines the LightGBM training and release manifests, but a trainer
could still bypass them by reading arbitrary Parquet files, accepting
self-declared negatives, selecting only convenient sessions, or opening the
test fold during development.

## Decision

All later LightGBM training, calibration and test commands must load features
through `app.ml.lightgbm.data.load_governed_feature_dataset`.

The loader:

- locally recomputes corpus validation against the configured artifact root;
- validates the exact protocol, corpus, split and feature-configuration hashes;
- requires a complete `governed_feature_release_v1` manifest whose bytes match
  an externally supplied frozen SHA-256 digest;
- verifies release-pinned replay, run-metadata, feature and quality artifacts;
- maps each feature run to one registered base session and, when seeded, one
  registered synthetic campaign;
- binds run identity, tick size, lot size and tick interval to the exact
  canonical Java replay manifest;
- requires exact control/campaign coverage for every selected fold;
- locally revalidates the exact clean-window adjudication artifact and its
  reviewer/equivalence evidence;
- reconstructs every expected row label from governed campaign ground truth
  plus eligible verified-clean windows;
- rejects invalid, non-finite, misordered or incorrectly labeled rows;
- keeps unlabeled rows immutable but excludes them from supervised batches;
- admits only independently verified clean negatives and synthetic-scenario
  positives; and
- derives a deterministic fold-membership hash from the frozen assignment and
  exact feature/run-manifest digests.

Two non-overlapping access modes are provided:

- `development` loads exactly train and validation; and
- `final_test` loads exactly the frozen test fold.

There is deliberately no mode that returns every fold together.

The ML packages are isolated in the backend `ml` optional dependency set.
LightGBM, scikit-learn and the MLflow client are available to governed ML jobs
without enlarging the current online backend image before a verified inference
adapter exists.

## Consequences

- Training code cannot silently reinterpret unlabeled historical rows as clean.
- Session or campaign cherry-picking fails the exact fold-inventory check.
- Test access becomes an explicit separate operation before the trainer exists.
- Later trainer code consumes supervised record batches without redefining
  corpus, split or label semantics.
- Feature files remain local and licence-controlled; the loader returns hashes
  suitable for Phase 0 manifests and MLflow traceability.
- Editing a feature bundle, replay, adjudication or release manifest requires a
  new explicitly frozen release digest; bundle-local checksum rewrites cannot
  preserve the previous release identity.

The loader does not train, calibrate, score or release a model. Those remain
later Track A phases.

## Related documentation

- [ARD-0024: Versioned Causal Feature Engineering](ARD-0024-versioned-causal-feature-engineering.md)
- [ARD-0025: Governed Corpus and ML Benchmark Protocol](ARD-0025-governed-corpus-and-ml-benchmark.md)
- [ARD-0026: Governed LightGBM Release Boundary](ARD-0026-governed-lightgbm-release-boundary.md)
- [ARD-0027: Shared MLflow Tracking Plane](ARD-0027-shared-mlflow-tracking.md)
- [Causal Feature Engineering for LightGBM](../feature-engineering-lightgbm.md)
