"""VM-only context transport; the Job independently verifies the signed context.

Run through the existing SSH operator path as root. No dependencies, credentials,
model imports, API calls or filesystem mounting; the mount must already exist.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

MOUNT = Path("/mnt/g8-native-rehearsal")
TAG = "g8-native-rehearsal"


def sync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def check_mount():
    if os.geteuid() != 0 or MOUNT.resolve() != MOUNT:
        raise ValueError("root and canonical native mount required")
    found = []
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        before, after = line.split(" - ", 1)
        fields, fs = before.split(), after.split()
        if fields[4].startswith(str(MOUNT) + "/"):
            raise ValueError("nested native mounts are forbidden")
        if fields[4] == str(MOUNT):
            found.append(fs[0] == "virtiofs" and fs[1] == TAG
                         and "rw" in fields[5].split(",") and "rw" in fs[2].split(","))
    capacity = os.statvfs(MOUNT)
    if found != [True] or not 9 * 1024**3 <= capacity.f_blocks * capacity.f_frsize <= 11 * 1024**3:
        raise ValueError("reviewed writable native mount and capacity required")


def read_input(path, digest, maximum):
    if path.absolute() != path.resolve() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError("bounded canonical input required")
    content = path.read_bytes()
    if len(content) > maximum or hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("context transport hash differs")
    return content


def immutable_write(path, content):
    """Publish complete bytes without replacing any existing file, even on retry."""
    descriptor, temporary = tempfile.mkstemp(prefix=".context-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fchmod(stream.fileno(), 0o400)
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
                raise ValueError("existing context differs; replacement forbidden") from None
        sync_directory(path.parent)
    finally:
        os.unlink(temporary)


def publish(context, signature, context_sha256, signature_sha256, phase):
    if phase not in {"score", "recover"}:
        raise ValueError("reviewed context phase required")
    raw = read_input(context, context_sha256, 65536)
    sig = read_input(signature, signature_sha256, 64)
    value = json.loads(raw)
    if len(sig) != 64 or value.get("phase") != phase:
        raise ValueError("context phase or signature length differs")
    check_mount()
    destination = MOUNT / "contexts"
    destination.mkdir(mode=0o700, exist_ok=True)
    metadata = destination.lstat()
    if (not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != 0
            or stat.S_IMODE(metadata.st_mode) != 0o700):
        raise ValueError("root-owned private context directory required")
    sync_directory(MOUNT)
    immutable_write(destination / (phase + ".json"), raw)
    immutable_write(destination / (phase + ".sig"), sig)  # Completion signal last.
    return {"phase": phase, "context_sha256": context_sha256, "signature_sha256": signature_sha256,
            "context_transport_verified": True, "job_signature_verified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("context", "signature"):
        parser.add_argument("--" + name, type=Path, required=True)
        parser.add_argument("--" + name + "-sha256", required=True)
    parser.add_argument("--phase", choices=("score", "recover"), required=True)
    print(json.dumps(publish(**vars(parser.parse_args())), sort_keys=True))
