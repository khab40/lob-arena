# Public execution evidence and secret scans

[Bug #341](https://github.com/khab40/lob-arena/issues/341) under
[Story #24](https://github.com/khab40/lob-arena/issues/24), Project #3.
The operator approved these four safeguards on 7 October 2026.

Exact execution files, signatures, proposal bytes and approval hashes remain
immutable in the approved local evidence store. Publish a separate **non-executable**
view with `scripts/public_job_evidence.py`; never use that view as launcher input.
The view exposes logical credential/file roles, explicit Job settings and the
SHA-256 of the original command bytes. The export receipt hashes the public bytes
separately. Unknown flags, unsafe command values and non-allowlisted metadata fail
before creating output. Existing files cannot be overwritten.

From the task checkout, use the local exact command file and a new public filename:

```sh
rtk proxy backend/.venv/bin/python scripts/public_job_evidence.py \
  --command /absolute/path/to/exact/create-argv.json \
  --output docs/evidence/new-public-command-view.json
```

Keep the exact file accessible to the approving operator. A checksum establishes
integrity; it does not replace review of the exact authorized operation. This
follow-up adds no replacement run approval or permission change.

## Local publication gate

Install ggshield 1.55.0 in `outputs/tools/ggshield-venv`, separately from the pinned
research operator environment. Authenticate with `ggshield auth login --lifetime 30`;
never paste the resulting token into code or chat. ggshield sends scanned text to
GitGuardian's API. The operator authorized staged/outgoing public code scanning;
private evidence and signing custody are outside that scope.

Install repository-scoped hooks from the reviewed task checkout:

```sh
rtk proxy backend/.venv/bin/python scripts/install_publication_hooks.py \
  --python /absolute/repository/outputs/tools/ggshield-venv/bin/python \
  --gitleaks /absolute/repository/outputs/tools/gitleaks-v8.24.3/gitleaks \
  --ggshield /absolute/repository/outputs/tools/ggshield-venv/bin/ggshield
```

The installer preserves foreign hooks and an existing `core.hooksPath` by refusing
replacement. It copies the reviewed runner into the common Git hooks directory,
so it works across retained worktrees and survives task branch retirement.

Pre-commit captures the index, excluding unstaged/untracked content. Pre-push uses
live advertisements from the exact push destination (including a separate push URL)
and captures every outgoing commit's changed postimages
and messages, including files added and removed between commits. It does not use
ggshield's default 50-commit pre-push limit. Multiple versions are concatenated at
their original paths for Gitleaks; Git ignore rules and attributes cannot alter
the captured index bytes. ggshield receives identical text under controlled `.txt`
names to avoid extension skips, option injection and response-file expansion.
The gate first refuses private/custody paths (including `.ssh` and private `.env.*`),
then scans a disposable snapshot with Gitleaks and ggshield, in that order. Neither
engine receives the working checkout. ggshield must report complete file coverage.
Scanner output is withheld to avoid exposing
secret values; missing tools/auth, nonzero results and timeouts block publication.

Binary, symlink/submodule, non-UTF8 or aggregated text over 900,000 bytes is refused
rather than silently skipped. Arrange a reviewed complete scan for such material;
do not bypass the hook. Gitleaks uses the existing narrow repository rules. ggshield
uses an explicit default-detector config, no local ignored matches or detector
exclusions, and removes environment overrides that weaken scanning. Individually
dismissed dashboard findings still follow GitGuardian's backend disposition.

Hooks supplement CI and GitGuardian's GitHub integration. Do not use `--no-verify`,
disable scanners, ignore all `docs/evidence`, or rewrite sealed evidence to avoid
alerts. Local Gitleaks rules and ggshield ignores do not dismiss dashboard incidents.

## Individual false positives

Incidents [37916297](https://dashboard.gitguardian.com/workspace/201515/incidents/37916297?occurrence=301233361)
and [37916298](https://dashboard.gitguardian.com/workspace/201515/incidents/37916298?occurrence=301233362)
refer to the public exact-command JSON in commit `17b3efc`. Static review found
MysteryBox resource/version references rather than credential payloads. The operator
confirmed both individual dismissals. No broad scanner exception was added.

Focused inert tests cover export rejection, original-byte preservation, snapshot
scope, all 61 outgoing commits, private paths and scanner failures. CI also runs
`check_publication_secret_gate.py` with verified Gitleaks: a planted inert credential
must stop before any external scanner invocation.
