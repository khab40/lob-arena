# Frozen LightGBM candidate inventory

Use this read-only inspection before live MLflow or Object Storage readback.
It produces one portable JSON index of the selected model's resolved configuration,
artifact hashes, development lineage, execution identities and exact result-object
URIs. It imports only Python's standard library; it never loads the model, parses
Parquet rows, trains, scores, contacts a service or authorizes final evaluation.

## Build the index

Use a stable local copy of the retained G7 freeze and a trusted freeze digest from
outside that directory. The recorded September 12 digest is in
[ARD-0035](../architecture/ARD-0035-nebius-lightgbm-first.md). Do not substitute a
digest computed from a changed copy merely to make the check pass.

From the checkout containing the script, with an existing output directory:

```bash
python3 scripts/build_lightgbm_candidate_inventory.py \
  --freeze-root /path/to/outputs/lightgbm-wave1/nasdaq-g7-freeze-20260912 \
  --freeze-sha256 232f1a88e39caf2591df5ee135bb25b6ce2fb080688dc197cd96676840f8d7fc \
  --output /path/to/outputs/lightgbm-candidate-inventory-20260922/inventory.json
```

Python 3.11 or newer suffices; no ML dependencies or credentials are needed.
The output must be new and outside the frozen evidence directory. Existing files,
noncanonical paths, symlinks and unlisted result files are rejected. Keep the index
outside disposable worktrees alongside the original evidence; preserve its SHA-256.

## What is verified and saved

- The external digest anchors G7's freeze, which anchors the candidate, G6 selection,
  collection/monitor receipts and original result `SUCCESS` inventory.
- Every inventoried candidate-result file is rehashed and size-checked, including
  model weights and development Parquet bytes. The complete file set and checksum
  list must agree. Parquet contents and model behavior are not interpreted.
- Candidate, campaign, image, request, selected Job and MLflow identities are
  cross-checked. Training/calibration bindings, ordered features, hyperparameters,
  seed, operating mode and frozen threshold must agree with retained metadata.
- The output records resolved experiment settings, early stopping, class weighting,
  preprocessing, calibration breakpoints, every operating point, feature order,
  data/split bindings, source commits, runtime environment and cloud identities.
- `artifact_roles` maps weights, schema, calibration and supporting evidence to
  root-relative paths. `result_objects` supplies exact S3 URIs, sizes and SHA-256
  values, including publication markers, for a later independent reader.

The [September 22 receipt](../evidence/lightgbm-candidate-inventory-20260922.json)
records 107 verified local objects for the existing frozen candidate. Original
evidence is unchanged. The index contains metadata only and can be rebuilt from
the same freeze with identical bytes regardless of its local directory name.

## Remaining verification

`remote_storage_verified` and `live_mlflow_verified` deliberately remain false.
The S3 locations and MLflow IDs are read from anchored historical receipts; this
command does not establish current remote availability or permissions. Input
release manifests outside the candidate copy remain references for separate readback.
G6's trial decisions are retained through its referenced comparison receipt; this
tool does not re-run selection or audit every other trial's stored model.

The index is not a replacement for the release verifier, approval signature,
prediction/label pairing, semantic comparison audit or G8 final result. Historical
`test_fold_accessed=false` describes development, not subsequent R4 final-data access.
Follow the [remaining work plan](../roadmap/CURRENT_STATUS.md#lightgbm-remaining-work-plan--2026-09-22)
and [G8 completion procedure](../operations/g8/g8-completion-recovery.md).
