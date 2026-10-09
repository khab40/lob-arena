# First frozen Transformer holdout recovery — 7 October 2026

Historical plan/execution record; reconciled 8 October 2026. This recovery was later exactly approved and completed; its approval is consumed.
[Current status](../roadmap/CURRENT_STATUS.md) owns remaining acceptance.
[ARD-0042](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md) owns research ordering;
pending instructions below do not authorize another run or reuse consumed approval.

Tracking: [Bug #339](https://github.com/khab40/lob-arena/issues/339) under
[Transformer #24](https://github.com/khab40/lob-arena/issues/24),
[settings #314](https://github.com/khab40/lob-arena/issues/314),
[Project #3](https://github.com/users/khab40/projects/3), [PR #340](https://github.com/khab40/lob-arena/pull/340).

As a validation engineer,
I want the unused first holdout Job submitted and supervised in one process,
So that the frozen comparison can run once without a dispatch gap.

The original observer attempt expired before creation. No creation intent,
signed context, GPU Job or December payload read occurred. All 23 observations
were absent; fresh MCP reconciliation returned NotFound. Keep that proposal,
approval and attempt history in `outputs/transformer-holdout-run-package-20261006/`.
Do not restart it or copy its approval into this recovery directory.

Both original policies were independently restored on 7 October:
final version **12 / 2 rules**, results version **13 / 9 rules**, exact full-rule
equality. Removal completed at 01:09:08 and 01:09:18 UTC, after the approved
three-hour window ended at 20:53:33 UTC on 6 October. **The access overrun is
recorded; this was not a compliant access window.** No execution used that access.

The [corrected exact proposal](../evidence/transformer-holdout-first-run-recovery-proposal-20261007.json)
SHA-256 is `332437336b900c690fa765d1f0e9fe410bf993345eeeaea6fe4aead468eda13d`.
It requires fresh exact recovery approval. It reuses the existing held
**$6.25 excluding VAT** reservation; no additional cap or replacement is proposed.

```gherkin
Feature: Same-input first holdout recovery
  Scenario: Submit the unused first Job
    Given the exact recovery proposal is approved and its temporary policies verified
    And no attempt receipt or Job exists
    When coordinated supervision verifies Job absence
    Then one durable creation intent precedes one submission in that same process
    And exact live identity and specification precede one signed context delivery

  Scenario: Preserve an uncertain outcome
    Given submission times out or its response is uncertain
    When supervision reconciles the approved Job name
    Then creation is not retried
    And existing ownership and cancellation bounds remain enforced

  Scenario: Restore permissions before reporting
    Given the evaluation is verified or the attempt aborts
    When bounded collection and verification stop
    Then the operator restores both original policies and independent readback confirms it
    And report writing or a research decision does not delay removal
```

The [frozen protocol](transformer-holdout-protocol-20261005.md) is unchanged:
width 128, rate 0.0003, seed 42, epoch 4; checkpoint, normalization, calibration
and thresholds remain fixed. All **252 version-pinned inputs**, request
`fbf88f60fbfcf7f41f38a33ec6483b7aa03138ca28c337d8957892431b3fee66`,
provider spec, nonce, signing public identity and policy bytes are preserved.
Only the two local injection paths and two reviewed operator source hashes changed.

Image remains `cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/tr@sha256:f381263db4095fdb1fec24da505339195033f66e9c26cb98c3d13584a6ae402e`.
Repository length is 47; execution source is
`fe5eaaa931791d3c3e809a1d0c2ff8a6811dc508`; numerical/training source remains
`87ce8a933c40fe825569e3de6a8699b519808c34`. No rebuild or mutable tag.
Operator source is `8cde2d17e8651f77f870bbe2193d5bb7222d0444`; all 236 source pins match.
The fresh [provider dry-run](../evidence/transformer-holdout-recovery-dry-run-20261007.json)
succeeded without creation. The copied `provider-dry-run.json` is historical
6 October evidence; `fresh-provider-dry-run.json` validates the corrected argv.
Pinned SDK/Python and actual local CLI-help preflight passed without credentials.

Bounds: one on-demand L40S / 8 vCPU / 32 GiB, disk 100 GiB, shared memory 1 GiB,
restart never, one attempt, runtime 3,600 seconds, create-to-terminal 7,200 seconds,
temporary access 10,800 seconds. Input/output limits are 16/2 GiB, IO limit 10,000.
Cancellation starts at 7,080 seconds. Admission/creation/observation/access reserves
remain **120/90/30/300 seconds**. Transient reads use 30/60/90/120-second attempts
within remaining budgets; creation and context delivery never retry.
The retained 6 October pricing estimate is $1.5484/hour compute plus
$0.0097222/hour disk, about $3.12 for two hours; actual billing is unreconciled.

Execution directory: root `outputs/transformer-holdout-first-run-recovery-20261007/`.
The private key is retained there at mode 0600, using the existing signing identity.
No credential, signature or old attempt/approval receipt is included in public docs.

After exact approval, retain its reply and exact-hash `operator-approval.json`.
Complete the pinned offline preflight again before grants. Fresh MCP readbacks
must still match both original policies and versions 12/13; if they differ, stop
and reconcile rather than overwrite concurrent changes. Operator handoffs apply
the byte-pinned temporary files; independently verify final13/results14 and exact
rules before custody/context delivery. Policy updates remain operator-only.

Run the single coordinated command from the repository root after those gates:

```sh
rtk proxy outputs/transformer-comparison-20261004/operator-venv/bin/python .worktrees/transformer-input-contract/scripts/watch_transformer_holdout.py --output outputs/transformer-holdout-first-run-recovery-20261007 --proposal-sha256 332437336b900c690fa765d1f0e9fe410bf993345eeeaea6fe4aead468eda13d --submit
```

The [fully resolved creation argv](../evidence/transformer-holdout-recovery-create-argv-20261007.json)
is invoked by that process exactly once, after a durable intent. Never dispatch
creation separately. The exact command is shown for authorization review:

```sh
rtk proxy nebius ai job create --parent-id project-e00g6zvxpr00waz8t3y51k --name transformer-holdout-c4-20261006-r1 --image cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/tr@sha256:f381263db4095fdb1fec24da505339195033f66e9c26cb98c3d13584a6ae402e --platform gpu-l40s-a --preset 1gpu-8vcpu-32gb --disk-size 100Gi --shm-size 1Gi --subnet-id vpcsubnet-e00ppzc4353dxv210j --timeout 1h --restart-policy never --on-demand --env-secret AWS_ACCESS_KEY_ID=mbsec-e00arhndyprqr8egjw@mbsecver-e00rjzerny1pf9qhna --env-secret AWS_SECRET_ACCESS_KEY=mbsec-e00s7qtjj5n9ghacnh@mbsecver-e00yfn5w54jc1ybkwv --inject-file /Users/akhabalov-da_1/Documents/STUDY/nebius-ai-performance-engineering/code/ai-market-abuse-detection-arena/outputs/transformer-holdout-first-run-recovery-20261007/request.json.gz:/opt/research/holdout-request.json.gz --inject-file /Users/akhabalov-da_1/Documents/STUDY/nebius-ai-performance-engineering/code/ai-market-abuse-detection-arena/outputs/transformer-holdout-first-run-recovery-20261007/approval-preview.json:/opt/research/holdout-approval.json --async --format json --no-browser --retries 1
```

CUDA must reproduce the saved 64-row development reference
before any December GET. Then frozen inference evaluates **15,160 targets**
(135 positives), pairs original saved G8 predictions without LightGBM rescoring,
and publishes checksummed/versioned results durably.

Observe terminal state and independently verify exact publication receipts with
`holdout_readback.verify_result`; retain artifacts in root outputs. On uncertainty
or failure, reconcile/cancel the owned Job within its budget and restore grants.
After bounded collection/verification or abort, restore original policies
immediately using freshly checked resource versions. Complete the Markdown
report, plots, resource/cost disposition and continue/stop/inconclusive decision
offline after verified removal. No fitting, reselection, G8 rerun, promotion,
extra replacement, merge or deletion is included.

December is unseen by this fixed Transformer but already reported by LightGBM G8.
Three base sessions on one date with research controls and synthetic attack labels
limit quality claims. Complete verified research and the operator decision before
#90/#91 demo implementation; MLflow/platform reconciliation follows.
