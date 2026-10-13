# Reconcile delivered recovery fixes

Scoped delta, 13 October 2026: reconcile evidence and tracking for Bugs
[#358](https://github.com/khab40/lob-arena/issues/358),
[#376](https://github.com/khab40/lob-arena/issues/376),
[#379](https://github.com/khab40/lob-arena/issues/379) and
[#382](https://github.com/khab40/lob-arena/issues/382), for
[Story #90](https://github.com/khab40/lob-arena/issues/90), their intended parent, in
[Project #3](https://github.com/users/khab40/projects/3).

**Behavioral change: none.** All four fixes were delivered previously. This
increment publishes a non-executable metadata summary and reconciles their open
tracking. Its invariant is that existing behavior, frozen packages, specifications,
historical receipts and private custody remain unchanged. Verification uses the
existing inert tests, exact prior review pins and allowlisted terminal metadata.

The [public metadata receipt](../evidence/recovery-bug-closure-20261013.json)
binds exact source/specification/test/review files by SHA-256. Those existing
specifications own acceptance; this document adds no competing requirements.
Private file references identify retained evidence without publishing its contents.
The root evidence directory is `outputs/bug-fixes-387-reconciliation-20261013/iteration2/`.

## Acceptance reconciliation

| Bug and owned scope | Implementation / verification | Result and retained evidence |
| --- | --- | --- |
| #358: configured custody protected with playback enabled or disabled | `backend/app/main.py` checks enabled **or** explicitly configured custody before `LocalStore` and retention. Existing `test_private_root_guard_precedes_startup_cleanup[True/False]` rejects overlap before either initializer; root overlap and generic-download tests cover containment and disjoint custody. | Duplicate of closed [#359](https://github.com/khab40/lob-arena/issues/359), merged in [PR #362](https://github.com/khab40/lob-arena/pull/362), merge `41ae6d24601e7fd2b7f359051a6ccdc330402b13`. Its independent backend correction review records 48 inert cases and no actionable P0/P1/P2. Five existing focused cases pass in this increment. |
| #376: preserve primary collection failure through finalization | Pinned v2 collection successor; `test_final_stdout_preserves_primary_accounting_when_close_also_fails` exercises nine primary/close-fault combinations, including close-only failure, persistent failure and cancellation. | Exact correction review closes `CEO-COLLECTION-I1-01`: 22 inert cases and Ruff pass. It asserts final stdout stage, ordinal, counts, safe reasons, single close, restored umask and no duplicate object calls. |
| #379: preserve safe observation before a responded receipt write | Pinned v2 HEAD diagnostic; `test_responded_custody_failure_keeps_safe_observation` covers four OSError/cancellation and persistent-write combinations. | Exact correction review closes `CEO-HEAD-DIAG-I1-01`: 34 inert cases and Ruff pass. Primary failure/accounting and safe response observation survive write refusal; raw invented canaries are absent and GET counts remain zero. |
| #382: refuse broadened or ambiguous same-group access cleanup | Pinned v2 guard; ACCESS-03/04 and the 13 exact tests listed in the receipt cover native matching, invalid paths, mixed/reordered rules, unrelated changes and fresh resource versions. | Exact correction review closes `ACCESS-CLEANUP-PREFIX-01`: 13 inert tests plus eight subtests and Ruff pass. Broader matching rules are refused rather than removed or reported absent. |

#358's canonical contract is [verified saved-score playback](../ml/verified-saved-score-mock.md).
Its unconfigured disabled startup branch retains the existing behavior by the
guard condition; that branch is inspected, not claimed as an additional test case.
The fresh five-case check also covers disabled route refusal and private error
redaction. Its log and check receipt are retained under the root iteration directory.

For #376/#379/#382 the reviewed private successor specifications remain canonical
for their bounded helper scopes. The receipt pins their exact paths and bytes.
No private helper code, executable plans, policy documents or payloads are copied
into this reconciliation.

## Actual outcomes and their limits

#379's independently bound terminal receipt records a failed output HEAD at
ordinal 9: safe observation `http_403`, exit 255, zero stdout bytes and 133 stderr
bytes. Six grounding and two selector stages validated; the single HEAD responded
but did not validate. GET counts were zero; cleanup and finalization completed.
This establishes diagnostic accounting, not successful original output access.

Later #376/#382 supporting metadata records three validated HEADs and three
validated GETs, 10,388,606 verified bytes and completed collection finalization.
The temporary exact rule was removed; independent metadata audit confirms the
original nine-rule specification was preserved with fresh removal/readback.
These outcomes supplement the inert failure-boundary proofs. They do not replace
those proofs or establish complete #90/#91 product acceptance.

## Tracking and closure boundary

Read-only GitHub inspection on 13 October found all four issues open in Project #3.
#358 was Todo with no actual parent despite its body reference; it is a duplicate
of #359. The other three were In Progress and actual children of #90.
Their intended parent placement for this reconciliation is #90.

All four dispositions are **prior-delivery closure_pending_merge**: the delivered
fixes are verified, while closure from the reconciliation PR remains pending its
review, publication and merge. Record #358's duplicate lineage and actual parent
when updating tracking. Preserve the open #90/#91 acceptance gates and unrelated
active PRs #368/#380.

This increment authorizes no new diagnostic invocation, credential/payload read,
policy mutation, model execution, cloud run, spend, promotion, merge or deletion.
The independent review of this exact documentation delta remains separate from
the retained correction reviews. Normal publication secret checks remain enabled;
private custody is excluded from their API input.
