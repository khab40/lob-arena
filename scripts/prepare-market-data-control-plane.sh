#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
JAVA_ROOT="${ROOT_DIR}/java"
OUTPUT_DIR="${ROOT_DIR}/build/market-data"
LIB_DIR="${JAVA_ROOT}/control-plane/build/libs"

"${JAVA_ROOT}/gradlew" --no-daemon -p "${JAVA_ROOT}" :control-plane:bootJar

jar_paths=()
while IFS= read -r path; do
  jar_paths+=("${path}")
done < <(find "${LIB_DIR}" -maxdepth 1 -type f -name '*.jar' ! -name '*-plain.jar' -print | sort)
if [[ "${#jar_paths[@]}" -ne 1 ]]; then
  printf '%s\n' "control-plane build must produce exactly one non-plain JAR" >&2
  exit 1
fi

mkdir -p "${OUTPUT_DIR}"
cp "${jar_paths[0]}" "${OUTPUT_DIR}/control-plane.jar"
test -s "${OUTPUT_DIR}/control-plane.jar"
shasum -a 256 "${OUTPUT_DIR}/control-plane.jar"
