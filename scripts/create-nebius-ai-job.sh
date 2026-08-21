#!/usr/bin/env bash
set -euo pipefail

NAME="${NEBIUS_JOB_NAME:-market-abuse-smart-batch}"
IMAGE="${NEBIUS_JOB_IMAGE:-ghcr.io/khab40/lob-arena-jobs:latest}"
PLATFORM="${NEBIUS_JOB_PLATFORM:-cpu-d3}"
PRESET="${NEBIUS_JOB_PRESET:-4vcpu-16gb}"
DISK_SIZE="${NEBIUS_JOB_DISK_SIZE:-100Gi}"
TIMEOUT="${NEBIUS_JOB_TIMEOUT:-1h}"
RUNS="${NEBIUS_JOB_RUNS:-1000}"
BATCH_SIZE="${NEBIUS_JOB_BATCH_SIZE:-100}"
OUTPUT_DIR="${NEBIUS_JOB_OUTPUT_DIR:-/job/outputs/serverless-batch}"
SCENARIOS="${NEBIUS_JOB_SCENARIOS:-normal_market,spoofing_like_wall,layering_like,quote_stuffing,liquidity_evaporation}"
S3_OUTPUT_URI="${NEBIUS_JOB_OUTPUT_URI:-}"
S3_ENDPOINT_URL="${NEBIUS_OBJECT_STORAGE_ENDPOINT_URL:-}"
WORKLOAD="${NEBIUS_JOB_WORKLOAD:-synthetic}"
WAVE1_INPUT_URI="${NEBIUS_WAVE1_INPUT_URI:-}"

if [[ -n "${NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID:-}${NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY:-}${NEBIUS_OBJECT_STORAGE_SESSION_TOKEN:-}" ]]; then
  printf "%s\n" "Inline Object Storage credentials are forbidden; use MysteryBox secret IDs." >&2
  exit 2
fi

if [[ -z "${NEBIUS_SUBNET_ID:-}" ]]; then
  printf "%s\n" "NEBIUS_SUBNET_ID is required." >&2
  exit 2
fi

if [[ "${WORKLOAD}" == "lightgbm-wave1" ]]; then
  [[ "${IMAGE}" =~ @sha256:[0-9a-f]{64}$ ]] || {
    printf "%s\n" "LightGBM Wave 1 requires an immutable image digest." >&2
    exit 2
  }
  [[ "${WAVE1_INPUT_URI}" =~ ^s3://aimada-wave1-(dev|final)-e00g6zvxpr00/releases/[a-z0-9][a-z0-9-]{2,62}/staging/?$ ]] || {
    printf "%s\n" "NEBIUS_WAVE1_INPUT_URI must be an exact approved release prefix." >&2
    exit 2
  }
  [[ "${S3_ENDPOINT_URL%/}" == "https://storage.eu-north1.nebius.cloud" ]] || {
    printf "%s\n" "The approved eu-north1 Object Storage endpoint is required for Wave 1." >&2
    exit 2
  }
  [[ -n "${NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID:-}" && -n "${NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID:-}" ]] || {
    printf "%s\n" "Both MysteryBox credential selectors are required for Wave 1." >&2
    exit 2
  }
  [[ -z "${NEBIUS_VOLUME:-}" ]] || {
    printf "%s\n" "NEBIUS_VOLUME is forbidden for Wave 1; use S3 API staging." >&2
    exit 2
  }
  JOB_COMMAND="/job/serverless/jobs/run_lightgbm_wave1.py run-s3 --input-uri ${WAVE1_INPUT_URI} --work-root /job/wave1 --endpoint-url ${S3_ENDPOINT_URL}"
else
  JOB_COMMAND="/job/serverless/jobs/run_batch_experiments.py --runs ${RUNS} --batch-size ${BATCH_SIZE} --scenarios ${SCENARIOS} --output ${OUTPUT_DIR}${S3_OUTPUT_URI:+ --s3-output-uri ${S3_OUTPUT_URI}}${S3_ENDPOINT_URL:+ --s3-endpoint-url ${S3_ENDPOINT_URL}}"
fi

args=(
  nebius ai job create
  --name "${NAME}"
  --image "${IMAGE}"
  --container-command python
  --args "${JOB_COMMAND}"
  --platform "${PLATFORM}"
  --preset "${PRESET}"
  --disk-size "${DISK_SIZE}"
  --timeout "${TIMEOUT}"
  --subnet-id "${NEBIUS_SUBNET_ID}"
  --restart-policy never
  --format json
)

if [[ -n "${NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID:-}" ]]; then
  args+=(--env-secret "AWS_ACCESS_KEY_ID=${NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID}")
fi

if [[ -n "${NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID:-}" ]]; then
  args+=(--env-secret "AWS_SECRET_ACCESS_KEY=${NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID}")
fi

if [[ -n "${NEBIUS_OBJECT_STORAGE_SESSION_TOKEN_SECRET_ID:-}" ]]; then
  args+=(--env-secret "AWS_SESSION_TOKEN=${NEBIUS_OBJECT_STORAGE_SESSION_TOKEN_SECRET_ID}")
fi

args+=(--env "AWS_DEFAULT_REGION=${NEBIUS_OBJECT_STORAGE_REGION:-eu-north1}")
args+=(--env "AWS_EC2_METADATA_DISABLED=true")

if [[ -n "${NEBIUS_PARENT_ID:-}" ]]; then
  args+=(--parent-id "${NEBIUS_PARENT_ID}")
fi

if [[ -n "${NEBIUS_VOLUME:-}" && "${WORKLOAD}" != "lightgbm-wave1" ]]; then
  args+=(--volume "${NEBIUS_VOLUME}")
fi

printf "%s\n" "Creating Nebius Serverless AI Job ${NAME}"
"${args[@]}"
