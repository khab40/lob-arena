# Temporary braces depth patch

Tracks [Bug #294](https://github.com/khab40/lob-arena/issues/294) in
[Project #3](https://github.com/users/khab40/projects/3) and
[Dependabot alert #54](https://github.com/khab40/lob-arena/security/dependabot/54).

As of 2026-10-04, [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)
affects braces through 3.0.3 and lists no patched release. Tailwind's Chokidar
and fast-glob/micromatch paths load it during frontend and website tooling.
The deployed frontend image serves static files with nginx.

`braces@3.0.3.patch` backports only the five library changes from upstream
[PR #72](https://github.com/micromatch/braces/pull/72), immutable commit
`28d440b5dd449dbf1fe6f3506cf94ecca4d02660`. The upstream PR is unmerged;
this is a locally tested mitigation, not a released upstream upgrade. Unrelated
changes on upstream main (including quote parsing) are not backported, preserving
the released 3.0.3 behavior outside the nesting and cycle guards.

The parser and direct AST APIs cap nesting at 100. Callers can set a lower
`maxDepth`, but cannot raise or disable the cap. Excessive nesting throws a
bounded depth error; expansion also rejects cyclic parent chains. Ordinary
glob, range, escaped literal and parser-created AST behavior is retained.

Both manifests configure the patch. The shared lockfile binds its hash;
`website/patches` points here. Docker copies patches before its frozen install,
and release snapshots retain them with the lockfile. The shared regression
suite runs against each application's actual installed dependency graph.

The ignored July deployment npm lock is historical evidence, not an active
install input; its original checksums remain unchanged. Use the current pnpm
manifests and frozen lockfile for supported builds.

When upstream publishes a fixed release, replace this patch with that release,
regenerate the shared lockfile, and rerun both applications' tests, lint and
builds plus the Docker build. Keep the depth regressions. Dependabot may retain
the alert while the package version remains 3.0.3; do not dismiss or suppress it
as proof of remediation.
