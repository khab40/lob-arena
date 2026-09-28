# Transformer campaign readiness — 2026-09-28

The operator approved [PR #241's plan](transformer-gpu-campaign-plan.md) with
“follow the plan”. This implements its first configuration/role-audit increment
under [Story #24](https://github.com/khab40/lob-arena/issues/24), Feature #16 →
Epic #15, [Project #3](https://github.com/users/khab40/projects/3).

As a validation engineer,
I want immutable campaign settings and audited development roles,
So that training cannot proceed on unsupported or overlapping evidence.

Actor: validation engineer. Goal/value: enforce the approved campaign boundary.
Acceptance: [readiness scenarios](transformer-campaign-readiness.feature).
Out of scope: model implementation/execution, new permission grants, MLflow
upgrade, final access and source-data resplitting.
Verification: mutation tests, inert row fixtures, checksum-bound metadata inspection
locally; real class-support/causal payload audit in a separately packaged CPU Job.

## Implemented

- [Resolved campaign JSON](../../configs/experiments/transformer/c4-campaign-20260928.json)
  binds the fixed grid, seeds, checkpoint/calibration policy, lineage and ten Job
  slots. Canonical digest `e7601f6e265f583eaffdaca3e2e23ca6cff53dbd0a73ccc9fdcc13ed1d744e86`.
  Its loader rejects changed policy even with a freshly recomputed file checksum.
  The receipt also records the separate checksum of the formatted JSON file;
  supply that file-byte checksum to the loader, not the canonical protocol digest.
- Metadata preparation checks the three externally pinned C4 manifest hashes,
  exact source sessions, fold counts and sequence/target identities. All variants
  of one base source stay together. Canonical source-identity hashes determine
  role order; labels and scores do not participate.
- CPU audit entrypoint verifies the original development adapter and frozen
  normalizer, retains exact validation target IDs/digests and class counts, and
  rejects missing/extra/duplicate targets. Insufficient support exits unsuccessfully.
  No model, optimizer, training or scoring import is introduced.

## Metadata result, not a completed runtime audit

The [receipt](../evidence/transformer-campaign-readiness-20260928.json) records
inspection of the retained development manifests only: zero row payload reads,
zero Jobs, zero model runs. The assignment is:

| Role | Base session | Targets | Replay shards |
| --- | --- | ---: | ---: |
| Selection | 2019-10-30 NVDA | 1,250 | 10 |
| Calibration | 2019-10-30 MSFT | 5,490 | 10 |
| Operating points | 2019-10-30 AAPL | 2,470 | 10 |

Reproduce the metadata artifact with the tracked, read-only inspection entrypoint:

```sh
python -m app.ml.transformer.role_manifest INPUT_DIRECTORY NEW_OUTPUT_FILE
```

`INPUT_DIRECTORY/manifests/` contains the frozen root, tabular and sequence JSON
files from the r2 inventory. The command verifies their exact pinned hashes and
creates the output exclusively; its digest must match the retained receipt.

This separates source symbols, not dates. One date, one symbol per role, unequal
support and prior development exposure limit quality claims. Class support is
not inferred from metadata. Source-observation/label-horizon separation still
needs a receipt connecting the symbol-local C3 provenance to these exact groups.
The role audit therefore always reports `gpu_ready: false`; it is a prerequisite
artifact, not an authorization service. A future execution gate must bind that
provenance receipt, platform readiness and exact approved Job package as well.

The CPU audit command is intended for the reviewed Job image, not local model work:

```sh
python -m app.ml.transformer.role_audit INPUT_DIRECTORY NORMALIZATION_JSON NEW_OUTPUT_DIRECTORY
```

Its output includes governed row IDs and belongs in restricted evidence storage.
The CLI is not a cloud submission wrapper: automatic signed context, bounded S3
transport and provider-log-anchored publication must be packaged before execution.
No Job has been authorized merely by adding this command.

## Platform and next gate

Fresh Nebius MCP readback confirms the existing MLflow VM is STOPPED. GitHub
#19 was reopened by the operator at 14:34:28 UTC; its unfinished application
recovery/registration criteria are again tracked as open. Existing metadata
restore evidence is preserved and does not prove those remaining criteria.

Bootstrap inspection shows only three existing experiments and the LightGBM
registry namespace. The [specific permission/readiness proposal](../evidence/transformer-mlflow-readiness-proposal-20260928.json)
names the two Transformer resources and four additive application grants; no
grant, restart, namespace creation or live deployment change has been performed.
MLflow's [authentication reference](https://mlflow.org/docs/latest/self-hosting/security/basic-http-auth/)
documents resource-scoped EDIT/READ and the 3.13+ RBAC API. Verify the deployed
client/server API before applying; do not use removed legacy permission calls.

Next: review this increment, complete source-provenance binding and exact CPU
audit packaging, and obtain the proposed application-permission authorization.
Keep GPU execution blocked until those receipts verify. #20/#21 infrastructure
and observability acceptance remain separate dependencies; G8/G9 stay closed.
