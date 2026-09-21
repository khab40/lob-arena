# G8 operations

Start with [current status](../../roadmap/CURRENT_STATUS.md) and the
[current recovery plan](../../roadmap/PHASES.md#g8-recovery-and-completion-plan),
then the [production package](g8-production-package.md). These own dated
readiness and the order of remaining gates. Reading a runbook grants no execution
authority; final-test/replacement approval remains separate.

| Need | Detailed reference |
| --- | --- |
| Four-date metrics, provenance and report verification | [C4 evaluation contract](g8-c4-evaluation-contract.md) |
| Seal scored results before logging; restore after workspace loss | [Pre-logging checkpoint](g8-prelogging-checkpoint.md) |
| Recover logging without rescoring or changing run identity | [Same-run MLflow recovery](g8-mlflow-recovery.md) |
| Publish a completed release without scoring or MLflow writes | [Publication recovery](g8-publication-recovery.md) |
| Native package bindings, transport and two-Job synthetic proof | [Native rehearsal package](g8-native-rehearsal-package.md), [context handoff](g8-native-context-handoff.md) |
| Replacement integration and earlier approval/staging history | [Live replacement record](g8-live-replacement.md) |
| Recovery implementation and earlier gates | [Completion record](g8-completion-recovery.md) |
| Storage exception bindings and disposition | [Persistent storage exception](g8-persistent-storage-exception.md) |
| Historical source staging and execution-location decision | [Source SDK](g8-source-sdk.md) |
| C4 provenance remediation evidence | [Provenance fix](g8-c4-provenance-fix.md) |

The detailed records retain their original procedures, failure semantics,
authorization boundaries and evidence. Superseded dated observations inside
them are history; consult the current status/plan before preparing any action.
The [execution policy](../../ml/model-validation-execution-policy.md) applies to
all agent-initiated model workloads.
