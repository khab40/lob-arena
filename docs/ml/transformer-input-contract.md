# Transformer input contract — 2026-09-28

Ticket: [Story #24](https://github.com/khab40/lob-arena/issues/24), under
[Feature #16](https://github.com/khab40/lob-arena/issues/16) and
[Epic #15](https://github.com/khab40/lob-arena/issues/15), in
[Project #3](https://github.com/users/khab40/projects/3).
The operator approved this input-contract plan on September 28. The wider
Transformer story remains In Progress; training and qualification remain open.

As a detector developer,
I want verified, reproducible Transformer inputs from the governed C4 sequences,
So that model development uses the same causal observations as the frozen baseline.

Actor: detector developer, with validation-engineer verification.
Goal: versioned inputs and train-only preprocessing. Value: causal, comparable
model development without silent row mismatch. Acceptance behavior is recorded
in the [approved Gherkin scenarios](transformer-input-contract.feature).
Verification uses inert adversarial fixtures, C4 regression tests and measured
input-array processing. Training, scoring, final-test access, serving, calibration
and checkpoint registration are outside this chunk.

## Input and artifact boundary

Call `DevelopmentInputs.open` from
[data.py](../../backend/app/ml/transformer/data.py) with a trusted
`FrozenPublicSampleRoot`, externally expected tabular/sequence manifest SHA-256
values, manifest paths and a local artifact root. Expected hashes must come from
the approved release, not be recomputed from an untrusted download. Use this
factory rather than constructing the internal dataset dataclass directly.

The factory reuses governed manifest loading, artifact resolution and supervised
row identities. It rejects final-test manifests before shard access and completes
all-row verification before returning. Each later pass rechecks artifact hashes.
Artifacts must remain immutable during consumption; the adapter is not a storage
snapshot or a defense against a concurrent privileged writer.

The contract binds corpus, assignment, feature-release ID/hash, manifests,
ordered features, training shards, target semantics and mask conventions.
It consumes existing 64-step histories of 60 retained-row features, stride one.
Targets and labels are unchanged. Each history must equal its exact trailing
tabular window, including timestamp ties resolved by source sequence. Shards use
the baseline fold/session/campaign/run order; rows are never silently reordered.

## Preprocessing and output

`fit_normalization(dataset)` fits each unique training target once, excluding
history overlap, padding, missing values and validation. Float64 Welford population
statistics record counts, fitting-row digest and training lineage. Constant
features use scale 1; wholly missing features use mean 0, scale 1 and count 0.
The training binding excludes validation-manifest hashes deliberately: changing
validation values cannot change the fitted artifact. The full input contract
still binds both complete manifests.

`save_normalization` writes canonical JSON without overwrite. Persist its returned
SHA-256 externally; `load_normalization` checks that checksum and training binding.
Persist `dataset.contract.canonical_bytes()` with its `sha256()` alongside it.
`iter_batches(dataset, normalization, batch_size=64, fold="validation")` reuses
these statistics without refitting. Batch size is bounded to 1–1,024.

| Output | Meaning |
| --- | --- |
| `values` | Finite float32 `[batch,64,60]`; standardized observed features, zero missing/padding |
| `valid_steps` | Boolean `[batch,64]`; true only for actual retained rows |
| `missing_features` | Boolean `[batch,64,60]`; true for unknown features on real steps |
| `causal_allowed` | Boolean `[batch,64,64]`; true only for valid keys at/before valid query |
| Audit metadata | Target/history IDs, timestamps, labels, folds/run IDs and both artifact hashes |

Labels remain separate from features. Framework-specific attention-mask inversion
belongs in the future model adapter. No PyTorch dependency is added. Histories,
Parquet reads and output batches are bounded; complete shards are never loaded
by the consumer. Malformed inputs, infinite values and float32 overflow fail.

## Scenario-to-test mapping

Tests are in [input tests](../../backend/tests/test_transformer_inputs.py) and
[normalization tests](../../backend/tests/test_transformer_normalization.py).
Names below omit their common `test_` prefix. CI runs both in the ML dependency
job so missing NumPy cannot turn this contract check into a silent skip.

| Gherkin behavior | Automated coverage |
| --- | --- |
| Governed release and alignment | `governed_sources_and_exact_target_order`, `feature_order_and_manifest_hash_are_bound` |
| Future observation with equal timestamp | `later_source_row_with_same_timestamp_is_rejected` |
| Invalid sequence examples | `preflight_rejects_corrupt_late_rows_before_returning_adapter`, `manifest_mismatch_rejected_before_shard_access`, `source_run_metadata_must_match_manifest`, `infinite_source_feature_rejected` |
| Zero/missing/padding; causal attention | `masks_missingness_and_attention_have_explicit_semantics` |
| Unique training rows; constant/missing features | `unique_training_rows_define_population_statistics` |
| Validation cannot alter fitting | `validation_changes_cannot_change_fitted_normalization` |
| Separate labels | `labels_do_not_enter_input_values_or_masks` |
| No final-test access | `final_manifest_rejected_without_accessing_shards` |
| Batch invariance | `batch_boundaries_never_change_logical_outputs` plus six measured cases |
| Changed normalizer | `training_binding_changes_fail_closed`, checksum round-trip/tamper coverage in the statistics test |

## Measurements and remaining proof

The [measurement receipt](../evidence/transformer-input-measurements-20260928.json)
records six fresh local Python processes on macOS arm64. For 8,192 windows,
batch sizes 16/64/256 took 25.86/25.63/25.30 seconds total, with peak RSS
116.2/133.9/169.8 MiB. All batch sizes produced identical logical output digests
and normalizer bytes for each fixture size. Reported throughput covers batching
and digesting; total time also includes preflight and fitting. This is one sample
per case, not a production estimate. No model, cloud Job or GPU ran.

Reproduce using `python scripts/measure_transformer_inputs.py --output NEW_DIR`
in the backend ML environment. The deterministic counter recipe uses no random
seed. Fixture generation occurs outside measured child processes. Canonical
[example contract](../evidence/transformer-input-fixture-contract-20260928.json)
and [normalizer](../evidence/transformer-input-fixture-normalization-20260928.json)
are for the 1,024-window inert fixture only. Full fixtures/receipts are retained
in root `outputs/transformer-input-contract-20260928/measurements/`.

Next: review a bounded Nebius proposal binding real development artifacts and
execution resources, then verify governed-data input consumption. Architecture,
training, calibration, MLflow checkpoint registration and an explicitly approved
future evaluation protocol follow in later chunks. G8/G9 remain closed.
