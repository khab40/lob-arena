# ML architecture documentation review — 2026-09-21

Baseline: `origin/main` commit
`722622d15120c6ff2442bfdf08a09d3d9476c81b`.
Scope: ARD-0001, 0003, 0004, 0006, 0007, 0017, 0018 and 0022–0040,
the system overview and related ML use cases. This is a documentation/source
review, not a model validation run. No training, scoring, cloud mutation,
final-test access or candidate change is part of this work.

## Findings and disposition

| Finding | Correction and evidence |
| --- | --- |
| Transformer sequence materialization described as unstarted | ARD-0036 now separates implemented C4 64-step feature sequences from the absent classifier/trainer. [Projection code](../../backend/app/market_data/projections.py), [freeze implementation](../../backend/app/market_data/projection_freeze.py) |
| A universal governed loader / independently clean negatives implied | ARD-0028 now distinguishes the [general loader](../../backend/app/ml/lightgbm/data.py) from the explicit C4 research projection loader. C4 assumed-control labels are not adjudicated-clean production labels |
| Nonzero embargo implied for every protocol | ARD-0025 names protocol-specific embargo; [general v2](../../configs/benchmark/governed-benchmark-v2-float32.json) uses one date group, [public sample](../../configs/benchmark/nasdaq-public-sample-v1.json) zero |
| All trained models implied to retain all 60 columns | ARD-0029/0030 distinguish the complete source schema from hashed Wave 1 feature exclusions. [Runner](../../backend/app/ml/lightgbm/cloud_runner.py) selects the ordered subset; [G6 plan](../../configs/experiments/lightgbm-wave1/g6-campaign-20260907.json) excludes 29 state columns in the winner |
| Validation-only calibration could be read as independent quality proof | ARD-0031 and the use case state that fitting and reported calibration metrics reuse validation rows, also used for model/threshold selection. [Scoring implementation](../../backend/app/ml/lightgbm/scoring.py) |
| “Checkpoint” conflated training resume and evaluation recovery | Training saves one best-iteration booster; periodic boosting-state resume is absent. Scored and completed-release seals are different recovery artifacts. [Training](../../backend/app/ml/lightgbm/training.py), [scored checkpoint](../../backend/app/ml/lightgbm/g8_scored_checkpoint.py) |
| MLflow namespace/run logging could imply model-version promotion | ARD-0027/0031 and overview distinguish explicit artifact logging, namespace bootstrap and planned registration/aliases. [Tracking](../../backend/app/ml/lightgbm/tracking.py), [bootstrap](../../deployments/mlflow/bootstrap_resources.py) |
| MLflow version stale | Architecture and ARD-0027 now match checked-in 3.16.0 [Dockerfile](../../deployments/mlflow/Dockerfile); no running-service version inferred |
| Recovery described as unintegrated or native storage merely proposed | ARD-0001/0027/0031/0035/0038/0039/0040 and overview now distinguish integrated replacement code, native synthetic proof and pending production qualification |
| ITCH cloud preparation described as wholly future work | ARD-0007/0032 acknowledge acquisition, multi-date preparation and frozen projections; local ingestion adapter remains separate |
| Causal temporal features alone treated as sufficient cascade leakage protection | ARD-0037 adds a proposed producer-to-row training exclusion/cross-fitting requirement; this does not claim an implemented cascade |
| Existing Python detector adapter could imply live service integration | Serving use case makes absence of Java-stream wiring, feature parity service and inference endpoint explicit. [Detector](../../backend/app/ml/lightgbm/detector.py) is currently used by tests/package exports |
| Local model execution and remaining-credit queries remained in guidance | Runbook flags legacy model-execution examples; ARD-0034 uses current execution policy; ARD-0036 removes the credit-query instruction |
| Legacy confidence, tournament and artifact claims blurred with governed ML | ARD-0003/0004/0017 distinguish heuristic confidence, demo leaderboards and old artifact shapes from calibrated binary models and versioned releases |
| Historical Python stream ownership / LOBSTER-only replay list stale | ARD-0018 points to Java ownership; ARD-0023 includes ITCH and scheduled batch injection |

## Records checked without a substantive contract change

- ARD-0006: scenario labels remain separate from detector input; unreviewed
  history is not automatically clean. C4's separately declared research
  assumption is explained in the lifecycle guide.
- ARD-0022: normalized immutable source manifests and Java replay ownership
  agree with [ingestion](../../backend/app/data_ingestion) and its later ITCH extension.
- ARD-0026: model/training/calibration/prediction artifact identity and
  verification boundary agree with
  [contracts](../../backend/app/ml/lightgbm/contracts.py) and
  [release verification](../../backend/app/ml/lightgbm/release.py).
- ARD-0033: exact-trigger hybrid scheduling and separate truth remain the
  relevant batch contract; no change to immutable historical-participant behavior.

## Evidence and remaining work

The [native recovery receipt](../evidence/g8-native-recovery-20260917.json)
records synthetic fixtures, one scoring invocation, same-run authenticated
MLflow readback and an unresolved nonfatal provider mount error. Its initial
independent-reader denial is preserved; the later
[independent S3 receipt](../evidence/g8-independent-s3-readback-20260917.json)
verifies all 64 objects. These receipts do not prove production G8 quality.

The parallel G8 readiness PR #207 is outside this documentation branch.
Operational metadata/payload readiness evolves there. This review keeps the
conservative production gates from main and does not import unsigned approvals,
modify historical receipts, or change frozen candidate/threshold bytes.

The [use-case guide](../use-cases/ml-lifecycle.md) records unimplemented work:
Transformer training/checkpointing; label-independent sequence sampling and
missingness semantics; leakage-safe cascade fitting; verified registry-version
publication; online causal-feature parity, stream recovery, alert integration,
latency measurement and signed promotion. These are design requirements and
open implementation work, not capabilities delivered by this documentation PR.

Validation: 497 local links and 10 anchors resolve across 33 changed documents;
all nine new/changed Mermaid diagrams render. Source/plan inspection confirms
the nine G6 trials and 31-column selected subset. Whitespace checks pass. No
model workloads were run for this documentation change.
