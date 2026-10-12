"""Bounded private durable artifacts owned by a Google subject and workspace."""
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import re
import secrets
import stat

from app.research.saved_score_io import canonical, json_value, sha256

IDENTIFIER = re.compile(r"[a-f0-9]{32}\Z")
MAX_BYTES, MAX_FILES = 256 * 1024, 1000
MAX_STORE_BYTES = 256 * 1024**2


class ArtifactUnavailable(ValueError):
    pass


class InvalidSelection(ValueError):
    pass


def private_directory(path):
    if not path.is_absolute() or any(part.is_symlink() for part in (path, *path.parents)):
        raise ArtifactUnavailable()
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise ArtifactUnavailable()
    return path


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


class JourneyStore:
    def __init__(self, root: Path):
        private_directory(root.parent)
        try:
            root.mkdir(mode=0o700)
            sync_directory(root.parent)
        except FileExistsError:
            pass
        self.root = private_directory(root)

    def home(self, subject, *, create=False):
        private_directory(self.root)
        owner = sha256(canonical({"subject": subject, "workspace_id": "ceo-demo"}))
        path = self.root / owner
        if create:
            try:
                path.mkdir(mode=0o700)
                sync_directory(self.root)
            except FileExistsError:
                pass
        if not path.exists():
            raise LookupError()
        return private_directory(path)

    def path(self, subject, identifier, kind, *, create=False):
        if not isinstance(identifier, str) or not IDENTIFIER.fullmatch(identifier):
            raise LookupError()
        if kind not in {"snapshot", "explanation", "saved"}:
            raise ArtifactUnavailable()
        return self.home(subject, create=create) / (identifier + "." + kind + ".json")

    def read(self, path):
        private_directory(path.parent)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            raise LookupError() from None
        with os.fdopen(fd, "rb") as stream:
            before = os.fstat(stream.fileno())
            if (not stat.S_ISREG(before.st_mode) or before.st_uid != os.geteuid()
                    or stat.S_IMODE(before.st_mode) != 0o600 or before.st_nlink != 1
                    or not 0 < before.st_size <= MAX_BYTES):
                raise ArtifactUnavailable()
            raw = stream.read(MAX_BYTES + 1)
            after = os.fstat(stream.fileno())
        if (len(raw) != before.st_size or len(raw) > MAX_BYTES
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ArtifactUnavailable()
        value = json_value(raw)
        if canonical(value) != raw:
            raise ArtifactUnavailable()
        return value

    def existing(self, subject, identifier, kind):
        return self.read(self.path(subject, identifier, kind))

    @contextmanager
    def write_budget(self, added_bytes):
        private_directory(self.root)
        path = self.root / ".writes.lock"
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size != 0):
                raise ArtifactUnavailable()
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ArtifactUnavailable() from None
            count, size = 0, 0
            for home_number, home in enumerate(self.root.iterdir()):
                if home_number > MAX_FILES:
                    raise ArtifactUnavailable()
                if home == path:
                    continue
                if not re.fullmatch(r"[a-f0-9]{64}", home.name):
                    raise ArtifactUnavailable()
                private_directory(home)
                for entry in home.iterdir():
                    item = entry.lstat()
                    if (not stat.S_ISREG(item.st_mode) or item.st_uid != os.geteuid()
                            or item.st_nlink != 1 or stat.S_IMODE(item.st_mode) != 0o600
                            or item.st_size > MAX_BYTES):
                        raise ArtifactUnavailable()
                    count, size = count + 1, size + item.st_size
                    if count >= MAX_FILES or size + added_bytes > MAX_STORE_BYTES:
                        raise ArtifactUnavailable()
            yield
        finally:
            os.close(fd)

    def write(self, subject, identifier, kind, value):
        path = self.path(subject, identifier, kind, create=True)
        raw = canonical(value)
        if not 0 < len(raw) <= MAX_BYTES:
            raise ArtifactUnavailable()
        if path.exists() or path.is_symlink():
            sync_directory(path.parent)
            return self.read(path)
        with self.write_budget(len(raw)):
            temporary = path.parent / (".partial-" + secrets.token_hex(16))
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            if canonical(self.read(temporary)) != raw:
                raise ArtifactUnavailable()
            try:
                os.link(temporary, path, follow_symlinks=False)
            except FileExistsError:
                pass
            # An exclusive link publishes complete bytes without replacing another artifact.
            temporary.unlink()
            sync_directory(path.parent)
        return self.read(path)

    def saved_ids(self, subject):
        try:
            home = self.home(subject)
        except LookupError:
            return []
        entries = []
        for entry in home.iterdir():
            entries.append(entry)
            if len(entries) > MAX_FILES:
                raise ArtifactUnavailable()
        return sorted(path.name.removesuffix(".saved.json") for path in entries
                      if path.name.endswith(".saved.json"))
