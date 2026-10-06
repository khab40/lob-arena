# Sealed Transformer holdout execution packaging

Date: 2026-10-05; source-provenance correction verified 2026-10-06.
Status: image/startup packaging implemented; exact inventory,
provider dry-run and execution authorization pending.
[Story #24](https://github.com/khab40/lob-arena/issues/24),
[settings Story #314](https://github.com/khab40/lob-arena/issues/314),
[Project #3](https://github.com/users/khab40/projects/3).

As a validation engineer,
I want the fixed candidate packaged with verified runtime and startup bindings,
So that later-date inference preserves the selected model and rejects unapproved access.

Actor: validation engineer. Goal: prepare a reviewable, sealed inference runtime.
Value: fixed-candidate research with reference parity before final reads.
Out of scope: fitting, G8 rerun, local detector execution, new permissions,
Job submission, production promotion, online MLflow, merge and deletion.
Verification: inert tests, static image inspection and retained metadata hashes;
CUDA reference parity and final inference require a separately authorized Job.

## Delivered

PR #321's consumer and measurement correction are merged. This chunk adds
`holdout_runtime`, `holdout_entrypoint`, `holdout_delivery`, the sealed Dockerfile
and `scripts/transformer_holdout_image.py`. The [evidence receipt](../evidence/transformer-holdout-packaging-20261005.json)
records source/image identity and the remaining admission gaps.

The image inherits the verified comparison image `56ccf4ee…6d460`; no packages
are installed or upgraded. Its runtime lock verifies all 48 installed distributions
and 13 pinned numerical source files. Only explicit holdout/settings modules are
overlaid. The 134,645-byte portable package remains hash-identical and contains
metadata, not weights. The original checkpoint is a separately pinned input.
Source commit `fe5eaaa931791d3c3e809a1d0c2ff8a6811dc508` identifies the corrected built
code; later documentation/CI commits do not change the sealed image contents.
The receipt's local Docker image ID is **not** a published registry digest.

The builder rejects an image repository longer than 64 characters, a mutable
base, changed portable package, numerical-file overlay or an existing output
directory. The request uses deterministic gzip, bounded to 64 KiB compressed
and 256 KiB expanded, with canonical JSON required after decoding.

[P1 Bug #325](https://github.com/khab40/lob-arena/issues/325) fixes false source
attribution. Preparation requires `--source-commit` to match a clean tracked Git
checkout and compares every captured repository file with its immutable commit
blob before creating output. Staged/unstaged changes, a wrong commit or raced
file capture fail. The source file is generated from that verified commit;
Docker no longer accepts a free-form `SOURCE_COMMIT` build argument.
The image verifies all 20 copied context files, sizes and hashes against its
manifest, including source identity, overlay, Dockerfile and portable package.
The earlier local image remains preserved as superseded evidence.

## Startup and context delivery

Inject two read-only files: `/opt/research/holdout-request.json.gz` and
`/opt/research/holdout-approval.json`. The latter contains the externally approved
request SHA-256 and trusted public key. It must come from the operator's exact
approval, not a script treating request-derived values as authorization.
Separating file contents from ordinary provider-path observations avoids a
self-referential request/provider hash. No secret-view GET is needed.

Before constructing an S3 client, startup checks approval, signing key, source,
portable package and numerical/dependency inventory. The attester's pure
`context_for_job` validates ordinary provider identity, immutable image, resources,
credential version selectors, injected paths, restart policy and private access
against the externally approved request/provider hash before custody signing.
Public endpoints, extra replicas, terminal Jobs and unreviewed fields fail closed.

`deliver_context` verifies the signed envelope before one conditional PUT to a
nonce-scoped control key outside the immutable result prefix. It verifies the
returned object version, bytes and checksum metadata. An uncertain PUT requires
reconciliation; it is never automatically retried. This helper does not create
Jobs, issue credentials, grant permissions or generate a signing key.

Startup polls for context for at most 600 seconds, verifies its canonical bytes
and signature, then passes the same read/request/deadline budget to the worker.
Missing context produces sanitized durable provider logs without claiming results.
The worker still requires development-reference parity before any final payload
read, then pairs final rows with original G8 predictions and publishes SUCCESS last.

## Evidence and remaining admission work

403 inert regressions pass without skips, including 60 new packaging cases.
The rebuilt image passed static imports with networking disabled and a read-only
filesystem; Torch was not imported. These checks do not prove CUDA parity.
Initial backend CI exposed optional-dependency collection errors in the new tests.
[Bug #324](https://github.com/khab40/lob-arena/issues/324) removes the metadata
fixture's ML dependencies and guards the two optional-ML modules. The base
installation now passes all 33 metadata/image cases with two module skips; the full
ML installation exercises all packaging cases without skips. The collection-only
repair preserved its image; the separate P1 correction rebuilds the image with verified source bindings.
The original G9 metadata archive's checksum and two restored records authenticate
the saved G8 prediction key, version, size and checksum. No final payload was
read, and historical receipts do not prove current remote availability.

Next, authenticate final manifests and every shard, retain a deterministic bounded
development-reference artifact, resolve exact credential selectors/access and
removal, publish the digest image and complete the exact Nebius dry-run and scoped
estimate. Only then request fresh combined final-access/run/spend approval.
The proposed one-hour L40S / $6.25 additional excluding-VAT cap is unapproved.
No cloud Job, final payload read or new permission occurred in this chunk.

```gherkin
Feature: Sealed fixed-candidate holdout startup
  Scenario: Preserve the trained runtime
    Given a verified digest image and pinned numerical source and dependencies
    When a numerical file or installed dependency differs
    Then startup rejects the package before constructing credentials or a consumer

  Scenario: Reject mismatched provider context
    Given an externally approved request and trusted signing key
    When observed Job resources, credential versions or injected paths differ
    Then no execution context is accepted for that Job

  Scenario: Reject mislabelled build source
    Given a declared Git commit for the holdout code
    When the checkout is dirty or belongs to a different commit
    Then no build context is created

  Scenario: Preserve an uncertain context publication
    Given a verified signed context and an unused nonce-scoped control key
    When its conditional publication has an uncertain outcome
    Then the attempt requires reconciliation and no mutation retry occurs
```

See the [consumer](transformer-holdout-consumer.md),
[fixed December protocol](transformer-holdout-protocol-20261005.md) and
[week plan](transformer-week-plan-20261004.md). G8/G9 remain closed.
