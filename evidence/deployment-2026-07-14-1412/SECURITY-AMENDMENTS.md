# Security amendments to the dependency snapshot

## 2026-09-21: AnyIO 4.14.2

The maintained copy of `versions/requirements/backend/uv.lock` updates AnyIO
from 4.13.0 to 4.14.2 for Dependabot alerts
[#41](https://github.com/khab40/lob-arena/security/dependabot/41) and
[#43](https://github.com/khab40/lob-arena/security/dependabot/43).
The fixes cover [process-worker stderr blocking](https://github.com/advisories/GHSA-5p39-cfhj-2xmp)
and [TLS hostname encoding](https://github.com/advisories/GHSA-82r6-8w77-94w6).
Only the AnyIO version and distribution metadata change; its dependency edges
remain unchanged. The active `backend/uv.lock` already used 4.14.2.

This is a security-maintained derivative, not a new capture or evidence that
the July deployment ran the patched version. The original snapshot remains
available in Git at commit `916e3ce`. Commit `264a848` previously upgraded
cryptography in this same lockfile. The sanitized snapshot project name is
`[REDACTED]-backend`; use the active backend project for installations.

The original `manifest.json`, `checksums.sha256`, README, package inventory,
and deployment outcomes remain unchanged. The original checksum command in
README already reported a mismatch for this lockfile after the cryptography
update; that single amended-file mismatch remains expected. In a fresh Git
checkout, the original checksum list also references the untracked archived
frontend `package-lock.json`, which may be absent.

SHA-256 history for `versions/requirements/backend/uv.lock`:

| Revision | SHA-256 |
| --- | --- |
| Original captured file (`916e3ce`) | `6ec340a7a4bcf80eea2877d0620c70f4a428d8125ab83e86932dec4ee2d109ac` |
| Before this amendment (`63fe41d`) | `76976f0cb22c33399178e0acbe7fdd8c81f622c9d0d44fa994b70eca051c059c` |
| After this amendment | `8536d1bcbd47e8f6ddea1ce32fa1e002ce7f3c8dd427e7ab1380700084f3de54` |

Verify the amended file from this directory:

```sh
printf '%s  %s\n' '8536d1bcbd47e8f6ddea1ce32fa1e002ce7f3c8dd427e7ab1380700084f3de54' \
  'versions/requirements/backend/uv.lock' | shasum -a 256 -c -
```

The backend dependency-floor tests cover AnyIO >=4.14.2 in both lockfiles,
while retaining the existing cryptography and framework security checks.
