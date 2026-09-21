# G8 native context handoff

> **Status reconciliation — 2026-09-21:** The 10 GiB filesystem binding is the historical rehearsal context. PR #207 records 32 GiB capacity; production bindings require a fresh package and preflight.
> See [current roadmap evidence](../../roadmap/CURRENT_STATUS.md) and the
> [execution policy](../../ml/model-validation-execution-policy.md). Earlier
> dated receipts retain their values; obsolete billing/expiry gates do not apply.

This completes the operator procedure for the
[native rehearsal package](g8-native-rehearsal-package.md). It creates no new
final-test authorization and consumes no additional Jobs. Apply the
[validation execution policy](../../ml/model-validation-execution-policy.md): no billing
checks, mandatory session/retention windows or package-age rejection. All training/scoring and runtime
rehearsals remain on Nebius Serverless.

## Fixed transport

| Binding | Value |
| --- | --- |
| Existing VM | `computeinstance-e00xq8hqrzks2pf3gn` (`aimada-wave1-mlflow`) |
| Project | `project-e00g6zvxpr00waz8t3y51k` |
| Private MLflow address | `10.4.0.54:5500` |
| Operator connection | Existing key-authenticated SSH as `aimada`; preserve host-key checking and firewall |
| Filesystem | One returned ID, `NETWORK_SSD`, READY, 10 GiB; same ID in both Jobs |
| VM mount tag/path | `g8-native-rehearsal` / `/mnt/g8-native-rehearsal` |
| Job mount path | `/g8-durable` |
| Context destination | Native filesystem root: `contexts/score.{json,sig}`, then `contexts/recover.{json,sig}` |
| Temporary VM transport files | `/opt/aimada/g8-native-handoff/`; no private signing key or credentials copied |

## Prepare and attach

1. Complete any interactive CLI authentication and command approvals while the VM
   is stopped. Spend monitoring belongs to the operator's alerts; no billing
   query or refreshed balance is required. Archive the VM's current
   API readback. Stop the VM and read it back again as `vm-before.json`.
2. Require no existing filesystem attachments. Create only the approved 10 GiB
   filesystem and preserve its raw API readback, including READY status and
   actual capacity. Do not attach while the VM is running.
3. Render a resource-version-guarded patch with the tool below. Execute the printed
   argument array only after reviewing it. Read the VM again and use
   `verify-attached` to reject unrelated disk, identity or network changes.
4. Start with `g8_vm_deadline.py start --operator-managed --directory
   /absolute/new-start-directory`. This records a single-use intent without a
   mandatory stop lease or remaining-session gate. Resolve an ambiguous response
   by VM readback, never by repeating the start in a new directory.
5. An explicit stop timer remains optional: `arm --directory /absolute/new-guard
   --deadline TIMESTAMP`, then `start --directory /absolute/new-guard`. Only a
   future deadline and live guard are required; there is no fixed three-hour cap
   or two-hour headroom minimum. Keep the operator host and CLI available when
   choosing this local guard. An expired chosen timer still blocks a timed start.
   Record the uptime start and repeat `verify-attached`
   with `--running`. Through its existing SSH connection, require the chosen
   mount path to be absent or an empty canonical directory. Mount with
   `sudo mount -t virtiofs -o rw,nodev,nosuid,noexec g8-native-rehearsal /mnt/g8-native-rehearsal`.
   Do not add an fstab entry. The mount is for data/context transport only.

```bash
rtk proxy python3 scripts/g8_native_handoff.py attach --before /absolute/vm-before.json --current /absolute/vm-current.json --filesystem /absolute/filesystem.json --filesystem-id computefilesystem-APPROVED
rtk proxy python3 scripts/g8_native_handoff.py verify-attached --before /absolute/vm-before.json --current /absolute/vm-attached.json --filesystem /absolute/filesystem.json --filesystem-id computefilesystem-APPROVED
```

Supply the filesystem ID independently from the approved provisioning receipt;
use that identical ID when signing the Job package. Verification receipts require
a VM resource version newer than the pre-attachment baseline. Only rendering the
initial attach command allows the unchanged baseline.

## Deliver and archive

Sign the ordinary Job readback locally with `sign_g8_native_context.py` after
binding its returned Job ID. Transfer only the signed context pair and reviewed
`publish_g8_native_context.py` through the existing operator SSH connection.
Verify transferred script/context hashes before invocation. Run the publisher as
root with `--context`, `--signature`, their SHA-256 flags and `--phase`.
It checks the exact writable virtiofs tag, capacity, absence of nested mounts and
root-owned private context directory. It fsyncs complete files and publishes the
signature last, using links that cannot overwrite existing paths. An identical
transport retry is allowed; changed bytes and symlinks fail. The waiting Job still
verifies the Ed25519 signature, signed package, actual code/mount and API readback.
The transport receipt alone does not attest successful Job validation.

Before cleanup, archive the retained native evidence and sealed checkpoint through
the same operator connection; verify hashes independently against the native
inventory. Independently verify S3 and MLflow evidence as specified in the package.

## Restore

After both Jobs are terminal and independent copies are verified, unmount the VM
path, stop the VM, and get fresh VM/filesystem readbacks. Render `detach` using
those readbacks. Detachment preserves the full current VM configuration and
resource version, omitting only `spec.filesystems`. The live API rejected the
clear-mask-only patch with `invalid resource size type: <nil>`; preserve that
failed attempt and re-read before using the full configuration. Run
`verify-restored` after a fresh readback; require the original
VM configuration, preserved network and STOPPED state. Verify no filesystem
attachment owners remain before deleting only the recorded temporary filesystem
and Jobs. Keep MLflow disks and evidence. Remove only this handoff's temporary
transport files; preserve readbacks and cleanup receipts locally.

Provider references: [attachment and mounting](https://docs.nebius.com/compute/storage/use),
[detachment](https://docs.nebius.com/compute/storage/detach-volume),
[filesystem API](https://github.com/nebius/api/blob/main/nebius/compute/v1/filesystem.proto).

## September 15–16 preflight outcome

The [retained receipt](../../evidence/g8-native-handoff-preflight-20260916.json) records
an actual native VM mount and authenticated MLflow read (200), with unauthenticated
access denied (401). No Job context or evaluation was submitted. An overnight
tool-approval wait left the VM running for approximately 10h43m, exceeding its
four-hour limit; operator monitoring failed to enforce the bound. Package
validation then rejected stale billing before submission. The failed signed
package is retained as rejected, never relabeled successful.

Cleanup restored the VM to STOPPED at version 44 and deleted the temporary
filesystem within 24 hours. VM disks remain intact. Only the non-secret publisher
script remains in the temporary VM transport directory; remove it during the next
authorized VM session rather than restarting solely for deletion.
The independent guard was added after this failure. The September 16 validation
policy subsequently made timed guards optional and removed billing/session gates;
the historical overrun remains recorded. The two-Job rehearsal,
authenticated artifact recovery and independent S3/MLflow verification remain open.
