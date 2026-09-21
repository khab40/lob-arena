# G8 production native execution package

Status: **unsigned review package prepared; no production Job authorized or submitted**.
This follows [PR #200](https://github.com/khab40/lob-arena/pull/200) and independent
[readback of all 64 rehearsal S3 objects](evidence/g8-independent-s3-readback-20260917.json). Their sizes/hashes, SUCCESS inventory,
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

See the [preparation receipt](evidence/g8-production-package-review-20260917.json).
Full local review files and frozen metadata are retained under
`outputs/g8-production-review-20260917-v2/`.

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

1. Verify original Java comparison checkpoints and genuine dataset registration;
   bind the final projection metadata, C4 profile, comparison inventory and input
   locations. Rehearsal fixtures cannot stand in for this evidence.
2. Validate the production transport/entrypoint on Nebius. Static checks use inert
   code; they do not claim execution of this changed production package.
3. Complete fresh permissions, pinned image alias, storage capacity, credentials
   and empty output/intent checks. Historical R4 selectors are review inputs only.
4. Obtain replacement-specific final-test approval, bind its authorization files
   into the final canonical request, then sign the complete v3 replacement plan.
   Preserve the resulting immutable package and separately signed actual Job context.

No billing check, package submission expiry or fixed VM window is introduced.
Per-Job resource/time bounds and separate final-test approval remain. G8 is open;
G9 remains blocked, and actual model quality is not established by this package.

## September 21 readiness continuation

The [readiness receipt](evidence/g8-production-readiness-20260921.json) locates the
completed original C3 test-date Job and C4 projection Job through fresh provider
readback. Their completed states do not prove current checkpoint availability.
The exact original `preparation.json` GET is denied to the development identity;
its current bucket grant covers `releases/*`, not preparation metadata.

The [proposed metadata read grant](evidence/g8-comparison-metadata-access-proposal-20260921.json)
adds `storage.viewer` for 89 exact metadata keys in the development bucket,
preserving both existing rules. It requires explicit approval and a fresh baseline
check; no policy change has been applied. The bounded audit reads no rows, Parquet,
checkpoint payloads or final-bucket objects, submits no Jobs, and removes the
appended rule afterward. Full original payload verification and live dataset
registration remain separate gates. The native filesystem is READY (10 GiB),
the MLflow VM is STOPPED and the production final key remains INACTIVE.
