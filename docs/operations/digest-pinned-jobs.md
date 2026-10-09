# Immutable Job images and repository preflight

[Bug #84](https://github.com/khab40/lob-arena/issues/84) and
[Bug #246](https://github.com/khab40/lob-arena/issues/246),
[Project #3](https://github.com/users/khab40/projects/3).

## Mandatory preflight for every new Job image

Before building, uploading or submitting a Nebius Job image, check the repository
portion (registry host plus repository path, excluding tag/digest) is **at most
64 characters**. This operator rule applies to synthetic/research Jobs too.
Keep the full `repository@sha256:<64 hex>` reference in `spec.image`; labels use
separate repository and 64-character digest values. Never substitute a mutable tag.
[Bug #285](https://github.com/khab40/lob-arena/issues/285) records the recurring
boundary: the 65-character `.../transformer-research` fails, while the 47-character
`cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/tr` passes with the same digest.
Length 64 passes; length 65 must stop locally before any provider call.

An inert preflight, before any build/upload/create command:

```sh
IMAGE_REPOSITORY=cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/tr
IMAGE_DIGEST='REPLACE_WITH_APPROVED_64_HEX_DIGEST'
python3 - "$IMAGE_REPOSITORY" "$IMAGE_DIGEST" <<'PY'
import re, sys
repository, digest = sys.argv[1:]
if (len(repository) > 64 or not repository or "@" in repository
        or ":" in repository.split("/", 1)[-1] or any(c.isspace() for c in repository)):
    raise SystemExit("repository must be nonempty and at most 64 characters")
if not re.fullmatch(r"[0-9a-f]{64}", digest):
    raise SystemExit("use the full approved SHA-256 digest")
print(f"image={repository}@sha256:{digest}")
print(f"repository_label={repository}\ndigest_label={digest}")
PY
```

Replace the digest placeholder before using this check. It validates fields only;
it neither resolves an image nor supplies execution approval. Governed builders
also enforce this bound. Legacy synthetic YAML/tag renderers are inspection-only
until their request contract supports these rules; changing a label cannot repair
a mutable `spec.image`. Local build tags are separate from Job image references.

## Governed submission and historical recovery

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
