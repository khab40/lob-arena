#!/usr/bin/env python3
"""Inert planted-secret regression: Gitleaks must stop before any ggshield call."""
from pathlib import Path
import shutil
import sys
import tempfile

import publication_secret_scan as gate


def check(gitleaks: str) -> None:
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="lob-secret-regression-") as directory:
        repo = Path(directory)
        for name in (".gitleaks.toml", ".gitleaksignore"):
            shutil.copyfile(root / name, repo / name)
        gate.git(repo, "init", "-q")
        # Assemble an inert recognizable pattern; never log it or store it in this repository.
        fixture = "gh" + "p_" + "1234567890" * 4
        (repo / "fixture.txt").write_text(f"value={fixture}\n")
        gate.git(repo, "add", "fixture.txt")
        marker = repo / "unexpected-api-call"
        fake_ggshield = repo / "ggshield"
        fake_ggshield.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n")
        fake_ggshield.chmod(0o700)
        captured = gate.captured(repo, "pre-commit", "origin", "")
        for extra in ({}, {".gitignore": b"fixture.txt\n"},
                      {".gitattributes": b"fixture.txt -diff\n"}):
            try:
                gate.scan(repo, {**captured, **extra}, gitleaks, str(fake_ggshield))
            except gate.ScanFailure:
                if marker.exists():
                    raise RuntimeError("external scanner ran before local rejection") from None
            else:
                raise RuntimeError("planted-secret regression was not rejected")
    print("Planted-secret regression passed; no external scanner invocation.")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not shutil.which(sys.argv[1]):
        raise SystemExit("Provide the installed Gitleaks binary; no silent skip.")
    check(sys.argv[1])
