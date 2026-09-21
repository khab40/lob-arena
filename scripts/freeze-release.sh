#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

ROOT_DIR="${FREEZE_RELEASE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
OUTPUT_ROOT="${FREEZE_RELEASE_OUTPUT_ROOT:-${ROOT_DIR}/evidence}"
ENV_FILE="${FREEZE_RELEASE_ENV_FILE:-${ROOT_DIR}/.env}"
TIMESTAMP="${FREEZE_RELEASE_TIMESTAMP:-$(date -u +%Y-%m-%d-%H%M)}"
OFFLINE="${FREEZE_RELEASE_OFFLINE:-false}"
HTTP_TIMEOUT="${FREEZE_RELEASE_HTTP_TIMEOUT:-30}"

usage() {
  cat <<'EOF'
Usage: ./scripts/freeze-release.sh [options]

Options:
  --output-root DIR  Evidence parent directory (default: ./evidence)
  --env-file FILE   Environment source to sanitize (default: ./.env)
  --timestamp VALUE Override deployment timestamp (YYYY-MM-DD-HHMM)
  --offline         Skip Docker, local API, and Nebius CLI probes
  -h, --help        Show this help

The final bundle contains no credential values. Live command output is staged
privately, recursively redacted, scanned, checksummed, and only then published.
EOF
}

while (($#)); do
  case "$1" in
    --output-root)
      OUTPUT_ROOT="${2:?--output-root requires a directory}"
      shift 2
      ;;
    --env-file)
      ENV_FILE="${2:?--env-file requires a file}"
      shift 2
      ;;
    --timestamp)
      TIMESTAMP="${2:?--timestamp requires a value}"
      shift 2
      ;;
    --offline)
      OFFLINE=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

[[ "${TIMESTAMP}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{4}$ ]] || {
  printf 'Invalid timestamp: %s (expected YYYY-MM-DD-HHMM)\n' "${TIMESTAMP}" >&2
  exit 2
}

command -v git >/dev/null 2>&1 || { printf 'git is required\n' >&2; exit 2; }
command -v python3 >/dev/null 2>&1 || { printf 'python3 is required\n' >&2; exit 2; }
git -C "${ROOT_DIR}" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  printf 'Not a Git repository: %s\n' "${ROOT_DIR}" >&2
  exit 2
}

BUNDLE_NAME="deployment-${TIMESTAMP}"
BUNDLE_DIR="${OUTPUT_ROOT}/${BUNDLE_NAME}"
[[ ! -e "${BUNDLE_DIR}" ]] || { printf 'Evidence bundle already exists: %s\n' "${BUNDLE_DIR}" >&2; exit 2; }

STAGING_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aimada-freeze.XXXXXX")"
cleanup() {
  rm -rf "${STAGING_DIR}"
}
trap cleanup EXIT

mkdir -p \
  "${STAGING_DIR}/git" \
  "${STAGING_DIR}/docker" \
  "${STAGING_DIR}/endpoint/config" \
  "${STAGING_DIR}/endpoint/metadata" \
  "${STAGING_DIR}/environment" \
  "${STAGING_DIR}/versions" \
  "${STAGING_DIR}/model" \
  "${STAGING_DIR}/prompts" \
  "${STAGING_DIR}/architecture" \
  "${STAGING_DIR}/documentation" \
  "${STAGING_DIR}/screenshots" \
  "${STAGING_DIR}/benchmarks"

capture() {
  local target="$1"
  shift
  mkdir -p "$(dirname "${target}")"
  if "$@" >"${target}" 2>&1; then
    return 0
  else
    local status=$?
    printf '\n[command exited with status %s]\n' "${status}" >>"${target}"
  fi
}

copy_tracked() {
  local destination="$1"
  shift
  local relative source target
  while IFS= read -r -d '' relative; do
    source="${ROOT_DIR}/${relative}"
    [[ -f "${source}" && ! -L "${source}" ]] || continue
    target="${STAGING_DIR}/${destination}/${relative}"
    mkdir -p "$(dirname "${target}")"
    cp "${source}" "${target}"
  done < <(git -C "${ROOT_DIR}" ls-files -z -- "$@")
}

