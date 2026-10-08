# Frontend security update recovery — 8 October 2026

Tracking: [Bug #347](https://github.com/khab40/lob-arena/issues/347), under
[Story #58](https://github.com/khab40/lob-arena/issues/58), in
[Project #3](https://github.com/users/khab40/projects/3).

Main CI and CodeQL passed after PR #346. The failed
[Dependabot run](https://github.com/khab40/lob-arena/actions/runs/37725786098)
could not resolve three security updates in its frontend group:

| Dependency | Existing version | Disposition |
| --- | --- | --- |
| postcss-selector-parser | 6.1.3 | Override vulnerable versions to 7.1.6. |
| source-map-js | 1.2.1 | Override vulnerable versions to 1.2.2. |
| braces | 3.0.3 | Preserve the reviewed local depth patch; no upstream fixed release is listed. |

The selector fix bounds flat-selector parsing; see the
[maintainer release](https://github.com/postcss/postcss-selector-parser/releases/tag/7.1.6)
and [advisory](https://github.com/advisories/GHSA-rj75-hqrm-r3gf).
The source-map fix rejects invalid, excessive and accumulated nested section
offsets; see the [upstream fix](https://github.com/7rulnik/source-map-js/commit/cf76580)
and [advisory](https://github.com/advisories/GHSA-68fv-2mgg-jv7q).

Frontend and website retain identical pnpm overrides. Website uses the shared
frontend lockfile and patch directory. Focused installed-dependency regressions
exercise Tailwind's selector parser and PostCSS's source-map consumer, including
hostile inputs and normal behavior; both surfaces retain the existing braces tests.
Use pnpm 10.30.3 and a frozen install, then run tests, lint and builds for both.

The [braces advisory](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm) still lists
no fixed upstream version. [Bug #294](https://github.com/khab40/lob-arena/issues/294)
delivered the local mitigation. Dependabot's version database cannot recognize
that patch as a new published release, so its braces updater/alert can remain
open after these two fixes merge. No ignore rule, alert dismissal or failing-check
suppression is introduced. The historical failed run remains a failure receipt;
new runs and alert state must be checked after merge. Older dependency PRs #297
and #298 have separate failures outside this latest-run repair.

No Transformer artifact, model workload, cloud resource or deployment is changed.
