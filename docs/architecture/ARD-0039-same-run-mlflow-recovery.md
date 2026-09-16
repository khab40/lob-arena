# ARD-0039: Same-Run MLflow Evaluation Recovery

Status: Accepted

Date: 2026-09-15

Implementation Status: `[recovery API implemented; live runner integration pending]`

## Validation execution policy — 2026-09-16

The operator removed administrative submission/retention windows, billing checks
and fixed validation spend/VM limits until LightGBM and Transformers validation
have recorded outcomes. Apply the [validation execution policy](../model-validation-execution-policy.md)
in preference to older operational bounds in this record. No billing queries or
balance-refresh requests. Finite Job timeouts, execution identities, evidence
integrity and separate final-test authorization remain. This is an execution-policy
change, not model-quality acceptance or a completed G8/G9 milestone.

## Context

A lost MLflow response may follow a successful write. Retrying with a new run
would duplicate a frozen evaluation; treating a run ID as completion would hide
missing metrics, lineage or artifacts. Recovery must preserve one identity and
the original verified evidence.

## Decision

Separate reservation before scoring from independently verified logging:

1. `reserve_run(ResumeTarget(...))` binds the execution package, request,
   candidate, C4 profile, request run ID and tracking URI. Require an existing
   experiment and ledger root, an exclusive lock, atomic/fsynced intent records
   and `MLFLOW_HTTP_REQUEST_MAX_RETRIES=0` before creating a run.
2. After an ambiguous create response, reconcile by search using the same
   ledger. Adopt exactly one matching active run; zero matches after intent,
   duplicates, deleted/FAILED/KILLED runs or conflicting identities stop recovery.
   Never silently replace a saved run ID.
3. `log_governed_evaluation_run(..., resume_target=...)` independently verifies
   the release and [C4 evidence](ARD-0038-c4-specific-evaluation.md). It cannot
   reserve or create a run. Seal the logging plan and privately snapshot artifacts.
4. Compare existing tags, full metric histories, dataset lineage and artifact
   bytes. Write only missing evidence; reject conflicts. Preserve original
   source URIs and cloud metrics across recovery. Normalize dataset tags by key
   and value, rejecting duplicate keys before normalization.
5. Require complete readback and `FINISHED`. Repeating completed logging verifies
   the same evidence with zero writes. Interrupted runs remain RUNNING.

The at-most-one-create property depends on the same intact ledger and exclusive
writer. Independent ledgers have no server-side uniqueness transaction. This
ledger is neither a scoring-once guard nor an execution approval.

## Implementation and verification

[g8_mlflow_recovery.py](../../backend/app/ml/lightgbm/g8_mlflow_recovery.py)
provides reservation and recovery through the shared
[tracking.py](../../backend/app/ml/lightgbm/tracking.py) API.
The [reviewed synthetic receipt](../evidence/g8-mlflow-tag-review-20260914.json)
records one run creation, one scoring call, 24 metrics, 30 dataset inputs and
four verified artifacts, including reordered tag readback and zero writes on
completed recovery. Lost create, metric, artifact and FINISHED responses are
covered by the [recovery rehearsal](../g8-mlflow-recovery.md).

The production runner still uses its legacy logger and temporary workspace.
Pre-logging scored-payload retention, fresh-process recovery after workspace
loss, native-mount durability and authenticated remote rehearsal remain open.

## Alternatives and consequences

Creating a replacement run after timeout can duplicate evaluation history.
Blindly repeating writes can duplicate metric histories or lineage. Read-before-
write verification preserves evidence at the cost of additional reads and an
intentionally fail-closed response to ambiguous reservation state.

## Dependencies and related documentation

- [ARD-0027: Shared MLflow plane](ARD-0027-shared-mlflow-tracking.md) — tracking infrastructure and release authority.
- [ARD-0035: Nebius qualification](ARD-0035-nebius-lightgbm-first.md) — replacement execution gates.
- [ARD-0038: C4 evaluation](ARD-0038-c4-specific-evaluation.md) — required provenance verification.
- [ARD-0040: Publication recovery](ARD-0040-completed-release-publication-recovery.md) — subsequent completed-release publication.
- [G8 MLflow recovery](../g8-mlflow-recovery.md) — operational contract and evidence.
