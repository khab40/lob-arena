# Transformer holdout admission — 6 October 2026

Historical plan/execution record; reconciled 8 October 2026. Reference publication and metadata admission completed before the authorized holdout.
[Current status](../roadmap/CURRENT_STATUS.md) owns remaining acceptance.
[ARD-0042](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md) owns research ordering;
pending instructions below do not authorize another run or reuse consumed approval.

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[settings #314](https://github.com/khab40/lob-arena/issues/314),
[Project #3](https://github.com/users/khab40/projects/3).
This continues the approved [December protocol](transformer-holdout-protocol-20261005.md)
and [execution design](transformer-holdout-execution-package.md).

As a validation engineer,
I want authenticated development reference outputs and an exact holdout object inventory,
So that the fixed Transformer can be admitted without silently changing inputs or reading holdout rows early.

Actor: validation engineer. Goal: prepare exact reference and object pins.
Value: catch lineage, missing-object and access failures before GPU execution.
Out of scope: model execution, training, calibration, candidate selection,
Parquet body reads, image publication and production promotion.
Verification: inert boundary tests, offline SDK preflight, separate-agent review;
remote metadata verification requires the exact approval below.

## P1 credential-boundary correction

[Bug #329](https://github.com/khab40/lob-arena/issues/329) under Story #24 repairs
the full research-operator import after preflight. Credential lookup now uses the
existing metadata-only helper. The proposal pins both package initializers and
every loaded first-party module; origin/hash checks run before and after SDK
preflight, before credentials. Research execution/readback/storage modules are
not imported. Fourteen fresh-process regressions cover changed files, an unknown
module, a wrong helper origin and a post-preflight source change.
51 focused inert tests and the real offline SDK preflight pass; independent
correction review found no actionable P0/P1/P2 issues.

The operator approved the exact audit and handoffs conditional on fixing P1.
The corrected proposal SHA-256 is
`8f1b8cef787026a60a9dc9c29aa9ea77c320c387960b51bd276f60b98ceb38ef`.
Only source pins changed from the approved `e73297b4…` proposal; exact keys,
request/access limits, policy hashes, cleanup and $0.01 cap remain identical.
Both proposals, the approval reply and the scope comparison are retained in the
project-root evidence folder. PR #328 merged with all 25 checks passed. The
[completed audit](transformer-holdout-metadata-results-20261006.md) independently
verified all 65 metadata receipts; both temporary grants are removed. The
operator delegated the approved CLI updates with an explicit `run` instruction;
Nebius MCP supplied independent policy readbacks. No Parquet bodies or models ran.

## Saved reference preparation

`scripts/prepare_transformer_holdout_reference.py` authenticates selected settings,
the saved independent comparison receipt and all 5,490 calibration predictions.
It validates full target order, labels, finite raw logits and checkpoint lineage
before retaining the first 64 rows. It does not recompute or calibrate logits.
The resulting artifact is 7,544 bytes, SHA-256
`220a2cf373290c846e1da29252ed149156b3f74d6598d2da4e9863bfbca364a5`.
Local receipts and the saved reference are retained in
`outputs/transformer-holdout-admission-20261006/reference/` in the project root.
No reference object has been published; its S3 URI/version and CUDA parity remain pending.

## Exact metadata audit — approved and completed

The [proposal](../evidence/transformer-holdout-metadata-proposal-20261006.json)
allowed one attempt, now consumed: three frozen JSON manifest GETs, 60 December shard HEADs
and two version-pinned original G8 prediction HEADs. Each JSON is at most
256 KiB; total collection is at most five minutes, with no automatic retries.
Approved additional spend cap: **$0.01 excluding VAT**, under the existing
operator-managed cost policy. Zero Jobs. Any failed attempt stops and preserves receipts.

The removed temporary `storage.viewer` access covered 63 exact final-bucket keys and two exact
results-bucket keys for the existing development group. The role permits object
bodies, but this approved collector uses GET only for three JSON manifests and
HEAD for the remaining 62 objects; it never fetches Parquet bodies.
Seven added rules left the final bucket at nine rules; one added rule left
results at ten. Each added rule had at most ten paths, with no wildcards.

The following procedure describes the consumed audit, not a new authorization.
Nebius MCP safe mode excludes policy updates; the operator delegated the approved
CLI grant/removal commands explicitly. Before any grant, rerun
the offline `--preflight` and independently read both current bucket policies.
Use fresh resource versions and verify the approved exact added rules before
collection. Keep access at most one hour; after success or any abort, remove
only those added rules and independently verify both buckets. Preserve unrelated
concurrent rules; stale baseline removal files must not overwrite them.
Policy files, hashes and initial versions are bound in the proposal and retained
under `outputs/transformer-holdout-admission-20261006/` in the project root.

The operator wrapper requires an externally supplied approved proposal hash
before credentials, verifies reviewed source hashes, probes the actual SDK with
sockets/subprocesses blocked and checks backend import origins. The offline
preflight passed on Python 3.11.15 without credentials or cloud calls.
The live collector writes only to a new local evidence directory.
HEAD proves version/size availability; it does **not** verify fresh payload bytes.
Exact manifest hashes, 30 replay identities, 15,160 rows, causal order and
64-step sequence/row alignment must match before the 62 HEADs begin.

```gherkin
Feature: Fixed Transformer holdout admission

  Scenario: Prepare an authenticated development reference
    Given saved comparison predictions and matching selected settings and verification receipts
    When a bounded reference is prepared
    Then the first 64 targets retain their saved order, labels and raw logits
    And no model runs

  Scenario: Reject changed saved predictions
    Given saved predictions whose full checksum or target order differs
    When reference preparation is requested
    Then no reference artifact is created

  Scenario: Verify exact metadata without reading holdout rows
    Given exact approved temporary grants and a passing offline preflight
    When the bounded metadata audit completes
    Then three authenticated JSON manifests and 62 object headers are retained
    And no Parquet body is read
    And HEAD evidence does not claim fresh payload integrity

  Scenario: Reject an unapproved audit before credentials
    Given a proposal whose checksum differs from the external approval
    When the operator wrapper is invoked
    Then it stops before obtaining credentials or making cloud calls

  Scenario: Reject changed credential-path source
    Given a changed or unpinned module in the metadata operator's import closure
    When the audit wrapper checks source and origins before credential lookup
    Then it stops before credentials or object requests

  Scenario: Remove access after an interrupted audit
    Given the audit stops at a manifest or object mismatch
    When the operator performs the approved cleanup
    Then only the added rules are removed from both buckets
    And independent readback confirms removal
```

Next: bind the verified inventory into the exact request, publish/pin the saved
development reference, finish credential/access pins and publish the immutable
image. Complete provider dry-run and scoped cost estimate, then obtain fresh
final-access/run/spend approval. The audit approval is consumed; do not repeat it. Proposed GPU bounds
remain one L40S, one hour, $6.25 additional excluding VAT. They are unapproved.
G8/G9 remain closed. December results and the research decision remain pending.
