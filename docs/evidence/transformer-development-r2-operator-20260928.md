# Preserved r2 orchestration helper

For [Bug #240](https://github.com/khab40/lob-arena/issues/240), under Story #24.
The [Python source](transformer-development-r2-operator-20260928.py) is the exact
127-line helper used for the approved r2 operation. Its SHA-256 is
`d9b236ce1288def87425e80222f7f71f063d0f9e66425c8b557996f377bafefb`, matching the
unchanged [approved proposal](transformer-development-replacement-r2-20260928.json).
It contains credential selectors, not credential values. The private context
key is excluded; it remains in the operator-controlled original evidence directory.

This is an evidence archive, not a request to execute r2 again. Its historical
layout resolves the repository root from
`outputs/transformer-development-r2-20260928/cloud/verification_operator.py` and
imports source from `.worktrees/transformer-input-contract/backend` at the proposal's
`request.source_commit`. Restore those paths before using the helper in a fresh
workspace. Reconstruct `request.json` from the proposal's `request` object using
sorted keys and compact JSON separators, without a trailing newline; verify its
recorded checksum. Readback requires existing authorized development credentials,
but not the private context key. `arm` requires that private key and a new reviewed
execution authorization; r2's existing Job/output must never be submitted again.

The dedicated regression test validates the archived byte hash and rejects
changed bytes using the same checksum guard. Review does not execute the helper.
