"""One unused CPU audit envelope; constructing it confers no execution authority."""
from __future__ import annotations

import re

from .campaign_spec import configuration, configuration_sha256
from .verification_spec import (  # noqa: F401 - shared immutable data identities
    ENDPOINT, INPUT_BUCKET, INPUT_PREFIX, INVENTORY_SHA, MAX_INPUT, MAX_OBJECT,
    canonical, digest, load_inventory,
)

RUN_ID = "transformer-role-audit-c4-20261002-r1"
OUTPUT_BUCKET = "aimada-wave1-results-e00g6zvxpr00"
OUTPUT_PREFIX = f"campaigns/wave1-research-20260816/development/{RUN_ID}/"
PROJECT = "project-e00g6zvxpr00waz8t3y51k"
SUBNET = "vpcsubnet-e00ppzc4353dxv210j"
IMAGE_REPOSITORY = "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/transformer-role-audit"
REQUEST_PATH = "/opt/role-audit/request.json"
BUNDLE_SHA = "697f29587002e8cb46f30c8942ebd1a3ac0e78701ed51e69f8aeb330431e83f3"
SOURCE_RECEIPT_SHA = "9ed4852ae01c952d76f59054e3db8ad1a8dce00b4ec7a543ce5a48641d7d07ae"
ROLE_METADATA_SHA = "0e1bc71a8442bd20df510a3be2b6576e9eb7bff391b38228c66c8422159c62be"
NORMALIZATION_SHA = configuration()["inputs"]["normalization_sha256"]
MAX_OUTPUT = 8 * 1024**2
MAX_GET_ATTEMPTS = 185
MAX_CONTEXT = 16384
CONTEXT_SECONDS = 300
CONTEXT_POLLS = 60


def resources():
    return {"platform": "cpu-e2", "preset": "4vcpu-16gb", "gpu_count": 0,
        "ephemeral_disk_bytes": 100 * 1024**3, "timeout_seconds": 3600,
        "restart_policy": "never", "preemptible": False, "concurrency": 1,
        "job_count": 1, "mounts": [], "public_endpoints": [],
        "publication_reserve_seconds": 600, "input_get_attempts": MAX_GET_ATTEMPTS,
        "input_cache_bytes": MAX_INPUT, "output_bytes": MAX_OUTPUT,
        "output_artifacts": 8, "context_get_attempts": CONTEXT_POLLS,
        "context_timeout_seconds": CONTEXT_SECONDS, "automatic_replacement": False,
        "cost_policy": "operator_managed_alerts"}


def secret_selectors():
    return {
        "AWS_ACCESS_KEY_ID": {"secret_id": "mbsec-e00arhndyprqr8egjw",
                              "version_id": "mbsecver-e00rjzerny1pf9qhna"},
        "AWS_SECRET_ACCESS_KEY": {"secret_id": "mbsec-e00s7qtjj5n9ghacnh",
                                  "version_id": "mbsecver-e00yfn5w54jc1ybkwv"},
    }


def request_template(source_commit, image_digest, context_public_key, nonce):
    """Build review material only; no approval, credentials or cloud operations."""
    return {"schema_version": "transformer_role_execution_v1", "run_id": RUN_ID,
        "attempt_id": "r1", "campaign_id": configuration()["campaign_id"],
        "campaign_sha256": configuration_sha256(), "source_commit": source_commit,
        "image_digest": image_digest, "inventory_sha256": INVENTORY_SHA,
        "bundle_sha256": BUNDLE_SHA, "source_receipt_sha256": SOURCE_RECEIPT_SHA,
        "normalization_sha256": NORMALIZATION_SHA, "role_metadata_sha256": ROLE_METADATA_SHA,
        "context_public_key": context_public_key, "nonce": nonce, "resources": resources(),
        "secret_selectors": secret_selectors(), "output_bucket": OUTPUT_BUCKET,
        "output_prefix": OUTPUT_PREFIX}


def validate_request(request, source_commit):
    if not isinstance(request, dict):
        raise ValueError("execution request must be an object")
    patterns = {"source_commit": r"[0-9a-f]{40}", "image_digest": r"sha256:[0-9a-f]{64}",
                "context_public_key": r"[0-9a-f]{64}", "nonce": r"[0-9a-f]{32}"}
    if (request.get("source_commit") != source_commit or any(
            not isinstance(request.get(key), str) or not re.fullmatch(pattern, request[key])
            for key, pattern in patterns.items())):
        raise ValueError("execution request has invalid immutable identities")
    expected = request_template(*(request[key] for key in patterns))
    if canonical(request) != canonical(expected):
        raise ValueError("execution request differs from the reviewed CPU envelope")


def provider_spec(request):
    """Canonical ordinary provider readback, with explicit proto3 defaults."""
    validate_request(request, request["source_commit"])
    return {"image": IMAGE_REPOSITORY + "@" + request["image_digest"],
        "platform": "cpu-e2", "preset": "4vcpu-16gb", "timeout": "3600s",
        "disk": {"type": "NETWORK_SSD", "size_bytes": str(100 * 1024**3)},
        "subnet_id": SUBNET, "environment_variables": [
            {"name": name, "mysterybox_secret": selector}
            for name, selector in sorted(request["secret_selectors"].items())],
        "injected_files": [{"container_path": REQUEST_PATH}],
        "container_command": "", "args": "", "working_dir": "", "ports": [],
        "registry_credentials": {}, "public_ip": False, "ssh_authorized_keys": [],
        "preemptible": False, "restart_attempts": "0", "shm_size_bytes": "0", "volumes": []}
