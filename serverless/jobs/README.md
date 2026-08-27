# Serverless Jobs

Nebius-oriented batch jobs for offline synthetic experiments.

These jobs are educational simulation utilities. They do not evaluate real
market manipulation, do not provide trading signals, and should not be used for
compliance decisions.

## Structured lifecycle logs

Executable Jobs emit one JSON object per lifecycle event. Each record includes
UTC timestamp, level, job type, stable event name, and a plain-language
description of the work. Timed phases produce `.started`, `.completed`, or
`.failed` events and include `duration_ms`; failures include only the exception
type, never the exception message.

Example:

```json
{"description":"Train LightGBM with the frozen hyperparameters, seed, class weighting, and early-stopping policy.","event":"model.train.started","job_type":"lightgbm-wave1","level":"INFO","run_id":"wave1-development-001","timestamp":"2026-08-27T00:00:00+00:00"}
```

The LightGBM profile explains input download/checksum verification, request and
resource binding, fold isolation, training, calibration, candidate freezing,
MLflow publication, evidence finalization, and Object Storage publication. The
synthetic batch, tournament, and dataset jobs log their deterministic plan,
execution, artifact production, optional upload, and final outcome.

Credential-, password-, secret-, and token-shaped field names are rejected by
the logging helper. Logs never include raw environment values, input payloads,
MLflow credentials, or exception messages. `PYTHONUNBUFFERED=1` makes events
visible immediately in cloud logs; the optional GitPython discovery warning is
silenced because governed source provenance is logged explicitly.

## Detector Tournament

Runs synthetic simulations, launches labeled scenario families, evaluates
detector outputs, and writes benchmark artifacts.

```bash
python serverless/jobs/detector_tournament.py \
  --runs 100 \
  --scenarios spoofing_like_wall,layering_like,quote_stuffing,liquidity_evaporation \
  --detectors spoofing_like,layering_like,quote_stuffing,liquidity_shock \
  --random-seed 42 \
  --difficulty-mix '{"easy":0.2,"medium":0.5,"hard":0.2,"adversarial":0.1}' \
  --output outputs/benchmark
```

`--runs` is the exact total scenario count, distributed reproducibly across
scenario families and difficulty levels.

Outputs:

- `benchmark_report.md`
- `metrics.csv`
- `results.json`
- `charts/f1_by_scenario.png`
- `charts/confidence_distribution.png`
- `charts/detection_latency.png`

Metrics:

- precision
- recall
- F1
- average detection latency in milliseconds
- specificity and false-positive rate for normal-market negative controls
- temporal overlap, event attribution, participant/order attribution, and phase detection

## Synthetic Dataset Factory

Generates labeled synthetic event, snapshot, incident, and label artifacts.

```bash
python serverless/jobs/synthetic_dataset_factory.py \
  --samples 100 \
  --output outputs/synthetic-dataset
```

Outputs:

- `events.jsonl`
- `incidents.jsonl`
- `labels.jsonl`
- `snapshots.parquet` when Parquet dependencies are available
- `snapshots.parquet.jsonl` when Parquet dependencies are unavailable
- `manifest.json`

## Docker

Build from the repository root so the image can copy the shared backend
simulator code:

```bash
docker build -f serverless/jobs/Dockerfile -t nebius-market-abuse-jobs .
```

Run the detector tournament:

```bash
docker run --rm -v "$PWD/outputs:/job/outputs" nebius-market-abuse-jobs
```

Run the dataset factory:

```bash
docker run --rm -v "$PWD/outputs:/job/outputs" nebius-market-abuse-jobs \
  python synthetic_dataset_factory.py --samples 100 --output /job/outputs/synthetic-dataset
```

## Notes

- Keep run counts small while testing on Nebius to control time and cost.
- The scripts reuse the backend synthetic simulator and deterministic detector
  engine.
- The generated labels are synthetic ground truth from scenario injection, not
  real surveillance labels.

## Smart Attack/Detect Batch

The Phase 4 runner lives in `serverless/jobs/run_batch_experiments.py` and is
also available through the compatibility wrapper `run_batch_benchmark.py`.

```bash
python serverless/jobs/run_batch_experiments.py \
  --runs 1000 \
  --batch-size 100 \
  --scenarios normal_market,spoofing_like_wall,layering_like,quote_stuffing,liquidity_evaporation \
  --random-seed 42 \
  --difficulty-mix '{"easy":0.2,"medium":0.5,"hard":0.2,"adversarial":0.1}' \
  --output outputs/serverless-batch
```

Outputs:

- `order_book_events.jsonl`
- `trades.jsonl`
- `attack_labels.jsonl`
- `blue_team_alerts.jsonl`
- `detector_metrics.csv`
- `generated_report.md`
- `manifest.json`

## Experiment Job Config Rendering

Use the existing `serverless/jobs/nebius_job_config.yaml` as the template for
real Nebius Serverless Job submission. Experiment-specific parameters are
rendered with:

```bash
python serverless/jobs/render_job_config.py \
  --experiment-id EXP-001 \
  --runs 100 \
  --batch-size 10 \
  --scenarios normal_market,spoofing_like_wall \
  --image ghcr.io/your-org/lob-arena-jobs:latest
```

The rendered config is written to
`outputs/experiments/<experiment_id>/nebius_job_config.rendered.yaml` and
overrides the runner args, scenarios, output directory, and image
repository/tag without creating a parallel Dockerfile or job template.

## Governed LightGBM Wave 1 profile

The same Jobs image now includes the CPU-only governed LightGBM runner. Its
profile requires an immutable image digest:

```bash
python serverless/jobs/render_job_config.py \
  --workload lightgbm-wave1 \
  --experiment-id wave1-development-001 \
  --image registry.eu-north1.nebius.cloud/PROJECT/jobs@sha256:DIGEST \
  --input-uri s3://aimada-wave1-dev-e00g6zvxpr00/releases/RELEASE_ID/staging \
  --work-root /job/wave1 \
  --endpoint-url https://storage.eu-north1.nebius.cloud \
  --rendered-path outputs/lightgbm-wave1/job.yaml
```

Wave 1 never attaches an Object Storage filesystem volume. The container lists
only the requested prefix, downloads it to ephemeral job disk with S3 API
calls, verifies `SUCCESS` and `checksums.sha256`, runs the local-path model
runner, verifies the result, uploads objects through the S3 API, and publishes
`SUCCESS` last. `NEBIUS_VOLUME` therefore makes Wave 1 submission fail closed.

The submission helpers accept only MysteryBox-backed IDs through
`NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID`,
`NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID`, `NEBIUS_MLFLOW_USERNAME_SECRET_ID`,
`NEBIUS_MLFLOW_PASSWORD_SECRET_ID`, and the optional session-token secret ID.
Inline access-key values cause submission to fail before invoking the Nebius
CLI. A Wave 1 submission also requires the staged request evidence, reconciled
spend and Job count, plus the SHA-256 of the Operator-reviewed dry run. The G4
monitor verifies the actual Job resources and cancels at 15 minutes. See the
[LightGBM runbook](../../docs/lightgbm-v1-runbook.md) for the complete staged
submission, monitoring, S3 collection, and exit-gate commands.
