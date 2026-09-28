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

The next implementation steps are the fixed 29-key inventory, a verifier anchored
to the frozen validation preparation SHA-256, and a bounded collector retaining
object versions. The existing development reader returned `AccessDenied` on the
preparation object. Temporary metadata access needs separate approval; no grant
has been applied. Keys derive from the retained C4 freeze request and the C3
checkpoint naming contract; the verifier rejects references that differ.

A passing metadata chain does **not** establish independent observations or label
horizons. Those checks, replay/feature lineage, class support, platform readiness
and exact CPU/GPU execution authorization remain required by the campaign plan.
Retain the fixed role assignment; do not regroup using observed labels or results.

The [access proposal](../evidence/transformer-validation-metadata-access-proposal-20260928.json)
adds `storage.viewer` for exactly 29 JSON objects to the existing development
group for at most one hour, then removes only that rule. Existing grants remain.
Nebius MCP safe mode excludes policy updates: an approved operator applies and
removes the rule; the agent verifies the policy before and afterward.

After access approval, use the existing authorized development identity with
`python -m app.ml.transformer.role_provenance_transport INPUT_DIRECTORY NEW_OUTPUT_DIRECTORY`
from `backend/`. Collection is metadata-only, at most 29 GETs, 256 KiB per object
and 300 seconds. Existing output directories are rejected. `receipts.json` records
versions/hashes; `provenance.json` exists only after complete verification.
Failures retain sanitized diagnostics and partial receipts, with no retry.
