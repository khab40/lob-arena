"""Validate ordinary Nebius Job readbacks without requesting the SECRET view.

Normal reads omit file content and plain environment values. This module checks
their identities only; the native runtime must separately check actual bytes.
"""
from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime

if __package__:
    from .g8_native_contract import PROJECT, SUBNET, canonical, environment, injections, job_name
else:
    from g8_native_contract import PROJECT, SUBNET, canonical, environment, injections, job_name


def _unique(items, key):
    if not isinstance(items, list) or any(not isinstance(v, dict) or key not in v for v in items):
        raise ValueError("missing or malformed Job identity list")
    result = {v[key]: v for v in items}
    if len(result) != len(items):
        raise ValueError("duplicate Job identity")
    return result


def verify_previous_job(plan, original, previous, *, recovery_job_id, now=None):
    current = now or datetime.now(UTC)
    if (original["execution_package_sha256"] != plan.identity() or original["phase"] != "score"
            or original["job_id"] == recovery_job_id or previous is None
            or any(previous["metadata"].get(k) != original["readback"]["metadata"].get(k)
                   for k in ("id", "parent_id", "name", "created_at"))
            or previous["metadata"]["id"] != original["job_id"]
            or previous["spec"] != original["readback"]["spec"] or previous["status"]["state"] != "FAILED"):
        raise ValueError("original score Job must be terminal with the same reviewed configuration")
    created = datetime.fromisoformat(previous["metadata"]["created_at"].replace("Z", "+00:00"))
    finished = datetime.fromisoformat(previous["status"].get("finished_at", "").replace("Z", "+00:00"))
    if created.tzinfo is None or finished.tzinfo is None or not plan.verified_at <= created <= finished <= current:
        raise ValueError("original Job terminal time is invalid")


def verify_readback(plan, raw, *, phase, expected_job_id, now=None):
    """Operator supplies the ID returned by create; never infer it from a name."""
    current = now or datetime.now(UTC)
    if re.fullmatch(r"aijob-[a-z0-9]+", expected_job_id) is None:
        raise ValueError("actual Job ID required")
    metadata, spec = raw["metadata"], raw["spec"]
    if (metadata.get("id") != expected_job_id or metadata.get("name") != job_name(phase)
            or metadata.get("parent_id") != PROJECT):
        raise ValueError("Job metadata differs from submitted native phase")
    created = datetime.fromisoformat(metadata["created_at"].replace("Z", "+00:00"))
    deadline = plan.expires_at if phase == "score" else plan.cleanup_deadline
    if created.tzinfo is None or not plan.verified_at <= created <= current < deadline:
        raise ValueError("Job is outside the reviewed time window")
    required = {"image": plan.image, "container_command": "python",
        "args": f"/job/g8/run_g8_native_rehearsal.py --phase {phase}",
        "platform": "cpu-d3", "preset": "4vcpu-16gb", "subnet_id": SUBNET, "timeout": "3600s"}
    if any(spec.get(k) != v for k, v in required.items()):
        raise ValueError("Job execution configuration differs")
    # Proto3 omits zero/false scalar defaults from ordinary JSON readbacks.
    defaults = {"working_dir": "", "ports": [], "registry_credentials": {}, "public_ip": False,
                "ssh_authorized_keys": [], "preemptible": False, "restart_attempts": "0", "shm_size_bytes": "0"}
    if set(spec) - set(required) - set(defaults) - {"disk", "volumes", "environment_variables", "injected_files"}:
        raise ValueError("unreviewed Job spec fields")
    for key, default in defaults.items():
        value = spec.get(key, default)
        if key in {"restart_attempts", "shm_size_bytes"}:
            if value not in (0, "0") or isinstance(value, bool):
                raise ValueError("unexpected Job restart or shared memory setting")
        elif value != default:
            raise ValueError("unreviewed Job access or execution option: " + key)
    disk = spec.get("disk", {})
    if disk not in ({"type": "NETWORK_SSD", "size_bytes": str(100 * 1024**3)},
                    {"type": "NETWORK_SSD", "size_bytes": 100 * 1024**3}):
        raise ValueError("Job ephemeral disk differs")
    volumes = spec.get("volumes")
    expected_volume = {"source": plan.filesystem_id, "container_path": "/g8-durable", "mode": "READ_WRITE"}
    if volumes not in ([expected_volume], [{**expected_volume, "source_path": ""}]):
        raise ValueError("exact native filesystem mount required")
    expected_plain = environment(plan)
    observed = _unique(spec.get("environment_variables"), "name")
    if set(observed) != set(expected_plain) | set(plan.secret_selectors):
        raise ValueError("Job environment names differ")
    for name, entry in observed.items():
        if name in plan.secret_selectors:
            secret_id, version_id = plan.secret_selectors[name].split("@")
            if entry != {"name": name, "mysterybox_secret": {"secret_id": secret_id, "version_id": version_id}}:
                raise ValueError("Job secret ID or exact version differs: " + name)
        elif entry not in ({"name": name}, {"name": name, "value": expected_plain[name]}):
            raise ValueError("Job plain environment differs: " + name)
    files = _unique(spec.get("injected_files"), "container_path")
    if set(files) != set(injections(plan)) or any(v != {"container_path": k} for k, v in files.items()):
        raise ValueError("exact ordinary-readback injection paths required")
    status = raw.get("status", {})
    if status.get("state") not in {"PROVISIONING", "STARTING", "IMAGE_PULLING", "RUNNING"}:
        raise ValueError("Job is not waiting/running for its signed context")
    if status.get("public_endpoints") or any(i.get("public_ip") for i in status.get("instances", [])):
        raise ValueError("native rehearsal must remain private")
    return {
        "schema_version": "g8_native_job_readback_v1", "job_id": expected_job_id, "phase": phase,
        "execution_package_sha256": plan.identity(), "filesystem_id": plan.filesystem_id,
        "job_readback_sha256": hashlib.sha256(canonical(raw)).hexdigest(),
        "secret_version_selectors_verified": True, "injected_file_paths_verified": True,
        "injected_file_bytes_verified": False, "runtime_environment_verified": False,
        "native_storage_verified": False, "remote_mlflow_verified": False,
    }
