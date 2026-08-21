#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Usage: bootstrap-nebius-mlflow-env.sh --output PATH --access-key-id ID \
  --bucket NAME --private-host HOST [--image IMAGE]

Reads the Object Storage secret access key as one line from standard input.
Creates PATH with mode 0600 and never prints secret values.
EOF
}

output=""
access_key_id=""
bucket=""
private_host=""
image="lob-arena/mlflow:3.13.0-nebius"

while (($# > 0)); do
  case "$1" in
    --output) output="${2:-}"; shift 2 ;;
    --access-key-id) access_key_id="${2:-}"; shift 2 ;;
    --bucket) bucket="${2:-}"; shift 2 ;;
    --private-host) private_host="${2:-}"; shift 2 ;;
    --image) image="${2:-}"; shift 2 ;;
    *) usage; exit 2 ;;
  esac
done

for value_name in output access_key_id bucket private_host image; do
  if [[ -z "${!value_name}" ]]; then
    echo "required value is empty: ${value_name}" >&2
    usage
    exit 2
  fi
done

if [[ -e "${output}" ]]; then
  echo "refusing to overwrite existing file: ${output}" >&2
  exit 1
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required" >&2
  exit 1
fi

IFS= read -r secret_access_key
if ((${#secret_access_key} < 16)); then
  echo "Object Storage secret access key is missing or too short" >&2
  exit 1
fi

postgres_password="$(openssl rand -hex 32)"
admin_password="$(openssl rand -hex 32)"
flask_secret="$(openssl rand -hex 48)"
exporter_password="$(openssl rand -hex 32)"

umask 077
temporary="$(mktemp "${output}.tmp.XXXXXX")"
trap 'rm -f "${temporary}"' EXIT

cat >"${temporary}" <<EOF
MLFLOW_IMAGE=${image}
MLFLOW_POSTGRES_USER=mlflow
MLFLOW_POSTGRES_PASSWORD=${postgres_password}
MLFLOW_POSTGRES_DB=mlflow

MLFLOW_S3_BUCKET=${bucket}
MLFLOW_ARTIFACTS_PREFIX=artifacts
MLFLOW_S3_ENDPOINT_URL=https://storage.eu-north1.nebius.cloud
MLFLOW_S3_REGION=eu-north1
AWS_ACCESS_KEY_ID=${access_key_id}
AWS_SECRET_ACCESS_KEY=${secret_access_key}

MLFLOW_ADMIN_USERNAME=admin
MLFLOW_ADMIN_PASSWORD=${admin_password}
MLFLOW_FLASK_SERVER_SECRET_KEY=${flask_secret}
MLFLOW_EXPORTER_USERNAME=prometheus
MLFLOW_EXPORTER_PASSWORD=${exporter_password}
MLFLOW_EXPORTER_EXPERIMENTS=lob-arena/corpus-releases,lob-arena/lightgbm-development,lob-arena/governed-evaluation
MLFLOW_EXPORTER_METRIC_KEYS=precision,recall,f1,false_alerts_per_million_events,cloud_wall_seconds,cloud_cpu_seconds,cloud_peak_rss_bytes,cloud_rows_per_second,cloud_estimated_cost_usd
MLFLOW_EXPORTER_MODEL_NAMES=lob-arena-lightgbm-attack-active
MLFLOW_EXPORTER_MAX_RUNS_PER_EXPERIMENT=1000
MLFLOW_EXPORTER_MAX_MODEL_VERSIONS=1000
MLFLOW_EXPORTER_CACHE_SECONDS=30
MLFLOW_EXPORTER_HTTP_REQUEST_TIMEOUT=3
MLFLOW_EXPORTER_HTTP_REQUEST_MAX_RETRIES=0

MLFLOW_BIND_ADDRESS=0.0.0.0
MLFLOW_PORT=5500
MLFLOW_ALLOWED_HOSTS=${private_host}:*,localhost:*,127.0.0.1:*,mlflow:5000
MLFLOW_CORS_ALLOWED_ORIGINS=http://${private_host}:5500,http://localhost:5500,http://127.0.0.1:5500
MLFLOW_ENABLE_WORKSPACES=false
MLFLOW_SERVER_WORKERS=2
EOF

chmod 600 "${temporary}"
mv "${temporary}" "${output}"
trap - EXIT
echo "Created private Nebius MLflow environment at ${output} (mode 0600)."
