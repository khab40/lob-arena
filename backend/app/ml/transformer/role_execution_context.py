"""Signed actual Job identity and bounded delivery for the new CPU audit slot."""
from __future__ import annotations

import json
import re
import time

from .role_execution_spec import (
    CONTEXT_POLLS, CONTEXT_SECONDS, MAX_CONTEXT, PROJECT, RUN_ID, canonical, digest,
    provider_spec, validate_request,
)

LIVE_STATES = {"PROVISIONING", "STARTING", "IMAGE_PULLING", "RUNNING"}
DEFAULTS = {"container_command": "", "args": "", "working_dir": "", "ports": [],
    "registry_credentials": {}, "public_ip": False, "ssh_authorized_keys": [],
    "preemptible": False, "restart_attempts": "0", "shm_size_bytes": "0", "volumes": []}


def context_for_job(job, request):
    """Verify ordinary provider data before signing; never requests secret values."""
    expected = provider_spec(request)
    metadata, raw, status = job["metadata"], job["spec"], job["status"]
    job_id = metadata.get("id")
    if (not isinstance(job_id, str) or not re.fullmatch(r"aijob-[a-z0-9]+", job_id)
            or metadata.get("name") != RUN_ID or metadata.get("parent_id") != PROJECT
            or status.get("state") not in LIVE_STATES):
        raise ValueError("provider Job identity differs or is no longer live")
    instances = status.get("instances", [])
    if (not isinstance(instances, list) or len(instances) > 1 or status.get("public_endpoints")
            or any(not isinstance(i, dict) or i.get("public_ip") for i in instances)):
        raise ValueError("provider Job has unexpected replicas or public access")
    # Ordinary proto3 JSON omits zero/false fields; restart never is zero attempts.
    normalized = {**DEFAULTS, **raw}
    for key in ("restart_attempts", "shm_size_bytes"):
        if type(normalized[key]) is int:
            normalized[key] = str(normalized[key])
    disk = normalized.get("disk")
    if isinstance(disk, dict) and type(disk.get("size_bytes")) is int:
        normalized["disk"] = {**disk, "size_bytes": str(disk["size_bytes"])}
    environment = normalized.get("environment_variables")
    if not isinstance(environment, list) or any(
            not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in environment):
        raise ValueError("provider environment is malformed")
    normalized["environment_variables"] = sorted(environment, key=lambda item: item["name"])
    if canonical(normalized) != canonical(expected):
        raise ValueError("provider resources, access, secrets or request injection differ")
    return {"schema_version": "transformer_role_job_context_v1",
        "request_sha256": digest(canonical(request)), "job_id": job_id, "job_name": RUN_ID,
        "image_digest": request["image_digest"], "nonce": request["nonce"],
        "provider_spec_sha256": digest(canonical(expected)),
        "provider_readback_sha256": digest(canonical(job))}


def verify_context(envelope, request):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    validate_request(request, request.get("source_commit"))
    if not isinstance(envelope, dict) or set(envelope) != {"context", "signature"}:
        raise ValueError("unexpected signed context envelope")
    context = envelope["context"]
    fields = {"schema_version", "request_sha256", "job_id", "job_name", "image_digest", "nonce",
              "provider_spec_sha256", "provider_readback_sha256"}
    if not isinstance(context, dict) or set(context) != fields:
        raise ValueError("unexpected Job context fields")
    expected = {"schema_version": "transformer_role_job_context_v1", "job_name": RUN_ID,
        "request_sha256": digest(canonical(request)), "image_digest": request["image_digest"],
        "nonce": request["nonce"], "provider_spec_sha256": digest(canonical(provider_spec(request)))}
    patterns = {"job_id": r"aijob-[a-z0-9]+", "provider_readback_sha256": r"[0-9a-f]{64}"}
    if (any(context[key] != value for key, value in expected.items()) or any(
            not isinstance(context[key], str) or not re.fullmatch(pattern, context[key])
            for key, pattern in patterns.items())
            or not isinstance(envelope["signature"], str)
            or not re.fullmatch(r"[0-9a-f]{128}", envelope["signature"])):
        raise ValueError("Job context binding differs")
    key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(request["context_public_key"]))
    key.verify(bytes.fromhex(envelope["signature"]), canonical(context))
    return context


def wait_context(s3, request, *, pause=time.sleep):
    from .role_deadline import deadline

    validate_request(request, request.get("source_commit"))
    with deadline(CONTEXT_SECONDS):
        for attempt in range(CONTEXT_POLLS):
            try:
                response = s3.get_object(Bucket=request["output_bucket"],
                    Key=request["output_prefix"] + "execution-context.json")
            except Exception as error:
                if getattr(error, "response", {}).get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
                    raise
                if attempt + 1 < CONTEXT_POLLS:
                    pause(5)
                continue
            body = response["Body"]
            try:
                size = response["ContentLength"]
                version = response.get("VersionId")
                if (type(size) is not int or not 0 < size <= MAX_CONTEXT
                        or not isinstance(version, str) or not version or version == "null"):
                    raise ValueError("context has invalid size or missing object version")
                payload = body.read(MAX_CONTEXT + 1)
                if len(payload) != size:
                    raise ValueError("context length differs")
                envelope = json.loads(payload)
                if canonical(envelope) != payload:
                    raise ValueError("context must use canonical encoding")
                return verify_context(envelope, request)
            finally:
                body.close()
    raise TimeoutError("signed actual Job context was not published within its bound")
