# Transformer r3 metadata audit results — 2026-10-01

Story [#24](https://github.com/khab40/lob-arena/issues/24) → Feature #16 → Epic #15,
[Project #3](https://github.com/users/khab40/projects/3).
This record completes the approved metadata audit; Transformer training remains gated.

Both authorized phases succeeded once. The retained bytes and all 30 validation-run
bindings passed offline semantic readback and independent verification. Operator
removal was independently checked through Nebius MCP at bucket version **143**:
the original two policy rules and non-policy settings were restored exactly.

| Phase | Successful GETs | Bytes | Temporary access (seconds) |
| --- | ---: | ---: | ---: |
| 1: request, inventory and feature metadata | 58 | 250,298 | 570.225036 |
| 2: replay and label-window metadata | 57 | 105,742 | 210.213551 |
| Total | 115 | 356,040 | 780.438587 |

Each phase stayed within its approved one-hour access bound. All earlier attempts
remain preserved and consumed. The audit did not read event or sequence payloads,
run models or GPU Jobs, access final data, or reopen G8/G9.

## Verified evidence

The [audit record](../evidence/transformer-lineage-r3-audit-20261001.json) binds the
approved proposal, collection receipts, runtime identities, independent readback
and access removal. Its [object inventory](../evidence/transformer-lineage-r3-objects-20261001.jsonl)
retains the 115 authenticated objects; its
[run inventory](../evidence/transformer-lineage-r3-runs-20261001.jsonl) records all
30 replay, feature, label and row-count bindings.

Collection used the approved backend at `8d93e3d`; semantic verification used
merged PR [#267](https://github.com/khab40/lob-arena/pull/267) at `ef397e6`.
The audit record retains the complete commit and backend-tree identities.
Semantic readback performs local artifact inspection without additional S3 GETs.

The completed checks authenticate producer bytes and agree on run, dataset,
instrument, source session, event-stream identity, replay-file checksum, feature
configuration, label specification and emitted/supervised row counts. The 9,210
emitted rows match the frozen supervised counts; this is inventory agreement, not
a count of independent observations. Stream hashes and replay-file hashes are
verified according to their distinct producer contracts.

## Limitations and next steps

Negative labels retain the **research-control assumption** and are not independently
verified clean. Positive labels come from synthetic scenarios. Label windows use
producer tick coordinates; metadata agreement does not establish independent source
observations, label-horizon separation, per-role class support or model quality.

1. Resolve source-observation and label-horizon separation using the authenticated
   lineage, with an explicit disposition for any overlap or unresolved mapping.
2. Complete the signed CPU role-audit package for exact row alignment and class
   support, obtain exact execution approval, and independently verify its results.
3. Complete MLflow and platform readiness, including required artifact lineage and
   recovery evidence under [#19](https://github.com/khab40/lob-arena/issues/19)–[#21](https://github.com/khab40/lob-arena/issues/21).
4. Present the bounded GPU execution package for separate authorization, following
   the approved [training, checkpoint-selection, calibration and MLflow plan](transformer-gpu-campaign-plan.md).

Story #24 remains in progress. These results close the metadata-lineage check;
they do not authorize CPU or GPU execution or qualify a Transformer model.
