# Governed Job images — 2026-09-28

[Bug #84](https://github.com/khab40/lob-arena/issues/84) and
[Bug #246](https://github.com/khab40/lob-arena/issues/246),
[Project #3](https://github.com/users/khab40/projects/3).

New G4 development dry runs and submissions use the exact request image
`registry/path@sha256:<64 hex>`. A distinct `--deployment-image` or
`--allow-short-tag-workaround` fails before any provider call. After creation,
the submitter reads the actual Job and requires its exact ID and `spec.image`.
Unavailable or mismatched readback records failure and requests cancellation;
it never retries creation. Matching evidence retains the actual digest image.

Historical short-tag receipts remain readable for monitoring and recovery of
an already-created Job. They cannot qualify a new G4 result collection by
converting an observed alias into the approved digest. Read-only recovery does
not submit a replacement Job. The market-data and synthetic native-rehearsal
historical contracts are separate; this repair does not rewrite their evidence.
Recovery flags with the default synthetic workload are rejected, so a missing
`--workload lightgbm-wave1` can never turn a recovery request into Job creation.

New G8 production execution/recovery commands also use the signed plan digest.
Fresh final-evaluation requests through the generic G4 submitter are rejected;
they must use the signed replacement-package path with its pre-access handshake.
The [replacement runbook](g8/g8-live-replacement.md) defines the signed actual
Job readback and current-runner requirement. Offline historical package validation
and the frozen candidate, signatures, G8/G9 exit and existing artifacts are retained.

Provider capability evidence: the September 28
[r2 acceptance receipt](../evidence/transformer-development-acceptance-r2-20260928.json)
records completed Job `aijob-e00avfmh58qjzav9tr`. Its retained create/terminal
readbacks have a [sanitized inspectable projection](../evidence/digest-image-provider-readback-20260928.json)
with source-file checksums. Both contain
the exact direct `ti@sha256:01dba2d703be82c12a207fbe14fddc11e89ea1a350687a9aa6e2160c5cf2f7dc`
image reference. No additional Job or model evaluation was needed for this repair.

Verification uses inert command/signature/readback fixtures: digest equality,
legacy-context rejection, stale-runner rejection, mismatched Job/image failure,
cancellation without retry, and refusal to promote alias evidence. New cloud
execution still requires its own reviewed package and applicable authorization.
