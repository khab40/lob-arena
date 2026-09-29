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
[removal is independently verified](../evidence/transformer-validation-metadata-cleanup-20260928.json)
at bucket version 134. Only the original two rules remain; other settings are
unchanged. Access lasted 48 minutes 31 seconds, within the one-hour approval.
Keys derive from the retained C4 freeze request and C3 naming contract; the
verifier rejects references that differ.

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
records equivalent scope and the corrected policy checksum. The root evidence
file `outputs/transformer-role-provenance-20260928/temporary-policy-v2.json` recorded
the applied handoff; the old invalid file remains historical evidence.

The completed collection used the existing authorized development identity with
`python -m app.ml.transformer.role_provenance_transport INPUT_DIRECTORY NEW_OUTPUT_DIRECTORY`
from `backend/`. Collection is metadata-only, at most 29 GETs, 256 KiB per object
and 300 seconds. Existing output directories are rejected. `receipts.json` records
versions/hashes; `provenance.json` exists only after complete verification.
Failures retain sanitized diagnostics and partial receipts, with no retry.

## CPU evidence packaging — 2026-09-29

As a validation engineer,
I want the future CPU audit to consume the already verified evidence,
So that it can check lineage without reopening temporary metadata access.

Definition of Ready: actor validation engineer; goal deterministic evidence reuse;
value preserved provenance after grant removal. Acceptance covers all-file hash
binding, size limits, changed inventory, unchanged readiness gates and overwrite
rejection in the Gherkin scenarios above. Verification uses inert metadata tests
and independent inspection of the retained bundle. Execution, payload reads,
permission changes and proof of source independence remain outside this increment.

`role_audit_bundle` packages three frozen development manifests, 29 metadata
objects, immutable version receipts and the r2 train-only normalizer. The bundle
is canonical JSON, capped at 512 KiB with a 256 KiB per-file bound. Verification
checks frozen manifest hashes, the independently verified receipt hash, all 29
objects, the preparation chain, unchanged role assignment and train-only binding.
It rejects extra files and ambiguous/noncanonical JSON. Publication is local and
exclusive; an existing destination is never replaced.

The retained bundle is 220,125 bytes; its receipt is
[recorded here](../evidence/transformer-role-audit-bundle-20260929.json).
Run from `backend/`:
`python -m app.ml.transformer.role_audit_bundle INPUT_DIRECTORY METADATA_DIRECTORY NORMALIZER NEW_BUNDLE`.
This prepares evidence only. The signed request/context, digest-pinned image,
bounded transport and independent CPU output readback still need integration and
review before requesting exact Job execution approval. The old r2 authorization
and metadata grant are not reused.

## Source/window review and remaining evidence

The retained validation domains share 10:00–10:30 on October 30, 2019. Their
instruments differ. At C4's request-bound producer commit `5c851822`, the ITCH
parser routes each global source sequence to one instrument and keeps separate
books; replay export writes one instrument/session per manifest; feature state
is per replay; sequence materialization stays within a shard. Labels describe
attack-active windows in that replay. These semantics support instrument-scoped
separation, but code inspection alone does not authenticate the actual artifact
chain. Same-time instruments can also be correlated; independence is not proven.

The [code inspection record](../evidence/transformer-source-lineage-review-20260929.json)
retains full producer commit/file hashes. Remaining evidence is the 30 actual
validation replay manifests (hashes already pinned in C4), their feature metadata
and label-spec/ground-truth bindings, plus C3's actual producer request/runtime
binding. The prepared/checkpoint JSON does not embed those records. Any extra
cloud metadata read must first have an exact inventory and applicable access
approval. Class support requires the separately authorized CPU payload audit.
Do not alter the frozen roles or claim source/window separation from this bundle.

## Review repairs — 2026-09-29

[Bug #251](https://github.com/khab40/lob-arena/issues/251) addresses the P1/P2 review
of merged #249 before further campaign work. Every normalized instrument now must
have `source_stream_sha256` equal to the frozen validation source hash. Missing,
null and different hashes fail even when checkpoint/preparation checksums agree;
the collector cannot publish a success report for them. Retained evidence still
passes, and the audit bundle bytes are unchanged.

The historical Gitleaks commit fingerprint is replaced by a `generic-api-key`
allowlist requiring both the exact approval-evidence path and the exact public
proposal checksum. This follows [Gitleaks rule allowlist semantics](https://github.com/gitleaks/gitleaks/blob/v8.24.3/README.md#configuration).
An actual scanner regression in CI exercises rewritten Git history, moved lines,
an unsuppressed baseline and negative controls at the same and different paths.
The original September 28 scanner record is historical; this repair supersedes
its fingerprint-only disposition. Actual post-merge CI was green; no current
main-branch failure or credential exposure is claimed.
