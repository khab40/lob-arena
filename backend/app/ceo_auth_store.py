"""Private durable opaque-token custody; never retain Google credentials."""

import hashlib
import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

TOKEN = re.compile(r"[A-Za-z0-9_-]{43}\Z")


def token_hash(value: str) -> str:
    if not TOKEN.fullmatch(value):
        raise ValueError("Invalid opaque token")
    return hashlib.sha256(value.encode("ascii")).hexdigest()


class AuthStore:
    def __init__(self, directory: Path, excluded: tuple[Path, ...]):
        if not directory.is_absolute() or any(part.is_symlink() for part in (directory, *directory.parents)):
            raise ValueError("Unsafe state directory")
        resolved = directory.resolve()
        for root in excluded:
            root = root.resolve()
            if resolved == root or resolved.is_relative_to(root) or root.is_relative_to(resolved):
                raise ValueError("Overlapping state directory")
        if not directory.exists():
            directory.mkdir(mode=0o700)
        self.directory = directory
        self.path = directory / "auth.sqlite3"
        self._check_directory()
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        except FileExistsError:
            pass
        else:
            os.fsync(fd)
            os.close(fd)
            fd = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        self._identity = self._check_file()
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS challenges (token TEXT PRIMARY KEY, nonce TEXT, origin TEXT, expires REAL)")
            db.execute("CREATE TABLE IF NOT EXISTS sessions (token TEXT PRIMARY KEY, sub TEXT, email TEXT, name TEXT, expires REAL)")

    def _check_directory(self):
        if any(part.is_symlink() for part in (self.directory, *self.directory.parents)):
            raise ValueError("Unsafe state directory")
        info = self.directory.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ValueError("Unsafe state directory")

    def _check_file(self):
        self._check_directory()
        info = self.path.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1):
            raise ValueError("Unsafe state file")
        return info.st_dev, info.st_ino

    @contextmanager
    def connection(self):
        if self._check_file() != self._identity:
            raise ValueError("State file identity changed")
        db = sqlite3.connect(self.path, timeout=1)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            if self._check_file() != self._identity:
                raise ValueError("State file identity changed")
            db.commit()
        finally:
            db.close()

    def challenge(self, token: str, nonce: str, origin: str, now: float):
        with self.connection() as db:
            db.execute("DELETE FROM challenges WHERE expires <= ?", (now,))
            if db.execute("SELECT count(*) FROM challenges").fetchone()[0] >= 1000:
                raise ValueError("Challenge capacity reached")
            db.execute("INSERT INTO challenges VALUES (?, ?, ?, ?)",
                       (token_hash(token), token_hash(nonce), origin, now + 300))

    def consume(self, token: str, origin: str, now: float) -> str | None:
        key = token_hash(token)
        with self.connection() as db:
            row = db.execute("SELECT nonce, origin, expires FROM challenges WHERE token = ?", (key,)).fetchone()
            db.execute("DELETE FROM challenges WHERE token = ?", (key,))
        return row[0] if row and row[1] == origin and row[2] > now else None

    def create_session(self, token: str, user: dict, expires: float, now: float):
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE expires <= ?", (now,))
            if db.execute("SELECT count(*) FROM sessions").fetchone()[0] >= 1000:
                raise ValueError("Session capacity reached")
            db.execute("INSERT INTO sessions VALUES (?, ?, ?, ?, ?)",
                       (token_hash(token), user["id"], user["email"], user["name"], expires))

    def session(self, token: str):
        with self.connection() as db:
            return db.execute("SELECT sub, email, name, expires FROM sessions WHERE token = ?",
                              (token_hash(token),)).fetchone()

    def revoke(self, token: str):
        with self.connection() as db:
            db.execute("DELETE FROM sessions WHERE token = ?", (token_hash(token),))
