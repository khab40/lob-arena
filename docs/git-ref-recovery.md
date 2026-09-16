# Recover copied Git refs

File-copy or sync conflicts can leave loose refs such as
`refs/heads/main 2`. Spaces make these invalid Git ref names and can block
`git fetch`. The filename alone does not identify the creating process.

Pause any known synchronization or copy operation before repair. From a checkout,
run:

```sh
python3 scripts/repair_duplicate_git_refs.py
python3 scripts/repair_duplicate_git_refs.py --apply
git fetch origin
```

The default is inspection only. Apply accepts only invalid loose refs ending in
an integer copy suffix beginning with 2–9 and containing an existing commit hash.
It preflights all candidates, preserves each commit under
`refs/recovery/copied-refs/<hash>`, saves the original bytes below the common Git
directory's `ref-copy-backups/refs/`, and removes the invalid loose file.
Recovery refs keep commits reachable during garbage collection. Existing valid
branches are not changed, even when their hashes differ from copied refs.
Conflicting backups or recovery refs stop the repair. Unsupported invalid refs
require manual inspection. Repeating a successful repair is a no-op.

The utility also works from linked worktrees through `--git-common-dir`.
Do not run it concurrently with tools modifying these files. It does not repair
packed refs, index copies, or duplicate working-tree documents. Review those
separately; a suffix is not proof that a file is disposable. Investigate the
copying process and exclude active Git metadata from file synchronization where
appropriate.

## September 15, 2026 incident

Three invalid refs were found: `refs/heads/main 2`,
`refs/remotes/origin/main 2`, and
`refs/heads/feat/g8-native-rehearsal-20260915 2`. They contained two distinct
commit hashes, different from their corresponding valid refs. Preserve both
commits rather than assuming the copies are redundant. The local metadata repair
cannot be delivered by merging a PR; this utility makes the procedure reviewable
and repeatable for affected checkouts.
