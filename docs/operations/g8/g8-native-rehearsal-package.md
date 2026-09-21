# G8 native-storage and MLflow rehearsal package

Status: **native two-Job recovery completed on September 17; independent MLflow
and S3 readbacks passed**.
Runtime implementation: merged PR #190 at `cba03dad383e75ba8236699e0ea568cf97a3a00b`.
This follows the completed
[source staging window](g8-source-sdk.md#approved-input-staging-completed).
The [existing synthetic rehearsal authorization](g8-live-replacement.md#approved-scope-synthetic-nativeremote-rehearsal-only)
uses two phases/Jobs; its input-writer window is closed. The
[2026-09-16 validation policy](../../ml/model-validation-execution-policy.md) removes
administrative expiry, billing gates and fixed VM/filesystem windows.
The [September 15–16 preflight](g8-native-context-handoff.md#september-1516-preflight-outcome)
exceeded the VM uptime limit during an overnight approval wait. The VM is stopped
and that temporary filesystem was deleted. At the time, refreshed billing and a
renewed VM window were required; those gates are now superseded. No evaluation
Job was submitted in that attempt. On September 16 the
operator reported $33.25 and renewed the VM window. The provider then rejected the
44-file package: a container may inject at most 16 files. The independently guarded
VM was stopped and restored, and the empty filesystem deleted. No Job was created.
See the [rejection receipt](../../evidence/g8-native-injection-rejection-20260916.json).

## Bootstrap injection and native package transport

### September 17 execution evidence

The [native execution receipt](../../evidence/g8-native-recovery-20260917.json) records
the v5 package from commit `5b735de3d5a7d458aa4033fb1180495137b60fd5`.
The score Job `aijob-e00rqsnbarhxt04s15` scored once, sealed its checkpoint and
exited deliberately with code 73. The recovery Job `aijob-e00w8srejmj1jz44w4`
reattached that filesystem and **COMPLETED at 2026-09-17 05:35:55 UTC**.
It recovered the same MLflow run after a deliberate artifact-upload interruption,
recovered publication after withholding SUCCESS, and verified a completed repeat
with zero writes. No recovery scoring or new MLflow run was allowed.

Both Jobs emitted a provider `storage_mount` preparation error before starting
their containers. The recovery runtime nevertheless verified the expected
`virtiofs` identity, loaded the read-only package and recovered the retained
checkpoint. Preserve the error: its cause is unknown, and successful execution
does not establish why the provider reported it.

Independent authenticated readback through the separate MLflow VM verified
24 metrics (including single-value histories), 30 dataset inputs, identity tags
and all four artifact hashes. The Job verified all 64 published S3 objects;
the separate verifier received AccessDenied using the MLflow service identity.
The subsequent [authorized-reader verification](../../evidence/g8-independent-s3-readback-20260917.json)
downloaded all 64 objects and verified every size/hash, both inventories and all
four MLflow artifact hashes. It used the existing development identity without
widening permissions. The earlier AccessDenied remains preserved history. The native
checkpoint, package and receipts were downloaded in a verified 828-file archive.

This is synthetic transport/recovery evidence. Dataset lineage uses synthetic
placeholders and rules comparisons use contract fixtures, not actual Java
execution. It neither qualifies production model quality nor closes G8/G9.

The v5 package injects only the small read-only bootstrap. The bulk package is
staged on the existing native filesystem and mounted read-only at `/g8-package`;
the package directory is `/g8-package/package`. The same filesystem remains
writable at `/g8-durable` for checkpoints and signed contexts. No additional
filesystem or image is provisioned. The deterministic archives
retain all reviewed overlay bytes plus the archive reader; no model/data member
is regenerated. The signed plan binds each archive, bootstrap and individual
Python member hash. The old 44-file v1 package remains rejected and is not reused.

The bootstrap checks all three archive hashes against the injected configuration and checks
read-only mounts before installing an import hook. It imports members directly
from memory without extracting code to writable storage. The ordinary signed
package gate then validates exact archive membership and individual source hashes
before input access. Both recovery children enter through this same bootstrap.
Packaging tests exercise inert source only; the frozen runtime still runs on Nebius.

## KMS rejection and payload headroom

The v3 package met the 16-file and 64 KiB raw-file limits, but actual creation
failed with `plaintext must not exceed 65536 bytes` from KMS. No Job was created.
The identical request subsequently passed the provider's `--dry-run` validation.
The [rejection receipt](../../evidence/g8-native-kms-rejection-20260916.json) preserves
both outcomes. The MLflow VM was stopped; its empty native filesystem is retained.

The [Job schema](https://github.com/nebius/api/blob/main/nebius/ai/v1/job.proto)
describes each injection as a SecretStash payload, but neither it nor the
[KMS schema](https://github.com/nebius/api/blob/main/nebius/kms/v1/symmetric_crypto_service.proto)
specifies the internal encryption envelope. Encoding/metadata overhead is an
unconfirmed cause, not a diagnosed provider implementation detail.

The subsequent v4 attempt capped all 16 injections at 40 KiB. It also passed
dry-run and failed with the same KMS error. The
[second rejection](../../evidence/g8-native-kms-headroom-rejection-20260916.json)
disproves per-file headroom as a sufficient fix; it still does not establish the
provider's internal serialization. No Job or evaluation was created.

V5 removes bulk files from the injection path. The 40 KiB archive/file bound and
64 KiB uncompressed member bound remain local parser limits. Native package
publication verifies every byte against a hash-bound transport inventory, fsyncs
files/directories and rejects an occupied destination. The Job requires the
read-only package mount, verifies its signed inventory and checks archive hashes
before importing any overlay. The writable checkpoint view can address the same
underlying files: read-only mounting is not claimed as storage immutability.
Pinned archive hashes and in-memory import protect the code bytes; signed package
verification is repeated after context waiting, before source access.

The wrapper retains a [provider dry-run](https://docs.nebius.com/cli/reference/ai/job/create)
receipt before checking the registry and writing a create intent. A failure stops
submission; a pass does not prove KMS persistence, mount access or runtime success.
Preserve both rejected packages and intents. The September 17 v5 execution above
establishes native acceptance and recovery for the unchanged synthetic sources.

## Existing short-tag exception

The next submission passed the injection-count gate but was rejected before Job
creation because Nebius copied the 131-character image reference into a 64-character
Compute label. This is the [existing approved provider workaround](../../roadmap/nebius-lightgbm-wave1-implementation-plan.md#2026-08-26-g4-submission-reconciliation),
tracked in [Issue #84](https://github.com/khab40/lob-arena/issues/84).
The VM was stopped/restored at version 52 and the empty filesystem deleted;
the [rejection receipt](../../evidence/g8-native-image-label-rejection-20260916.json) preserves this attempt.

Keep `plan.image` at the full frozen digest. Submit only the existing
`cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/g:dc32b12d7216bfee` alias.
Use `scripts.submit_nebius_job._verify_short_tag` to record its exact full digest
when preparing bindings. The package emits only commands for
`scripts/submit_g8_native_rehearsal.py`, which requires the clean signed source
commit, checks the registry immediately before creation, writes a single-use
submission intent, validates the returned Job and registry mapping afterward,
and requests cancellation on any post-create failure. Preserve its evidence;
an ambiguous create is resolved by readback, never another call. Never retag or
rebuild an image during this procedure.

Supply the post-create registry JSON to `sign_g8_native_context.py` with
`--registry-verification`. The signer rejects a different alias/digest, observations
before Job creation, future timestamps and observations older than five minutes.
The signed context carries that evidence into the waiting Job. Recovery children
reuse the signed observation during recovery. These checks retain the
approved short-tag exception; they do not claim a mutable tag is digest addressing.

## Frozen source capsule

The retained source inventory is **74,744 bytes**. Nebius permits at most
**64 KiB per injected file**, so directly injecting `source-package.json` fails
the documented [Job file limit](https://docs.nebius.com/serverless/jobs/manage).
`serverless/jobs/g8_native_source_capsule.py` splits those exact bytes into
40,960-byte and 33,784-byte parts. Six additional parts carry the unchanged request,
C4 profile/paths and synthetic authorization. No checkpoint or data is injected.

The [original capsule receipt](../../evidence/g8-native-source-capsule-20260915.json)
preserves the old split. Rebuild capsule v2 from the retained verified source tree;
do not overwrite the old capsule. Its new part hashes belong in the signed v5
package. Reassembly must preserve source SHA-256
`792b25de957556d287ec2812645fe36f92aeca79b89bc62448e071f67cc60de9`.
The candidate remains
`e04f50ff0748a0077c0602c397ed7c9c3087757fe0892f1a2d284e91b2383b7c`.

Local orchestration, with no model imports or cloud calls:

```bash
rtk proxy python3 serverless/jobs/g8_native_source_capsule.py --source /absolute/source-reader-copy --capsule /absolute/new-capsule
rtk proxy python3 serverless/jobs/g8_native_source_capsule.py --capsule /absolute/new-capsule
```

Stage the eight parts under `/g8-package/package/source-capsule/`. Keep the
receipt outside that exact eight-file directory. The native entrypoint
calls `hydrate(capsule, destination)` after verifying its Job context and mount.
Hydration verifies the development access-ID fingerprint, requires an explicit
production-object HEAD denial, downloads only the 350 inventory-bound synthetic
objects and writes the original source marker last. Partial downloads remain
unsealed. The helper cannot submit Jobs, claim native durability, or prove which
secret version provided environment credentials. It deliberately has no hydration
CLI that could bypass the native entrypoint's gates.

After hydration, call `prepare_g8_native_sources.verify` with the fixed source hash
to verify the full candidate/C4/comparison/authorization contract before scoring.
The six local metadata members are not misreported as S3 downloads.

## Required execution package bindings

The package builder requires these bindings before submission:

| Binding | Required value or evidence |
| --- | --- |
| Runtime | Existing `linux/amd64` image digest `dc32b12d7216bfeef8e5d95c50363f34bb76f34159ef9343ff3d6996983a89b2` |
| Code | Injected bootstrap; exact signed overlay inventory on the read-only native package view; pinned archive hashes before in-memory import |
| Source | Eight capsule hashes above, source manifest hash, candidate hash and both source SUCCESS hashes from PR #188 |
| Storage | One returned `computefilesystem-…` ID, `network_ssd`, 10 GiB; `/g8-durable:rw` and `/g8-package:ro`; reject identity/mode drift and nested checkpoint mounts |
| Network | Project `project-e00g6zvxpr00waz8t3y51k`, subnet `vpcsubnet-e00ppzc4353dxv210j`; private MLflow `http://10.4.0.54:5500` |
| Credentials | Four explicit `SECRET_ID@VERSION_ID` selectors for development S3 and MLflow; no latest-version selectors or inline values |
| Spend monitoring | Operator-managed alerts; no billing queries, receipts, freshness gate or dollar ceiling |
| Jobs | Two named phases, `cpu-d3`, `4vcpu-16gb`, 100 GiB ephemeral disk, 1h timeout each, restart `never`, no GPU |
| Retention | Keep sealed outputs through verification/recovery; stop idle compute; archive before approved cleanup |

Each submitted Job needs a fresh API readback matching the immutable image,
resources, mount ID, injection paths and **both secret ID and version ID for each
environment binding**. Preserve its hash and actual Job ID. An operator-signed
context binds that readback to the package before the entrypoint accesses inputs.
Runtime access-ID matching and authenticated calls complement that control-plane
evidence; they do not independently attest secret-version provenance. Do not
resolve the PR #188 attestation gap by changing a receipt boolean alone.

The ordinary API view omits bootstrap bytes but includes plain environment
configuration values. This was verified against R4's current readback and the
[Job API definition](https://github.com/nebius/api/blob/main/nebius/ai/v1/job.proto).
`g8_native_readback.py` therefore checks paths, exact version selectors and plain
configuration values;
`g8_native_runtime.py` separately verifies package bytes, read-only mounts and
environment values against the signed package before any source access. Neither
the ordinary readback nor these static tests alone establishes native durability.

MysteryBox selectors in the contract are resource/version identifiers, not AWS
credential values. GitGuardian incident 37285889 flags one such identifier as a
generic high-entropy secret; classify that specific incident as a false positive
through GitGuardian's supported workflow. Keep credential scanning enabled.

## Package and context tools

`scripts/prepare_g8_native_rehearsal.py` requires a clean reviewed checkout, the
retained capsule, the returned filesystem JSON, completed
plan bindings and an existing Ed25519 reviewer key. It archives the 22 reviewed
code files and copies the bootstrap, eight capsule parts, filesystem
evidence and reviewer public key. It signs the immutable manifest and prints the
two wrapper commands without submitting. The bootstrap is the only injected file.
The builder also emits `package-transport.json`
outside the package, with hashes and sizes for every physical file. Copy the
package and inventory through the existing SSH operator path and run
`scripts/publish_g8_native_package.py` on the VM with `--source`, `--inventory`
and `--inventory-sha256`. It requires the already-verified native mount, creates
`package/` without replacement and reads all bytes back before returning success.
Verify that receipt before Job creation. Preserve partial staging on failure;
never overwrite it or submit against an incomplete package.
The reviewer private key stays outside the package and is never transported.

```bash
rtk proxy python3 scripts/prepare_g8_native_rehearsal.py --capsule /absolute/capsule --bindings /absolute/bindings.json --filesystem /absolute/filesystem.json --private-key /absolute/reviewer.pem --output /absolute/new-package
rtk proxy python3 scripts/sign_g8_native_context.py --package /absolute/new-package --readback /absolute/score-job.json --job-id aijob-REPLACE --phase score --private-key /absolute/reviewer.pem --registry-verification /absolute/post-create-registry.json --output /absolute/new-score-context
```

Use Python with the repository's Pydantic/cryptography dependencies. Bindings
contain the `NativePlan` fields except `files` and `source_commit`, which the
builder derives. The v3 schema carries the validation policy and operator-managed
alerts, without billing or expiry fields. The filesystem readback must identify the
approved project, exact returned ID, API enum `NETWORK_SSD`, exactly one configured
size unit equivalent to 10 GiB, and READY status reporting that capacity without
reconciliation in progress. Preserve the API readback unchanged; the CLI's
lowercase create option is not its returned enum spelling.

Sign each context only after validating the actual Job ID returned by create.
Recovery additionally requires `--previous-terminal` and `--original-context`;
the original context's `.sig` must be adjacent. Context output contains canonical
`score.json`/`score.sig` or `recover.json`/`recover.sig`. Publish both to
`/g8-durable/contexts/` through the reviewed native-filesystem attachment while the
Job waits, at most five minutes. The native entrypoint rechecks signature, package
integrity, code and kernel mount identity after this wait. An absent context stops
the Job before source access; it never triggers another submission.

The [native handoff procedure](g8-native-context-handoff.md) binds the existing
MLflow VM, mount tag/path, version-guarded attachment, immutable context transport
and restoration checks. Its static validation does not establish cloud transport:
retain actual attachment/mount/context receipts before claiming that evidence.
Do not use output/intent prefixes for context transport; they must begin empty.

## Two-Job sequence

1. **Score and seal.** Check inactive production key, source/output
   access, empty synthetic output and intent, actual mount and submitted Job
   readback. Start the existing MLflow VM only when these gates are ready.
   Verify authenticated MLflow readiness and require an unauthenticated request
   to be denied. Hydrate and semantically verify the source capsule inside Nebius.
   Use the actual `run_live` lifecycle with a synthetic plan, the frozen scorer,
   original synthetic request and remote transports. Reserve one MLflow evaluation
   run before scoring. Terminate the Job process deliberately immediately after
   `scored-receipt.json` is fsynced, before logging. Record the expected exit and
   actual Job ID; a receipt alone does not establish Job termination.
2. **Reattach and recover.** After the first Job is terminal, attach the same native
   filesystem to the second Job and verify the original reservation, scored seal,
   lock and mount evidence before mutation. Remove only the identified disposable
   synthetic scoring workspace, preserving the seal and ledger. Reject a recovery
   path reaching input downloads, model execution or run creation. In a child
   process, interrupt immediately after a real authenticated MLflow artifact PUT.
   Resume in a fresh child process using the same ledger and run. Verify metrics,
   histories, all artifact bytes and 30 dataset inputs, then publish the verified
   release with conditional writes, deliberately withhold SUCCESS once, and resume
   publication from the retained seal. Repeating completed recovery
   must perform zero MLflow or S3 writes. Archive evidence before cleanup.

`run_g8_native_rehearsal.py` is the native entrypoint. Its score Job exits with
code 73 after the fsynced seal; the second Job requires the first Job's FAILED
terminal readback and verifies that seal before removing its scoring workspace.
A recovery child exits with code 74 after a real MLflow artifact write, then a
fresh child completes logging/publication and verifies a read-only repeat.
Preflight and both recovery children share a 55-minute deadline from entrypoint
start. The artifact-loss child has at most 15 minutes; the finish child receives
only the remaining budget. No child starts after expiry, leaving five minutes
within the one-hour Job limit for final evidence and execution overhead.
Both Jobs retain the original execution identity. MLflow reservation/logging tags
explicitly mark synthetic rehearsal, placeholder dataset registration and fixture
comparison evidence. Neither source transport nor remote tracking is mocked.

The existing `g8_live_rehearsal.py` supplies earlier offline fault patterns and
remains separate. No fixture regeneration, local
runtime rehearsal, extra probe Job, or unreviewed fallback image is part of this
sequence. Ambiguous submission is resolved by readback, never another create call.

## Evidence and interpretation

Independently download the final S3 release and verify it against the retained
scored/publication seals. Independently query the original MLflow run, metric
histories and artifact hashes. Preserve both Job readbacks/terminal statuses,
mount observations, reservation ID, package/code hashes, fault logs, exact output
inventory and cleanup receipts. Stop the MLflow VM and delete only the
identified rehearsal Jobs/filesystem after evidence has been archived and checked.

The source receipt contains a **synthetic placeholder** dataset-registration ID
and 27 **synthetic contract fixtures**, not original Java comparison executions.
Keep these labels in the resulting evidence. This rehearsal can prove native
retention and authenticated evaluation logging; it cannot establish original C3
availability, production quality, replacement authorization or G8 completion.

## Delivery gates

- PR #189: source capsule construction, corruption checks and bounded hydration.
- This implementation: native entrypoint, immutable package/command rendering,
  signed contexts, exact Job-readback validation and native/remote fault hooks.
  Static checks pass; no native/authenticated runtime receipt is claimed.
- Before provisioning: complete the unresolved execution bindings above. Use the
  reviewed package under the validation policy; approval delays do not expire it.
- After rehearsal: preserve evidence and reconcile
  [ARD-0035](../../architecture/ARD-0035-nebius-lightgbm-first.md), Issue #23 and the roadmap.
  G8 remains open and G9 blocked until the separately approved production work passes.
