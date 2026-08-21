#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
IMAGE_NAMESPACE="${IMAGE_NAMESPACE:-ghcr.io/khab40}"
TAG="${TAG:-latest}"
PLATFORM="${PLATFORM:-linux/amd64}"
PUSH="${PUSH:-false}"
SMOKE="${SMOKE:-false}"
TARGET="${TARGET:-all}"

if [[ "${TARGET}" != "all" && "${TARGET}" != "endpoint" && "${TARGET}" != "jobs" ]]; then
  printf "%s\n" "TARGET must be one of: all, endpoint, jobs" >&2
  exit 2
fi

ENDPOINT_IMAGE="${ENDPOINT_IMAGE:-${NEBIUS_ENDPOINT_IMAGE:-${IMAGE_NAMESPACE}/lob-arena-endpoint:${TAG}}}"
JOBS_IMAGE="${JOBS_IMAGE:-${NEBIUS_JOB_IMAGE:-${IMAGE_NAMESPACE}/lob-arena-jobs:${TAG}}}"

if [[ "${ENDPOINT_IMAGE}" == "${JOBS_IMAGE}" ]]; then
  printf "%s\n" "Endpoint and Jobs image tags must be different: ${ENDPOINT_IMAGE}" >&2
  exit 2
fi

endpoint_args=(
  docker build
  --platform "${PLATFORM}"
  -f "${ROOT_DIR}/serverless/endpoint/Dockerfile"
  -t "${ENDPOINT_IMAGE}"
  "${ROOT_DIR}/serverless/endpoint"
)

jobs_args=(
  docker build
  --platform "${PLATFORM}"
  -f "${ROOT_DIR}/serverless/jobs/Dockerfile"
  -t "${JOBS_IMAGE}"
  "${ROOT_DIR}"
)

if [[ "${TARGET}" != "jobs" ]]; then
  printf "%s\n" "Building endpoint image: ${ENDPOINT_IMAGE}"
  "${endpoint_args[@]}"
fi

if [[ "${TARGET}" != "endpoint" ]]; then
  printf "%s\n" "Building jobs image: ${JOBS_IMAGE}"
  "${jobs_args[@]}"
fi

if [[ "${SMOKE}" == "true" ]]; then
  if [[ "${TARGET}" != "jobs" ]]; then
    printf "%s\n" "Smoke checking endpoint image metadata"
    docker image inspect "${ENDPOINT_IMAGE}" >/dev/null
  fi

  if [[ "${TARGET}" != "endpoint" ]]; then
    printf "%s\n" "Smoke checking jobs image metadata"
    docker image inspect "${JOBS_IMAGE}" >/dev/null
    docker run --rm --entrypoint python "${JOBS_IMAGE}" -c \
      "import lightgbm, mlflow, pyarrow; from app.ml.lightgbm.cloud_runner import execute_wave1_request; print('wave1-ok')"
  fi
fi

if [[ "${PUSH}" == "true" ]]; then
  if [[ "${TARGET}" != "jobs" ]]; then
    printf "%s\n" "Pushing endpoint image: ${ENDPOINT_IMAGE}"
    docker push "${ENDPOINT_IMAGE}"
  fi

  if [[ "${TARGET}" != "endpoint" ]]; then
    printf "%s\n" "Pushing jobs image: ${JOBS_IMAGE}"
    docker push "${JOBS_IMAGE}"
  fi
fi

printf "%s\n" "Serverless image build complete"
