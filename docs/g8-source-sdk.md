# Bounded synthetic source staging

Prepared from `main` at `7afd1f4` (PR #186). G8 remains open and G9 blocked.
PR #169 is closed; its useful C4-layout work is already superseded on main.

## Verified transport

The optional `--sdk` path in `stage_g8_native_sources.py` reuses one S3 client
from AWS CLI 1.46.1's vendored Botocore 1.43.62 in the existing frozen image.
No image, candidate, feature, calibration or threshold changes are required.
The default CLI transport remains available. Both paths use the same sealed
inventory, private upload copies, conditional PUTs, byte readbacks and marker-last
publication. Shared verification helpers accept an explicit transport; production
publication still defaults to its existing CLI implementation.

The SDK makes one attempt per request, uses 5-second connection and 15-second
read timeouts, and caps each download at its sealed size. A main-thread process
timer bounds the entire SDK operation, including streaming: 900 seconds by
default, at most 1,800 seconds. Expiry exits without entering ambiguous-PUT
reconciliation or retrying publication. It preserves partial objects. This timer
does **not** revoke IAM permissions; cleanup remains an operator responsibility.
`--session-seconds` requires `--sdk` so the CLI cannot silently ignore that bound.
See the SDK [configuration](https://docs.aws.amazon.com/botocore/latest/reference/config.html)
and [conditional PUT contract](https://docs.aws.amazon.com/botocore/latest/reference/services/s3/client/put_object.html).

The [execution receipt](evidence/g8-sdk-source-transport-20260915.json) records:

- 17 tests passing in the pinned image with networking disabled, covering SDK
  request models, failed marker publication, lost PUT responses, preserved
  partial uploads, zero-write completed repeats, bounded downloads and deadlines.
- An actual authenticated, read-only S3 probe using the exact previously reviewed
  development MysteryBox versions. All 25 candidate objects / 343,345 bytes were
  verified and an independent reader copy retained in **19.566 seconds**.
- 50 GETs, 26 HEADs and two listings; zero writes. The synthetic input prefix
  remained empty and HEAD of the known production object was explicitly denied.

The read timing establishes removal of per-object emulated CLI startup overhead;
it is not a guarantee of publication throughput. Full remote source publication,
native Job-loss durability and authenticated MLflow recovery are still unproved.
The original 350-object package and completed candidate release remain frozen.

## Next reviewed writer window

The previous staging authorization ended with verified revocation. The new
[unapplied proposal](evidence/g8-input-only-staging-proposal-20260915.json)
requests only development-group writes to
`releases/g8-native-rehearsal-20260914/staging/*` in
`aimada-wave1-final-e00g6zvxpr00`. Its observed resource version is **6**.
It preserves both existing reader rules and every other bucket setting.
The candidate needs no writer grant because its complete release is verified.

After fresh operator approval, re-read the complete policy and version before
applying the partial update. A version conflict stops execution for reconciliation.
Review the applied GET before the single 900-second publication session. Revoke
only the appended input writer rule within **30 minutes**, preserving concurrent
changes; independently verify cleanup. Do not rerun any historical grant.
Then run the full read-only download verification, before any paid rehearsal Job.

Use the six frozen-image overlays and retained package described in
[the rehearsal instructions](g8-live-replacement.md), plus `g8_source_sdk.py`.
The source marker remains
`792b25de957556d287ec2812645fe36f92aeca79b89bc62448e071f67cc60de9`.
Append `--sdk --session-seconds 900` to the existing `--publish` command;
after revocation, append those same options to `--readback --destination <new-path>`.
Any timeout or partial result preserves uploaded bytes and requires a fresh
read-only assessment; it does not authorize another writer session or rescoring.

This proposal starts no Job, filesystem, MLflow VM or final evaluation. The
previously approved two-Job/$2 synthetic rehearsal still requires complete source
readback, current billing and a reviewed native/remote execution package. The
production replacement requires its separate signed exception afterward.
