#!/usr/bin/env python3
"""Scan captured publication material; never give ggshield a repository path."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile

MAX_TEXT_BYTES = 900_000  # Stay below the scanner's document-size boundary.
OID = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?\Z")
GG_CONFIG = "version: 2\nexit-zero: false\nsecret:\n  fail-on-server-error: true\n"


class ScanFailure(Exception):
    pass


def run(argv: list[str], cwd: Path, *, data: bytes | None = None) -> bytes:
    try:
        result = subprocess.run(argv, cwd=cwd, input=data, capture_output=True,
                                timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ScanFailure("tool unavailable or timed out; publication blocked") from exc
    if result.returncode:
        # Never echo scanner/Git stdout or stderr: either could contain a secret.
        raise ScanFailure(f"{Path(argv[0]).name} failed; publication blocked")
    return result.stdout


def git(repo: Path, *args: str) -> bytes:
    return run(["git", "--literal-pathspecs", *args], repo)


def public_path(name: str) -> None:
    parts = PurePosixPath(name).parts
    private = {"outputs", "custody", ".aws", ".ssh", ".codex", ".agents", ".git", ".worktrees"}
    if (not parts or name.startswith("/") or ".." in parts
            or any(part.lower() in private for part in parts)
            or any((part.lower() == ".env" or part.lower().startswith(".env."))
                   and part.lower() not in {".env.example", ".env.template"} for part in parts)
            or Path(name).suffix.lower() in {".key", ".pem", ".p12", ".pfx"}):
        raise ScanFailure("private/custody path present; no content transmitted")


def outgoing(repo: Path, remote: str, updates: str) -> list[str]:
    tips = set()
    lines = []
    for line in updates.splitlines():
        fields = line.split()
        if len(fields) != 4 or not OID.fullmatch(fields[1]) or not OID.fullmatch(fields[3]):
            raise ScanFailure("invalid pre-push input")
        if set(fields[1]) == {"0"}:  # A ref deletion has no outgoing content.
            continue
        lines.append(fields)
    if not lines:
        return []
    # Live advertisements avoid trusting stale origin/task tracking references.
    advertised = git(repo, "ls-remote", "--heads", "--tags", "--", remote).decode().splitlines()
    for line in advertised:
        oid = line.split()[0]
        if OID.fullmatch(oid):
            try:
                tips.add(git(repo, "rev-parse", "--verify", f"{oid}^{{commit}}").decode().strip())
            except ScanFailure:
                pass  # Unknown remote objects cause extra scanning, never omission.
    commits = set()
    for _, local, _, old in lines:
        excludes = sorted(tips | ({old} if set(old) != {"0"} else set()))
        commits.update(git(repo, "rev-list", local, "--not", *excludes).decode().splitlines())
    return sorted(commits)


def captured(repo: Path, mode: str, remote: str, updates: str) -> dict[str, bytes]:
    versions: list[tuple[str, list[str]]] = []
    messages = []
    if mode == "pre-commit":
        tree = git(repo, "write-tree").decode().strip()
        try:
            base = git(repo, "rev-parse", "--verify", "HEAD").decode().strip()
        except ScanFailure:
            base = run(["git", "hash-object", "-w", "-t", "tree", "--stdin"],
                       repo, data=b"").decode().strip()
        paths = git(repo, "diff", "--name-only", "-z", base, tree).decode().split("\0")
        versions.append((tree, [p for p in paths if p]))
    else:
        for commit in outgoing(repo, remote, updates):
            paths = git(repo, "diff-tree", "--root", "-m", "--no-commit-id",
                        "--name-only", "-r", "-z", commit).decode().split("\0")
            versions.append((commit, sorted({p for p in paths if p})))
            messages.append(git(repo, "show", "-s", "--format=%B", commit))
    # Check ALL paths first, including deletions, before reading any content.
    for _, paths in versions:
        for name in paths:
            public_path(name)
    material: dict[str, bytes] = {}
    for tree, paths in versions:
        for name in paths:
            entry = git(repo, "ls-tree", "-z", tree, "--", name)
            if not entry:  # Deleted file; earlier outgoing postimages still scanned.
                continue
            header, _ = entry.split(b"\t", 1)
            mode_bits, kind, oid = header.split()
            if mode_bits not in {b"100644", b"100755"} or kind != b"blob":
                raise ScanFailure("symlink/submodule publication requires manual review")
            if int(git(repo, "cat-file", "-s", oid.decode())) > MAX_TEXT_BYTES:
                raise ScanFailure("file exceeds scan boundary; publication blocked")
            content = git(repo, "cat-file", "blob", oid.decode())
            material[name] = material.get(name, b"") + content + b"\n"
    if messages:
        message_path = ".publication-commit-messages.txt"
        while message_path in material:
            message_path = "_" + message_path
        material[message_path] = b"\n".join(messages)
    for content in material.values():
        if len(content) > MAX_TEXT_BYTES or b"\0" in content:
            raise ScanFailure("binary/oversize material cannot be completely scanned")
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ScanFailure("non-UTF8 material cannot be completely scanned") from exc
    return material


