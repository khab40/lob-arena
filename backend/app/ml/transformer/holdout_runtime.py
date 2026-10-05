"""Bounded request decoding and static inspection; never import a model."""
import gzip
import importlib.metadata
import io
from pathlib import Path

from .holdout_spec import HoldoutRequest
from .settings_release import json_record
from .verification_spec import digest

MAX_REQUEST = 256 * 1024
MAX_INJECTION = 64 * 1024


def bounded_read(path, limit):
    with Path(path).open("rb") as stream:
        raw = stream.read(limit + 1)
    if not raw or len(raw) > limit:
        raise ValueError("runtime file exceeds its envelope")
    return raw


def encode_request(request):
    raw = request.canonical_bytes()
    packed = gzip.compress(raw, mtime=0)
    if len(raw) > MAX_REQUEST or len(packed) > MAX_INJECTION:
        raise ValueError("request exceeds Nebius injection envelope")
    return packed


def load_request(path):
    packed = bounded_read(path, MAX_INJECTION)
    with gzip.GzipFile(fileobj=io.BytesIO(packed)) as stream:
        raw = stream.read(MAX_REQUEST + 1)
    if len(raw) > MAX_REQUEST:
        raise ValueError("decompressed request exceeds envelope")
    request = HoldoutRequest.model_validate_json(raw)
    if request.canonical_bytes() != raw:
        raise ValueError("injected request must be canonical")
    return request


def inspect_runtime(root, *, installed=None):
    root = Path(root)
    lock = json_record(bounded_read(root / "runtime-lock.json", MAX_INJECTION))
    actual = installed if installed is not None else {
        dist.metadata["Name"].lower(): dist.version for dist in importlib.metadata.distributions()}
    if actual != lock["dependencies"]:
        raise ValueError("installed runtime dependencies differ from trained image")
    for name, expected in lock["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or digest(bounded_read(path, 1024**2)) != expected:
            raise ValueError("trained numerical source differs")
    return {"base_image": lock["base_image"], "files": len(lock["files"]),
            "dependencies": len(actual), "model_execution": False}


if __name__ == "__main__":
    import json
    print(json.dumps(inspect_runtime("/opt/research"), sort_keys=True))
