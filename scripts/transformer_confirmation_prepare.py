"""Prepare fresh confirmation requests from verified local evidence; no network."""
import argparse
import json
from pathlib import Path
import secrets
import shlex

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.ml.transformer.research_confirmation_contract import CONTEXT_PUBLIC_KEY, LEGACY_PRIOR
from app.ml.transformer.research_execution_spec import (
    PROJECT, REPOSITORY, SUBNET, replacement_template, request_sha, validate,
)
from app.ml.transformer.verification_spec import canonical, digest

VERIFIED_SHA = {
    "smoke": "0cce5804d05ff1c9b2b0bbb2b7f62475a1175ac24d1529dd82d4aba48e2a802c",
    "search-64-0003": "2a6c76f716c31ba096e9d573c60b338dc1f2927511cf4588fa918bd84214b00b",
    "search-64-001": "e451e7e8e7f09bebeeabcabae04ba2834668f6251b5560840358745113df481a",
    "search-128-0003": "e26e8212dd147f5feb28bf1093aa5e3bbbea530327f67a992e32626cba7ace33",
    "search-128-001": "7b421725b91881aa7d45f4e55e17c3701b35fd73a8e1be522c6bf42901c147e8",
}


def verify_legacy(legacy):
    receipts = []
    for slot, fixed in LEGACY_PRIOR.items():
        directory = legacy / slot
        request = json.loads((directory / "request.json").read_bytes())
        verified_raw = (directory / "verification.json").read_bytes()
        verified = json.loads(verified_raw)
        if (digest(verified_raw) != VERIFIED_SHA[slot] or verified["status"] != "verified"
                or request_sha(request) != fixed["request"]["sha256"]
                or json.loads((directory / "success-receipt.json").read_bytes()) != fixed["success"]
                or verified["context"]["request_sha256"] != request_sha(request)):
            raise ValueError("legacy verification differs from fixed prerequisite")
        for name, item in verified["inventory"].items():
            path = directory / "artifacts" / name
            if not path.resolve().is_relative_to((directory / "artifacts").resolve()):
                raise ValueError("artifact path escapes legacy evidence")
            raw = path.read_bytes()
            if len(raw) != item["size_bytes"] or digest(raw) != item["sha256"]:
                raise ValueError("legacy local artifact differs")
        if json.loads((directory / "artifacts/configuration.json").read_bytes()) != request:
            raise ValueError("legacy saved configuration differs")
        receipts.append({"slot": slot, "verification_sha256": digest(verified_raw),
            "request_sha256": request_sha(request), "success": fixed["success"],
            "artifact_count": len(verified["inventory"]), "local_artifact_hashes_verified": True})
    return receipts


def create_command(request, path):
    validate(request)
    command = ["nebius", "ai", "job", "create", "--parent-id", PROJECT, "--name", request["run_id"],
        "--image", REPOSITORY + "@" + request["image_digest"], "--platform", "gpu-l40s-a",
        "--preset", "1gpu-8vcpu-32gb", "--timeout", "2h", "--disk-size", "100Gi",
        "--shm-size", "1Gi", "--subnet-id", SUBNET, "--restart-policy", "never", "--on-demand"]
    for name, selector in sorted(request["secret_selectors"].items()):
        command += ["--env-secret", f'{name}={selector["secret_id"]}@{selector["version_id"]}']
    return command + ["--inject-file", str(path.resolve()) + ":/opt/research/request.json",
        "--async", "--format", "json", "--retries", "1", "--no-browser", "--auth-timeout", "120s"]


def prepare(legacy, output, custody, source_commit, image_digest):
    receipts = verify_legacy(legacy)
    key = Ed25519PrivateKey.from_private_bytes(custody.read_bytes())
    public = key.public_key().public_bytes_raw().hex()
    if public != CONTEXT_PUBLIC_KEY:
        raise ValueError("existing signing custody differs")
    requests = []
    # Validate everything before creating either request directory.
    for slot in ("seed-7", "seed-2027"):
        request = replacement_template(slot, source_commit, image_digest, public, secrets.token_hex(16))
        validate(request)
        requests.append(request)
    output.mkdir(parents=True, exist_ok=False)
    trials = []
    for request in requests:
        path = output / request["slot"] / "request.json"
        path.parent.mkdir()
        with path.open("xb") as stream:
            stream.write(canonical(request))
        command = create_command(request, path)
        trials.append({"slot": request["slot"], "trial": request["trial"],
            "trial_sha256": digest(canonical(request["trial"])), "run_id": request["run_id"],
            "request_path": str(path.resolve()), "request_sha256": request_sha(request),
            "request_bytes": path.stat().st_size, "output_bucket": request["output_bucket"],
            "output_prefix": request["output_prefix"], "create_command": shlex.join(command)})
    manifest = {"schema_version": "transformer_confirmation_requests_v2", "trials": trials,
        "dependencies": receipts, "custody_public_key_continuity": True,
        "jobs_created": 0, "context_attestation_started": False}
    (output / "prepared.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("legacy", "output", "custody"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--image-digest", required=True)
    args = parser.parse_args()
    result = prepare(args.legacy, args.output, args.custody, args.source_commit, args.image_digest)
    print(json.dumps({"requests_prepared": len(result["trials"]), "jobs_created": 0}))
