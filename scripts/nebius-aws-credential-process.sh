#!/usr/bin/env bash
set -euo pipefail

: "${NEBIUS_AWS_SECRET_REFERENCE_ID:?NEBIUS_AWS_SECRET_REFERENCE_ID is required}"

access_key_id="${NEBIUS_AWS_ACCESS_KEY_ID:-}"
if [[ -z "${access_key_id}" ]]; then
  : "${NEBIUS_AWS_ACCESS_KEY_REFERENCE_ID:?NEBIUS_AWS_ACCESS_KEY_ID or NEBIUS_AWS_ACCESS_KEY_REFERENCE_ID is required}"
  access_key_id="$({
    nebius mysterybox payload get \
      --secret-id "${NEBIUS_AWS_ACCESS_KEY_REFERENCE_ID}" \
      --format json
  } | jq -er '[.data[]? | .string_value? | select(type == "string" and length > 0)] | first')"
fi

secret="$({
  nebius mysterybox payload get \
    --secret-id "${NEBIUS_AWS_SECRET_REFERENCE_ID}" \
    --format json
} | jq -er '[.data[]?] | map(select(.key == "secret")) | first | .string_value')"

jq -cn \
  --arg access_key_id "${access_key_id}" \
  --arg secret_access_key "${secret}" \
  '{Version:1,AccessKeyId:$access_key_id,SecretAccessKey:$secret_access_key}'
