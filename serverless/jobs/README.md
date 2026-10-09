# Serverless Jobs

Batch utilities for synthetic rule experiments, public-data acquisition/preparation
and governed LightGBM execution. Synthetic labels and detector scores are not
verified real-market manipulation or compliance decisions.

Agent-initiated model workloads, including training/scoring/evaluation rehearsals,
run on Nebius under the [execution policy](../../docs/ml/model-validation-execution-policy.md).
Local commands below describe retained rule-simulation or inert packaging
capabilities; they are not authorization to run a model workload locally.

## Structured lifecycle logs

Jobs emit JSON lifecycle events with UTC timestamp, level, job type, event name
and a plain-language description. Timed phases emit `.started`, `.completed`
or `.failed` with `duration_ms`; failures retain exception type, not message.

```json
{"description":"Train LightGBM with the frozen hyperparameters, seed, class weighting, and early-stopping policy.","event":"model.train.started","job_type":"lightgbm-wave1","level":"INFO","run_id":"wave1-development-001","timestamp":"2026-08-27T00:00:00+00:00"}
```

Credential/password/secret/token-shaped field names are rejected; logs do not
include raw environment values, credentials or input payloads.
`PYTHONUNBUFFERED=1` exposes events immediately. Governed source provenance is
explicit, so the optional GitPython discovery warning is silenced.

LightGBM phases cover download/integrity, request/resource binding, fold isolation,
training, calibration, freezing, MLflow, evidence and publication. Synthetic jobs
cover planning, execution, artifact production, optional upload and outcome.

## Detector Tournament

From the repository root, the retained rule-runner argument form is:

```bash
python serverless/jobs/detector_tournament.py \
  --runs 100 \
  --scenarios normal_market,spoofing_like_wall,layering_like,quote_stuffing,liquidity_evaporation \
  --detectors spoofing_like,layering_like,quote_stuffing,liquidity_shock \
  --random-seed 42 \
  --difficulty-mix '{"easy":0.2,"medium":0.5,"hard":0.2,"adversarial":0.1}' \
  --output outputs/benchmark
```

`--runs` is the exact total, distributed through seeded scenario/difficulty
plans. Seed and difficulty affect simulation profiles. Every selected detector
uses attack-active truth; `normal_market` supplies negative controls.
Undefined precision/recall/F1 denominators remain null.

