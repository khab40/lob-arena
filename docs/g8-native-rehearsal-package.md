# G8 native-storage and MLflow rehearsal package

Status: **source injection ready; execution package not yet ready to submit**.
Base: `286f4b516e9aaea0ff7e5db1486d931152f17db4` (merged PR #188).
This is the next implementation slice after the completed
[source staging window](g8-source-sdk.md#approved-input-staging-completed).
The [existing synthetic rehearsal authorization](g8-live-replacement.md#approved-scope-synthetic-nativeremote-rehearsal-only)
remains bounded to two Jobs and $2; its input-writer window is closed.

## Frozen source capsule

The retained source inventory is **74,744 bytes**. Nebius permits at most
**64 KiB per injected file**, so directly injecting `source-package.json` fails
the documented [Job file limit](https://docs.nebius.com/serverless/jobs/manage).
`serverless/jobs/g8_native_source_capsule.py` splits those exact bytes into
65,536-byte and 9,208-byte parts. Six additional parts carry the unchanged request,
C4 profile/paths and synthetic authorization. No checkpoint or data is injected.

The [capsule receipt](evidence/g8-native-source-capsule-20260915.json) binds all eight
parts. Reassembly must preserve source SHA-256
`792b25de957556d287ec2812645fe36f92aeca79b89bc62448e071f67cc60de9`.
The candidate remains
`e04f50ff0748a0077c0602c397ed7c9c3087757fe0892f1a2d284e91b2383b7c`.

Local orchestration, with no model imports or cloud calls:

```bash
rtk proxy python3 serverless/jobs/g8_native_source_capsule.py --source /absolute/source-reader-copy --capsule /absolute/new-capsule
rtk proxy python3 serverless/jobs/g8_native_source_capsule.py --capsule /absolute/new-capsule
```

Inject the eight parts individually into `/job/g8/source-capsule/`. Keep the
receipt outside that exact eight-file directory. The future native entrypoint
calls `hydrate(capsule, destination)` after verifying its Job context and mount.
Hydration verifies the development access-ID fingerprint, requires an explicit
production-object HEAD denial, downloads only the 350 inventory-bound synthetic
objects and writes the original source marker last. Partial downloads remain
unsealed. The helper cannot submit Jobs, claim native durability, or prove which
secret version provided environment credentials. It deliberately has no hydration
CLI that could bypass the native entrypoint's pending gates.

After hydration, call `prepare_g8_native_sources.verify` with the fixed source hash
to verify the full candidate/C4/comparison/authorization contract before scoring.
The six local metadata members are not misreported as S3 downloads.

## Required execution package bindings

The next runner integration must seal the following before submission:

| Binding | Required value or evidence |
| --- | --- |
| Runtime | Existing `linux/amd64` image digest `dc32b12d7216bfeef8e5d95c50363f34bb76f34159ef9343ff3d6996983a89b2` |
| Code | Exact allowlist of injected runner, lifecycle, source SDK and evaluation overlays; per-file SHA-256 and size; no writable code mount |
| Source | Eight capsule hashes above, source manifest hash, candidate hash and both source SUCCESS hashes from PR #188 |
| Storage | One returned `computefilesystem-…` ID, `network_ssd`, 10 GiB, `/g8-durable`; observed writable `virtiofs` mount; reject nested mounts |
| Network | Project `project-e00g6zvxpr00waz8t3y51k`, subnet `vpcsubnet-e00ppzc4353dxv210j`; private MLflow `http://10.4.0.54:5500` |
| Credentials | Four explicit `SECRET_ID@VERSION_ID` selectors for development S3 and MLflow; no latest-version selectors or inline values |
| Budget | Fresh provider billing plus lag allowance, campaign below $40, total ceiling $50, additional rehearsal ceiling $2 |
| Jobs | Two named phases, `cpu-d3`, `4vcpu-16gb`, 100 GiB ephemeral disk, 1h timeout each, restart `never`, no GPU |
| Retention | Filesystem deadline within 24h; MLflow VM uptime within 4h; cleanup identity list |

Each submitted Job needs a fresh API readback matching the immutable image,
resources, mount ID, code injections and **both secret ID and version ID for each
environment binding**. Preserve its hash and actual Job ID. An operator-signed
context binds that readback to the package before the entrypoint accesses inputs.
Runtime access-ID matching and authenticated calls complement that control-plane
evidence; they do not independently attest secret-version provenance. Do not
resolve the PR #188 attestation gap by changing a receipt boolean alone.

## Two-Job sequence

1. **Score and seal.** Check fresh budget, inactive production key, source/output
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
   release with conditional writes and SUCCESS last. Repeating completed recovery
   must perform zero MLflow or S3 writes. Archive evidence before cleanup.

The existing `g8_live_rehearsal.py` provides fault patterns but substitutes mounts
and transports. It is not the native entrypoint. No fixture regeneration, local
runtime rehearsal, extra probe Job, or unreviewed fallback image is part of this
sequence. Ambiguous submission is resolved by readback, never another create call.

## Evidence and interpretation

Independently download the final S3 release and verify it against the retained
scored/publication seals. Independently query the original MLflow run, metric
histories and artifact hashes. Preserve both Job readbacks/terminal statuses,
mount observations, reservation ID, package/code hashes, fault logs, exact output
inventory and billing/cleanup receipts. Stop the MLflow VM and delete only the
identified rehearsal Jobs/filesystem after evidence has been archived and checked.

The source receipt contains a **synthetic placeholder** dataset-registration ID
and 27 **synthetic contract fixtures**, not original Java comparison executions.
Keep these labels in the resulting evidence. This rehearsal can prove native
retention and authenticated evaluation logging; it cannot establish original C3
availability, production quality, replacement authorization or G8 completion.

## Delivery gates

- This PR: source capsule construction, corruption checks, bounded hydration helper
  and the reviewed two-Job sequence. The receipt records static byte verification.
- Next fresh branch from merged `main`: native entrypoint, immutable execution
  package/command rendering and exact Job-readback validation, including explicit
  synthetic lineage labeling and native/remote fault hooks. Hash that final code.
- Before provisioning: complete the unresolved execution bindings above and refresh
  billing. Run within the existing approval only when the concrete package is ready.
- After rehearsal: preserve evidence and reconcile
  [ARD-0035](architecture/ARD-0035-nebius-lightgbm-first.md), Issue #23 and the roadmap.
  G8 remains open and G9 blocked until the separately approved production work passes.
