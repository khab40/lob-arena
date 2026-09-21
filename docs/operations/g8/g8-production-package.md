# G8 production native execution package

> **Status reconciliation — 2026-09-21:** The unsigned review package remains the production starting point. PR #207 adds original metadata/payload verification, capacity, live registration and a new unsigned review; it does not authorize final evaluation.
> See [current roadmap evidence](../../roadmap/CURRENT_STATUS.md) and the
> [execution policy](../../ml/model-validation-execution-policy.md). Earlier
> dated receipts retain their values; obsolete billing/expiry gates do not apply.

Status: **unsigned review package prepared; no production Job authorized or submitted**.
This follows [PR #200](https://github.com/khab40/lob-arena/pull/200) and independent
[readback of all 64 rehearsal S3 objects](../../evidence/g8-independent-s3-readback-20260917.json). Their sizes/hashes, SUCCESS inventory,
checksum inventory and four MLflow artifact hashes match the retained checkpoint.

## Frozen review bindings

- New run: `nasdaq-g8-replacement-r5-20260917`.
- Candidate: `5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff`.
- Image digest: `dc32b12d7216bfeef8e5d95c50363f34bb76f34159ef9343ff3d6996983a89b2`.
- Isotonic calibration: `a27d88091988dc6e504e3e84d57c985f774f5865ea534882ba7fe87c6ea49e30`.
- Selected balanced threshold: **0.5769230769230769**. Retained high-precision
  threshold: `1.0`; high-recall threshold: `0.01296456352636128`.
- Candidate-bound experiment, feature schema and calibration parameters remain
  unchanged. Nothing is trained, calibrated, scored or downloaded from final S3.
- R4 Job `aijob-e00vtamgkr07mwzt4t`, consumed approval references, four prior
  submissions and prior test access remain historical facts. R4 monitor/log
  bytes are checked against the hashes required by `ReplacementPlan` and copied
  into review history. R4's approval is removed from the new draft request.

See the [preparation receipt](../../evidence/g8-production-package-review-20260917.json).
The original local review is preserved under `outputs/g8-production-review-20260917-v2/`.
The current unsigned review is `outputs/g8-production-review-20260921-v3/`, bound to
the [verified original payload and updated readiness evidence](../../evidence/g8-original-payload-verification-20260921.json).

## Transport and preparation

The actual replacement entrypoint now enters through the same bounded,
hash-anchored, in-memory bootstrap used by the native rehearsal. The production
target is explicit; the rehearsal default is unchanged. `/g8-package/production`
contains the flat signed package and archives. `/g8-durable` retains execution
state. `publish_g8_native_package.py --destination-name production` stages into a
new directory, refuses overwrite and preserves the existing rehearsal package.
No staging or provisioning is performed by the review builder.

`scripts/prepare_g8_production_review.py` takes `--r4`, `--candidate`, `--rehearsal`,
`--run-id`, `--output` and optional `--frozen-root`. It requires a clean checkout,
reads literal contract constants without importing model code, verifies retained
identities, assembles archives and writes an unsigned inventory. Its draft request
uses the corrected C4 `artifacts` layout and the new output prefix. It emits
neither a runnable signed manifest nor a submission command.

## Still required before production signing/submission

1. Preserve the verified original checkpoint bytes and genuine registration now
   bound into the unsigned review. Validate production comparison semantics on
   Nebius; byte verification did not parse protected rows.
2. Preserve the completed [production transport verification](evidence/g8-production-transport-probe-20260921.json).
   Recheck the finalized signed package and actual execution context at submission.
3. Complete fresh permissions, pinned image alias, storage capacity, credentials
   and empty output/intent checks. Historical R4 selectors are review inputs only.
4. Obtain replacement-specific final-test approval, bind its authorization files
   into the final canonical request, then sign the complete v3 replacement plan.
   Preserve the resulting immutable package and separately signed actual Job context.

No billing check, package submission expiry or fixed VM window is introduced.
Per-Job resource/time bounds and separate final-test approval remain. G8 is open;
G9 remains blocked, and actual model quality is not established by this package.

## September 21 readiness continuation

Fresh provider readback located the completed original C3 test-date and C4 Jobs.
The original preparation metadata initially returned AccessDenied; the
[initial readiness receipt](../../evidence/g8-production-readiness-20260921.json) preserves
that observation. The operator then approved the exact 89-key metadata scope.

The [completed metadata audit](../../evidence/g8-original-comparison-metadata-20260921.json)
verified all 27 original checkpoint inventories, 30 replay domains and the unchanged
final projection manifest: 89 objects / 273,680 bytes, with no row or payload reads.
Nebius rejected the large single policy, so the same exact keys were granted in
12 batches of at most eight. Every temporary rule was removed; the complete bucket
spec was restored (resource version 34 → 58), and a fresh metadata GET was denied.
No model Job, final-bucket access or object write occurred.

The unsigned metadata supplement at
`outputs/g8-production-readiness-20260921/production-metadata-bindings/` prepares
`projection.json`, `profile.json`, `comparison-inventory.json`, `c4-inputs.json`
and the comparison manifest. Its hashes are in the audit receipt. It does not
assert full payload verification, live dataset registration or execution authority.
Preserve the original v2 review rather than silently changing its hash.

The original comparison inventory contains **2,632,277,460 bytes (2.451 GiB)**.
Scored retention copies all 27 checkpoint trees. A 10 GiB filesystem permits a
maximum 2 GiB checkpoint under the five-copy guard, so production cannot use the
rehearsal's original capacity. The [capacity proposal](../../evidence/g8-production-capacity-proposal-20260921.json)
expands the same filesystem to 32 GiB and proposes a 4 GiB checkpoint bound,
requiring 20 GiB actual free space before final access. The operator approved it,
and [execution evidence](../../evidence/g8-capacity-registration-20260921.json) confirms
32 GiB mounted capacity and 34,346,348,544 free bytes. The preserved 828-file
archive hash verifies. The VM is stopped again; production storage bindings and
a fresh free-space check at execution remain required.
The original rehearsal's 10 GiB receipt remains historical evidence.

Live C4 registration also verifies: the original FINISHED run contains 240 dataset
inputs, with all 30 final-tabular entries matching frozen source URIs, hashes,
counts and root identity; all four metadata artifact hashes match. No payload
rows were accessed. The earlier unsigned supplement remains historical.

The separately approved [payload audit](../../evidence/g8-original-payload-verification-20260921.json)
then staged 294 original objects (2,632,277,460 bytes). All 377 staged payload/metadata
files were independently rehashed. The complete bucket policy was restored after
each of 37 exact-key batches (version 58 → 132); the final GET returned HTTP 403.
The VM is STOPPED again and the final-access key remains INACTIVE. No rows were
parsed, no model Job ran and no final bucket was accessed.

The new 25-file unsigned review preserves the frozen candidate, prior R4 history
and original v2 package. Its profile/input/comparison and native durability bindings
now include verified payload bytes, live registration and 32 GiB capacity, with a
4 GiB / 2,000-file checkpoint bound. Archive contents and all member hashes/sizes
verify. Historical Job-loss evidence is retained separately from fresh capacity
and staged-byte verification. No authorization files or executable plan are emitted.

The [non-final production transport probe](evidence/g8-production-transport-probe-20260921.json)
completed on Job `aijob-e00samq5cpe1bysr4x` using the frozen image and exact reviewed
runtime. All 12 overlays, read-only package/bootstrap, native filesystem and signed
actual-Job context verified. The real unsigned entrypoint and wrong context failed
closed. Independent readback verified all 25 package hashes before archiving the
probe-created package and freeing the canonical production path. The VM is stopped
and the final key inactive. No protected rows, model scoring or final access occurred.
The provider mount warning recurred; successful runtime checks do not explain it.

Remaining gates: separately approved protected-comparison semantic verification on
Nebius, fresh preflight, canonical request and replacement-specific authorization.
G8 remains open; the unsigned review is not execution authority.

The [comparison semantics proposal](evidence/g8-comparison-semantics-proposal-20260921.json)
binds the prepared audit worker and original inventory to one credential-free,
read-only Nebius Job (4 vCPU, 16 GiB, at most one hour). It requests parsing original
test-date events, snapshots, alerts and synthetic ground truth for structural checks.
Only aggregate pass/fail evidence is returned. This extends the earlier byte-only
approval and awaits operator approval; it excludes final features and model scoring.
Prediction/feature pairing remains part of the separately authorized final evaluation.
