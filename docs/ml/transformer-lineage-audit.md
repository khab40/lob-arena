# Transformer validation lineage audit — 2026-09-29

The [first approved attempt](../evidence/transformer-lineage-attempt-20260929.json)
aborted after one request GET. [Bug #260](https://github.com/khab40/lob-arena/issues/260)
fixes hashing that injected a later optional model default into historical
producer bytes. The original request reproduces the frozen binding; the repaired
verifier checks those exact bytes, retaining strict schema/domain validation.
Access removal is pending operator readback. No automatic retry is authorized.

Story [#24](https://github.com/khab40/lob-arena/issues/24) → Feature #16 → Epic #15,
in [Project #3](https://github.com/users/khab40/projects/3). Continues the approved
[GPU campaign plan](transformer-gpu-campaign-plan.md) after merged #249/#254.

As a validation engineer,
I want replay, feature and label metadata authenticated against frozen C3/C4 evidence,
So that unrelated files cannot justify development-role separation.

## Definition of ready

- Actor: validation engineer.
- Goal: bind the actual C3 request and missing metadata bytes to the frozen release.
- Value: establish trustworthy inputs for source/window and label-horizon review.
- Acceptance: [Gherkin scenarios](transformer-lineage-audit.feature).
- Out of scope: payloads, final-test data, model Jobs, GPU training, MLflow changes.
- Verification: inert metadata tests, exact object-version receipts, offline rehash,
  fresh Nebius MCP policy readback and CI. No model runtime is exercised locally.

Implementation continues existing approval. New metadata permissions require
approval of the [exact proposal](../evidence/transformer-lineage-access-proposal-20260929.json)
before application or collection. Preparing a policy file grants no permission.

## Why these records are needed

The C4 producer in `backend/app/market_data/projection_freeze.py` supplies a
checkpoint's canonical **event-stream** hash to `materialize_tabular_shard` as
`replay_sha256`. Consequently the frozen shard field `replay_manifest_sha256`
contains that stream hash. It cannot authenticate the bytes of `manifest.json`.
Keep frozen evidence unchanged and distinguish the two identities explicitly.

The authentication chain in this increment is:

1. Reverify the retained 34-file CPU evidence bundle and its frozen manifests.
2. Authenticate `request.json` through the frozen preparation checkpoint binding:
   hash of the producer's retained canonical bytes (without injecting newer model
   defaults), image, source manifest, source bytes, Git commit and
   feature configuration file hash must match together.
3. Authenticate 27 `SUCCESS` checksum inventories against the frozen payload
   inventory hash, count and total size, plus the retained checkpoint's byte hash.
4. Authenticate every requested feature/replay/ground-truth file by its exact
   inventory path, byte size and SHA-256. Never follow paths discovered remotely.

This proves metadata-byte identity. It does **not** yet prove that source
observations or label horizons are separated, that classes have enough support,
or that GPU execution is ready. Those outputs remain explicitly false.

## Exact bounded access and operator handoff

Phase 1 reads 58 objects: one request, 27 checksum inventories and 30 feature
metadata JSON files. Phase 2 reads 57 objects: 30 replay manifests and 27
ground-truth JSONL files containing label-window metadata. All belong to the
2019-10-30 validation preparation in the development bucket. No Parquet, events,
snapshots or final data are included. Retained prior metadata is read locally.

Each phase uses six temporary `storage.viewer` rules with at most ten exact paths
per rule. The two original bucket rules plus six fit the provider's ten-rule cap.
The operator replaces phase 1 with phase 2; the phases are never granted together.
The [provider schema](https://github.com/nebius/api/blob/318bd5fefafa95918e9168cf17182853bcfd3609/nebius/storage/v1/bucket_policy.proto)
defines both limits. Unrelated concurrent rules must survive; exceeding capacity,
changed/partial grants or ambiguous removal stops the handoff.

Bounds: 115 GET attempts total, no SDK retries, 256 KiB per object, five minutes
per collection phase, maximum 30,146,675 response bytes including overflow probes.
Temporary access is limited to one hour per phase, two hours total. Stop at the
first failure and remove the active grant. No Job or compute allocation is needed;
the existing operator-managed cost policy covers this bounded metadata audit.

Nebius MCP safe mode requires the operator to perform policy updates/removal.
Before **each** transition, obtain fresh `storage bucket get` readback through MCP,
render from it and use its resource version as the update precondition. Never
reuse a stale version or overwrite a policy from an earlier snapshot.

From `backend`, the offline renderer is:

```text
python -m app.ml.transformer.lineage_handoff PROPOSAL_SHA BUCKET_JSON BEFORE_OR_0 AFTER_OR_0 NEW_POLICY
```

Allowed transitions are `0 1` (grant), `1 2` (replace), `1 0` (abort/remove) and
`2 0` (remove). It writes a new local JSON file and reports the bucket ID, resource
version, rule count and policy checksum. The operator update is:

```text
rtk proxy nebius storage bucket update --id storagebucket-e001935725601413893009 --resource-version FRESH_VERSION --patch --bucket-policy-rules "$(rtk proxy cat EXACT_POLICY_FILE)"
```

These are templates, not authorization to run now. After approval, provide concrete
file paths/version for each handoff, then independently verify the resulting rules.

The collector requires the approved proposal file's SHA-256:

```text
python -m app.ml.transformer.lineage_transport APPROVED_PROPOSAL_SHA BUNDLE 1 NEW_PHASE_ONE
python -m app.ml.transformer.lineage_transport APPROVED_PROPOSAL_SHA BUNDLE 2 NEW_PHASE_TWO RETAINED_PHASE_ONE
```

Phase 2 locally reauthenticates all phase-1 bytes and receipts before any GET.
Both output directories must be new. Partial evidence retains sanitized failure
types and attempt/byte measurements, and cannot emit a success receipt.

## Remaining steps

1. Obtain exact access approval; execute both phases with policy readback and removal.
2. Independently rehash retained files; review actual C3 producer identity,
   feature configuration, stream hashes, actual replay-file hashes and label specs.
   Confirm per-instrument source observations and label horizons against those records.
3. Bind verified lineage to the signed CPU role-audit package, then obtain its
   separate exact execution approval. Check class support without role reassignment.
4. Complete MLflow readiness under #19 before requesting GPU execution.

G8/G9 stay closed. No replacement evaluation is part of this work.
