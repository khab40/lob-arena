# Transformer role provenance — 2026-09-28

Story [#24](https://github.com/khab40/lob-arena/issues/24), Feature #16, Epic #15;
[Project #3](https://github.com/users/khab40/projects/3). Continues the approved
[campaign plan](transformer-gpu-campaign-plan.md) after merged PR #248.

As a validation engineer,
I want preparation and checkpoint metadata bound to frozen C4,
So that unrelated metadata cannot justify independent validation roles.

Definition of Ready: actor validation engineer; goal exact metadata provenance;
value auditable source identities before GPU execution. Observable acceptance is
in [the Gherkin scenarios](transformer-role-provenance.feature). Verification uses
inert metadata fixtures, bounded authorized readback and CI. Payload reads, Jobs,
permission mutation, final-test access, G8 and MLflow changes are out of scope.

The fixed 29-key inventory, verifier anchored to frozen validation preparation
SHA-256, and bounded collector are implemented. After the original `AccessDenied`
and corrected operator grant, the [live audit](../evidence/transformer-validation-metadata-audit-20260928.json)
verified all 29 objects (42,064 bytes) and all 30 replay domains. A fresh process
verified every retained object/version/hash and reproduced the report. Temporary
access has [operator approval](../evidence/transformer-validation-metadata-approval-20260928.json);
operator removal is pending. Keys derive from the retained C4 freeze request and
C3 naming contract; the verifier rejects references that differ.

A passing metadata chain does **not** establish independent observations or label
horizons. Those checks, replay/feature lineage, class support, platform readiness
and exact CPU/GPU execution authorization remain required by the campaign plan.
Retain the fixed role assignment; do not regroup using observed labels or results.

The [access proposal](../evidence/transformer-validation-metadata-access-proposal-20260928.json)
adds `storage.viewer` for exactly 29 JSON objects to the existing development
group for at most one hour. [Bug #250](https://github.com/khab40/lob-arena/issues/250)
corrects the provider representation: three rules of 10/10/9 paths, then removal
of only those three rules. Existing grants remain. The approved proposal bytes
are retained unchanged; effective permissions are identical.
Nebius MCP safe mode excludes policy updates: an approved operator applies and
removes the rules; the agent verifies the policy before and afterward.

Nebius's [policy schema](https://github.com/nebius/api/blob/318bd5fefafa95918e9168cf17182853bcfd3609/nebius/storage/v1/bucket_policy.proto)
limits both total rules and paths per rule to ten. The offline
`provenance_policy` renderer validates both limits, pins the approved proposal
checksum and rejects partial application. Removal uses the fresh current policy
and removes only the three exact rules, preserving unrelated changes. The first
operator request was rejected with no mutation: version 132/two original rules
were independently confirmed. [Repair evidence](../evidence/transformer-metadata-policy-repair-20260928.json)
records equivalent scope and the corrected policy checksum. Use the root evidence
file `outputs/transformer-role-provenance-20260928/temporary-policy-v2.json` recorded
the applied handoff; the old invalid file remains historical evidence.

After access approval, use the existing authorized development identity with
`python -m app.ml.transformer.role_provenance_transport INPUT_DIRECTORY NEW_OUTPUT_DIRECTORY`
from `backend/`. Collection is metadata-only, at most 29 GETs, 256 KiB per object
and 300 seconds. Existing output directories are rejected. `receipts.json` records
versions/hashes; `provenance.json` exists only after complete verification.
Failures retain sanitized diagnostics and partial receipts, with no retry.
