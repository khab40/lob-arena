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
  script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  exec python "${script_dir}/submit_nebius_job.py" --workload lightgbm-wave1
fi

JOB_COMMAND="/job/serverless/jobs/run_batch_experiments.py --runs ${RUNS} --batch-size ${BATCH_SIZE} --scenarios ${SCENARIOS} --output ${OUTPUT_DIR}${S3_OUTPUT_URI:+ --s3-output-uri ${S3_OUTPUT_URI}}${S3_ENDPOINT_URL:+ --s3-endpoint-url ${S3_ENDPOINT_URL}}"

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
