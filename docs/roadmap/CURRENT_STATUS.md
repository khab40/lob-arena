# Roadmap status — 2026-09-21

This is the dated status snapshot for the [main roadmap](ROADMAP-MAIN.md).
Dates are approved baseline targets, not a revised delivery forecast. A passed
software test, synthetic rehearsal or metadata audit does not close a model-quality gate.

## Sources and precedence

- [Project #3](https://github.com/users/khab40/projects/3) and linked issue states
  were read on 2026-09-21, together with all seven dated milestone descriptions.
- Merged implementation baseline: `origin/main` at `fb78b608d4e081cb32901f6b02cbca27574ff730`.
- Readiness continuation: [open PR #207](https://github.com/khab40/lob-arena/pull/207),
  observed at `ebf91a5e1b1de6228a585f0f1013aff1a79872c9`. Its receipts are evidence
  of those operations; its documentation is not yet merged into the baseline.
- Gate receipts establish outcomes. Issue/board states establish work status.
  Milestone dates establish targets. Historical narrative and milestone counters
  must not override more specific evidence. Revalidate before execution.

## Milestones

| Milestone | Baseline target | Verified position and remaining dependency |
| --- | --- | --- |
| M1 corpus/infrastructure | 2026-09-11 | Corpus [#22](https://github.com/khab40/lob-arena/issues/22) closed; infrastructure [#20](https://github.com/khab40/lob-arena/issues/20) open/In Progress. Partially overdue. |
| M2 LightGBM | 2026-09-23 | [#23](https://github.com/khab40/lob-arena/issues/23) open/In Progress; G0–G7 complete, G8 open, G9 blocked. Target at risk. |
| M3 Transformer | 2026-10-09 | [#24](https://github.com/khab40/lob-arena/issues/24) open/Todo; follows LightGBM exit. September 24 baseline start is at risk. |
| M4 cascade | 2026-10-23 | [#25](https://github.com/khab40/lob-arena/issues/25) open/Todo; needs verified standalone Transformer and leakage-safe feature release. |
| M5 integrated evidence | 2026-10-30 | [#90](https://github.com/khab40/lob-arena/issues/90) open/Todo; requires three-model Nasdaq comparison and LOBSTER robustness evidence. |
| M6 secure CEO UI | 2026-11-13 | [#91](https://github.com/khab40/lob-arena/issues/91) open/Todo; existing demo UI does not satisfy the secure five-step workflow. |
| M7 acceptance | 2026-11-20 | [#15](https://github.com/khab40/lob-arena/issues/15) and [#16](https://github.com/khab40/lob-arena/issues/16) open/In Progress; final rehearsal and verified acceptance remain. |

M1 infrastructure still needs repeatable/idempotent reconciliation, safe teardown,
billing notification/FOCUS integration and the broad-editor-permission disposition.
M2 supporting stories #14/#18/#19/#21 remain open/In Progress; corpus completion
alone does not close them. #84 (immutable image selection) remains open/Todo.
The investigator baseline (#17/#26) is in progress; model comparison #27 and
learned-evidence integration #28 remain Todo. Qwen explanations are not the
standalone market-sequence Transformer classifier.

BYO inbound adapter #87, detector adapter #88, expanded scenarios #85,
adversarial/customer-integration epics #92/#93 and storage expansion #94 remain
open/Todo and outside the dated critical path. Do not present them as delivered.

## Data and model gates

C0–C4 are complete for four dates: train 2019-01-30/2019-03-27, validation
2019-10-30, final test 2019-12-30. Both tabular and sequence projections exist.
The public-sample negatives use a research-control assumption, not independent
clean-window review. Client qualification retains its stronger governance requirements.

G5 reproducibility passed on September 7, G6's nine-Job campaign on September 10,
and G7 freeze on September 12. The selected isotonic LightGBM candidate remains
`5cdd3b55c86338f4b492362c87e21682ff83ce9ae5258d1ddae60a5b6ff768ff`.
R4 downloaded final data and failed before scoring; its authorization is consumed.
Do not claim the final fold has never been accessed or reuse that authorization.

The September 17 two-Job native synthetic rehearsal verified scoring followed by
workspace-loss recovery into the same MLflow run; independent readback verified
[all 64 S3 objects](../evidence/g8-independent-s3-readback-20260917.json).
The [production review package](../operations/g8/g8-production-package.md) is unsigned.
This is recovery engineering evidence, not a production G8 quality result.

PR #207 separately records [89 original metadata objects](https://github.com/khab40/lob-arena/blob/ffbc2310ca9e40af5cd3c8fc86ba13eb13bbc380/docs/evidence/g8-original-comparison-metadata-20260921.json)
and [32 GiB mounted capacity plus live C4 registration](https://github.com/khab40/lob-arena/blob/ffbc2310ca9e40af5cd3c8fc86ba13eb13bbc380/docs/evidence/g8-capacity-registration-20260921.json).
The latter verifies 240 dataset inputs and 30 final-tabular entries without
reading final payload rows. Earlier 10 GiB/registration-pending observations are
historical. Its later [payload/readiness receipt](https://github.com/khab40/lob-arena/blob/ebf91a5e1b1de6228a585f0f1013aff1a79872c9/docs/evidence/g8-original-payload-verification-20260921.json)
records 294 original objects / 2,632,277,460 bytes staged and 377 files independently
rehashed. A new 25-file unsigned review binds those bytes, live registration and
32 GiB capacity. No rows were parsed, model Jobs submitted or final bucket accessed.
Production transport/context handoff and comparison semantic verification on
Nebius, fresh preflight (including 20 GiB free space for the 4 GiB checkpoint bound),
canonical request and replacement-specific authorization remain open.

G9 requires verified G8 evidence and a signed exit disposition; Transformer,
cascade and live learned-model integration remain planned. Candidate artifacts
in MLflow are not automatically registered model versions or serving deployments.
See the [ML lifecycle](../use-cases/ml-lifecycle.md) for implemented versus planned steps.

## GitHub milestone reconciliation

All [seven milestone descriptions](https://github.com/khab40/lob-arena/milestones)
were updated and read back on 2026-09-21 at 10:25 UTC. Titles, states and baseline
due dates were preserved. M2 now records merged PR #200, the successful 64-object
readback and separately identified PR #207 payload/readiness evidence. M1 retains
its open infrastructure work; downstream descriptions expose their dependency risk.

M1's API counters still reported zero issues despite assignments to #20/#22; use
linked issue states. Some issue bodies still name earlier main commits and omit
PR #207's later receipts. Those issue-body discrepancies remain flagged; this
update changed milestone descriptions, not issue bodies or board states.

Historical spend figures and consumed Job counts remain audit facts. The current
[execution policy](../ml/model-validation-execution-policy.md) supersedes old billing,
expiry and fixed-spend gates. Current operator instructions still govern each
execution scope; nothing in these documents grants cloud or final-test access.
