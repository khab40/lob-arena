# Transformer development-input verification — 2026-09-28

Plan for [Story #24](https://github.com/khab40/lob-arena/issues/24), under
[Feature #16](https://github.com/khab40/lob-arena/issues/16) / Epic #15 in
[Project #3](https://github.com/users/khab40/projects/3).
[PR #236](https://github.com/khab40/lob-arena/pull/236) is merged at
`a4ae14619a3e93da3a6e6d679ee64601740878d7`; its input-consumer implementation is
unchanged from the reviewed code. Dependency PRs #203/#227/#228 are also merged.
Status: **proposal for approval; runner/transport not implemented; no Job submitted**.

## Need and scope

As a validation engineer,
I want the approved Transformer input contract verified on the frozen development release,
So that the first GPU training experiment starts with verified causal inputs and preprocessing.

Actor: validation engineer. Goal: verify development input consumption on Nebius.
Value: catch real-data incompatibilities before model training. Verification:
inert adversarial tests, code review, CI, one bounded CPU Job and independent
artifact readback. Out of scope: Transformer model/training/scoring, new labels
or splits, final-test access, G8 reruns, model registration and production claims.
Observable acceptance criteria are in the
[Gherkin scenarios](transformer-development-verification.feature).

**CPU is for input preparation only. Transformer training is a later GPU step.**
This Job reads and verifies existing sequences, fits feature normalization and
hashes prepared batches; it does not instantiate or execute a neural network.

## Exact inputs

The [inventory receipt](../evidence/transformer-development-inventory-20260928.json)
binds the [185 object versions and hashes](../evidence/transformer-development-input-inventory-20260928.jsonl)
at `s3://aimada-wave1-dev-e00g6zvxpr00/releases/nasdaq-public-sample-v1-c4-5c85182-20260905/staging`.
All 185 retained local files match publication sizes/checksums: **30,034,660 bytes**.
No row payload was parsed during this planning audit.

The 90 tabular/sequence shard pairs contain **33,450 training** and **9,210
validation** rows, with 64 steps and 60 ordered features. Three manifests,
180 Parquet artifacts, `checksums.sha256` and `SUCCESS` form the exact allowlist.
The receipt binds feature-release ID/hash, root file and canonical root identities,
both projection hashes and the existing MLflow dataset-lineage receipt.
Manifest row counts are expectations; the Job must verify them from consumption.

## Proposed execution envelope

The [machine-readable proposal](../evidence/transformer-development-proposal-20260928.json)
records the same limits and explicitly unresolved execution bindings.

- One Nebius Serverless CPU Job, `cpu-d3` / `4vcpu-16gb`, 100 GiB ephemeral disk,
  no GPU, provider timeout 3,600 seconds, restart policy `never`.
- Project `project-e00g6zvxpr00waz8t3y51k`; subnet `vpcsubnet-e00ppzc4353dxv210j`.
- Name/run ID `transformer-input-c4-development-20260928-r1`.
- Three fresh child processes, batch sizes 16/64/256, each at most 600 seconds.
  Each opens the full release, fits training statistics, emits all 42,660 rows
  and hashes logical outputs. No raw transformed arrays are published.
- SDK GET only the 185 inventory keys/versions: at most 2 MiB per object,
  64 MiB aggregate successful input payload, 300-second transfer deadline.
  At most three attempts per key (555 requests / 192 MiB response-byte budget);
  every retry consumes the same deadline. No unbounded bucket sync/listing.
- Publish at most 12 artifacts / 8 MiB beneath the new run prefix
  `s3://aimada-wave1-results-e00g6zvxpr00/campaigns/wave1-research-20260816/development/transformer-input-c4-development-20260928-r1`.
  This uses the existing research campaign namespace, not the G8 final namespace.
- Require output absence; conditional no-overwrite writes, checksums and terminal
  marker last. An ambiguous create is resolved by Job-name/ID readback before any
  retry. Timeout/failure retains diagnostics and requires review before another Job.
- No G8 filesystem mount, final credentials, public endpoint, SSH rule or MLflow
  VM startup. No new persistent volume. Spend uses the existing
  [operator-managed policy](model-validation-execution-policy.md); no billing query
  or new monetary ceiling. Record actual resources, duration and peak memory.

## Plan → approval → code → review → test → measure

1. Approve this bounded chunk. Approval covers implementing its runner and one
   CPU verification Job after the checks below pass; it grants no GPU campaign.
2. Implement a development-only runner reusing `DevelopmentInputs.open`,
   normalization serialization and batch hashing from the merged contract.
   Bind the allowlist and expected hashes independently of downloaded content.
3. Package reviewed code in a dedicated image; pin the resulting registry digest
   and source commit in the execution request. Do not substitute the old G8 image.
   Verify image imports, exact CLI request, development credentials and output
   permissions before create. Use Nebius MCP help before cloud actions.
4. Review trust boundaries and test failure paths with inert fixtures: altered
   download/version/hash, unexpected keys, final scope, existing output, partial
   publication, timeout and mismatched batch digests. Keep commits at most 200 lines.
5. After CI and preflight pass, submit once. Verify full row counts, feature/root
   lineage and identical normalizer/ordered output digests across all three sizes.
   Report preflight, fit and batching time separately; retain actual Job identity.
6. Independently read back the result package from S3; verify artifact hashes,
   config, normalizer counts, fitting-row digest and terminal Job state. Retain
   receipts in root outputs and publish sanitized evidence in the implementation PR.

Expected package: input contract, normalization JSON, run configuration, exact
input inventory/reference, per-fold row digests/counts, three measurement records,
code/image/runtime lineage, checksums and success/failure evidence. These are
preprocessing artifacts, not model weights. Preserve MLflow-ready lineage metadata;
this chunk does not claim a new MLflow run or model registration.

## Readiness and next decision

Nebius MCP confirmed the old final Job is COMPLETED and its 32 GiB filesystem
is READY; neither is reused. Live development/results bucket metadata checks
failed with storage-API DNS timeouts. Historical policies permit development
release reads and this research output namespace, but **current IAM and object
access remain unverified**. No permission change was attempted.

Execution is not ready until the runner exists, its reviewed source/image/request
are bound, current development permissions and credential versions are verified,
and the result prefix is absent. Any newly required permission must be presented
as an exact change; do not broaden access silently. Relevant CLI help was checked
through Nebius MCP; the [provider Job reference](https://docs.nebius.com/cli/reference/msp/serverless/v1alpha1/job/index)
is supplemental and does not override the installed `nebius ai job` interface.

After successful input verification: propose the smallest GPU Transformer model,
bounded training matrix, validation/checkpoint selection and MLflow logging plan.
Later calibration, model freeze and separately authorized evaluation remain open.
G8/G9 stay closed; the previously inspected final fold is not a new untouched test set.
