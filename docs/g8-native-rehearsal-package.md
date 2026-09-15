# G8 native-storage and MLflow rehearsal package

Status: **native entrypoint and package tools implemented; cloud rehearsal not executed**.
Implementation base: `6ab428694cebc4707fe03f042af54b73bfae4bad` (merged PR #189).
This follows the completed
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
| Code | Exact allowlist of injected runner, lifecycle, source SDK and evaluation overlays; per-file SHA-256 and size; no writable code mount |
| Source | Eight capsule hashes above, source manifest hash, candidate hash and both source SUCCESS hashes from PR #188 |
| Storage | One returned `computefilesystem-…` ID, `network_ssd`, 10 GiB, `/g8-durable`; observed writable `virtiofs` mount; reject nested mounts |
| Network | Project `project-e00g6zvxpr00waz8t3y51k`, subnet `vpcsubnet-e00ppzc4353dxv210j`; private MLflow `http://10.4.0.54:5500` |
| Credentials | Four explicit `SECRET_ID@VERSION_ID` selectors for development S3 and MLflow; no latest-version selectors or inline values |
| Budget | Fresh provider billing plus lag allowance, campaign below $40, total ceiling $50, additional rehearsal ceiling $2 |
| Jobs | Two named phases, `cpu-d3`, `4vcpu-16gb`, 100 GiB ephemeral disk, 1h timeout each, restart `never`, no GPU |
| Retention | Filesystem deadline within 24h; MLflow VM uptime within 4h; cleanup identity list |

Each submitted Job needs a fresh API readback matching the immutable image,
resources, mount ID, injection paths and **both secret ID and version ID for each
environment binding**. Preserve its hash and actual Job ID. An operator-signed
context binds that readback to the package before the entrypoint accesses inputs.
Runtime access-ID matching and authenticated calls complement that control-plane
evidence; they do not independently attest secret-version provenance. Do not
resolve the PR #188 attestation gap by changing a receipt boolean alone.

The ordinary API view omits injected file bytes but includes plain environment
configuration values. This was verified against R4's current readback and the
[Job API definition](https://github.com/nebius/api/blob/main/nebius/ai/v1/job.proto).
`g8_native_readback.py` therefore checks paths, exact version selectors and plain
configuration values;
`g8_native_runtime.py` separately compares actual file bytes, read-only mounts and
environment values against the signed package before any source access. Neither
the ordinary readback nor these static tests alone establishes native durability.

MysteryBox selectors in the contract are resource/version identifiers, not AWS
credential values. GitGuardian incident 37285889 flags one such identifier as a
generic high-entropy secret; classify that specific incident as a false positive
through GitGuardian's supported workflow. Keep credential scanning enabled.

## Package and context tools

`scripts/prepare_g8_native_rehearsal.py` requires a clean reviewed checkout, the
retained capsule, fresh billing JSON, the returned filesystem JSON, completed
plan bindings and an existing Ed25519 reviewer key. It copies only the 21 reviewed
code files, eight capsule parts, billing/filesystem evidence and reviewer public
key. It signs the immutable manifest and prints the two commands without submitting.
The reviewer private key stays outside the package and is never injected.

```bash
rtk proxy python3 scripts/prepare_g8_native_rehearsal.py --capsule /absolute/capsule --bindings /absolute/bindings.json --billing /absolute/billing.json --filesystem /absolute/filesystem.json --private-key /absolute/reviewer.pem --output /absolute/new-package
rtk proxy python3 scripts/sign_g8_native_context.py --package /absolute/new-package --readback /absolute/score-job.json --job-id aijob-REPLACE --phase score --private-key /absolute/reviewer.pem --output /absolute/new-score-context
```

Use Python with the repository's Pydantic/cryptography dependencies. Bindings
contain the `NativePlan` fields except `files`, `source_commit` and
`billing_receipt_sha256`, which the builder derives. Billing JSON has exactly
`observed_at` (timezone-aware ISO timestamp), `campaign_spend_usd`,
`lag_allowance_usd` and `provider_reference`; the first two cost values sum to the
plan's reconciled campaign spend. The filesystem readback must identify the
approved project, exact returned ID, `network_ssd` and 10 GiB in `size_bytes`.

Sign each context only after validating the actual Job ID returned by create.
Recovery additionally requires `--previous-terminal` and `--original-context`;
the original context's `.sig` must be adjacent. Context output contains canonical
`score.json`/`score.sig` or `recover.json`/`recover.sig`. Publish both to
`/g8-durable/contexts/` through the reviewed native-filesystem attachment while the
Job waits, at most five minutes. The native entrypoint rechecks signature, package
expiry, code and kernel mount identity after this wait. An absent context stops
the Job before source access; it never triggers another submission.

**Context delivery is still an operational preflight gate.** Before provisioning,
review how the operator will write the context and archive retained outputs through
the private network. A proposed temporary attachment to the existing MLflow VM
must bind that VM ID, attachment/mount paths, permission checks and restoration
steps to its before/after API readbacks. This PR does not attach storage, open a
Job SSH port or declare that path tested. Do not use the output/intent prefixes
for context transport, because the live lifecycle requires them empty initially.

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
   release with conditional writes, deliberately withhold SUCCESS once, and resume
   publication from the retained seal. Repeating completed recovery
   must perform zero MLflow or S3 writes. Archive evidence before cleanup.

`run_g8_native_rehearsal.py` is the native entrypoint. Its score Job exits with
code 73 after the fsynced seal; the second Job requires the first Job's FAILED
terminal readback and verifies that seal before removing its scoring workspace.
A recovery child exits with code 74 after a real MLflow artifact write, then a
fresh child completes logging/publication and verifies a read-only repeat.
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
inventory and billing/cleanup receipts. Stop the MLflow VM and delete only the
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
- Before provisioning: complete the unresolved execution bindings above and refresh
  billing. Run within the existing approval only when the concrete package is ready.
- After rehearsal: preserve evidence and reconcile
  [ARD-0035](architecture/ARD-0035-nebius-lightgbm-first.md), Issue #23 and the roadmap.
  G8 remains open and G9 blocked until the separately approved production work passes.
