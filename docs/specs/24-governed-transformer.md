# Governed Transformer acceptance

Maintained closure specification for [Story #24](https://github.com/khab40/lob-arena/issues/24)
under Feature #16 / Epic #15 in [Project #3](https://github.com/users/khab40/projects/3).
Created 9 October 2026 from the story's seven complete-story scenarios. Historical
campaign specifications, frozen settings, approvals and evidence remain unchanged.

As a detector developer,
I want a reproducible causal market-sequence Transformer challenger using governed inputs,
So that I can measure its incremental value against the frozen LightGBM baseline.

Actor: detector developer; independent verifier: validation engineer.
Goal: close the existing research challenger acceptance with exact artifact lineage.
Value: an honest, reproducible decision about the selected candidate.
Dependencies: accepted LightGBM #23; existing MLflow #19; resource foundation #22.
Assumptions: the frozen seed-42/epoch-4 candidate, calibration and operating points
remain unchanged; completed/consumed runs cannot authorize another run.
Out of scope: production promotion, cascade implementation #25, broader data/ablation
studies and live event sampling, queues, incident consolidation or shared GUI deployment.
Those remain separate integration scope under #90/#91 and the integration plan.

## Contract owners

[ARD-0036](../architecture/ARD-0036-market-sequence-transformer.md) owns model design;
[ARD-0042](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md) owns
research ordering/disposition. The [input contract](../ml/transformer-input-contract.md),
[selected settings](../ml/transformer-settings-release.md),
[holdout protocol](../ml/transformer-holdout-protocol-20261005.md) and
[execution package](../ml/transformer-holdout-execution-package.md) retain their subjects.
The [validation policy](../ml/model-validation-execution-policy.md) owns operator-managed
cost disposition: no billing/balance query or invented new monetary ceiling.
This specification grants no access, Job, application permission, promotion, merge
or deletion authority. Use Nebius CLI and installed Nebius skills for cloud operations.

## Complete-story scenarios

```gherkin
Feature: Governed market-sequence Transformer challenger

  Scenario: AC-01 Verify the candidate package
    Given a completed approved Transformer training run
    When its candidate package is verified
    Then its preprocessing, weights, calibration, thresholds and sequence contract have recorded checksums
    And MLflow records their code, data and feature lineage

  Scenario: AC-02 Record quality and resources
    Given a completed approved Transformer run
    When its evidence is published
    Then learning curves, parameter count, GPU time, peak memory and runtime are recorded
    And detector metrics and the applicable operator cost disposition are included

  Scenario: AC-03 Preserve causal and split boundaries
    Given the governed input contract and approved split assignment
    When training or scoring inputs are verified
    Then no input contains observations beyond its prediction cutoff
    And normalization uses only training observations

  Scenario: AC-04 Use a dedicated classifier path
    Given a verified Transformer candidate
    When its serving package is exercised
    Then inference uses the dedicated classifier runtime
    And vLLM is not used as the learned-detector runtime

  Scenario: AC-05 Publish one authorized final result
    Given frozen model choices and a separately authorized final evaluation protocol
    When final evaluation completes
    Then one immutable result is published with exact evaluation-row identities
    And no automatic rerun is performed

  Scenario: AC-06 Release execution resources
    Given an approved bounded GPU campaign
    When it terminates or reaches its provider timeout
    Then its compute workers are released
    And terminal state and retained artifact identities are recorded

  Scenario: AC-07 Decide feature-producer eligibility
    Given verified standalone quality and resource evidence
    When the operator records the go or no-go decision
    Then eligibility for story #25 is explicit
    And not being the standalone champion does not conceal a failed incremental-value result
```

## Dedicated classifier increment

The 9 October request authorizes completing existing #24 engineering. This increment
prepares a dedicated research classifier over verified development projections;
it does not resolve ARD-0036's pending live-integration decisions. Preserve the
original numerical model/training source and frozen holdout consumer. Authenticate
the selected settings against external caller trust pins and their original seven
artifacts; retain exact checkpoint bytes and original version/size/SHA-256 identity.
Verify checkpoint schema, selected epoch, trial, code/data bindings and precision
before loading model state; never load an optimizer or restore training RNG.

Only the dedicated CUDA runtime loads weights or scores. Metadata import/preparation
must work without Torch. Research inference keeps the exact feature order,
train-only normalizer and governed window/missingness/padding checks. Inputs are
verified development projections, not arbitrary fabricated event windows. Final
data remains denied. Preserve ordered target identities in output; apply unchanged
temperature and the requested frozen operating point. Reject nonfinite or mismatched
results. Production serving remains denied by the selected settings release.

```gherkin
Feature: Dedicated research classifier package

  Scenario: AC-04a Authenticate before loading weights
    Given externally pinned selected settings and retained artifact versions
    When any settings, checkpoint, normalization or source receipt differs
    Then preparation rejects the package before importing the numerical runtime

  Scenario: AC-04b Preserve frozen decisions and identities
    Given verified development windows and fixed candidate settings
    When the dedicated classifier returns finite logits in original target order
    Then each output binds its original target and selected release
    And probability and alert use the unchanged temperature and operating point

  Scenario: AC-04c Refuse invalid input or output
    Given a changed input contract, final fold or nonfinite or misaligned classifier result
    When research inference is requested
    Then no detector score is returned

  Scenario: AC-04d Preserve execution and promotion gates
    Given metadata-only local verification
    When the increment's acceptance is reported
    Then fresh numerical parity remains pending until an authorized Nebius Job is verified
    And production serving remains denied
```

## Verification and traceability

Local/CI checks use invented inert fixtures; no model training/scoring. Numerical
exercise requires a separately reviewed immutable Job package, explicit resources,
finite timeout, Job count, declared cost policy and applicable authorization.
New collection uses RetainingReadbackStore in a new root outputs custody directory;
recovery uses OfflineReadbackStore plus separately retained pinned settings. Retain
original payload version/size/hash receipts and verifier-input responses. Export
only safe aggregate public evidence, with normal Gitleaks/ggshield hooks enabled.

| Scenario | Implementation / contract | Test or check | Evidence | Status |
| --- | --- | --- | --- | --- |
| AC-01 | Selected settings; MLflow #19 | Original settings integrity checks; authenticated MLflow readback pending | [Settings disposition](../ml/transformer-research-disposition-20261008.md#selected-settings-acceptance) | Partial; MLflow gated |
| AC-02 | Frozen research reports; validation cost policy | Four trial indexes, seven report manifests and 23 report/chart hashes verified; cost remains unknown/operator-managed | Root outputs/governed-transformer-closure-20261009/frozen-resource-audit-story24_audit.json; [holdout](../ml/transformer-holdout-report-20261007.md) | Pass for frozen research |
| AC-03 | Governed input contract | Existing causal/mask/split/normalization tests and verified Jobs | [Development results](../ml/transformer-development-results-r2.md), [holdout](../ml/transformer-holdout-report-20261007.md) | Pass for frozen research |
| AC-04 | Frozen holdout dedicated FixedGpuConsumer | Independently verified CUDA reference parity and holdout inference; frozen runtime source identity checked | [Verified holdout](../ml/transformer-holdout-report-20261007.md); root outputs/governed-transformer-closure-20261009/original-acceptance-reassessment-story24_audit.json | Pass for frozen research; new increment separately gated |
| AC-04a | classifier_package.prepare_classifier; reauthenticate_classifier; checkpoint header verification | test_authenticated_snapshots_keep_original_bytes_and_receipts; test_package_drift_rejected_before_runtime; test_external_trust_pin_drift_has_no_artifact_reads; test_selected_checkpoint_header_drift_rejected_without_deserialization; test_constructed_or_replaced_package_fails_before_opens_and_numerical_imports; test_reauthentication_uses_retained_original_pins_receipts_and_fresh_metadata; test_exact_checkpoint_check_precedes_deserialization | Root outputs/governed-transformer-closure-20261009/classifier-iteration3-inert-tests.txt | Pass for inert checks; numerical exercise gated |
| AC-04b | classifier_package.research_inference | test_frozen_calibration_boundaries_and_original_order | Same retained test receipt | Inert check pass; numerical parity gated |
| AC-04c | Governed development reopen, shared source validation and result checks | test_invalid_scope_or_deadline_has_zero_opens_or_numerical_calls; test_changed_development_contract_rejected_before_consumer; test_invalid_declared_output_returns_no_scores; test_invalid_verified_target_inventory_precedes_numerical_consumer; test_changed_train_target_digest_precedes_numerical_consumer; test_direct_infer_provenance_rejected_before_gpu_batcher_or_prediction; test_direct_infer_authentic_metadata_reaches_declared_batcher_in_order | Same retained test receipt | Pass for inert checks; numerical exercise gated |
| AC-04d | Torch-free metadata and unchanged serving denial | test_metadata_import_and_preparation_do_not_import_torch; test_authenticated_snapshots_keep_original_bytes_and_receipts; test_adapter_collection_skips_when_optional_numpy_is_absent; manual acceptance-state check | Same retained test receipt; plan-review.json | Metadata checks pass; numerical/production gates preserved |
| AC-05 | Frozen holdout protocol | Original independent versioned readback and offline replay | [Verified holdout](../ml/transformer-holdout-report-20261007.md) | Pass; consumed authorization |
| AC-06 | Finite campaign and holdout Jobs | Five current CLI COMPLETED states plus original terminal/artifact receipts; worker release inferred from Nebius automatic container-VM deletion contract | Root outputs/governed-transformer-closure-20261009/original-acceptance-reassessment-story24_audit.json; [provider lifecycle](https://docs.nebius.com/serverless/jobs/manage) | Pass for original workers by service-contract inference; no per-ID absence or mounted-volume deletion claim |
| AC-07 | Operator disposition / ARD-0037 | Explicit #25 eligibility decision | [Continue research](../ml/transformer-research-disposition-20261008.md); cascade unapproved | Explicit final eligibility pending |

Pin this file and the exact implementation diff in each independent review receipt.
Update mappings only for observed verification; pending/gated scenarios remain
incomplete. Full #24 closure follows all seven criteria, independently clear review,
CI and explicit remaining decisions. Report implementation, verified execution and
merge/deployment states separately.
