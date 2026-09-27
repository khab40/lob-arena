# Portable G9 audit evidence

Fix: [Bug #232](https://github.com/khab40/lob-arena/issues/232), child of
[story #23](https://github.com/khab40/lob-arena/issues/23), in
[PR #231](https://github.com/khab40/lob-arena/pull/231).

As a validation engineer, I want the exact audit source and detailed metadata
available in a clean checkout, so that I can inspect the G9 evidence without
operator-local files or cloud credentials.

The original files were retained in the operator's project-root `outputs/`,
outside the disposable worktree. They were absent from remote review checkouts
because `outputs/` is ignored. This additive archive repairs that visibility gap;
it does not change the approved proposal, signed decision or frozen results.

## Inspect from any checkout

```bash
python3 scripts/verify_g9_audit_archive.py
python3 scripts/test_g9_audit_archive.py
python3 -m zipfile -l docs/evidence/g9-audit-20260927/metadata.zip
```

[archive.json](archive.json) lists every original source path, member size and
SHA-256, plus the archive hash and exact governed S3 result URI. The eight JSON
members in [metadata.zip](metadata.zip) retain original bytes: audit receipt,
176-object S3 readback receipt, frozen candidate inventory, final report, bundle,
training manifest, calibration manifest and scoring resource receipt.
Each object receipt includes path, SHA-256, size and version ID. Append its path
to the result URI for the exact object location.

[assemble.py.txt](assemble.py.txt) is the unchanged historical source, with the
SHA-256 already bound by the approved audit receipt. It is provided for inspection,
not execution in this directory: it expects the original root `outputs/` layout
and writes the unsigned proposal. Do not run it against the signed working tree.

The verifier checks the archive members against the original source anchors,
not just the new archive manifest; matches all 13 bundle references and seven
development artifact identities; compares feature order, preprocessing and
metrics; and totals 176 object identities / 24,463,251 recorded bytes.
It reads JSON metadata only and does not execute the historical assembler.
Full payload bytes remain in the operator evidence store and governed S3;
this portable check does **not** repeat the 176-object payload rehash or establish
current remote availability. No raw rows, model weights or signing private key
are included. Signature verification remains documented in the
[closure record](../../operations/g8/g9-closure-20260927.md).

## Acceptance and review

```gherkin
Feature: Portable G9 audit evidence
  Scenario: Review without privileged data access
    Given a clean checkout without outputs or cloud credentials
    When the portable verifier runs
    Then original source and metadata match the existing approved hash anchors
    And it reports object identities without claiming a fresh payload rehash

  Scenario: Reject rewritten evidence
    Given a changed object receipt and recomputed archive manifest
    When the portable verifier runs
    Then the existing S3 receipt anchor rejects the replacement
```

Four inert tests cover clean-checkout operation, changed source, corrupted archive
and a rewritten receipt even when the archive manifest is also recomputed.

The other P1, [360-line commit](https://github.com/khab40/lob-arena/pull/231#discussion_r4116259783),
is a false positive. Git and GitHub's commit API agree: `092bab3` has parent
`ac9f184` and 170 insertions + 5 deletions (175 changed lines). Its parent has 185
changed lines. The review counted the cumulative 360-line PR diff as one commit.
No history rewrite or squash occurred; preserve these separate commits at merge.

Verification scope: artifact inspection and inert tests only; no model/cloud work.
The signed G9 decision and both approved document hashes remain unchanged.
