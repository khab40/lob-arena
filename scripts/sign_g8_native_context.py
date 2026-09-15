"""Sign a validated ordinary Job readback for the waiting native rehearsal.

No API calls or submission. Copy the two outputs through the reviewed native
filesystem attachment; never place them in the synthetic result/intent prefixes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from serverless.jobs.g8_native_contract import canonical  # noqa: E402
from serverless.jobs.g8_native_readback import verify_readback  # noqa: E402
from serverless.jobs.g8_native_runtime import bounded, signed, verify_package  # noqa: E402


def sign_context(*, package, readback, job_id, phase, private_key, output,
                 previous_terminal=None, original_context=None):
    from cryptography.hazmat.primitives.serialization import load_pem_private_key, Encoding, PublicFormat
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    public = bounded(package / "reviewer-public.pem")
    trusted = hashlib.sha256(public).hexdigest()
    plan = verify_package(package, phase=phase, trusted=trusted)
    key = load_pem_private_key(bounded(private_key), password=None)
    if (not isinstance(key, Ed25519PrivateKey)
            or key.public_key().public_bytes(Encoding.PEM, PublicFormat.SubjectPublicKeyInfo) != public):
        raise ValueError("context signer must be the package reviewer")
    job = json.loads(bounded(readback))
    receipt = verify_readback(plan, job, phase=phase, expected_job_id=job_id)
    prior = None
    if phase == "recover":
        if previous_terminal is None or original_context is None:
            raise ValueError("recovery requires the signed score context and terminal Job readback")
        original_raw = bounded(original_context)
        signed(original_raw, bounded(original_context.with_suffix(".sig"), 64), public, trusted)
        original = json.loads(original_raw)
        prior = json.loads(bounded(previous_terminal))
        if (original["execution_package_sha256"] != plan.identity() or original["phase"] != "score"
                or original["job_id"] == job_id or prior["metadata"]["id"] != original["job_id"]
                or prior["spec"] != original["readback"]["spec"] or prior["status"]["state"] != "FAILED"
                or not prior["status"].get("finished_at")):
            raise ValueError("original score Job must be terminal with the same reviewed configuration")
    elif previous_terminal is not None or original_context is not None:
        raise ValueError("score context cannot carry a previous execution")
    context = {"execution_package_sha256": plan.identity(), "phase": phase, "job_id": job_id,
               "readback": job, "previous_terminal": prior}
    content = canonical(context)
    if len(content) > 65536 or output.absolute() != output.resolve():
        raise ValueError("bounded context and canonical new output required")
    output.mkdir(parents=True, exist_ok=False)
    (output / (phase + ".json")).write_bytes(content)
    (output / (phase + ".sig")).write_bytes(key.sign(content))
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("package", "readback", "private-key", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--phase", choices=("score", "recover"), required=True)
    parser.add_argument("--previous-terminal", type=Path)
    parser.add_argument("--original-context", type=Path)
    print(json.dumps(sign_context(**vars(parser.parse_args())), indent=2))
