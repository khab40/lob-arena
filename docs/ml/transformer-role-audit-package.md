# Bounded Transformer CPU role audit — 2026-10-02

Work: [Story #24](https://github.com/khab40/lob-arena/issues/24), Feature #16,
Epic #15, [Project #3](https://github.com/users/khab40/projects/3).
This implements the next package in the approved
[campaign plan](transformer-gpu-campaign-plan.md) after merged
[PR #272](https://github.com/khab40/lob-arena/pull/272).

As a validation engineer,
I want exact validation coverage and class support checked in a bounded CPU Job,
So that unsupported or misaligned targets cannot enter GPU training.

Actor: validation engineer. Goal: independently verifiable role-audit artifacts.
Value: preserve the declared selection, calibration and operating-point roles.
Acceptance: [Gherkin scenarios](transformer-role-audit-package.feature).
Out of scope: fitting, scoring, training, role reassignment, new permissions,
final-test access, G8/G9 work, submission and promotion.
Verification: local inert tests, real SDK Stubber tests, authenticated retained
metadata inspection and CI image import checks. Actual rows run only in the
separately authorized Nebius Job.

## Package behavior

The worker authenticates the frozen 220,125-byte evidence bundle and separate
4,663-byte source-separation receipt. It uses the unchanged 185-object inventory,
train-only normalizer and source roles: NVDA selection 1,250 targets, MSFT
calibration 5,490 and AAPL operating points 2,470. It does not refit normalization.

The existing adapter verifies C4 inputs. The worker then records each validation
target's run, identity and binary label in a restricted canonical JSONL ledger.
Independent readback verifies exact per-run counts, ordered identity hashes,
complete run order, no duplicate targets and per-role class-count arithmetic.
Labels remain trusted to the checksum-bound worker adapter; this is not an
independent relabeling of ground truth. Source/label separation retains the
[producer-contract limitations](transformer-source-separation.md).

Fewer than 20 positives or 20 negatives in any role produces a retained negative
audit result. Publication success means the audit completed; it does not mean
class support passed or GPU execution is authorized. Roles never change based
on observed support.

The new attempt identity is `transformer-role-audit-c4-20261002-r1`. Its request
binds campaign, source commit, image digest, inventory/bundle/source/normalizer/
role hashes, public signing key, nonce, secret version selectors and resources.
The automatic publisher verifies the actual Job's complete configuration before
signing its identity. It checks version-specific intent freshness and rechecks
the provider Job immediately before delivery. Ordinary provider defaults are
normalized explicitly; unrecognized fields fail closed.

Eight versioned artifacts are published: configuration, frozen normalizer,
input contract, source receipt, role aggregate, restricted ledger, measurements
and execution lineage. Conditional writes prevent overwrite; checksums bind
every version, and SUCCESS is last. Independent readback requires the SUCCESS
hash from provider logs and recomputes the ledger aggregates. Uncertain writes
require readback; they never trigger an automatic replacement or a later FAILED
marker. Failed processing retains a bounded failure record without raw SDK errors.

## Bounds and operational prerequisite

One `cpu-e2 / 4vcpu-16gb` Job; zero GPUs, 100 GiB ephemeral disk, provider timeout
3,600 seconds, restart never, non-preemptible, concurrency one, no volume mounts
or public endpoint. The worker caps its audit phase at 2,940 seconds from its
measurement origin, leaving 600 seconds before its 3,540-second outer deadline.
The provider timeout covers remaining startup and teardown. Nested phase
timeouts cannot extend their parent deadline.

Input transfer is exactly 185 version-specific GETs without retries: 30,034,660
declared bytes, largest object 348,308 bytes. Bounds are 2 MiB/object and 64 MiB
aggregate, tighter than the campaign's 8 GiB cache ceiling. Worker context polls
are separately capped at 60 GETs / five minutes. The publisher polls at most
120 times / ten minutes (provider reads, intent GET and bounded HEAD checks);
independent publication collection uses 12 GETs / five minutes. These operations
must be counted separately in the exact execution proposal.

Results are at most eight artifacts / 8 MiB, including a 64 KiB publication
reserve; the ledger is at most 9,210 records / 2 MiB. Costs remain unknown under
the existing operator-managed policy. Failed, timeout and ambiguous attempts
consume their slot; a replacement requires fresh authorization.

**This PR does not authorize or submit the Job.** The original campaign requires
MLflow/platform readiness before execution: private connectivity, actual client/
server versions, least-privilege writer, artifact round trip/readback and the
parent/child run journal. Reconcile [#19](https://github.com/khab40/lob-arena/issues/19)
through [#21](https://github.com/khab40/lob-arena/issues/21); application grants
retain their separate proposal/approval. A staged S3-only audit would require
an explicit change to the approved prerequisite ordering.

## Sealing and next execution step

CI builds only the `runtime` stage of
`serverless/transformer_role_audit/Dockerfile`; it verifies pinned dependencies,
imports, inventory and public source receipt without restricted audit material.
The `sealed` stage requires the exact retained bundle through BuildKit's
`role_bundle` file input, verifies its hash/contents and copies it into the
private image. The bundle is larger than Nebius's 64 KiB injected-file limit;
only the small execution request is injected at Job creation.

Before execution, build from a clean archive of the reviewed source commit,
seal the bundle, record the registry digest and verify source-to-image evidence.
`SOURCE_COMMIT` alone is a build assertion, not proof of source bytes. Check the
actual orchestrator interpreter and SDK before credentials or access changes.
Use fresh Nebius MCP catalog/help and provider admission/readback to verify
platform, subnet, secrets, no mounts and the exact request shape. MCP help was
checked on October 2; no deployment, credential retrieval or Job occurred.

Finish readiness, then present one immutable request with exact image, code,
signed-context custody, resource/I/O limits and output-prefix access for approval.
Arm the publisher and verify its receipt and live process before a single create.
Resolve ambiguous creation by provider readback. After execution, independently
verify the full package and worker/disk release, then reconcile MLflow and #24.
The later GPU smoke/search/calibration packages remain separately authorized.
