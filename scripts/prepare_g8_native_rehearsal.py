"""Assemble/sign a reviewed synthetic native package; never submit or resolve secrets."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serverless.jobs.g8_native_contract import CODE_PATHS, MODULES, NativePlan, canonical, job_command  # noqa: E402
from serverless.jobs.g8_native_runtime import bounded, verify_package  # noqa: E402
from serverless.jobs.g8_native_source_capsule import verify as verify_capsule  # noqa: E402


def prepare(*, capsule, bindings, billing, filesystem, private_key, output):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key, Encoding, PublicFormat
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    verify_capsule(capsule)
    key = load_pem_private_key(bounded(private_key), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("Ed25519 reviewer key required")
    if (output.absolute() != output.resolve() or output.resolve().is_relative_to(capsule.resolve())
            or capsule.resolve().is_relative_to(output.resolve())):
        raise ValueError("canonical output required")
    # Fail before writing a signed package when the source checkout is dirty.
    status = subprocess.run(["git", "status", "--porcelain", "--untracked-files=normal"],
                            cwd=ROOT, capture_output=True, text=True, check=True).stdout
    if status:
        raise ValueError("package preparation requires a clean reviewed checkout")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    values = json.loads(bounded(bindings))
    if set(values) & {"files", "source_commit", "billing_receipt_sha256"}:
        raise ValueError("file bindings and source commit are derived, never caller-supplied")
    output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(capsule, output / "source-capsule")
    for name in CODE_PATHS:
        source = ROOT / ("backend/app/ml/lightgbm" if name.removesuffix(".py") in MODULES else "serverless/jobs") / name
        (output / name).write_bytes(bounded(source))
    (output / "reviewer-public.pem").write_bytes(key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo))
    (output / "billing.json").write_bytes(bounded(billing))
    (output / "filesystem.json").write_bytes(bounded(filesystem))
    files = {p.relative_to(output).as_posix(): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                                              "size_bytes": p.stat().st_size} for p in output.rglob("*") if p.is_file()}
    plan = NativePlan.model_validate({**values, "source_commit": commit, "files": files,
                                     "billing_receipt_sha256": files["billing.json"]["sha256"]})
    raw = canonical(plan)
    (output / "native-plan.json").write_bytes(raw)
    (output / "native-plan.sig").write_bytes(key.sign(raw))
    verify_package(output, phase="score", trusted=files["reviewer-public.pem"]["sha256"])
    return {"package_sha256": plan.identity(), "source_commit": commit,
            "score_command": job_command(plan, output, phase="score"),
            "recovery_command": job_command(plan, output, phase="recover"),
            "jobs_submitted": 0, "native_storage_verified": False, "remote_mlflow_verified": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("capsule", "bindings", "billing", "filesystem", "private-key", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    print(json.dumps(prepare(**vars(parser.parse_args())), indent=2))
