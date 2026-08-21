#!/usr/bin/env bash
set -euo pipefail

PROJECT_ID="project-e00g6zvxpr00waz8t3y51k"
REGION="eu-north1"
CAMPAIGN_ID=""
PROFILE=""
APPLY=false
STATE_FILE=""

DEV_BUCKET="aimada-wave1-dev-e00g6zvxpr00"
FINAL_BUCKET="aimada-wave1-final-e00g6zvxpr00"
RESULTS_BUCKET="aimada-wave1-results-e00g6zvxpr00"
MLFLOW_BUCKET="aimada-mlflow-e00g6zvxpr00"

DEV_SA_NAME="aimada-wave1-dev-job"
FINAL_SA_NAME="aimada-wave1-final-job"
MLFLOW_SA_NAME="aimada-wave1-mlflow"

DEV_GROUP_NAME="aimada-wave1-dev-storage"
FINAL_GROUP_NAME="aimada-wave1-final-storage"
MLFLOW_GROUP_NAME="aimada-wave1-mlflow-storage"

DEV_KEY_NAME="aimada-wave1-dev-s3"
FINAL_KEY_NAME="aimada-wave1-final-s3"
MLFLOW_KEY_NAME="aimada-wave1-mlflow-s3"
DEV_ACCESS_ID_SECRET_NAME="aimada-wave1-dev-s3-access-id"
FINAL_ACCESS_ID_SECRET_NAME="aimada-wave1-final-s3-access-id"
MLFLOW_ACCESS_ID_SECRET_NAME="aimada-wave1-mlflow-s3-access-id"
KEY_EXPIRES_AT="2026-12-31T23:59:59Z"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

usage() {
  printf '%s\n' \
    "Usage: $0 --campaign-id ID [options]" \
    "" \
    "Dry-run is the default. Re-run with --apply to create the Wave 1 IAM/storage foundation." \
    "The script never retrieves or prints an access-key secret." \
    "" \
    "Options:" \
    "  --campaign-id ID    Required immutable Wave 1 campaign identifier" \
    "  --project-id ID     Default: ${PROJECT_ID}" \
    "  --region REGION     Must be eu-north1" \
    "  --profile NAME      Optional Nebius CLI profile" \
    "  --state-file PATH   Default: outputs/nebius/wave1-iam-<campaign>.json" \
    "  --apply             Perform cloud mutations" \
    "  -h, --help"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --campaign-id) CAMPAIGN_ID="${2:-}"; shift 2 ;;
    --project-id) PROJECT_ID="${2:-}"; shift 2 ;;
    --region) REGION="${2:-}"; shift 2 ;;
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --state-file) STATE_FILE="${2:-}"; shift 2 ;;
    --apply) APPLY=true; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "unknown argument: $1" ;;
  esac
done

[[ "${PROJECT_ID}" == "project-e00g6zvxpr00waz8t3y51k" ]] || die "Wave 1 project ID is fixed"
[[ "${REGION}" == "eu-north1" ]] || die "Wave 1 region must be eu-north1"
[[ "${CAMPAIGN_ID}" =~ ^[a-z0-9][a-z0-9-]{2,62}$ ]] || \
  die "--campaign-id must be 3-63 lowercase letters, digits, or hyphens"

if [[ -z "${STATE_FILE}" ]]; then
  STATE_FILE="${ROOT_DIR}/outputs/nebius/wave1-iam-${CAMPAIGN_ID}.json"
fi

print_plan() {
  printf '%s\n' \
    "Wave 1 least-privilege foundation:" \
    "  project: ${PROJECT_ID}" \
    "  region: ${REGION}" \
    "  campaign: ${CAMPAIGN_ID}" \
    "  key expiration: ${KEY_EXPIRES_AT}" \
    "" \
    "  development service account:" \
    "    read s3://${DEV_BUCKET}/releases/*" \
    "    edit s3://${RESULTS_BUCKET}/campaigns/${CAMPAIGN_ID}/development/*" \
    "    no policy on ${FINAL_BUCKET}" \
    "" \
    "  final service account:" \
    "    read s3://${FINAL_BUCKET}/releases/*" \
    "    read s3://${RESULTS_BUCKET}/campaigns/${CAMPAIGN_ID}/development/*" \
    "    edit s3://${RESULTS_BUCKET}/campaigns/${CAMPAIGN_ID}/final/*" \
    "    access key deactivated until signed final authorization" \
    "" \
    "  MLflow service account:" \
    "    edit s3://${MLFLOW_BUCKET}/artifacts/*" \
    "" \
    "  controls:" \
    "    custom groups only; no default editors membership" \
    "    S3 secrets delivered directly to SecretStash/MysteryBox" \
    "    prefix-scoped S3 API staging; no Object Storage filesystem mounts" \
    "    Standard storage, versioning, mutating-object audit logs" \
    "    incomplete multipart uploads removed after one day"
}

