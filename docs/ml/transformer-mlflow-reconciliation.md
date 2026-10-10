# Original Transformer tracking reconciliation

Tracking the original selected research execution completes the lineage part of
[#24](https://github.com/khab40/lob-arena/issues/24), under
[Project #3](https://github.com/users/khab40/projects/3). The
[canonical specification](../specs/24-governed-transformer.md) owns AC-01 and the
AC-01a–c reconciliation scenarios. [#19](https://github.com/khab40/lob-arena/issues/19)
owns the shared tracking service. Its registry and restoration acceptance are
separate from this original-run lineage operation.

This operation indexes `transformer-research-c4-20261003-r2-search-128-0003` in
`lob-arena/transformer-development`. It preserves the original seed-42 selection,
epoch-04 checkpoint reference, nine recorded training epochs, original execution
times, code/image/request identities, features, normalization and development
split membership. It performs no model execution or final-data access.

## Sealed metadata

`deployments/mlflow/transformer_lineage_plan.py` accepts externally pinned,
versioned metadata snapshots. It authenticates the original settings, selection
and comparison receipts, original configuration/result, twelve progress events,
input manifests and inventory before constructing a logging plan. It uses no
Torch, MLflow client, credentials or network calls.

The plan includes exact metadata artifact bytes and references the saved weights
by original URI, version, size and SHA-256. Weights and market-data shards are
excluded from MLflow uploads. Dataset inputs describe original training and
validation shards; full artifact hashes remain canonical even where MLflow uses
a shorter dataset digest. The selected settings remain unchanged and continue
to describe historical tracking reconciliation as pending.

Original epoch timestamps are retained where available. The historical journal
does not provide per-epoch wall-clock times; those points use the explicitly
recorded original-finish-milliseconds convention. Reconciliation time has its
own tag and never replaces the original execution start or end.

## One original-run record

`deployments/mlflow/transformer_lineage.py` uses injected, authenticated writer
and independent-reader adapters. It requires the existing active experiment and
the intended account access before any run mutation. An exclusive durable create
intent binds the sealed plan to one retrospective tracking record. A lost create
response is reconciled by unique readback; an unresolved reservation or duplicate
match cannot create a replacement.

The reconciler reads complete parameters, tags, metric histories, dataset inputs
and artifact bytes before writing. It adds missing exact values, rejects
conflicts and duplicates, and retains write intents before each mutation. It
verifies the complete plan through both identities before setting the run to
FINISHED with its original end time. A completed replay performs zero writes.
No registry version, alias, model flavor, namespace bootstrap or permission
change is part of this helper.

## Runtime activation and evidence

The existing MLflow VM is the intended metadata runtime. The last retained
provider observation was STOPPED; deployed MLflow 3.13.0 and the private endpoint
are historical configuration until a live preflight confirms them. Starting the
VM requires the exact Nebius CLI command and the installed Compute skill's
confirmation gate. Operator-managed spend remains unknown; no billing lookup or
new monetary cap is introduced by this procedure.

Activation must bind reviewed source and logging-plan hashes, private input and
journal directories, finite startup/helper/collection bounds, the cached deployed
image identity, and the existing canonical Compose credential binding. A missing
binding or experiment permission stops the operation for a separately reviewed
access delta. Do not guess credentials, initialize accounts or upgrade the image.
The original [October 2 maintenance package](../operations/mlflow-readiness.md)
remains historical and is not executed unchanged for this narrower operation.

Full request/readback receipts and exact verified artifact bytes belong in a new
private directory under root `outputs/`, outside disposable worktrees. Public
evidence exposes only safe identity, counts, verification status and receipt
hashes. AC-01 remains pending until the authenticated writer and independent
reader agree and retained evidence verifies the original lineage. Inert tests,
a logging-plan hash or a tracking run ID alone do not close that acceptance.
