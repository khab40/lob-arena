# Transformer input verification: replacement r2 — 2026-09-28

For [Story #24](https://github.com/khab40/lob-arena/issues/24) and
[Bug #238](https://github.com/khab40/lob-arena/issues/238), Feature #16 / Epic #15,
in [Project #3](https://github.com/users/khab40/projects/3).

**Prepared for one-run authorization; no replacement Job submitted.**
The operator reviewed the repair in merged [PR #237](https://github.com/khab40/lob-arena/pull/237).
This package uses that repair and a fresh run identity. The prior one-run approval
was consumed by [r1](../evidence/transformer-development-attempt-20260928-r1.json).
Its evidence and output prefix remain intact.

## Need, scope and acceptance

As a validation engineer,
I want the reviewed input verifier to complete with timely signed Job context,
So that GPU training can start from independently verified development inputs.

Actor: validation engineer. Goal: complete input verification after the startup
handoff repair. Value: validate preprocessing before spending on GPU training.
Acceptance: the existing [Gherkin scenarios](transformer-development-verification.feature),
including automatic context delivery and stale/terminal rejection. Verification:
100 inert focused tests, CI, one bounded Nebius CPU Job and independent artifact
readback. Out of scope: neural-network training/scoring, final-test access,
G8/G9 reopening, MLflow registration, new permissions, merge and deletion.

## Exact package

The [machine-readable proposal](../evidence/transformer-development-replacement-r2-20260928.json)
binds source `6c457d0040c99591fd01bbe15ead5cdb98c4692f`, image digest,
request, input inventory, resource limits and operational-helper checksum.

- Run: `transformer-input-c4-development-20260928-r2`.
- One additional CPU Job: 4 vCPU / 16 GiB, 100 GiB ephemeral disk,
  one-hour provider timeout, restart never. No GPU.
- Inputs: unchanged 185 development object versions / 30,034,660 bytes;
  expected 33,450 training and 9,210 validation rows. No local row processing.
- Three fresh processes at batch sizes 16/64/256, at most 600 seconds each.
  Preserve train-only normalization, exact row identities and logical-output parity.
- Result prefix: the existing research development namespace ending in the new
  r2 run ID, at most 12 objects / 8 MiB. Conditional writes; SUCCESS last.
- Existing operator-managed cost policy applies. Actual monetary cost is unknown;
  finite resources, Job count and deadlines bound this attempt. No billing query.

Build/import checks, registry digest readback, live metadata for all 185 inputs,
existing credential/bucket-policy checks, publisher CLI absence handling and exact
provider dry-run all passed. The run name and output prefix are absent. These are
preflight observations, not runtime acceptance; refresh them before launch.

## Startup sequence after approval and green CI

1. Verify the exact request and operational-helper hashes against the proposal.
   The helper lives in root `outputs/transformer-development-r2-20260928/cloud/`.
   Existing pinned development credentials are resolved into process memory;
   neither their values nor the private context key may enter logs or Git.
2. Start the helper's `arm` action as a persistent local orchestration process.
   It calls the reviewed `verification_publisher` module, checks output/Job absence,
   writes a ready receipt, and waits at most 600 seconds / 120 polling attempts.
   It cannot create Jobs. Its ephemeral signature binds runtime context; it is
   not an operator-identity signature or the G9 signing key.
3. Before create, verify the ready receipt matches the request, is younger than
   60 seconds, and the publisher process is still live. If not, do not create.
   Resolve tool execution permissions before this point. No interactive operation
   is needed for context delivery once the Job is submitted.
4. Submit the exact request once through Nebius MCP. The publisher independently
   reads the provider Job, checks its name/project/image/resources and matching
   INTENT, then conditionally writes signed context. It refuses terminal Jobs,
   terminal markers and INTENT age of 240 seconds or more. The Job's existing
   300-second context gate is unchanged.
5. Resolve an ambiguous create by exact name/ID readback; never retry creation
   blindly. Failure consumes this one-run authorization and requires review
   before another Job. Preserve the prefix and available diagnostics.
6. On success, independently read the six versioned result artifacts, verify
   their checksums and complete preprocessing lineage, and pin SUCCESS to the
   provider Job log. Record terminal state and worker release in this same PR.

Next after verified success: propose the smallest GPU Transformer experiment,
training/checkpoint selection, calibration and MLflow artifact logging. This CPU
attempt produces preprocessing evidence, not a trained model or qualification.
