# Transformer offline lineage semantics — 2026-09-29

Story [#24](https://github.com/khab40/lob-arena/issues/24) → Feature #16 → Epic #15, Project #3. Continues approved #241 scope after #258 merged. No cloud execution in this increment.

As a validation engineer,
I want replay, feature and label metadata cross-checked against authenticated frozen records,
So that matching file hashes cannot hide conflicting run identities or label definitions.

Actor: validation engineer. Goal: offline cross-artifact verification of the 30 validation runs. Value: trustworthy evidence before the CPU role audit.
Out of scope: payload reads, source-observation separation claims, class counts, model training, cloud grants or Jobs.
Verification: inert metadata fixtures, mutation/boundary tests, known producer schema comparisons, CI; later live audit readback remains separately gated.

```gherkin
Feature: Consistent frozen validation lineage
  Scenario: Verify complete authenticated metadata
    Given frozen manifests and two complete authenticated metadata phases
    When offline lineage verification completes
    Then all 30 replay, feature and label bindings agree
    And source separation and GPU readiness remain unverified
  Scenario: Reject conflicting metadata
    Given authenticated metadata bytes with conflicting run or label identities
    When lineage verification runs
    Then verification fails without a success receipt
  Scenario: Keep stream hashes separate from file hashes
    Given a C4 replay field containing the event-stream hash
    When feature metadata substitutes that hash for the replay file checksum
    Then lineage verification rejects the mismatch
```

1. Reauthenticate both phase directories before reading semantics; fixed local filenames only.
2. Cross-bind replay identity, dataset/source/date, stream hash, artifact references, feature metadata/config and research-control label spec; hash raw producer bytes where hashes refer to files.
3. Keep remaining source/window, class support and platform/authorization gates explicit; do not certify independent observations from metadata alone.
4. Test with inert metadata, review and publish one coherent PR with commits <=200 changed lines.
5. Preserve #258 refs in a verified bundle and request exact cleanup approval at handoff. The approved-scope replacement audit remains pending separate approval and must use its pinned backend snapshot, not this evolving checkout.

## Offline readback

After an approved collection produces both complete phase directories, run from
`backend/` with the repository environment:

```sh
python -m app.ml.transformer.lineage_readback BUNDLE PHASE_ONE PHASE_TWO NEW_RECEIPT
```

The command authenticates the frozen bundle, request, inventories, all 115 retained
objects and both collection receipts before checking semantic agreement. It uses
fixed metadata filenames and never opens referenced event, snapshot or feature
payloads. It refuses to overwrite a receipt; failures do not publish success.

C4's `replay_manifest_sha256` is the canonical event-stream hash. The feature
producer's field of the same name is the actual replay-file SHA-256. Both bindings
are checked according to their producer contracts. Configuration hashes use the
retained configuration object; the label parser and label/config models were
compared with producer commit `cf426c0db0940a985133fc7c8482623186acd5a4` and are unchanged.

The output preserves the research-control negative-label assumption. Label windows
are reported in producer tick coordinates; this does not prove observation or
label-horizon separation, independently clean negatives, or per-role class counts.
The approved [r3 collection and semantic readback passed on 2026-10-01](transformer-lineage-r3-results.md):
all 115 objects and 30 validation-run bindings were independently verified, and
temporary access was removed. Source/window separation, the signed CPU role-audit
package and exact execution approval remain next; metadata agreement does not
satisfy those gates.

Verification: [inert regression evidence](../evidence/transformer-lineage-semantics-20260929.json).

## Projection row-count binding

[Bug #262](https://github.com/khab40/lob-arena/issues/262) fixes PR #261's P2 review
finding. The verified `default_label=0` specification labels every emitted row,
so its feature row count must equal the frozen shard's supervised row count.
Successful per-run receipts retain both counts. This checks inventory agreement;
source separation and class-support proof remain pending.

```gherkin
Feature: Frozen projection row-count binding
  Scenario: Accept matching row inventories
    Given authenticated feature metadata with research-control default labels
    And its emitted row count equals the frozen supervised row count
    When offline lineage verification runs
    Then lineage verification succeeds with both counts recorded
  Scenario Outline: Reject conflicting row inventories
    Given authenticated feature metadata with research-control default labels
    And the frozen supervised row count is <relation> the emitted feature count
    When offline lineage verification runs
    Then verification fails without publishing a success receipt
    Examples:
      | relation     |
      | smaller than |
      | greater than |
```

All four control/hybrid count-mismatch cases failed before the repair because no
exception was raised; all 203 focused tests pass after repair. Fixtures contain
only metadata. No cloud reads, payload reads or model runs were required.
