# Documentation

Start with the [canonical architecture](architecture.md), the
[current roadmap status](roadmap/CURRENT_STATUS.md), or the
[ML lifecycle use cases](use-cases/ml-lifecycle.md).
The repository-root [ARCHITECTURE.md](../ARCHITECTURE.md) is only a navigation link;
`architecture/` contains individual decisions, not a competing system overview.

| Topic | Entry points |
| --- | --- |
| Architecture | [System overview](architecture.md), [ARD index](architecture/README.md) |
| Roadmap | [Current status and stale planning text](roadmap/CURRENT_STATUS.md), [dates and dependencies](roadmap/ROADMAP-MAIN.md), [phase history](roadmap/PHASES.md), [Wave 1 record](roadmap/nebius-lightgbm-wave1-implementation-plan.md), [public-data plan](roadmap/nebius-public-market-data-lightgbm-plan.md) |
| Use cases | [Workflow catalogue](use-cases/README.md), [ML lifecycle](use-cases/ml-lifecycle.md), [data preparation](use-cases/ml-data-preparation.md), [training and selection](use-cases/ml-training-selection.md), [serving plan](use-cases/ml-model-serving.md) |
| Data | [Nasdaq flow](data/nasdaq-public-sample-v1-data-flow.md), [corpus governance](data/governed-corpus-benchmark-protocol.md), [hybrid validation](data/hybrid-dataset-validation.md), [client runbook](data/client-historical-dataset-validation-runbook.md) |
| ML | [LightGBM runbook](ml/lightgbm-v1-runbook.md), [features](ml/feature-engineering-lightgbm.md), [benchmarks](ml/benchmark-methodology.md), [MLflow](ml/mlflow-tracking-server.md), [execution policy](ml/model-validation-execution-policy.md), [LLM prompting](ml/surveillance-prompting.md) |
| Runtime | [Ownership and APIs](runtime/runtime-model.md), [event stream](runtime/exchange-event-stream.md), [determinism](runtime/determinism-contract-v1.md), [hashing](runtime/canonical-hashing-v1.md), [observability](runtime/kernel-observability.md) |
| Runtime history | [Java migration](runtime/history/java-kernel-migration.md), [final authority](runtime/history/kernel-authority-rollout.md); retired shadow/fallback procedures are historical |
| Deployment | [Quickstart](deployment/QUICKSTART.md), [Nebius setup](deployment/nebius-deployment.md); current ML workload restrictions still apply |
| Operations | [G8 production package](operations/g8/g8-production-package.md), [native rehearsal](operations/g8/g8-native-rehearsal-package.md), [recovery](operations/g8/g8-completion-recovery.md), [Git ref recovery](operations/git-ref-recovery.md) |
| Product | [Functional scope](product/FUNCTIONAL_OVERVIEW.md), [one-pager](product/lob-arena-one-pager.md), [design ideas](product/DESIGN-IDEAS.md), [theme](product/ui-theme.md), [limitations](product/safety-and-disclaimers.md) |
| Research | [Background references](research/research-notes.md) |
| Publication | [Challenge submission](publication/challenge-submission.md), [demo script](publication/demo-script.md), [article draft](publication/linkedin-technical-blog-post-updated.md); dated demo/publication material |
| Archive | [Changelog](archive/CHANGELOG.md), [removed Google Auth implementation plan](archive/IMPLEMENTATION_PLAN_GOOGLE_AUTH.md), [L40S migration](archive/l40s-migration.md) |
| Evidence | Immutable machine-readable receipts in `evidence/`; historical receipts retain their original values |

The [documentation audit](documentation-review-20260921.md) inventories every
pre-existing Markdown file, its review outcome and any stale-history flag.
Use the [documentation guide](DOCUMENTATION_GUIDE.md) for ownership and update rules.

## Reading status correctly

“Accepted” in an ARD means a design decision was accepted; it does not mean every
consequence or future workflow is implemented. A dated execution record describes
that attempt only. Current guidance links to evidence and distinguishes implemented,
proposed, blocked and superseded behavior. Do not execute an old cloud command
merely because it appears in an archived successful run.
