"""Eight fixed research slots; exact immutable request validation."""
import re

from .research_baseline import CALIBRATION_SHA, PREDICTIONS_SHA
from .role_execution_spec import BUNDLE_SHA, PROJECT, SOURCE_RECEIPT_SHA, SUBNET, secret_selectors  # noqa: F401
from .verification_spec import INVENTORY_SHA, OUTPUT_BUCKET, canonical, digest

CAMPAIGN = "transformer-research-c4-20261002-r1"
PREFIX = f"campaigns/wave1-research-20260816/development/{CAMPAIGN}/"
REPOSITORY = "cr.eu-north1.nebius.cloud/e00jaawvmwdhya5z2w/tr"
SLOTS = ("smoke", "search-64-0003", "search-64-001", "search-128-0003", "search-128-001",
         "seed-7", "seed-2027", "inference")
MAX_OBJECT = 128 * 1024**2
MAX_OUTPUT = 2 * 1024**3


def dependencies(slot):
    if slot == "smoke":
        return ()
    if slot.startswith("search-"):
        return ("smoke",)
    if slot.startswith("seed-"):
        return SLOTS[:5]
    if slot == "inference":
        return SLOTS[:7]
    raise ValueError("unknown research slot")


def timeout(slot):
    return 3600 if slot in ("smoke", "inference") else 7200


def template(slot, source_commit, image_digest, context_public_key, nonce, prior):
    return {"schema_version": "transformer_research_execution_v1", "campaign": CAMPAIGN,
        "slot": slot, "run_id": f"{CAMPAIGN}-{slot}", "source_commit": source_commit,
        "image_digest": image_digest, "context_public_key": context_public_key, "nonce": nonce,
        "input_inventory_sha256": INVENTORY_SHA, "bundle_sha256": BUNDLE_SHA,
        "source_receipt_sha256": SOURCE_RECEIPT_SHA, "baseline_predictions_sha256": PREDICTIONS_SHA,
        "baseline_calibration_sha256": CALIBRATION_SHA, "prior": prior,
        "output_bucket": OUTPUT_BUCKET, "output_prefix": PREFIX + slot + "/",
        "resources": {"platform": "gpu-l40s-a", "preset": "1gpu-8vcpu-32gb",
            "timeout_seconds": timeout(slot), "disk_gib": 100, "shm_bytes": 1024**3,
            "restart_policy": "never", "preemptible": False, "max_output_bytes": MAX_OUTPUT,
            "publication_reserve_seconds": 600}, "secret_selectors": secret_selectors(),
        "final_test": False, "mlflow_online_required": False}


def receipt(item):
    if (not isinstance(item, dict) or set(item) != {"sha256", "size_bytes", "version_id"}
            or not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"])
            or type(item["size_bytes"]) is not int or not 0 < item["size_bytes"] <= MAX_OBJECT
            or not isinstance(item["version_id"], str) or item["version_id"] in ("", "null")):
        raise ValueError("invalid versioned artifact receipt")


def validate(request, source_commit=None):
    if len(REPOSITORY) > 64:
        raise ValueError("research image repository exceeds Nebius label limit")
    if not isinstance(request, dict) or request.get("slot") not in SLOTS:
        raise ValueError("invalid research request")
    patterns = {"source_commit": r"[0-9a-f]{40}", "image_digest": r"sha256:[0-9a-f]{64}",
                "context_public_key": r"[0-9a-f]{64}", "nonce": r"[0-9a-f]{32}"}
    if any(not isinstance(request.get(k), str) or not re.fullmatch(p, request[k]) for k, p in patterns.items()):
        raise ValueError("invalid research execution identity")
    if source_commit is not None and request["source_commit"] != source_commit:
        raise ValueError("image source commit mismatch")
    prior = request.get("prior")
    if not isinstance(prior, dict) or set(prior) != set(dependencies(request["slot"])):
        raise ValueError("fixed research dependency graph differs")
    for item in prior.values():
        if set(item) != {"success", "request"}:
            raise ValueError("prior receipt must bind its exact request")
        receipt(item["success"])
        previous = item["request"]
        # Previous requests are independently validated when read, without nesting
        # their dependency graphs into this small injected request.
        if (not isinstance(previous, dict) or set(previous) != {"sha256"}
                or not re.fullmatch(r"[0-9a-f]{64}", previous["sha256"])):
            raise ValueError("prior request checksum invalid")
    expected = template(request["slot"], *(request[k] for k in patterns), prior)
    if canonical(expected) != canonical(request) or len(canonical(request)) > 16384:
        raise ValueError("request escapes fixed research bounds")


def provider_spec(request):
    validate(request)
    return {"image": REPOSITORY + "@" + request["image_digest"], "platform": "gpu-l40s-a",
        "preset": "1gpu-8vcpu-32gb", "timeout": f'{timeout(request["slot"])}s',
        "disk": {"type": "NETWORK_SSD", "size_bytes": str(100 * 1024**3)}, "subnet_id": SUBNET,
        "environment_variables": [{"name": name, "mysterybox_secret": selector}
            for name, selector in sorted(secret_selectors().items())],
        "injected_files": [{"container_path": "/opt/research/request.json"}],
        "container_command": "", "args": "", "working_dir": "", "ports": [],
        "registry_credentials": {}, "public_ip": False, "ssh_authorized_keys": [],
        "preemptible": False, "restart_attempts": "0", "shm_size_bytes": str(1024**3), "volumes": []}


def request_sha(request):
    validate(request)
    return digest(canonical(request))
