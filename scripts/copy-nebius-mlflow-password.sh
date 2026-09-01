#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${NEBIUS_MLFLOW_PASSWORD_SECRET_ID:-}" ]]; then
  echo "Error: NEBIUS_MLFLOW_PASSWORD_SECRET_ID environment variable is required" >&2
  exit 1
fi
secret_id="${NEBIUS_MLFLOW_PASSWORD_SECRET_ID}"

for dependency in nebius jq pbcopy; do
  if ! command -v "${dependency}" >/dev/null 2>&1; then
    printf 'Required command not found: %s\n' "${dependency}" >&2
    exit 1
  fi
done

password="$({
  nebius mysterybox payload get \
    --secret-id "${secret_id}" \
    --format json
} | jq -er '[.data[]?] | map(select(.key == "secret")) | first | .string_value')"

if [[ -z "${password}" ]]; then
  printf 'MLflow password payload is empty for secret %s\n' "${secret_id}" >&2
  exit 1
fi

printf '%s' "${password}" | pbcopy
unset password

printf 'Copied the Nebius MLflow password to the clipboard. Username: admin\n'
