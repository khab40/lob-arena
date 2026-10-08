#!/usr/bin/env python3
"""Install repository-scoped fail-closed hooks without replacing foreign hooks."""
from __future__ import annotations

import argparse
from hashlib import sha256
from pathlib import Path
import shlex
import subprocess

MARKER = "# LOB Arena publication scanner v1"


def install(repo: Path, python: Path, gitleaks: Path, ggshield: Path) -> dict[str, str]:
    for binary in (python, gitleaks, ggshield):
        if not binary.is_file():
            raise ValueError("required scanner/tool environment missing")
    override = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=repo,
                              capture_output=True, check=False)
    if override.returncode == 0:
        raise ValueError("core.hooksPath is already configured; preserve and reconcile it first")
    common = Path(subprocess.check_output(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=repo,
        text=True).strip())
    hooks = common / "hooks"
    runner = hooks / "lob-publication" / "publication_secret_scan.py"
    source = (repo / "scripts" / "publication_secret_scan.py").read_bytes()
    wrappers = {}
    for mode in ("pre-commit", "pre-push"):
        argv = [str(python.resolve()), str(runner), mode]
        args = ' "$@"' if mode == "pre-push" else ""
        args += " " + shlex.join(["--gitleaks", str(gitleaks.resolve()),
                                  "--ggshield", str(ggshield.resolve())])
        wrappers[mode] = f"#!/bin/sh\n{MARKER}\nexec {shlex.join(argv)}{args}\n"
        target = hooks / mode
        if target.is_symlink() or (target.exists() and target.read_text() != wrappers[mode]):
            raise ValueError(f"existing {mode} preserved; reconcile it before installation")
    runner.parent.mkdir(parents=True, exist_ok=True)
    if runner.is_symlink():
        raise ValueError("scanner destination is a symlink")
    runner.write_bytes(source)
    for mode, contents in wrappers.items():
        target = hooks / mode
        if not target.exists():
            with target.open("x") as stream:
                stream.write(contents)
        target.chmod(0o755)
    return {"runner_sha256": sha256(source).hexdigest(),
            "pre_commit_sha256": sha256(wrappers["pre-commit"].encode()).hexdigest(),
            "pre_push_sha256": sha256(wrappers["pre-push"].encode()).hexdigest()}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, required=True)
    parser.add_argument("--gitleaks", type=Path, required=True)
    parser.add_argument("--ggshield", type=Path, required=True)
    arguments = parser.parse_args()
    try:
        receipt = install(Path.cwd(), arguments.python, arguments.gitleaks, arguments.ggshield)
    except ValueError as exc:
        parser.exit(1, f"{exc}\n")
    for key, value in receipt.items():
        print(f"{key}: {value}")
