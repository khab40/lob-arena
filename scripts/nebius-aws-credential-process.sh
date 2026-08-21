#!/usr/bin/env bash
set -euo pipefail

: "${NEBIUS_AWS_ACCESS_KEY_ID:?NEBIUS_AWS_ACCESS_KEY_ID is required}"
: "${NEBIUS_AWS_SECRET_REFERENCE_ID:?NEBIUS_AWS_SECRET_REFERENCE_ID is required}"

secret="$({
  nebius mysterybox payload get \
    --secret-id "${NEBIUS_AWS_SECRET_REFERENCE_ID}" \
    --format json
} | jq -er '[.data[]?] | map(select(.key == "secret")) | first | .string_value')"

jq -cn \
  --arg access_key_id "${NEBIUS_AWS_ACCESS_KEY_ID}" \
  --arg secret_access_key "${secret}" \
  '{Version:1,AccessKeyId:$access_key_id,SecretAccessKey:$secret_access_key}'
