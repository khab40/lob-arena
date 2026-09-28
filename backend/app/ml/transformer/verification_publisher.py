"""Arm before Job creation; deliver context without an interactive handoff (#238)."""
from __future__ import annotations

from datetime import datetime, UTC
import json
from pathlib import Path
import subprocess
import sys
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .verification_context import validate_request, verify_context
from .verification_spec import OUTPUT_BUCKET, OUTPUT_PREFIX, RUN_ID, canonical, digest
from .verification_transport import client, deadline, put_new, require_empty

PROJECT = "project-e00g6zvxpr00waz8t3y51k"
TERMINAL = {"FAILED", "COMPLETED", "CANCELLED", "STOPPED", "DELETING", "DELETED"}


def missing(error):
    return getattr(error, "response", {}).get("Error", {}).get("Code") in ("404", "NoSuchKey")


def provider_job():
    result = subprocess.run(["rtk", "proxy", "nebius", "ai", "job", "get-by-name",
        "--parent-id", PROJECT, "--name", RUN_ID, "--format", "json"],
        capture_output=True, timeout=15)
    if result.returncode:
        if b"code = NotFound" in result.stderr:
            return None
        raise RuntimeError("provider readback failed")
    return json.loads(result.stdout)


def deliver(s3, request, key, read_job, *, now=lambda: datetime.now(UTC), pause=time.sleep):
    with deadline(600):
        for _ in range(120):
            job = read_job()
            if job is None:
                pause(5)
                continue
            metadata, spec, status = job["metadata"], job["spec"], job["status"]
            if (metadata["name"] != RUN_ID or metadata["parent_id"] != PROJECT
                    or spec["image"] != "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/ti@" + request["image_digest"]
                    or spec["platform"] != "cpu-d3" or spec["preset"] != "4vcpu-16gb"
                    or spec["timeout"] != "3600s" or spec["disk"]["size_bytes"] != "107374182400"
                    or status["state"] in TERMINAL):
                raise ValueError("provider Job differs or has terminated")
            try:
                response = s3.get_object(Bucket=OUTPUT_BUCKET, Key=OUTPUT_PREFIX + "INTENT")
            except Exception as error:
                if not missing(error):
                    raise
                pause(5)
                continue
            body = response["Body"]
            try:
                raw = body.read(4097)
                if (response["ContentLength"] > 4096 or raw != canonical(request)
                        or not 0 <= (now() - response["LastModified"]).total_seconds() < 240):
                    raise ValueError("Job intent differs or is too old for safe delivery")
            finally:
                body.close()
            # Never append a context after an observed terminal marker.
            for name in ("FAILED", "SUCCESS"):
                try:
                    s3.head_object(Bucket=OUTPUT_BUCKET, Key=OUTPUT_PREFIX + name)
                except Exception as error:
                    if not missing(error):
                        raise
                else:
                    raise ValueError("Job already published a terminal marker")
            context = {"request_sha256": digest(canonical(request)), "job_id": metadata["id"],
                "job_name": RUN_ID, "image_digest": request["image_digest"], "nonce": request["nonce"]}
            envelope = {"context": context, "signature": key.sign(canonical(context)).hex()}
            verify_context(envelope, request)
            receipt = put_new(s3, "execution-context.json", canonical(envelope))
            return {"provider_readback": job, "envelope": envelope, "object": receipt}
    raise TimeoutError("armed publisher expired without a matching Job intent")


def main():
    request_path, key_path, evidence = map(Path, sys.argv[1:])
    request = json.loads(request_path.read_bytes())
    validate_request(request, request["source_commit"])
    key = Ed25519PrivateKey.from_private_bytes(key_path.read_bytes())
    if key.public_key().public_bytes_raw().hex() != request["context_public_key"]:
        raise ValueError("publisher key differs from reviewed request")
    s3 = client()
    with deadline(30):
        require_empty(s3)
        if provider_job() is not None:
            raise ValueError("Job already exists; resolve its state before arming")
    # Observe this receipt and a live process before submitting the Job via MCP.
    with evidence.with_suffix(".ready.json").open("xb") as stream:
        stream.write(canonical({"request_sha256": digest(canonical(request)), "armed": True}))
    result = deliver(s3, request, key, provider_job)
    with evidence.open("xb") as stream:
        stream.write(canonical(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(canonical({"publisher_status": "failed", "error_type": type(error).__name__}).decode())
        raise SystemExit(1) from None
