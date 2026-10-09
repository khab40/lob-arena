# Exact frozen Transformer holdout — 6 October 2026

Historical plan/execution record; reconciled 8 October 2026. The initial observer attempt created no Job; the separately approved same-input recovery completed.
[Current status](../roadmap/CURRENT_STATUS.md) owns remaining acceptance.
[ARD-0042](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md) owns research ordering;
pending instructions below do not authorize another run or reuse consumed approval.

> Historical execution package: approved, then aborted before Job creation.
> Both original policies were independently restored on 7 October at
> final12/results13; late removal is disclosed. Do not execute the instructions
> below or restart the original evidence directory. Use the separate
> [corrected recovery runbook](transformer-holdout-first-run-recovery-20261007.md),
> which requires fresh exact approval. The remaining text is the original snapshot.

Tracking: [Transformer #24](https://github.com/khab40/lob-arena/issues/24),
[settings #314](https://github.com/khab40/lob-arena/issues/314),
[Project #3](https://github.com/users/khab40/projects/3).
Fixes: [#332](https://github.com/khab40/lob-arena/issues/332),
[#333](https://github.com/khab40/lob-arena/issues/333),
[#334](https://github.com/khab40/lob-arena/issues/334),
[#335](https://github.com/khab40/lob-arena/issues/335),
[#336](https://github.com/khab40/lob-arena/issues/336).

As a validation engineer,
I want the frozen Transformer evaluated once on the prepared December population,
So that I can compare it with original saved LightGBM results without reselection.

```gherkin
Feature: One authorized fixed-candidate holdout
  Scenario: Gate December access on saved-reference parity
    Given the exactly authorized request and a matching observed GPU Job
    When CUDA inference reproduces the 64 saved development logits within tolerance
    Then the 15,160 December targets are evaluated with frozen settings
    And original saved LightGBM predictions are paired without rescoring

  Scenario: Abort a mismatched or overdue execution
    Given a provider observation, source or parity mismatch
    When the admission or execution gate checks it
    Then no replacement attempt is submitted
    And the owned live Job is cancelled once when applicable
    And temporary permissions are removed and independently checked
```

The [exact proposal](../evidence/transformer-holdout-run-proposal-20261006.json)
SHA-256 is `6e2a6ca69137e0a1ac427accdfe01c997311c82e6e816ce5457de3ce0d09ee2a`.
It remains **awaiting exact operator authorization**. Its public request, provider
specification, exact policies, original policies and publication receipts are retained
alongside it. The private context key remains only in root `outputs/` with mode 0600.

Published image: immutable index `sha256:f381263db4095fdb1fec24da505339195033f66e9c26cb98c3d13584a6ae402e`,
repository `cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/tr` (47 characters).
Source is `fe5eaaa931791d3c3e809a1d0c2ff8a6811dc508`; the 13 numerical files,
48 dependencies and original checkpoint remain unchanged. The fixed 64-row reference
is published at version `1`; conditional PUT and checksum/byte readback succeeded.

The 252-input request binds 185 development objects, 62 final manifest/shard keys,
one original G8 prediction object, three saved model inputs and the reference.
All object versions are pinned. Input budget is 16 GiB; output budget is 2 GiB;
IO ceiling is 10,000 calls. No December payload or model has run in this preparation.

One on-demand L40S, 8 vCPU, 32 GiB, 100 GiB disk, 1 GiB shared memory; restart never,
one attempt, one-hour execution and two-hour create-to-terminal ceiling. The watcher
cancels at 7,080 seconds, preserving 120 seconds for cancellation/readback. Transient
reads use at most 30/60/90/120-second attempts within remaining time; mutations never retry.
No fitting, calibration, threshold selection, G8 rerun, promotion or replacement.

Proposed additional cap: **$6.25 excluding VAT**. Nebius's calculator estimated
$1.5484/hour compute plus $0.0097222/hour disk, about $3.12 over the accounting bound.
This is an estimate, not actual billing; retain the full reservation until reconciliation.

Temporary final policy: 62 exact keys for the existing development group, nine rules total.
Temporary results policy: one baseline viewer key plus one result-prefix editor grant
and one nonce-specific context editor key. Equivalent retained rules consolidate to
fit six total rules; no retained access is expanded and baseline write is forbidden.
Both source policies (final version 10 / results version 11) are preserved for restoration.
Three-hour access ceiling; remove additions and undo consolidation after completion/abort.
Fresh policy/version readback is required before updates; never overwrite concurrent changes.

Execution order after exact approval:

1. Retain the reply binding this proposal hash and context signing custody; write
   root evidence `operator-approval.json` with `approved: true` and `proposal_sha256`.
2. Run the pinned operator Python and `scripts/watch_transformer_holdout.py --offline`
   with root evidence path and `--proposal-sha256`. SDK and actual local CLI help must pass.
   Complete this preflight before granting any temporary permission.
3. Independently read both bucket policies, apply the approved temporary files through
   the operator handoff, and verify exact policies. No credential lookup before this gate.
4. Start the watcher without `--offline`. Require a fresh (at most ten seconds old)
   absent/admission-ready heartbeat, confirm its PID/session is alive, then issue the
   [exact create argv](../evidence/transformer-holdout-create-argv-20261006.json) once.
   Nebius accepted these resource/injection flags in dry-run; no Job was created.
   Reconcile ambiguous creation by name; never submit a second attempt.
5. The watcher independently checks the live Job and delivers signed context once.
   Startup verifies image sources/package/dependencies; CUDA parity precedes final GETs.
6. Observe terminal state; independently use `holdout_readback.verify_result` on exact
   version/checksum publication receipts. Retain Markdown plots/metrics/resources and
   a continue/stop/inconclusive research decision before removing temporary grants.
   On failure or uncertainty, cancel/reconcile the owned Job and remove grants first.

December is unseen by this fixed Transformer, but G8 previously reported these data.
Only three base sessions support uncertainty estimates. Neither this preparation nor
a first GUI demo constitutes production qualification or full #24/#90/#91 acceptance.

The demo proceeds separately under #90/#91: checksum-bound retained-score playback
with explicit historical/control versus historical-with-synthetic-anomalies provenance.
MLflow reconciliation and platform maintenance follow the research result.