read_env_value() {
  local key="$1"
  python3 - "${ENV_FILE}" "${key}" <<'PY'
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
key = sys.argv[2]
value = os.environ.get(key, "")
if path.is_file():
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, candidate = line.removeprefix("export ").split("=", 1)
        if name.strip() == key:
            value = candidate.strip().strip("'\"")
print(value)
PY
}

# Git metadata: no diff contents are collected because a dirty diff can contain secrets.
capture "${STAGING_DIR}/git/commit.txt" git -C "${ROOT_DIR}" show -s --format=fuller HEAD
capture "${STAGING_DIR}/git/branch.txt" git -C "${ROOT_DIR}" branch --show-current
capture "${STAGING_DIR}/git/status.txt" git -C "${ROOT_DIR}" status --short --branch
capture "${STAGING_DIR}/git/remotes.txt" git -C "${ROOT_DIR}" remote -v
capture "${STAGING_DIR}/git/recent-commits.txt" git -C "${ROOT_DIR}" log -n 20 --date=iso-strict --format=%H%x09%ad%x09%an%x09%s
capture "${STAGING_DIR}/git/tags.txt" git -C "${ROOT_DIR}" tag --points-at HEAD

# Environment and model configuration use key-aware redaction and an explicit model allowlist.
python3 - "${ENV_FILE}" "${STAGING_DIR}/environment/sanitized.env" "${STAGING_DIR}/model/model-config.env" <<'PY'
import os
import re
import sys
from pathlib import Path

source = Path(sys.argv[1])
environment_target = Path(sys.argv[2])
model_target = Path(sys.argv[3])
sensitive = re.compile(
    r"(?:token|secret|password|credential|authorization|cookie|session|private|access[_-]?key|api[_-]?key|jwt|client[_-]?secret)",
    re.I,
)
relevant = re.compile(r"^(?:AIMADA|ARENA|NEBIUS|ENDPOINT|LOCAL_VLLM|VLLM|COMPOSE|DOCKER|VITE|PYTHON)[A-Z0-9_]*$")
model_keys = (
    "NEBIUS_ENDPOINT_MODE",
    "NEBIUS_ENDPOINT_IMAGE",
    "NEBIUS_ENDPOINT_HARDWARE_PRESET",
    "LOCAL_VLLM_MODEL",
    "LOCAL_VLLM_DTYPE",
    "LOCAL_VLLM_GPU_MEMORY_UTILIZATION",
    "LOCAL_VLLM_MAX_MODEL_LEN",
    "LOCAL_VLLM_ENABLE_PREFIX_CACHING",
    "LOCAL_VLLM_MAX_NUM_SEQS",
    "LOCAL_VLLM_TRUST_REMOTE_CODE",
)
values = {key: value for key, value in os.environ.items() if relevant.match(key)}
if source.is_file():
    for raw in source.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        key = key.strip()
        if relevant.match(key):
            values[key] = value.strip().strip("'\"")

def display(key: str, value: str) -> str:
    if sensitive.search(key):
        return "[REDACTED]"
    value = value.replace(str(Path.home()), "$HOME")
    return value.replace("\n", "\\n").replace("\r", "\\r")

environment_target.write_text(
    "# Sanitized LOB Arena deployment environment; credential values are never exported.\n"
    + "".join(f"{key}={display(key, values[key])}\n" for key in sorted(values)),
    encoding="utf-8",
)
defaults = {
    "NEBIUS_ENDPOINT_MODE": "local_vllm",
    "NEBIUS_ENDPOINT_HARDWARE_PRESET": "gpu-l40s-d",
    "LOCAL_VLLM_MODEL": "Qwen/Qwen2.5-14B-Instruct",
    "LOCAL_VLLM_DTYPE": "auto",
    "LOCAL_VLLM_GPU_MEMORY_UTILIZATION": "0.90",
    "LOCAL_VLLM_MAX_MODEL_LEN": "16384",
    "LOCAL_VLLM_ENABLE_PREFIX_CACHING": "true",
    "LOCAL_VLLM_MAX_NUM_SEQS": "16",
    "LOCAL_VLLM_TRUST_REMOTE_CODE": "true",
}
model_target.write_text(
    "# Effective model configuration (environment value or documented default).\n"
    + "".join(f"{key}={display(key, values.get(key, defaults.get(key, 'not set')))}\n" for key in model_keys),
    encoding="utf-8",
)
PY