print_plan
if [[ "${APPLY}" != "true" ]]; then
  printf '%s\n' "" "Dry-run only. No Nebius or local state changed." \
    "Apply with:" \
    "  $0 --campaign-id ${CAMPAIGN_ID}${PROFILE:+ --profile ${PROFILE}} --apply"
  exit 0
fi

command -v nebius >/dev/null 2>&1 || die "nebius CLI is required"
command -v jq >/dev/null 2>&1 || die "jq is required"

nb() {
  if [[ -n "${PROFILE}" ]]; then
    nebius "$@" --profile "${PROFILE}" --no-progress --color=false
  else
    nebius "$@" --no-progress --color=false
  fi
}

lookup_by_name() {
  local output status
  set +e
  output="$(nb "$@" 2>&1)"
  status=$?
  set -e
  if [[ ${status} -eq 0 ]]; then
    printf '%s' "${output}"
    return 0
  fi
  if [[ "${output}" == *"code = NotFound"* || "${output}" == *"NOT_FOUND"* ]]; then
    return 1
  fi
  printf '%s\n' "${output}" >&2
  printf '%s\n' "ERROR: Nebius lookup failed; no create fallback was attempted" >&2
  return 70
}

json_id() {
  jq -er '.metadata.id' <<<"$1"
}

ensure_service_account() {
  local name="$1" description="$2" resource lookup_status=0
  resource="$(lookup_by_name iam service-account get-by-name \
    --parent-id "${PROJECT_ID}" --name "${name}" --format json)" || lookup_status=$?
  if [[ ${lookup_status} -eq 0 ]]; then
    printf 'Reusing service account %s\n' "${name}" >&2
  elif [[ ${lookup_status} -eq 1 ]]; then
    resource="$(nb iam service-account create \
      --parent-id "${PROJECT_ID}" \
      --name "${name}" \
      --description "${description}" \
      --labels "wave=1,managed-by=aimada-bootstrap" \
      --format json)"
    printf 'Created service account %s\n' "${name}" >&2
  else
    return "${lookup_status}"
  fi
  json_id "${resource}"
}

ensure_group() {
  local tenant_id="$1" name="$2" resource lookup_status=0
  resource="$(lookup_by_name iam group get-by-name \
    --parent-id "${tenant_id}" --name "${name}" --format json)" || lookup_status=$?
  if [[ ${lookup_status} -eq 0 ]]; then
    printf 'Reusing IAM group %s\n' "${name}" >&2
  elif [[ ${lookup_status} -eq 1 ]]; then
    resource="$(nb iam group create \
      --parent-id "${tenant_id}" \
      --name "${name}" \
      --labels "wave=1,managed-by=aimada-bootstrap" \
      --format json)"
    printf 'Created IAM group %s\n' "${name}" >&2
  else
    return "${lookup_status}"
  fi
  json_id "${resource}"
}

ensure_membership() {
  local group_id="$1" service_account_id="$2" memberships
  memberships="$(nb iam group-membership list-member-of \
    --subject-id "${service_account_id}" --page-size 100 --format json)"
  if jq -e --arg group_id "${group_id}" \
      'any(.items[]?; (.metadata.id // .spec.group_id // .group_id) == $group_id)' \
      <<<"${memberships}" >/dev/null; then
    printf 'Reusing membership %s -> %s\n' "${service_account_id}" "${group_id}" >&2
    return
  fi
  nb iam group-membership create \
    --parent-id "${group_id}" \
    --member-id "${service_account_id}" \
    --format json >/dev/null
  printf 'Created membership %s -> %s\n' "${service_account_id}" "${group_id}" >&2
}

