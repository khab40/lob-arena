"""Bind the research request to an independently observed live provider Job."""
import json
import re
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .research_execution_spec import PROJECT, provider_spec, request_sha
from .role_execution_context import DEFAULTS, LIVE_STATES
from .verification_spec import canonical, digest


def observed(job, request, *, allowed_states=LIVE_STATES):
    metadata, status = job["metadata"], job["status"]
    if (metadata.get("name") != request["run_id"] or metadata.get("parent_id") != PROJECT
            or not re.fullmatch(r"aijob-[a-z0-9]+", metadata.get("id", ""))
            or status.get("state") not in allowed_states or status.get("public_endpoints")):
        raise ValueError("research Job identity/state differs")
    instances = status.get("instances", [])
    if len(instances) > 1 or any(item.get("public_ip") for item in instances):
        raise ValueError("unexpected replica or public access")
    spec = {**DEFAULTS, **job["spec"]}
    for name in ("restart_attempts", "shm_size_bytes"):
        if type(spec[name]) is int:
            spec[name] = str(spec[name])
    spec["disk"] = {**spec["disk"], "size_bytes": str(spec["disk"]["size_bytes"])}
    spec["environment_variables"] = sorted(spec["environment_variables"], key=lambda item: item["name"])
    if canonical(spec) != canonical(provider_spec(request)):
        raise ValueError("actual Job resources, image or permissions differ")
    return {"request_sha256": request_sha(request), "job_id": metadata["id"],
        "run_id": request["run_id"], "image_digest": request["image_digest"],
        "nonce": request["nonce"], "provider_spec_sha256": digest(canonical(spec)),
        "provider_readback_sha256": digest(canonical(job))}


def verify(envelope, request):
    if set(envelope) != {"context", "signature"}:
        raise ValueError("invalid research context envelope")
    context = envelope["context"]
    expected = {"request_sha256": request_sha(request), "run_id": request["run_id"],
        "image_digest": request["image_digest"], "nonce": request["nonce"],
        "provider_spec_sha256": digest(canonical(provider_spec(request)))}
    if (set(context) != {*expected, "job_id", "provider_readback_sha256"}
            or any(context[k] != v for k, v in expected.items())
            or not re.fullmatch(r"aijob-[a-z0-9]+", context["job_id"])
            or not re.fullmatch(r"[0-9a-f]{64}", context["provider_readback_sha256"])):
        raise ValueError("research context binding differs")
    Ed25519PublicKey.from_public_bytes(bytes.fromhex(request["context_public_key"])).verify(
        bytes.fromhex(envelope["signature"]), canonical(context))
    return context


def wait(store):
    expires = time.monotonic() + 300
    for _ in range(60):
        if time.monotonic() >= expires:
            break
        try:
            raw, item = store.read(store.request["slot"], "execution-context.json", limit=16384)
        except Exception as error:
            if getattr(error, "response", {}).get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
                raise
            time.sleep(5)
            continue
        envelope = json.loads(raw)
        context = verify(envelope, store.request)
        store.artifacts["execution-context.json"] = item
        return context
    raise TimeoutError("signed provider context delivery expired")