# Version inventories contain package names and versions, never pip credential-bearing URLs.
PYTHON_BIN="python3"
[[ -x "${ROOT_DIR}/backend/.venv/bin/python" ]] && PYTHON_BIN="${ROOT_DIR}/backend/.venv/bin/python"
capture "${STAGING_DIR}/versions/python.txt" "${PYTHON_BIN}" --version
capture "${STAGING_DIR}/versions/python-packages.txt" "${PYTHON_BIN}" -m pip list --format=freeze --disable-pip-version-check
copy_tracked "versions/requirements" \
  'backend/pyproject.toml' 'backend/uv.lock' 'serverless/endpoint/requirements.txt' 'frontend/package.json' 'frontend/pnpm-lock.yaml'

VLLM_IMAGE="$(awk '/^FROM[[:space:]]+vllm\/vllm-openai:/ {print $2; exit}' "${ROOT_DIR}/serverless/endpoint/Dockerfile" 2>/dev/null || true)"
{
  printf 'declared_image=%s\n' "${VLLM_IMAGE:-not detected}"
  if command -v vllm >/dev/null 2>&1; then
    vllm --version 2>&1 || true
  else
    printf '%s\n' 'runtime_cli=not installed on collection host'
  fi
} >"${STAGING_DIR}/versions/vllm.txt"

if [[ "${OFFLINE,,}" == "true" ]]; then
  printf '%s\n' 'Offline collection requested; Docker metadata was not probed.' >"${STAGING_DIR}/docker/UNAVAILABLE.txt"
  printf '%s\n' 'Offline collection requested; live endpoint metadata was not probed.' >"${STAGING_DIR}/endpoint/metadata/UNAVAILABLE.txt"
else
  if command -v docker >/dev/null 2>&1; then
    capture "${STAGING_DIR}/docker/version.txt" docker version
    capture "${STAGING_DIR}/docker/compose-version.txt" docker compose version
    capture "${STAGING_DIR}/docker/images.jsonl" docker image ls --digests --format '{{json .}}'
    capture "${STAGING_DIR}/docker/containers.jsonl" docker ps -a --format '{{json .}}'
    if [[ -n "${VLLM_IMAGE}" ]]; then
      capture "${STAGING_DIR}/docker/vllm-image-digests.json" docker image inspect "${VLLM_IMAGE}" --format '{{json .RepoDigests}}'
    fi
  else
    printf '%s\n' 'docker is not installed on the collection host.' >"${STAGING_DIR}/docker/UNAVAILABLE.txt"
  fi

  if command -v curl >/dev/null 2>&1; then
    capture "${STAGING_DIR}/endpoint/metadata/backend-nebius-status.json" \
      curl --fail --silent --show-error --max-time "${HTTP_TIMEOUT}" http://localhost:8000/api/nebius/status
  else
    printf '%s\n' 'curl is not installed; backend endpoint metadata was not collected.' >"${STAGING_DIR}/endpoint/metadata/backend-status-UNAVAILABLE.txt"
  fi

  ENDPOINT_ID="$(read_env_value NEBIUS_ENDPOINT_ID)"
  if [[ -n "${ENDPOINT_ID}" ]] && command -v nebius >/dev/null 2>&1; then
    capture "${STAGING_DIR}/endpoint/metadata/nebius-endpoint.json" \
      nebius ai endpoint get "${ENDPOINT_ID}" --format json --no-check-update --no-progress
  else
    printf '%s\n' 'Nebius CLI or NEBIUS_ENDPOINT_ID is unavailable; CLI metadata was not collected.' >"${STAGING_DIR}/endpoint/metadata/nebius-cli-UNAVAILABLE.txt"
  fi