ensure_access_key() {
  local service_account_id="$1" name="$2" resource existing
  existing="$(nb iam v2 access-key list-by-account \
    --account-service-account-id "${service_account_id}" --page-size 100 --format json)"
  resource="$(jq -cer --arg name "${name}" \
    '[.items[]? | select(.metadata.name == $name and ((.status.state // "") | ascii_downcase) != "deleted")][0] // empty' \
    <<<"${existing}" 2>/dev/null || true)"
  if [[ -n "${resource}" ]]; then
    printf 'Reusing access key %s\n' "${name}" >&2
  else
    resource="$(nb iam v2 access-key create \
      --parent-id "${PROJECT_ID}" \
      --name "${name}" \
      --account-service-account-id "${service_account_id}" \
      --description "Wave 1 S3 key; expires with approved research campaign" \
      --expires-at "${KEY_EXPIRES_AT}" \
      --secret-delivery-mode mystery_box \
      --labels "wave=1,managed-by=aimada-bootstrap" \
      --format json)"
    printf 'Created access key %s directly in SecretStash/MysteryBox\n' "${name}" >&2
  fi
  jq -e '(.status.secret_reference_id // "") != ""' <<<"${resource}" >/dev/null || \
    die "access key ${name} is not MysteryBox-backed"
  printf '%s' "${resource}"
}

ensure_value_secret() {
  local name="$1" value="$2" resource lookup_status=0
  resource="$(lookup_by_name mysterybox secret get-by-name \
    --parent-id "${PROJECT_ID}" --name "${name}" --format json)" || lookup_status=$?
  if [[ ${lookup_status} -eq 0 ]]; then
    printf 'Reusing MysteryBox environment secret %s\n' "${name}" >&2
  elif [[ ${lookup_status} -eq 1 ]]; then
    resource="$({
      request_file="$(mktemp)"
      trap 'rm -f "${request_file}"' EXIT
      umask 077
      jq -n \
        --arg parent_id "${PROJECT_ID}" \
        --arg name "${name}" \
        --arg value "${value}" \
        '{
          metadata:{parent_id:$parent_id,name:$name,labels:{wave:"1","managed-by":"aimada-bootstrap"}},
          spec:{
            description:"Wave 1 AWS access-key ID for AI Job environment injection",
            secret_version:{
              description:"Managed access-key ID value",
              payload:[{key:"secret",string_value:$value}],
              set_primary:true
            }
          }
        }' >"${request_file}"
      nb mysterybox secret create --file "${request_file}" --format json
    })"
    printf 'Created MysteryBox environment secret %s\n' "${name}" >&2
  else
    return "${lookup_status}"
  fi
  json_id "${resource}"
}

ensure_final_key_inactive() {
  local resource="$1" key_id state
  key_id="$(json_id "${resource}")"
  state="$(jq -r '.status.state // "" | ascii_downcase' <<<"${resource}")"
  if [[ "${state}" == "active" ]]; then
    nb iam v2 access-key deactivate --id "${key_id}" --format json >/dev/null
    printf 'Deactivated final access key %s\n' "${key_id}" >&2
  elif [[ "${state}" != "inactive" ]]; then
    die "final access key has unexpected state: ${state:-missing}"
  fi
  nb iam v2 access-key get --id "${key_id}" --format json
}

lifecycle_rules='[{"id":"abort-incomplete-multipart-after-1-day","status":"enabled","filter":{"prefix":""},"abort_incomplete_multipart_upload":{"days_after_initiation":1}}]'

