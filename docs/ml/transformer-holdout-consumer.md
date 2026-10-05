# Separately gated Transformer holdout consumer

Tracking: [Story #24](https://github.com/khab40/lob-arena/issues/24),
[settings Story #314](https://github.com/khab40/lob-arena/issues/314),
[Project #3](https://github.com/users/khab40/projects/3).

As a validation engineer,
I want a separately authorized fixed-candidate holdout consumer,
So that later-date research compares the Transformer and LightGBM on identical rows.

Actor: validation engineer. Goal: immutable paired December inference.
Value: reproducible research without using December to make candidate choices.
Out of scope: training, fitting, threshold selection, data generation, G8 rerun,
production serving and online MLflow. Verification: inert adversarial arrays,
signed-context/IO faults, arithmetic readback and later authorized CUDA parity.

## Implemented sequence

The [locked protocol](transformer-holdout-protocol-20261005.md) and
[research settings](transformer-settings-release.md) remain unchanged.
The separate `holdout_spec` request binds exact S3 object keys/versions/hashes,
local paths and scopes, source, digest image, sealed evidence package, provider
specification digest, signing key, nonce, output prefix and fixed bounds.
Requests themselves are metadata, not approval.

`holdout_worker.execute` checks an **external approved-request hash**, trusted
signing key, signed observed-Job context, source commit and sealed package hash
before any IO. The attester must obtain approval and independently verify the
live provider specification before signing. Neither pin may be derived from
an untrusted request as an approval shortcut.

1. Claim an unused output prefix with a conditional INTENT. Publish signed context.
2. Read only declared development inputs; revalidate the settings from all seven
   artifacts and three independent evidence trust pins. Open DevelopmentInputs
   unchanged, using the original development manifest and training contract.
3. Load the original checkpoint in the CUDA-only consumer, with its original
   bindings; infer at most 64 predeclared development reference targets. Compare
   exact IDs/labels and saved logits with atol=1e-5, rtol=1e-6. Retain actual
   logits and the independently recomputable parity receipt.
4. Only after parity, read exact approved final inputs. HoldoutInputs authenticates
   final manifests, complete shard coverage, domain pairing, train exclusion,
   sequence shape and every original causal source window. Reuse frozen
   normalization through the original contract; never fit it on holdout rows.
5. Pair original G8 calibrated predictions on exact identities/order/labels,
   timestamps, session/campaign metadata and the frozen balanced threshold.
   Require 15,160 rows / 135 positives / three symbols and sessions / 27 campaigns /
   30 domains on December 30. No sorting or silent dropping repairs mismatches.
6. Score batch 64 once, apply unchanged temperature and operating points, and save
   logits/probabilities, labels and ledger. Compute fixed metrics, subgroup support,
   campaign coverage and 2,000 paired whole-session bootstrap draws.
7. Publish result, complete versioned checksum inventory and SUCCESS last.
   An ambiguous PUT is never retried; retain it for independent reconciliation.
   Other bounded failures publish a sanitized stage/type FAILED receipt.

The original checkpoint bindings remain distinct from new execution source/image
and final manifest bindings. Labels, run IDs and campaign IDs remain target/report
metadata; only the 60 ordered governed features and their missingness enter the NN.
Source history resets independently for every replay shard.

`holdout_readback.verify_result` reloads the settings against all seven original
artifacts, verifies the signed context and saved reference parity, reads exact
published versions and original G8 versions, checks manifest row inventories,
and recomputes fixed metrics and paired bootstrap without loading a model.
Reuse Bug #317's maximum-eight-ULP rule for named float64 reductions; hashes,
probabilities, rows, counts, thresholds, structure and decisions remain exact.
Unsupported precision/recall/AP remain null with explicit reasons.

The library uses a shared 10,000-request / 16-GiB read / 2-GiB publication budget,
one-attempt conditional writes, absolute execution deadline and publication reserve.
CUDA execution is restricted to the later approved Nebius Job. Local tests use
declared records and fake IO, including a 15,160-row *inert* publication fixture.
That fixture is neither Nasdaq data nor qualification evidence.

## Acceptance scenarios

```gherkin
Feature: Separately authorized fixed Transformer holdout
  Scenario: Stop before final access when parity fails
    Given an approved request and signed context for its observed Job
    When saved development reference logits fail the fixed parity tolerance
    Then no final input is read
    And no SUCCESS is published

  Scenario: Preserve development isolation
    Given a final-test projection and the development adapter
    When the adapter is opened
    Then it rejects the projection before reading a shard

  Scenario: Reject a different paired population
    Given verified holdout sequences and saved original G8 predictions
    When a row is duplicated, missing, reordered or has a different label
    Then the comparison is rejected

  Scenario: Reject incomplete publication
    Given a published holdout result
    When independent readback finds a changed version, checksum or metric
    Then the result is not accepted
    And no replacement Job starts automatically
```

## Remaining execution packaging

This consumer PR does **not** include a sealed runnable image or authorize execution.
Next: authenticate exact final metadata inventory and G8 prediction receipts without
payload reads; review development reference selection and consumed-data exclusion;
build the portable evidence package and entrypoint/context delivery; preserve/check
numerical source and dependency versions; digest-pin image; validate the <=64-character
repository/labels; run the exact Nebius dry-run; price all scoped charges and obtain
fresh final-access/run/spend authorization. Proposed one-hour L40S / $6.25 excluding
VAT remains unapproved. Independent provider observation and cleanup stay mandatory.
Actual GPU parity, holdout inference, research report/plots and operator decision
remain pending. G8/G9 stay closed; MLflow reconciliation follows research.
