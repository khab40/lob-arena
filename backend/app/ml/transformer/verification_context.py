"""Bind a launched Job to the request with an ephemeral orchestrator signature."""
from __future__ import annotations

import re
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .verification_spec import INVENTORY_SHA, OUTPUT_BUCKET, OUTPUT_PREFIX, RUN_ID, canonical, digest
from .verification_transport import deadline


def validate_request(request, source_commit):
    if set(request) != {"schema_version", "run_id", "source_commit", "image_digest",
                       "inventory_sha256", "context_public_key", "nonce"}:
        raise ValueError("unexpected execution request fields")
    if (request["schema_version"] != "transformer_input_execution_v1" or request["run_id"] != RUN_ID
            or request["source_commit"] != source_commit
            or not re.fullmatch(r"[0-9a-f]{40}", source_commit)
            or request["inventory_sha256"] != INVENTORY_SHA
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", request["image_digest"])
            or not re.fullmatch(r"[0-9a-f]{64}", request["context_public_key"])
            or not re.fullmatch(r"[0-9a-f]{32}", request["nonce"])):
        raise ValueError("execution request differs from reviewed bindings")


def verify_context(envelope, request):
    if set(envelope) != {"context", "signature"}:
        raise ValueError("unexpected context envelope")
    context = envelope["context"]
    if (set(context) != {"request_sha256", "job_id", "job_name", "image_digest", "nonce"}
            or context["request_sha256"] != digest(canonical(request))
            or context["job_name"] != RUN_ID or context["image_digest"] != request["image_digest"]
            or context["nonce"] != request["nonce"]
            or not re.fullmatch(r"aijob-[a-z0-9]+", context["job_id"])):
        raise ValueError("Job context binding differs")
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(request["context_public_key"]))
    key.verify(bytes.fromhex(envelope["signature"]), canonical(context))
    return context


def wait_context(s3, request):
    import json
    from botocore.exceptions import ClientError
    with deadline(300):
        for _ in range(60):
            try:
                response = s3.get_object(Bucket=OUTPUT_BUCKET, Key=OUTPUT_PREFIX + "execution-context.json")
            except ClientError as error:
                if error.response.get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
                    raise
                time.sleep(5)
                continue
            body = response["Body"]
            try:
                if not 0 < response["ContentLength"] <= 4096:
                    raise ValueError("context exceeds size limit")
                payload = body.read(4097)
                if len(payload) != response["ContentLength"]:
                    raise ValueError("context length differs")
                return verify_context(json.loads(payload), request)
            finally:
                body.close()
    raise TimeoutError("signed Job context was not published")
