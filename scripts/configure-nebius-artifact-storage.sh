#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"
PROJECT_ID=""
TENANT_ID=""
BUCKET_NAME=""
SERVICE_ACCOUNT_ID=""
ACCESS_KEY_SECRET_ID=""
SECRET_KEY_SECRET_ID=""
REGION="eu-north1"
APPLY=false
RESTART=false

usage() {
  printf '%s\n' \
    "Usage: $0 --project-id ID --bucket-name NAME [options]" \
    "" \
    "This helper never creates broad IAM grants or inline access keys." \
    "Provision the approved least-privilege identity and MysteryBox secrets in G3," \
    "then pass only their non-secret resource IDs." \
    "" \
    "Options:" \
    "  --env-file PATH" \
    "  --tenant-id ID (accepted for legacy dry runs; no group grant is made)" \
    "  --service-account-id ID" \
    "  --access-key-secret-id ID" \
    "  --secret-key-secret-id ID" \
    "  --region REGION (default: eu-north1)" \
    "  --apply"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file) ENV_FILE="$2"; shift 2 ;;
    --project-id) PROJECT_ID="$2"; shift 2 ;;
    --tenant-id) TENANT_ID="$2"; shift 2 ;;
    --bucket-name) BUCKET_NAME="$2"; shift 2 ;;
    --service-account-id) SERVICE_ACCOUNT_ID="$2"; shift 2 ;;
    --access-key-secret-id) ACCESS_KEY_SECRET_ID="$2"; shift 2 ;;
    --secret-key-secret-id) SECRET_KEY_SECRET_ID="$2"; shift 2 ;;
    --region) REGION="$2"; shift 2 ;;
    --apply) APPLY=true; shift ;;
    --restart) RESTART=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown argument: %s\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
done

[[ -n "${PROJECT_ID}" ]] || { printf '%s\n' '--project-id is required' >&2; exit 2; }
[[ -n "${BUCKET_NAME}" ]] || { printf '%s\n' '--bucket-name is required' >&2; exit 2; }
[[ "${REGION}" == "eu-north1" ]] || { printf '%s\n' 'Wave 1 region must be eu-north1' >&2; exit 2; }
[[ "${RESTART}" != "true" || "${APPLY}" == "true" ]] || { printf '%s\n' '--restart requires --apply' >&2; exit 2; }

printf '%s\n' \
  "Nebius artifact storage binding plan:" \
  "  - project: ${PROJECT_ID}" \
  "  - private bucket: ${BUCKET_NAME}" \
  "  - region: ${REGION}" \
  "  - IAM creation: external G3 least-privilege step" \
  "  - credentials: MysteryBox secret references only"

if [[ "${APPLY}" != "true" ]]; then
  printf '%s\n' 'Dry-run only. No Nebius or local state changed.'
  exit 0
fi

[[ -f "${ENV_FILE}" ]] || { printf 'Missing env file: %s\n' "${ENV_FILE}" >&2; exit 2; }
[[ -n "${SERVICE_ACCOUNT_ID}" ]] || { printf '%s\n' '--service-account-id is required with --apply' >&2; exit 2; }
[[ -n "${ACCESS_KEY_SECRET_ID}" ]] || { printf '%s\n' '--access-key-secret-id is required with --apply' >&2; exit 2; }
[[ -n "${SECRET_KEY_SECRET_ID}" ]] || { printf '%s\n' '--secret-key-secret-id is required with --apply' >&2; exit 2; }

WORK="$(mktemp "${ENV_FILE}.work.XXXXXX")"
cleanup() { rm -f "${WORK}"; }
trap cleanup EXIT
cp "${ENV_FILE}" "${WORK}"

set_env_value() {
  local key="$1" value="$2" next
  next="$(mktemp "${ENV_FILE}.next.XXXXXX")"
  awk -v target="${key}" -v replacement="${value}" '
    BEGIN { found = 0 }
    index($0, target "=") == 1 { print target "=" replacement; found = 1; next }
    { print }
    END { if (!found) print target "=" replacement }
  ' "${WORK}" > "${next}"
  mv "${next}" "${WORK}"
}

set_env_value NEBIUS_PARENT_ID "${PROJECT_ID}"
set_env_value NEBIUS_JOB_OUTPUT_URI "s3://${BUCKET_NAME}/aimada"
set_env_value NEBIUS_OBJECT_STORAGE_ENDPOINT_URL "https://storage.${REGION}.nebius.cloud"
set_env_value NEBIUS_OBJECT_STORAGE_REGION "${REGION}"
set_env_value NEBIUS_EVIDENCE_ARCHIVE_ENABLED "true"
set_env_value NEBIUS_OBJECT_STORAGE_SERVICE_ACCOUNT_ID "${SERVICE_ACCOUNT_ID}"
set_env_value NEBIUS_OBJECT_STORAGE_ACCESS_KEY_SECRET_ID "${ACCESS_KEY_SECRET_ID}"
set_env_value NEBIUS_OBJECT_STORAGE_SECRET_KEY_SECRET_ID "${SECRET_KEY_SECRET_ID}"
set_env_value NEBIUS_OBJECT_STORAGE_ACCESS_KEY_ID ""
set_env_value NEBIUS_OBJECT_STORAGE_SECRET_ACCESS_KEY ""
set_env_value NEBIUS_OBJECT_STORAGE_SESSION_TOKEN ""

chmod 600 "${WORK}"
mv "${WORK}" "${ENV_FILE}"
trap - EXIT
printf '%s\n' 'Local binding updated with non-secret resource references only.'
if [[ "${RESTART}" == "true" ]]; then
  printf '%s\n' 'Restart was not performed: inject MysteryBox references through the Job control plane in G3.' >&2
  exit 2
fi
