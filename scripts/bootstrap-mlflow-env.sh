#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output="${repo_root}/deployments/mlflow/.env"
force=false
upgrade_service_credentials=false

while (($# > 0)); do
  case "$1" in
    --output)
      if (($# < 2)); then
        echo "--output requires a path" >&2
        exit 2
      fi
      output="$2"
      shift 2
      ;;
    --force)
      force=true
      shift
      ;;
    --upgrade-service-credentials)
      upgrade_service_credentials=true
      shift
      ;;
    *)
      echo "unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to generate MLflow deployment secrets" >&2
  exit 1
fi

if [[ "${upgrade_service_credentials}" == "true" ]]; then
  if [[ "${force}" == "true" ]]; then
    echo "--upgrade-service-credentials cannot be combined with --force" >&2
    exit 2
  fi
  if [[ ! -f "${output}" ]]; then
    echo "cannot upgrade missing MLflow environment: ${output}" >&2
    exit 1
  fi
  if grep -q '^MLFLOW_MINIO_ACCESS_KEY=' "${output}" ||
     grep -q '^MLFLOW_MINIO_SECRET_KEY=' "${output}"; then
    if grep -q '^MLFLOW_MINIO_ACCESS_KEY=' "${output}" &&
       grep -q '^MLFLOW_MINIO_SECRET_KEY=' "${output}"; then
      echo "MLflow artifact service credentials already exist in ${output}."
      exit 0
    fi
    echo "refusing to repair a partial MLflow service-credential configuration" >&2
    exit 1
  fi
  umask 077
  temporary="$(mktemp "${output}.tmp.XXXXXX")"
  trap 'rm -f "${temporary}"' EXIT
  service_password="$(openssl rand -hex 24)"
  cp "${output}" "${temporary}"
  {
    printf '\nMLFLOW_MINIO_ACCESS_KEY=mlflow-artifacts\n'
    printf 'MLFLOW_MINIO_SECRET_KEY=%s\n' "${service_password}"
  } >>"${temporary}"
  chmod 600 "${temporary}"
  mv "${temporary}" "${output}"
  trap - EXIT
  echo "Added private MLflow artifact service credentials to ${output}."
  exit 0
fi

if [[ -e "${output}" && "${force}" != "true" ]]; then
  echo "refusing to overwrite existing MLflow environment: ${output}" >&2
  echo "use --force only when intentionally rotating this local deployment" >&2
  exit 1
fi

mkdir -p "$(dirname "${output}")"
umask 077
temporary="$(mktemp "${output}.tmp.XXXXXX")"
trap 'rm -f "${temporary}"' EXIT

postgres_password="$(openssl rand -hex 24)"
minio_password="$(openssl rand -hex 24)"
minio_service_password="$(openssl rand -hex 24)"
admin_password="$(openssl rand -hex 24)"
flask_secret="$(openssl rand -hex 32)"

cat >"${temporary}" <<EOF
MLFLOW_POSTGRES_USER=mlflow
MLFLOW_POSTGRES_PASSWORD=${postgres_password}
MLFLOW_POSTGRES_DB=mlflow

MLFLOW_MINIO_ROOT_USER=mlflow-admin
MLFLOW_MINIO_ROOT_PASSWORD=${minio_password}
MLFLOW_MINIO_ACCESS_KEY=mlflow-artifacts
MLFLOW_MINIO_SECRET_KEY=${minio_service_password}
MLFLOW_S3_BUCKET=lob-arena-mlflow
MLFLOW_ARTIFACTS_PREFIX=artifacts
MLFLOW_S3_REGION=us-east-1

MLFLOW_ADMIN_USERNAME=admin
MLFLOW_ADMIN_PASSWORD=${admin_password}
MLFLOW_FLASK_SERVER_SECRET_KEY=${flask_secret}

MLFLOW_BIND_ADDRESS=127.0.0.1
MLFLOW_PORT=5500
MLFLOW_ALLOWED_HOSTS=localhost:*,127.0.0.1:*,mlflow:5000
MLFLOW_CORS_ALLOWED_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
MLFLOW_ENABLE_WORKSPACES=false
MLFLOW_SERVER_WORKERS=2
EOF

chmod 600 "${temporary}"
mv "${temporary}" "${output}"
trap - EXIT
echo "Created private MLflow environment at ${output} (mode 0600)."
