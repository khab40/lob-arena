"""Arm before create and bind the observed CPU Job to its immutable request."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from .receipt_publication import publish_receipt
from .role_deadline import deadline
from .role_execution_context import context_for_job, verify_context
from .role_execution_spec import PROJECT, RUN_ID, validate_request
from .role_execution_transport import client, put_new, read_result, require_empty
from .verification_spec import canonical, digest


def missing(error):
    return getattr(error, "response", {}).get("Error", {}).get("Code") in ("404", "NoSuchKey")


def provider_job():
    result = subprocess.run(["rtk", "proxy", "nebius", "ai", "job", "get-by-name",
        "--parent-id", PROJECT, "--name", RUN_ID, "--format", "json", "--retries", "1"],
        capture_output=True, timeout=15)
    if result.returncode:
        if b"code = NotFound" in result.stderr:
            return None
        raise RuntimeError("provider readback failed")
    return json.loads(result.stdout)


def deliver(s3, request, key, read_job, *, now=lambda: datetime.now(UTC), pause=time.sleep):
    validate_request(request, request["source_commit"])
    if key.public_key().public_bytes_raw().hex() != request["context_public_key"]:
        raise ValueError("publisher key differs from reviewed request")
    with deadline(600):
        for _ in range(120):
            job = read_job()
            if job is None:
                pause(5)
                continue
            context = context_for_job(job, request)
            try:
                intent, intent_receipt = read_result(s3, request, "INTENT", 16384)
            except Exception as error:
                if not missing(error):
                    raise
                pause(5)
                continue
            head = s3.head_object(Bucket=request["output_bucket"], Key=request["output_prefix"] + "INTENT",
                                  VersionId=intent_receipt["version_id"])
            if (head.get("VersionId") != intent_receipt["version_id"] or intent != canonical(request)
                    or not 0 <= (now() - head["LastModified"]).total_seconds() < 240):
                raise ValueError("Job intent differs or is too old for safe delivery")
            for name in ("FAILED", "SUCCESS"):
                try:
                    s3.head_object(Bucket=request["output_bucket"], Key=request["output_prefix"] + name)
                except Exception as error:
                    if not missing(error):
                        raise
                else:
                    raise ValueError("Job already published a terminal marker")
            fresh_job = read_job()
            if fresh_job is None:
                raise ValueError("provider Job disappeared before delivery")
            fresh_context = context_for_job(fresh_job, request)
            if fresh_context["job_id"] != context["job_id"]:
                raise ValueError("provider Job was replaced before delivery")
            job, context = fresh_job, fresh_context
            envelope = {"context": context, "signature": key.sign(canonical(context)).hex()}
            verify_context(envelope, request)
            receipt = put_new(s3, request, "execution-context.json", canonical(envelope))
            return {"provider_readback": job, "envelope": envelope, "object": receipt}
    raise TimeoutError("armed publisher expired without a matching Job intent")


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: role_execution_publisher REQUEST PRIVATE_KEY NEW_EVIDENCE_PATH")
    request_path, key_path, evidence = map(Path, sys.argv[1:])
    request = json.loads(request_path.read_bytes())
    validate_request(request, request["source_commit"])
    key = Ed25519PrivateKey.from_private_bytes(key_path.read_bytes())
    if key.public_key().public_bytes_raw().hex() != request["context_public_key"]:
        raise ValueError("publisher key differs from reviewed request")
    s3 = client()
    with deadline(30):
        require_empty(s3, request)
        if provider_job() is not None:
            raise ValueError("Job already exists; resolve its state before arming")
    publish_receipt(evidence.with_suffix(".ready.json"), canonical({
        "request_sha256": digest(canonical(request)), "armed": True}))
    result = deliver(s3, request, key, provider_job)
    publish_receipt(evidence, canonical(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(canonical({"publisher_status": "failed", "error_type": type(error).__name__}).decode())
        raise SystemExit(1) from None
