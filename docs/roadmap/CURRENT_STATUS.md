# Current status — 8 October 2026

This page owns current gates and next work. The [main roadmap](ROADMAP-MAIN.md)
owns baseline dates; [phase scope](PHASES.md) owns forward acceptance.
Tracking: [Story #24](https://github.com/khab40/lob-arena/issues/24),
[Bug #357](https://github.com/khab40/lob-arena/issues/357),
[Project #3](https://github.com/users/khab40/projects/3).

## Current disposition

**Continue bounded Transformer research and prepare the private saved-score
mock under #90/#91.** The frozen training grid, seed confirmations, calibration,
paired development comparison and authorized December evaluation are complete
and independently verified. Scoped selected-settings/reference acceptance #314
is complete. Full #24 acceptance and production qualification remain open.
The [operator disposition](../ml/transformer-research-disposition-20261008.md)
owns the decision, limitations and integration sequence.

| Area | Recorded state | Evidence owner |
| --- | --- | --- |
| Four-date C4 corpus | Frozen; shared tabular/sequence rows and isolated final lane | [C4 contract](../operations/g8/g8-c4-evaluation-contract.md) |
| LightGBM | G8/G9 closed as `research_baseline_qualified`; retained baseline unchanged | [Signed G9 closure](../operations/g8/g9-closure-20260927.md) |
| Transformer | Fixed candidate and completed independently verified research | [Verified report](../ml/transformer-holdout-report-20261007.md) |
| Selected settings #314 | Persistence/integrity and retained-reference acceptance met | [Acceptance disposition](../ml/transformer-research-disposition-20261008.md#selected-settings-acceptance) |
| #24 full story | Open: MLflow lineage, dedicated serving path and resource/cost acceptance | [Remaining acceptance](../ml/transformer-research-disposition-20261008.md#selected-settings-acceptance) |
| #90/#91 first mock | Planned private local playback of verified saved predictions | [Next medium PRs](../ml/transformer-research-disposition-20261008.md#next-medium-prs) |
| Cascade #25 | Conditional, unimplemented and unapproved by continuation | [ARD-0037](../architecture/ARD-0037-transformer-to-lightgbm-cascade.md) |
| Client/production qualification | Open; research sample does not satisfy its data/quality/operational gates | [Functional acceptance](../product/FUNCTIONAL_OVERVIEW.md) |
| Platform #19–#21 | Remaining acceptance deferred under research-first priority | [Research sequence](../architecture/ARD-0042-transformer-lightgbm-research-sequence.md) |

## Interpreting the result

The report covers 15,160 retained rows / 135 positives, one date and three base
sessions with synthetic attack labels. Transformer balanced F1 is 95.35% versus
74.48% for frozen LightGBM. Both detect all 27 labelled campaigns. December was
unseen by this Transformer but previously evaluated by LightGBM. These limited
research results do not establish general-market performance or production
acceptance. Use the report for operating points, subgroup support and uncertainty.

## Next work and remaining gates

1. #90/#91: authenticate private saved-score evidence and expose bounded local
   playback. This first mock does not infer fresh scores or replay an order book.
2. #24/#90: prepare a dedicated selected-state classifier export/adapter and
   resolve causal event sampling, warm-up/reset/gap and queue/alert contracts.
3. Review an exact fresh replay package and obtain applicable execution/access/
   spend approval before any Nebius scoring. Keep Java book mutation separate.
4. Reconcile the same retained artifacts in MLflow under #19, resource/cost
   evidence and full #24/#90/#91 acceptance. Shared sensitive-data deployment
   requires #91's backend authentication/authorization gate.

Actual billing and online MLflow remain unreconciled. Existing reservations stay
held under the recorded operator-managed policy; this page releases no budget.
All seven roadmap milestones retain their original acceptance and baseline due
dates pending reforecast; completed research does not close them automatically.

## Authorization and durable custody

Past approvals and consumed attempts cannot authorize another Job or final read.
Model training/scoring/rehearsal uses separately authorized Nebius Jobs. Local
work is orchestration, static checks and artifact inspection. Apply
[digest preflight](../operations/digest-pinned-jobs.md),
[public-evidence safeguards](../operations/public-evidence-secret-prevention.md)
and [coordinated admission](../operations/transformer-coordinated-admission.md).
Future readback packages use the [retaining/offline custody contract](../ml/transformer-holdout-execution-package.md#future-readback-packages--8-october-2026),
with pinned settings retained separately. Frozen collectors, settings and evidence
remain unchanged. Serving promotion, cascade work, merge and deletion have
separate gates.

## Historical status

The [complete previous status journal](STATUS_HISTORY_20261008.md) preserves
all original entries and attempt history, including failures and access overruns.
It is not a current checklist. New current changes belong here; dated receipts
and attempt narratives belong in their owning result/history records.

<a id="lightgbm-remaining-work-plan--2026-09-22"></a>
The previously linked [September 22 LightGBM remaining-work plan](STATUS_HISTORY_20261008.md#lightgbm-remaining-work-plan--2026-09-22)
is retained historical planning, superseded by the signed G9 closure.
