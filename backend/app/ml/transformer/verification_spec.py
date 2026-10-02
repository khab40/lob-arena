"""The approved development release and execution envelope, independent of S3."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath

RUN_ID = "transformer-input-c4-development-20260928-r2"
INVENTORY_SHA = "d99876f0119c0a86e2395a7c61f4919b09506557f21b18dd8ef8e32b84dd0e23"
INPUT_BUCKET = "aimada-wave1-dev-e00g6zvxpr00"
INPUT_PREFIX = "releases/nasdaq-public-sample-v1-c4-5c85182-20260905/staging/"
OUTPUT_BUCKET = "aimada-wave1-results-e00g6zvxpr00"
OUTPUT_PREFIX = f"campaigns/wave1-research-20260816/development/{RUN_ID}/"
ENDPOINT = "https://storage.eu-north1.nebius.cloud"
ROOT_SHA = "642c7258b3424de05bbe8054a0b5c963b3f9fc9c2af65e1892e906c68fe0e7b9"
ROOT_IDENTITY_SHA = "eec7f9801ec0131ee88e51ace855fc0e0c22fb525de0432c281d8f80025c4803"
TABULAR_SHA = "f5810bff50185481cef63095d401e5203f5eca6aed0d97c3b0b9c906ae80c44b"
SEQUENCE_SHA = "8b2b6ecb1437144cbae2a672ef903af5cd77b8fe23f8f93c11a2b2c92c444759"
FOLD_ROWS = {"train": 33450, "validation": 9210}
SYMBOLS = ("AAPL", "MSFT", "NVDA")
BATCH_SIZES = (16, 64, 256)
MAX_OBJECT = 2 * 1024**2
MAX_INPUT = 64 * 1024**2
MAX_RESPONSE = 192 * 1024**2
MAX_OUTPUT = 8 * 1024**2


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def checked_file(path: Path, expected: str):
    payload = path.read_bytes()
    if digest(payload) != expected:
        raise ValueError("approved file checksum mismatch")
    return payload


def load_inventory(path: Path, expected_sha256: str):
    items = [json.loads(line) for line in checked_file(path, expected_sha256).splitlines()]
    keys = set()
    total = 0
    for item in items:
        if set(item) != {"key", "sha256", "size_bytes", "version_id"}:
            raise ValueError("unexpected inventory fields")
        key = item["key"]
        if not isinstance(key, str) or not key.startswith(INPUT_PREFIX):
            raise ValueError("inventory leaves development release")
        relative = key.removeprefix(INPUT_PREFIX)
        parts = PurePosixPath(relative).parts
        if (not parts or PurePosixPath(relative).is_absolute() or relative != str(PurePosixPath(relative)) or ".." in parts
                or any(p in ("test", "final") for p in parts) or "\\" in relative):
            raise ValueError("invalid development object path")
        size = item["size_bytes"]
        sha = item["sha256"]
        if (type(size) is not int or not 0 < size <= MAX_OBJECT or key in keys
                or not isinstance(sha, str) or len(sha) != 64
                or any(c not in "0123456789abcdef" for c in sha)
                or not isinstance(item["version_id"], str) or not item["version_id"]):
            raise ValueError("invalid inventory identity or size")
        keys.add(key)
        total += size
    if len(items) != 185 or total > MAX_INPUT:
        raise ValueError("inventory exceeds approved envelope")
    return items
