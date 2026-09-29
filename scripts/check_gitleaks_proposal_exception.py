"""Exercise the real scanner on disposable Git history, including a squash."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
APPROVAL = "docs/evidence/transformer-validation-metadata-approval-20260928.json"
PROPOSAL = ROOT / "docs/evidence/transformer-validation-metadata-access-proposal-20260928.json"


def check(binary):
    binary = shutil.which(binary)
    if not binary:
        raise RuntimeError("Gitleaks must be installed; regression check cannot be skipped")
    checksum = hashlib.sha256(PROPOSAL.read_bytes()).hexdigest()
    with tempfile.TemporaryDirectory(prefix="gitleaks-proposal-") as temporary:
        temp = Path(temporary)
        repo = temp / "repo"
        repo.mkdir()

        def git(*args):
            return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.PIPE)

        def scan(config):
            report = temp / "report.json"
            result = subprocess.run([binary, "git", str(repo), "--config", str(config),
                "--gitleaks-ignore-path", str(repo), "--enable-rule", "generic-api-key",
                "--log-opts=HEAD", "--redact", "--no-banner", "--report-format=json",
                "--report-path", str(report)], capture_output=True, check=False)
            if result.returncode not in (0, 1):
                raise RuntimeError("Gitleaks execution failed")
            findings = json.loads(report.read_bytes())
            if bool(findings) != (result.returncode == 1):
                raise AssertionError("scanner status and report disagree")
            return findings

        git("init", "-b", "main")
        git("config", "user.name", "Inert regression fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("commit", "--allow-empty", "-m", "base")
        git("switch", "-c", "feature")
        target = repo / APPROVAL
        target.parent.mkdir(parents=True)
        line = json.dumps({"metadata_access_proposal_sha256": checksum}) + "\n"
        target.write_text(line)
        git("add", ".")
        git("commit", "-m", "original evidence")
        original = git("rev-parse", "HEAD")
        target.write_text("\n" * 5 + line)
        git("add", ".")
        git("commit", "-m", "move evidence lines")
        config = ROOT / ".gitleaks.toml"
        if scan(config):
            raise AssertionError("public checksum was not suppressed before squash")
        git("switch", "main")
        git("merge", "--squash", "feature")
        git("commit", "-m", "squashed evidence")
        if original == git("rev-parse", "HEAD") or scan(config):
            raise AssertionError("public checksum exception did not survive squash")
        baseline = temp / "baseline.toml"
        baseline.write_text("[extend]\nuseDefault = true\n")
        if not scan(baseline):
            raise AssertionError("fixture did not reproduce the public-checksum false positive")
        # One-character near match and identical checksum at a different path must
        # still be detected: neither a prefix exception nor a path-only exception.
        other = ("1" if checksum[0] != "1" else "2") + checksum[1:]
        target.write_text(line + json.dumps({"metadata_access_proposal_sha256": other}) + "\n")
        (repo / "unrelated.json").write_text(line)
        git("add", ".")
        git("commit", "-m", "negative controls")
        findings = scan(config)
        if {item["File"] for item in findings} != {APPROVAL, "unrelated.json"}:
            raise AssertionError("exception suppressed a different value or unrelated path")
    return {"squash_and_line_move": "pass", "unsuppressed_control": "pass",
            "different_value_and_path": "pass"}


if __name__ == "__main__":
    print(json.dumps(check(sys.argv[1] if len(sys.argv) > 1 else "gitleaks"), sort_keys=True))
