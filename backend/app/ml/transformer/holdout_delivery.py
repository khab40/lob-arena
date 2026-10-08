"""Bind ordinary provider observations and deliver already-authorized context once."""
import re

from .holdout_context import verify_context
from .holdout_entrypoint import context_key
from .role_execution_context import DEFAULTS, LIVE_STATES
from .role_execution_spec import PROJECT, SUBNET
from .role_execution_transport import PublicationUncertain
from .verification_spec import canonical, digest

REQUEST_PATH = "/opt/research/holdout-request.json.gz"
APPROVAL_PATH = "/opt/research/holdout-approval.json"


def provider_spec(request, selectors):
    # Selectors must be independently approved with the exact provider hash.
    # No credential values or request hash enter this spec: public approval and
    # request are separate injected files, avoiding a self-referential hash.
    if (not isinstance(selectors, dict) or set(selectors) != {"AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"}
            or any(not isinstance(s, dict) or set(s) != {"secret_id", "version_id"}
                   or not isinstance(s["secret_id"], str) or not isinstance(s["version_id"], str)
                   or not re.fullmatch(r"mbsec-[a-z0-9]+", s["secret_id"])
                   or not re.fullmatch(r"mbsecver-[a-z0-9]+", s["version_id"])
                   for s in selectors.values())):
        raise ValueError("version-pinned credential selectors required")
    return {**DEFAULTS, "image": request.image_repository + "@" + request.image_digest,
        "platform": "gpu-l40s-a", "preset": "1gpu-8vcpu-32gb", "timeout": "3600s",
        "disk": {"type": "NETWORK_SSD", "size_bytes": str(100 * 1024**3)}, "subnet_id": SUBNET,
        "shm_size_bytes": str(1024**3), "pricing_model": {"on_demand": {}},
        "environment_variables": [{"name": name, "mysterybox_secret": selector}
                                  for name, selector in sorted(selectors.items())],
        "injected_files": [{"container_path": path} for path in sorted((REQUEST_PATH, APPROVAL_PATH))]}


def context_for_job(job, request, selectors, *, approved_request_sha256, trusted_public_key):
    expected = provider_spec(request, selectors)
    if (request.sha256() != approved_request_sha256 or request.context_public_key != trusted_public_key
            or request.provider_spec_sha256 != digest(canonical(expected))):
        raise ValueError("provider attestation lacks matching external approval")
    metadata, raw, status = job["metadata"], job["spec"], job["status"]
    if (not re.fullmatch(r"aijob-[a-z0-9]+", metadata.get("id", ""))
            or metadata.get("name") != request.run_id or metadata.get("parent_id") != PROJECT
            or status.get("state") not in LIVE_STATES):
        raise ValueError("observed Job identity differs or is no longer live")
    instances = status.get("instances", [])
    if (not isinstance(instances, list) or len(instances) > 1 or status.get("public_endpoints")
            or any(not isinstance(i, dict) or i.get("public_ip") for i in instances)):
        raise ValueError("unexpected provider replicas or public access")
    normalized = {**DEFAULTS, **raw}
    for key in ("restart_attempts", "shm_size_bytes"):
        if type(normalized[key]) is int:
            normalized[key] = str(normalized[key])
    disk = normalized.get("disk")
    if isinstance(disk, dict) and type(disk.get("size_bytes")) is int:
        normalized["disk"] = {**disk, "size_bytes": str(disk["size_bytes"])}
    for key, field in (("environment_variables", "name"), ("injected_files", "container_path")):
        values = normalized.get(key)
        if not isinstance(values, list) or any(not isinstance(v, dict) or not isinstance(v.get(field), str)
                                               for v in values):
            raise ValueError("malformed provider injection")
        normalized[key] = sorted(values, key=lambda v: v[field])
    if canonical(normalized) != canonical(expected):
        raise ValueError("observed provider resources, access or injections differ")
    return {"request_sha256": request.sha256(), "run_id": request.run_id,
        "image_digest": request.image_digest, "nonce": request.nonce,
        "provider_spec_sha256": request.provider_spec_sha256, "job_id": metadata["id"],
        "provider_readback_sha256": digest(canonical(job))}


def deliver_context(store, envelope, *, approved_request_sha256, trusted_public_key):
    verify_context(store.request, envelope, approved_request_sha256=approved_request_sha256,
                   trusted_public_key=trusted_public_key)
    raw = canonical(envelope)
    if len(raw) > 16384:
        raise ValueError("signed context exceeds delivery bound")
    store.start()
    try:
        location = {"Bucket": store.request.output_bucket, "Key": context_key(store.request)}
        response = store.s3.put_object(**location, Body=raw, IfNoneMatch="*",
                                      Metadata={"sha256": digest(raw)}, ContentType="application/json")
        version = response.get("VersionId")
        if not isinstance(version, str) or version in ("", "null"):
            raise ValueError("context publication has no version")
        saved, receipt = store.get({**location, "VersionId": version}, len(raw), metadata=True)
        if saved != raw:
            raise ValueError("context publication readback differs")
        return receipt
    except Exception as error:
        raise PublicationUncertain("context PUT requires reconciliation; never retry") from error