ensure_bucket() {
  local name="$1" policy="$2" resource actual_policy desired_policy versioning lifecycle_ok lookup_status=0
  resource="$(lookup_by_name storage bucket get-by-name \
    --parent-id "${PROJECT_ID}" --name "${name}" --format json)" || lookup_status=$?
  if [[ ${lookup_status} -eq 0 ]]; then
    actual_policy="$(jq -cS '.spec.bucket_policy.rules // []' <<<"${resource}")"
    desired_policy="$(jq -cS '.' <<<"${policy}")"
    versioning="$(jq -r '.spec.versioning_policy // "" | ascii_downcase' <<<"${resource}")"
    lifecycle_ok="$(jq -r \
      'any(.spec.lifecycle_configuration.rules[]?;
        ((.status // "") | ascii_downcase) == "enabled" and
        (.abort_incomplete_multipart_upload.days_after_initiation // 0) == 1)' \
      <<<"${resource}")"
    [[ "${actual_policy}" == "${desired_policy}" ]] || \
      die "existing bucket ${name} has a different policy; refusing to overwrite it"
    [[ "${versioning}" == "enabled" ]] || die "existing bucket ${name} does not have versioning enabled"
    [[ "${lifecycle_ok}" == "true" ]] || \
      die "existing bucket ${name} lacks the approved incomplete-upload cleanup rule"
    printf 'Reusing governed bucket %s\n' "${name}" >&2
  elif [[ ${lookup_status} -eq 1 ]]; then
    resource="$(nb storage bucket create \
      --parent-id "${PROJECT_ID}" \
      --name "${name}" \
      --default-storage-class standard \
      --force-storage-class \
      --versioning-policy enabled \
      --object-audit-logging mutate_only \
      --lifecycle-configuration-rules "${lifecycle_rules}" \
      --bucket-policy-rules "${policy}" \
      --labels "wave=1,managed-by=aimada-bootstrap" \
      --format json)"
    printf 'Created governed bucket %s\n' "${name}" >&2
  else
    return "${lookup_status}"
  fi
  json_id "${resource}"
}

printf '%s\n' "" "Resolving tenant and provisioning resources..." >&2
project_json="$(nb iam project get "${PROJECT_ID}" --format json)"
tenant_id="$(jq -er '.metadata.parent_id' <<<"${project_json}")"

dev_sa_id="$(ensure_service_account "${DEV_SA_NAME}" "Wave 1 development Job Object Storage identity")"
final_sa_id="$(ensure_service_account "${FINAL_SA_NAME}" "Wave 1 final Job Object Storage identity")"
mlflow_sa_id="$(ensure_service_account "${MLFLOW_SA_NAME}" "Wave 1 shared MLflow VM Object Storage identity")"

dev_group_id="$(ensure_group "${tenant_id}" "${DEV_GROUP_NAME}")"
final_group_id="$(ensure_group "${tenant_id}" "${FINAL_GROUP_NAME}")"
mlflow_group_id="$(ensure_group "${tenant_id}" "${MLFLOW_GROUP_NAME}")"

ensure_membership "${dev_group_id}" "${dev_sa_id}"
ensure_membership "${final_group_id}" "${final_sa_id}"
ensure_membership "${mlflow_group_id}" "${mlflow_sa_id}"

dev_policy="$(jq -cn --arg group_id "${dev_group_id}" \
  '[{paths:["releases/*"],roles:["storage.viewer"],group_id:$group_id}]')"
final_policy="$(jq -cn --arg group_id "${final_group_id}" \
  '[{paths:["releases/*"],roles:["storage.viewer"],group_id:$group_id}]')"
results_policy="$(jq -cn \
  --arg dev_group "${dev_group_id}" \
  --arg final_group "${final_group_id}" \
  --arg dev_path "campaigns/${CAMPAIGN_ID}/development/*" \
  --arg final_path "campaigns/${CAMPAIGN_ID}/final/*" \
  '[
    {paths:[$dev_path],roles:["storage.object-editor"],group_id:$dev_group},
    {paths:[$dev_path],roles:["storage.viewer"],group_id:$final_group},
    {paths:[$final_path],roles:["storage.object-editor"],group_id:$final_group}
  ]')"
mlflow_policy="$(jq -cn --arg group_id "${mlflow_group_id}" \
  '[{paths:["artifacts/*"],roles:["storage.object-editor"],group_id:$group_id}]')"

dev_bucket_id="$(ensure_bucket "${DEV_BUCKET}" "${dev_policy}")"
final_bucket_id="$(ensure_bucket "${FINAL_BUCKET}" "${final_policy}")"
results_bucket_id="$(ensure_bucket "${RESULTS_BUCKET}" "${results_policy}")"
mlflow_bucket_id="$(ensure_bucket "${MLFLOW_BUCKET}" "${mlflow_policy}")"

dev_key="$(ensure_access_key "${dev_sa_id}" "${DEV_KEY_NAME}")"
final_key="$(ensure_access_key "${final_sa_id}" "${FINAL_KEY_NAME}")"
final_key="$(ensure_final_key_inactive "${final_key}")"
mlflow_key="$(ensure_access_key "${mlflow_sa_id}" "${MLFLOW_KEY_NAME}")"

dev_access_id_secret_ref="$(ensure_value_secret \
  "${DEV_ACCESS_ID_SECRET_NAME}-$(json_id "${dev_key}")" \
  "$(jq -er '.status.aws_access_key_id' <<<"${dev_key}")")"
final_access_id_secret_ref="$(ensure_value_secret \
  "${FINAL_ACCESS_ID_SECRET_NAME}-$(json_id "${final_key}")" \
  "$(jq -er '.status.aws_access_key_id' <<<"${final_key}")")"
mlflow_access_id_secret_ref="$(ensure_value_secret \
  "${MLFLOW_ACCESS_ID_SECRET_NAME}-$(json_id "${mlflow_key}")" \
  "$(jq -er '.status.aws_access_key_id' <<<"${mlflow_key}")")"

mkdir -p "$(dirname "${STATE_FILE}")"
umask 077
jq -n \
  --arg schema_version "nebius_wave1_iam_state_v2" \
  --arg project_id "${PROJECT_ID}" \
  --arg tenant_id "${tenant_id}" \
  --arg region "${REGION}" \
  --arg campaign_id "${CAMPAIGN_ID}" \
  --arg expires_at "${KEY_EXPIRES_AT}" \
  --arg dev_sa_id "${dev_sa_id}" --arg final_sa_id "${final_sa_id}" --arg mlflow_sa_id "${mlflow_sa_id}" \
  --arg dev_group_id "${dev_group_id}" --arg final_group_id "${final_group_id}" --arg mlflow_group_id "${mlflow_group_id}" \
  --arg dev_bucket_id "${dev_bucket_id}" --arg final_bucket_id "${final_bucket_id}" \
  --arg results_bucket_id "${results_bucket_id}" --arg mlflow_bucket_id "${mlflow_bucket_id}" \
  --arg dev_key_id "$(json_id "${dev_key}")" \
  --arg dev_access_id_secret_ref "${dev_access_id_secret_ref}" \
  --arg dev_secret_ref "$(jq -er '.status.secret_reference_id' <<<"${dev_key}")" \
  --arg final_key_id "$(json_id "${final_key}")" \
  --arg final_access_id_secret_ref "${final_access_id_secret_ref}" \
  --arg final_secret_ref "$(jq -er '.status.secret_reference_id' <<<"${final_key}")" \
  --arg final_state "$(jq -er '.status.state' <<<"${final_key}")" \
  --arg mlflow_key_id "$(json_id "${mlflow_key}")" \
  --arg mlflow_access_id_secret_ref "${mlflow_access_id_secret_ref}" \
  --arg mlflow_secret_ref "$(jq -er '.status.secret_reference_id' <<<"${mlflow_key}")" \
  --arg endpoint_url "https://storage.eu-north1.nebius.cloud" \
  --arg dev_input_prefix "s3://${DEV_BUCKET}/releases/" \
  --arg dev_result_prefix "s3://${RESULTS_BUCKET}/campaigns/${CAMPAIGN_ID}/development/" \
  --arg final_input_prefix "s3://${FINAL_BUCKET}/releases/" \
  --arg final_result_prefix "s3://${RESULTS_BUCKET}/campaigns/${CAMPAIGN_ID}/final/" \
  '{
    schema_version:$schema_version,
    project_id:$project_id,
    tenant_id:$tenant_id,
    region:$region,
    campaign_id:$campaign_id,
    access_key_expiration:$expires_at,
    service_accounts:{development:$dev_sa_id,final:$final_sa_id,mlflow:$mlflow_sa_id},
    groups:{development:$dev_group_id,final:$final_group_id,mlflow:$mlflow_group_id},
    buckets:{development:$dev_bucket_id,final:$final_bucket_id,results:$results_bucket_id,mlflow:$mlflow_bucket_id},
    access_keys:{
      development:{id:$dev_key_id,access_id_secret_reference_id:$dev_access_id_secret_ref,secret_key_secret_reference_id:$dev_secret_ref},
      final:{id:$final_key_id,access_id_secret_reference_id:$final_access_id_secret_ref,secret_key_secret_reference_id:$final_secret_ref,state:$final_state},
      mlflow:{id:$mlflow_key_id,access_id_secret_reference_id:$mlflow_access_id_secret_ref,secret_key_secret_reference_id:$mlflow_secret_ref}
    },
    job_s3_api:{
      endpoint_url:$endpoint_url,
      development:{input_prefix:$dev_input_prefix,result_prefix:$dev_result_prefix},
      final:{input_prefix:$final_input_prefix,result_prefix:$final_result_prefix}
    }
  }' >"${STATE_FILE}"
chmod 600 "${STATE_FILE}"

final_key_id="$(json_id "${final_key}")"
printf '%s\n' \
  "" \
  "Provisioning complete. Non-secret resource state: ${STATE_FILE}" \
  "The final key is inactive. After verifying the signed final authorization, activate it once:" \
  "  nebius iam v2 access-key activate --id ${final_key_id}${PROFILE:+ --profile ${PROFILE}}" \
  "Immediately after the one final Job is submitted, deactivate it:" \
  "  nebius iam v2 access-key deactivate --id ${final_key_id}${PROFILE:+ --profile ${PROFILE}}" \
  "Do not commit the generated state file or any SecretStash payload."
