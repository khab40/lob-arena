# Dedicated research classifier package

Tracking: [Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).
The [canonical acceptance specification](../specs/24-governed-transformer.md)
owns the intended behavior and scenario mapping.

## Implemented boundary

`classifier_package.prepare_classifier` authenticates the original selected
settings against external settings/verification/selection/decision pins using
the existing settings loader. It snapshots all seven exact artifact reads with
their original version, size and SHA-256 references. Metadata preparation imports
no Torch and performs no cloud request or model execution. Checkpoint bytes stay
private; no weights are embedded in repository metadata.

Public inference and direct runtime construction reauthenticate retained settings,
caller trust pins and every original snapshot before any numerical import. Derived
metadata and checkpoint bytes must match the rebuilt package. Exact checkpoint
size and SHA-256 are checked again immediately before deserialization.

`classifier_package.research_inference` accepts development manifest paths,
artifact root, an explicit finite deadline, train/validation fold and a frozen
operating mode. It reopens DevelopmentInputs against the selected package's
original root and manifest hashes, preserving the governed preprocessing contract.
It preserves ordered targets and labels, checks aligned finite outputs and uses
the original float64 sigmoid with the frozen temperature and operating point.
There is no arbitrary event-array interface or public injected runtime argument.
Both inference entries validate the development input type, root, full contract,
access scopes and original manifest hashes. Direct runtime inference also requires
the original tabular and sequence manifest paths; copied metadata is insufficient.

`classifier_gpu.DedicatedGpuClassifier` is a separate lazily imported CUDA runtime.
It verifies the selected checkpoint schema, epoch, trial, original bindings,
precision and finite model state, loads weights with `weights_only=True` and strict
state matching, and uses the unchanged numerical classifier/prediction code.
It neither loads the optimizer nor restores the checkpoint's training RNG.
The frozen holdout consumer and numerical source remain unchanged.

This is a research classifier package, not a live event adapter. It rejects final
folds and preserves selected-settings production-serving denial. Batch timing
and GPU memory measurements describe this runtime segment only; they do not
establish event-to-alert latency or production capacity.

## Verification state

The corrected increment has 121 inert fixture cases covering artifact and external-pin
drift, exact snapshots, selected-state headers, Torch-free metadata import,
development-only inputs, deadline and target/label boundaries, fixed calibration
and operating modes, constructed/replaced packages, optional NumPy collection and
invalid outputs. Dedicated numerical execution remains
unverified until a separately prepared and authorized Nebius Job passes independent
readback. Local/CI fake-consumer results are not CUDA parity evidence.

The original story's dedicated-classifier scenario already passes for frozen
research through the independently verified holdout Job. This new adapter's
numerical verification is a separate increment, not a reason to repeat that run.
The [public verification summary](../evidence/transformer-classifier-verification-20261009.json)
pins the source, exact independent review and inert test receipts.

Root evidence: `outputs/governed-transformer-closure-20261009/`.
This directory retains this work's plan, reviews and tests. A network-disabled,
stdlib-only inspection recovered the exact frozen image's portable metadata
package (SHA-256 `612a904b055fb18da45f5b7fcbd7e7e4f5556e9f184b6368c381726c6d7dc9e2`).
Its selected settings and four content-addressed original evidence receipts match
their recorded hashes. The original checkpoint, contract, normalization and
journals remain unavailable locally; prepare exact version-bound recovery.
Do not infer payload availability from manifests or rerun a model to replace it.

## Next execution preparation

Use installed Nebius CLI skills for version/profile/context checks, exact provider
schema, read-only resource reconciliation, dry-run and approved submission.
Ground image repository length before building/uploading; retain the full digest.
A fresh package must bind this source, unchanged trained numerical source/runtime,
selected settings, exact development object inventory and original logits used
for parity, output destination, versioned secret selectors and finite resources.
DevelopmentInputs preflights all development shards: a small reference-row check
does not imply a small data-access inventory.

Declare one Job, its explicit platform/preset and provider timeout, restart never,
internal publication reserve and operator-managed cost disposition. Do not read
December inputs, refit, select thresholds or reuse consumed holdout approval.
Keep the original verification tolerances and exact threshold decisions explicit.
Retain verified publication bytes with original version/size/hash receipts and
verifier-input responses in a new private root outputs collection. Use retaining
readback and offline recovery with separately retained pinned settings; preserve
original frozen collectors and historical evidence.

Online MLflow lineage/registration remains a separate #19/#24 completion step,
using original journals/artifact identities without training or scoring. Resource
release and explicit #25 eligibility are assessed against the seven canonical
criteria; broader streaming/GUI work is not silently added to this story.