fi

# Only tracked source, screenshots, and benchmark artifacts are copied.
copy_tracked "endpoint/config" \
  'serverless/endpoint/Dockerfile' 'serverless/endpoint/start.sh' \
  'serverless/endpoint/endpoint_config.yaml' 'serverless/endpoint/endpoint_config.example.yaml' \
  'serverless/deployment.env.example' 'docker-compose.yml' \
  'deployments/modes/production-nebius.env' 'deployments/k8s/**' \
  'scripts/create-nebius-ai-endpoint.sh'
copy_tracked "prompts" \
  'serverless/endpoint/prompts.py' 'serverless/endpoint/surveillance.py' \
  'serverless/endpoint/schemas/**' 'serverless/endpoint/examples/**' 'docs/ml/surveillance-prompting.md'
copy_tracked "architecture" 'docs/architecture.md' 'docs/architecture/**'
copy_tracked "documentation" 'README.md'
copy_tracked "screenshots" 'assets/screenshots/**' 'assets/social/**' 'docs/evidence/screenshots/**' 'frontend/public/img/**'
copy_tracked "benchmarks" 'outputs/benchmark/**'

if [[ ! -f "${STAGING_DIR}/benchmarks/outputs/benchmark/README.md" ]]; then
  mkdir -p "${STAGING_DIR}/benchmarks/outputs/benchmark"
  {
    printf '# Benchmark Outputs\n\n'
    printf 'No tracked benchmark index was available in this checkout. '
    printf 'Commit-safe benchmark bundles, when present, are copied here from `outputs/benchmark/`.\n'
  } >"${STAGING_DIR}/benchmarks/outputs/benchmark/README.md"
fi

python3 - "${STAGING_DIR}/README.md" "${TIMESTAMP}" "${OFFLINE}" <<'PY'
import sys
from pathlib import Path

target = Path(sys.argv[1])
timestamp = sys.argv[2]
offline = sys.argv[3]
target.write_text(
    f"""# LOB Arena deployment evidence: {timestamp}

This timestamped bundle freezes the Git revision, sanitized deployment environment,
Docker and Python inventories, Nebius Endpoint metadata, model/vLLM configuration,
prompt contracts, architecture, project README, reviewed screenshots, and committed
benchmark outputs. Credential-bearing values, authorization headers, signed URL
parameters, private keys, and URL user-info are redacted before publication.

- Generated at (UTC): `{timestamp}`
- Repository: `https://github.com/khab40/lob-arena`
- Collection mode: `{'offline' if offline.lower() == 'true' else 'live'}`
- Source policy: tracked project files plus sanitized command metadata
- Integrity: run `shasum -a 256 -c checksums.sha256` from this directory

Absence of a live metadata file is documented by an adjacent `UNAVAILABLE.txt` file;
the script never fabricates endpoint, Docker, benchmark, or screenshot evidence.
""",
    encoding="utf-8",
)
PY

# Recursively redact staged text, reject residual credential patterns, then create integrity metadata.
python3 - "${STAGING_DIR}" "${ROOT_DIR}" "${ENV_FILE}" "${TIMESTAMP}" <<'PY'
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

root = Path(sys.argv[1])
repo = Path(sys.argv[2])
env_file = Path(sys.argv[3])
timestamp = sys.argv[4]
sensitive_key = re.compile(
    r"(?:authorization|credential|password|secret|token|cookie|session|private|access[_-]?key|api[_-]?key|jwt|client[_-]?secret)",
    re.I,
)

secret_values: set[str] = set()
for key, value in os.environ.items():
    if sensitive_key.search(key) and len(value) >= 6:
        secret_values.add(value)
if env_file.is_file():
    for raw in env_file.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        value = value.strip().strip("'\"")
        if sensitive_key.search(key) and len(value) >= 6:
            secret_values.add(value)

def sanitize_value(value: Any, key: str = "") -> Any:
    if sensitive_key.search(key):
        return "[REDACTED]"
    if isinstance(value, dict):
        return {item_key: sanitize_value(item, item_key) for item_key, item in value.items()}
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        return sanitize_text(value)
    return value

