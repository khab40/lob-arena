"""Bounded local evidence reads, with independently supplied trust pins."""
import hashlib
import json
import os
from pathlib import Path


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def json_value(raw: bytes):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate evidence key")
            result[key] = value
        return result

    def invalid_constant(_value):
        raise ValueError("nonfinite evidence number")

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid_constant)


def no_symlinks(path: Path) -> Path:
    absolute = path.absolute()
    if any(part.is_symlink() for part in (absolute, *absolute.parents)):
        raise ValueError("symlinked evidence path")
    return absolute.resolve(strict=True)


def validate_private_roots(directory: Path | None, artifact_roots: tuple[Path, ...]) -> Path:
    if directory is None:
        raise ValueError("private evidence directory required")
    private = no_symlinks(directory)
    if not private.is_dir():
        raise ValueError("private evidence directory required")
    for root in artifact_roots:
        # Generic roots may not exist until LocalStore initializes at startup.
        public = root.resolve()
        if private.is_relative_to(public) or public.is_relative_to(private):
            raise ValueError("private evidence overlaps generic artifacts")
    return private


def checked_read(path: Path, *, bound: int, digest: str, size: int | None = None) -> bytes:
    no_symlinks(path)
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        import stat
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > bound:
            raise ValueError("evidence file outside bound")
        raw = stream.read(bound + 1)
    if len(raw) > bound or (size is not None and len(raw) != size) or sha256(raw) != digest:
        raise ValueError("evidence bytes differ")
    return raw


def read_publication(base: Path, name: str, reference: dict):
    if (set(reference) != {"sha256", "size_bytes", "version_id"}
            or type(reference["size_bytes"]) is not int
            or not 0 < reference["size_bytes"] <= 16 * 1024**2
            or reference["version_id"] != "1"):
        raise ValueError("publication receipt differs")
    record = canonical(reference)
    checked_read(base / "receipts" / (name + ".json"), bound=1024,
                 digest=sha256(record), size=len(record))
    return json_value(checked_read(base / name, bound=16 * 1024**2,
                                  digest=reference["sha256"], size=reference["size_bytes"]))
