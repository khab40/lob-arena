"""One native submission with mandatory registry checks and drift cancellation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.submit_nebius_job import _verify_short_tag, _verify_created_short_tag_job  # noqa: E402
from serverless.jobs.g8_native_contract import job_command  # noqa: E402
from serverless.jobs.g8_native_readback import verify_readback, verify_registry  # noqa: E402
from serverless.jobs.g8_native_runtime import bounded, verify_package  # noqa: E402


def submission_command(package, phase):
    return [sys.executable, str(ROOT / "scripts/submit_g8_native_rehearsal.py"),
            "--package", str(package), "--phase", phase]


def write(path, value):
    with path.open("x") as stream:
        stream.write(json.dumps(value, sort_keys=True) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def invoke(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=180, check=False)


def submit(package, phase):
    trusted = hashlib.sha256(bounded(package / "reviewer-public.pem")).hexdigest()
    plan = verify_package(package, phase=phase, trusted=trusted)
    status = subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if status or commit != plan.source_commit:
        raise ValueError("submission requires the clean signed source commit")
    evidence = package.parent / (phase + "-submission")
    evidence.mkdir(mode=0o700, exist_ok=False)  # Never retry an ambiguous create.
    registry = _verify_short_tag(plan.deployment_image, plan.image)
    verify_registry(registry)
    write(evidence / "registry-before.json", registry)
    argv = job_command(plan, package, phase=phase) + ["--no-browser", "--retries", "1"]
    write(evidence / "intent.json", {"package_sha256": plan.identity(), "argv": argv})
    result = invoke(argv)
    write(evidence / "create-process.json", {"returncode": result.returncode,
          "stdout": result.stdout, "stderr": result.stderr})
    if result.returncode:
        raise RuntimeError("create failed or ambiguous; inspect retained evidence, never retry")
    created = json.loads(result.stdout)
    job_id = created["metadata"]["id"]
    if re.fullmatch(r"aijob-[a-z0-9]+", job_id) is None:
        raise ValueError("create returned no valid Job identity; resolve by readback")
    write(evidence / "created.json", created)
    try:
        _, registry = _verify_created_short_tag_job(job_id, plan.deployment_image, plan.image)
        result = invoke(["nebius", "ai", "job", "get", job_id, "--format", "json", "--no-browser"])
        if result.returncode:
            raise RuntimeError("post-create readback unavailable")
        readback = json.loads(result.stdout)
        verify_readback(plan, readback, phase=phase, expected_job_id=job_id)
        verify_registry(registry, created_at=readback["metadata"]["created_at"])
        write(evidence / "readback.json", readback)
        write(evidence / "registry-after.json", registry)
    except (Exception, SystemExit):
        cancelled = invoke(["nebius", "ai", "job", "cancel", job_id, "--format", "json", "--no-browser"])
        write(evidence / "cancel-process.json", {"returncode": cancelled.returncode,
              "stdout": cancelled.stdout, "stderr": cancelled.stderr})
        raise
    return {"job_id": job_id, "phase": phase, "execution_package_sha256": plan.identity(),
            "readback": str(evidence / "readback.json"),
            "registry_verification": str(evidence / "registry-after.json")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--phase", required=True, choices=("score", "recover"))
    args = parser.parse_args()
    print(json.dumps(submit(args.package, args.phase), sort_keys=True))
