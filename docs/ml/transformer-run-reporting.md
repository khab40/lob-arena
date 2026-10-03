# Per-run research reports — 2026-10-03

[Story #24](https://github.com/khab40/lob-arena/issues/24),
[Project #3](https://github.com/users/khab40/projects/3).
The operator requested basic results and epoch plots after each experiment,
with MLflow integration later. This extends the existing research evidence scope.

As a researcher,
I want a readable Markdown report after each verified training run,
So that I can inspect learning behavior and compare experiments before MLflow is available.

Actor: researcher. Goal: inspect saved experiment results. Value: faster research decisions.
Out of scope: new model execution, new tuning, cloud permissions, online MLflow,
final-test access and changes to frozen runtime/evidence.
Verification: inert artifact fixtures, completed-run backfill and rendered chart inspection.

```gherkin
Feature: Verified experiment reports
  Scenario: Report a completed training run
    Given independently verified training artifacts with epoch history
    When the run report is generated
    Then one Markdown entry point shows configuration, metrics and checkpoint identity
    And loss and selection F1 plots use the recorded epochs
    And saved selection predictions determine the confusion matrix

  Scenario: Reject incomplete or altered evidence
    Given missing verification or an artifact that differs from its recorded checksum
    When report generation is requested
    Then no successful experiment report is published

  Scenario: Recover presentation without repeating collection
    Given completed collection and a failed report render
    When reporting is retried
    Then only local saved artifacts are read
    And no model, provider or S3 operation is repeated
```

Plan: add an offline generator plus a collect-and-report wrapper; validate local
receipt bindings and consumed artifact hashes before plotting; generate one
`report.md` with adjacent PNG plots and exact epoch values. Backfill the four
completed trials and link them from an index. Keep the original operator helper,
immutable authorizations and GPU image unchanged. The wrapper runs the existing
collector once only when no verification receipt exists; rendering can be retried
separately without cloud access.

Plots: weighted training loss, raw selection log loss and selection F1 by epoch,
with the selected checkpoint marked; a count-based confusion matrix at raw
probability 0.5. Training and selection losses have different weighting, so the
report does not interpret their gap as a direct overfitting measure. Calibration,
precision-recall comparison and inference-latency plots follow measured evidence
from later stages. Reports preserve source hashes and MLflow reconciliation status.

## Local generation and automatic collection handoff

Install `scripts/requirements-transformer-report.txt` into a reporting-only Python
environment. The original SDK/operator environment and GPU image are unchanged.
The renderer uses [Matplotlib/Agg PNG export](https://matplotlib.org/stable/api/_as_gen/matplotlib.figure.Figure.savefig.html).
One Markdown entry point links two adjacent PNG files so GitHub and common editors
can display the charts; keep the report directory together when copying it.

```sh
# Read already-collected evidence; no network, credentials or model execution.
rtk proxy REPORT_PYTHON scripts/transformer_research_report.py \
  --evidence outputs/transformer-startup-repair-20261003/p2/execution \
  --slot search-128-0003
```

Replace `REPORT_PYTHON` with the reporting environment's Python executable.
Default output: `<evidence>/reports/<slot>/report.md`, accompanied by PNGs and
`report-manifest.json`; `<evidence>/reports/index.md` is refreshed after each run.
Use `--output <new-directory>` for a separate export without changing that index.
An identical rerun reuses the checked report. A changed renderer/input or damaged
report requires a new output directory, preserving the previous report.

For future **already-authorized** training runs, use the same command with
`--collect --operator-python <pinned-operator-python> --bundle <bundle.json>
--source-receipt <receipt.json>`, retaining the collector's required `PYTHONPATH`.
This invokes the existing collector once, then generates the report automatically.
It requires the usual completed Job and SUCCESS receipt; it cannot create a Job.
If verification already exists, it performs reporting only. A partial collection
requires reconciliation instead of an automatic repeat. Plotting dependencies are
imported before collection, so a missing renderer fails before cloud access.

The report checks consumed JSON hashes/sizes and receipt bindings, never loads
checkpoint weights, and never changes the authoritative verification receipt.
If rendering fails after collection, `report_status=failed` is separate from the
retained successful verification. Retry reporting only; do not rerun the Job.

Online MLflow will later receive the retained metrics, parameters and artifacts.
These reports are a readable view of that evidence, not a second tuning protocol.
Current support is training/search/confirmation runs; future calibration/inference
reports must use their measured stage-specific schema rather than fabricate curves.

## Verified backfill

The [four completed trials](experiments/transformer-grid-20261003/index.md) now
have reports and plots generated from their retained verified artifacts.
Fourteen inert reporting tests pass, including altered/missing evidence, threshold
zero, actual PNG output, idempotent reuse, rendering failure and an early collector
failure before artifact creation. An exclusive attempt receipt prevents automatic
recollection in that last case. Independent review and rendered inspection passed.
No GPU image, operator helper, prior authorization or original run artifact changed.