def sanitize_text(text: str) -> str:
    for secret in sorted(secret_values, key=len, reverse=True):
        text = text.replace(secret, "[REDACTED]")
    text = text.replace(str(repo), "$REPO_ROOT").replace(str(Path.home()), "$HOME")
    text = re.sub(r"(?i)\bBearer\s+(?!\[REDACTED\])[^\s\"']+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(https?://)[^/@\s]+@", r"\1[REDACTED]@", text)
    text = re.sub(r"(?i)([?&](?:X-Amz-(?:Signature|Credential|Security-Token)|Signature|token)=)[^&\s]+", r"\1[REDACTED]", text)
    text = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "[REDACTED]", text)
    text = re.sub(r"\bGOCSPX-[A-Za-z0-9_-]{12,}\b", "[REDACTED]", text)
    text = re.sub(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b", "[REDACTED]", text)
    text = re.sub(
        r"(?is)-----BEGIN [^-\n]*PRIVATE KEY-----.*?-----END [^-\n]*PRIVATE KEY-----",
        "[REDACTED PRIVATE KEY]",
        text,
    )
    text = re.sub(
        r"(?im)^(\s*(?:export\s+)?[A-Za-z0-9_.-]*(?:token|secret|password|credential|authorization|cookie|session|private|access[_-]?key|api[_-]?key|jwt)[A-Za-z0-9_.-]*\s*[:=]\s*).*$",
        r"\1[REDACTED]",
        text,
    )
    return text

for path in sorted(root.rglob("*")):
    if not path.is_file() or path.is_symlink():
        continue
    raw = path.read_bytes()
    if b"\x00" in raw:
        continue
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        continue
    if path.suffix.lower() == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            text = sanitize_text(text)
        else:
            text = json.dumps(sanitize_value(parsed), indent=2, sort_keys=True) + "\n"
    else:
        text = sanitize_text(text)
    path.write_text(text, encoding="utf-8")

violations: list[str] = []
residual_patterns = (
    re.compile(r"(?i)\bBearer\s+(?!\[REDACTED\])\S+"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bGOCSPX-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"-----BEGIN [^-\n]*PRIVATE KEY-----"),
    re.compile(r"(?i)[?&]X-Amz-Signature=(?!\[REDACTED\])[^&\s]+"),
)
for path in sorted(root.rglob("*")):
    if not path.is_file() or path.is_symlink():
        continue
    raw = path.read_bytes()
    if b"\x00" in raw:
        continue
    text = raw.decode("utf-8", errors="ignore")
    if any(secret in text for secret in secret_values):
        violations.append(f"known environment secret remains in {path.relative_to(root)}")
    if any(pattern.search(text) for pattern in residual_patterns):
        violations.append(f"credential pattern remains in {path.relative_to(root)}")
if violations:
    raise SystemExit("Release freeze rejected:\n" + "\n".join(sorted(set(violations))))

files = {
    path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(root.rglob("*"))
    if path.is_file() and path.name not in {"manifest.json", "checksums.sha256"}
}
manifest = {
    "schema_version": 1,
    "generated_at_utc": timestamp,
    "repository": "https://github.com/khab40/lob-arena",
    "redaction": "credential values, auth headers, signed URL values, private keys, URL user-info, and private local paths removed",
    "files": files,
}
(root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
(root / "checksums.sha256").write_text(
    "".join(f"{digest}  {name}\n" for name, digest in files.items()),
    encoding="utf-8",
)
PY

find "${STAGING_DIR}" -type d -exec chmod 0755 {} +
find "${STAGING_DIR}" -type f -exec chmod 0644 {} +
mkdir -p "${OUTPUT_ROOT}"
mv "${STAGING_DIR}" "${BUNDLE_DIR}"
trap - EXIT

printf 'Release evidence frozen: %s\n' "${BUNDLE_DIR}"
printf 'Credential scan: passed\n'
printf 'Verify: (cd %q && shasum -a 256 -c checksums.sha256)\n' "${BUNDLE_DIR}"
