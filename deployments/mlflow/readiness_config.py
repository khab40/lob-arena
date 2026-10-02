"""Add Transformer allowlist entries without parsing or rewriting other env bytes.

Run with exclusive operator custody of the file. The lock serializes cooperating
writers; the identity guard detects intervening changes, not arbitrary OS races.
"""
import fcntl
import os
from pathlib import Path
import re
import stat
import tempfile

ADDITIONS = {
    b"MLFLOW_EXPORTER_EXPERIMENTS": b"lob-arena/transformer-development",
    b"MLFLOW_EXPORTER_MODEL_NAMES": b"lob-arena-transformer-attack-active",
}
KEY = re.compile(rb"^[ \t]*(?:export[ \t]+)?(" + b"|".join(ADDITIONS) + rb")[ \t]*=")
VALUES = re.compile(rb"[A-Za-z0-9_./:-]+(?:,[A-Za-z0-9_./:-]+)*")


def append_allowlists(content: bytes) -> bytes:
    lines, seen = [], set()
    for line in content.splitlines(keepends=True):
        match = KEY.match(line)
        if match:
            key = match[1]
            if key in seen or not line.startswith(key + b"="):
                raise ValueError("duplicate or unsupported allowlist assignment")
            seen.add(key)
            body = line.removesuffix(b"\n").removesuffix(b"\r")
            value, ending = body[len(key) + 1:], line[len(body):]
            if not VALUES.fullmatch(value):
                raise ValueError("allowlist must use unquoted bootstrap CSV syntax")
            if ADDITIONS[key] not in value.split(b","):
                line = body + b"," + ADDITIONS[key] + ending
        lines.append(line)
    if seen != ADDITIONS.keys():
        raise ValueError("both existing allowlist keys are required")
    return b"".join(lines)


def _identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def update_allowlists(path: Path):
    """Atomically replace one canonical 0600 env file; never expose its content."""
    path = Path(path)
    if not path.is_absolute() or path.resolve(strict=True) != path:
        raise ValueError("env path must be absolute, canonical and without symlinks")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    temporary = None
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or stat.S_IMODE(before.st_mode) != 0o600
                or before.st_uid != os.geteuid() or before.st_size > 1024 * 1024):
            raise ValueError("env must be an owned regular 0600 file of at most 1 MiB")
        content = os.pread(descriptor, before.st_size + 1, 0)
        if len(content) != before.st_size:
            raise ValueError("env changed or was not completely read")
        updated = append_allowlists(content)
        if updated != content:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".allowlists-", delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), 0o600)
                if stream.write(updated) != len(updated):
                    raise OSError("incomplete allowlist write")
                stream.flush()
                os.fsync(stream.fileno())
        if (_identity(os.lstat(path)) != _identity(before)
                or os.pread(descriptor, before.st_size + 1, 0) != content):
            raise ValueError("env changed during allowlist preparation")
        if temporary is not None:
            os.replace(temporary, path)
            temporary = None
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return {"changed": updated != content, "prior_env_bytes_preserved": True}
    finally:
        os.close(descriptor)
        if temporary is not None:
            temporary.unlink()