Outputs are `benchmark_report.md`, `metrics.csv`, `results.json` and
`charts/{f1_by_scenario,confidence_distribution,detection_latency}.png`.
Metrics include precision/recall/F1, simulated detection latency, specificity,
false-positive rate, temporal overlap and available event/participant/order/phase
attribution. See [exact formulas and limitations](../../docs/runtime/calculations-explanations.md#step-4--detector-tournament)
and [facade contracts](../../docs/architecture/ARD-0017-ai-detector-tournament.md).

## Synthetic Dataset Factory

```bash
python serverless/jobs/synthetic_dataset_factory.py \
  --samples 100 --output outputs/synthetic-dataset
```

Outputs are `events.jsonl`, `incidents.jsonl`, `labels.jsonl`, `manifest.json`
and `snapshots.parquet`; without Parquet dependencies the fallback is
`snapshots.parquet.jsonl`. Ground truth comes from synthetic scenario injection.

## Docker

Build from the repository root so shared backend code is available. Before any
Job-image build/upload/submission, apply the
[repository-length/digest preflight](../../docs/operations/digest-pinned-jobs.md#mandatory-preflight-for-every-new-job-image).
Local image tags are build handles, not approved Job deployment identities.

```bash
docker build -f serverless/jobs/Dockerfile -t nebius-market-abuse-jobs .
```

The retained rule-only container argument forms are:

```bash
docker run --rm -v "$PWD/outputs:/job/outputs" nebius-market-abuse-jobs
docker run --rm -v "$PWD/outputs:/job/outputs" nebius-market-abuse-jobs \
  python synthetic_dataset_factory.py --samples 100 --output /job/outputs/synthetic-dataset
```

### Governed public-market-data images

C0–C2 use the Python-only acquisition image, without Java or PyArrow:

```bash
docker build --platform linux/amd64 \
  -f serverless/jobs/Dockerfile.market-data-acquisition \
  -t lob-arena-market-data-acquisition:local .
docker run --rm lob-arena-market-data-acquisition:local acquire-s3 --help
```

C3–C4 use a distinct preparation image. Compile the platform-independent Java
control-plane JAR on the host; the image copies it with a JRE and never runs Gradle:

```bash
./scripts/prepare-market-data-control-plane.sh
docker build --platform linux/amd64 \
  -f serverless/jobs/Dockerfile.market-data-preparation \
  -t lob-arena-market-data-preparation:local .
docker run --rm lob-arena-market-data-preparation:local prepare-s3 --help
docker run --rm lob-arena-market-data-preparation:local project-s3 --help
```

`build/market-data/control-plane.jar` is ignored and admitted only to this
build context. C4 verifies C3 checkpoint envelopes and downloads only
`checkpoint.json` plus small `features/` members; it neither starts Java nor
downloads multi-gigabyte replay payloads. The help commands inspect arguments
without acquiring data or executing preparation.

## Notes

Resource, timeout, Job-count and applicable spend bounds must be reviewed before
cloud execution. Keep original execution identities and durable artifacts;
a build/import check is not a completed detector/model run.

## Smart Attack/Detect Batch

`run_batch_experiments.py` is also available through the compatibility wrapper
`run_batch_benchmark.py`:

```bash
python serverless/jobs/run_batch_experiments.py \
  --runs 1000 --batch-size 100 \
  --scenarios normal_market,spoofing_like_wall,layering_like,quote_stuffing,liquidity_evaporation \
  --random-seed 42 \
  --difficulty-mix '{"easy":0.2,"medium":0.5,"hard":0.2,"adversarial":0.1}' \
  --output outputs/serverless-batch
```

Outputs are `order_book_events.jsonl`, `trades.jsonl`, `attack_labels.jsonl`,
`blue_team_alerts.jsonl`, `detector_metrics.csv`, `generated_report.md` and
`manifest.json`. The facade normalizes this artifact-heavy path and the
lightweight tournament; it does not introduce a third runner.

## Experiment Job Config Rendering

The generic `render_job_config.py` path and synthetic YAML examples retain the
old repository/tag contract. They are **inspection-only historical examples**
under [current image policy](../../docs/operations/digest-pinned-jobs.md).
Passing a digest to the old tag parser does not create a valid pinned Job.
Do not submit `nebius_job_config.yaml`, `job_config.example.yaml` or
`dataset_job_config.example.yaml` as current approved execution packages.

The [historical revision](https://github.com/khab40/lob-arena/blob/d896efe8ca501c1ef8e6c63442f3433948a6405e/serverless/jobs/README.md#experiment-job-config-rendering)
preserves the old renderer invocation. Governed profiles and independently
reviewed execution packages have separate request identities.

## Governed LightGBM Wave 1 profile

The CPU-only Wave 1 profile renders a digest object. Set the two variables below
from the reviewed package: `APPROVED_JOB_IMAGE` is the exact immutable image
that passed preflight; `APPROVED_RELEASE_STAGING_URI` is its authorized staging
prefix. This command renders configuration; it does not submit a Job.

```bash
python serverless/jobs/render_job_config.py \
  --workload lightgbm-wave1 \
  --experiment-id wave1-development-001 \
  --image "$APPROVED_JOB_IMAGE" \
  --input-uri "$APPROVED_RELEASE_STAGING_URI" \
  --work-root /job/wave1 \
  --endpoint-url https://storage.eu-north1.nebius.cloud \
  --rendered-path outputs/lightgbm-wave1/job.yaml
```

Wave 1 uses S3 API staging, never an Object Storage filesystem volume. It verifies
`SUCCESS`/`checksums.sha256`, runs inside the authorized Job, verifies outputs,
uploads exact artifacts and publishes `SUCCESS` last. `NEBIUS_VOLUME` fails
closed for this profile.

Submission accepts MysteryBox IDs through
`NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID`,
`NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID`,
`NEBIUS_MLFLOW_USERNAME_SECRET_ID`, `NEBIUS_MLFLOW_PASSWORD_SECRET_ID`
and the optional session-token secret ID. Inline access keys fail before cloud
calls. Staged request evidence, applicable execution bounds and the exact
operator-reviewed dry-run SHA-256 are required. Follow the
[LightGBM runbook](../../docs/ml/lightgbm-v1-runbook.md) for staging, submission,
monitoring, independent collection and exit gates.
