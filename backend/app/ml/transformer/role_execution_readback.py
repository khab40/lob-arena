"""Independent versioned publication and row-ledger verification, without models."""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

from .receipt_publication import publish_receipt
from .role_audit import verify_package
from .role_deadline import deadline
from .role_execution_context import verify_context
from .role_execution_spec import validate_request
from .role_execution_transport import read_result
from .verification_spec import INVENTORY_SHA, canonical, digest, load_inventory

AUDIT_FILES = {"role-audit.json", "target-ledger.jsonl", "input-contract.json", "normalization.json"}
REQUIRED = AUDIT_FILES | {"configuration.json", "source-separation.json", "measurements.json", "lineage.json"}


def verify_artifacts(artifacts, request, context, expected_job_id, bundle_raw, items):
    validate_request(request, request["source_commit"])
    if set(artifacts) != REQUIRED or artifacts["configuration.json"] != canonical(request):
        raise ValueError("role result inventory or request differs")
    if context["job_id"] != expected_job_id:
        raise ValueError("result belongs to another provider Job")
    verified = verify_package({n: artifacts[n] for n in AUDIT_FILES}, bundle_raw,
                              artifacts["source-separation.json"])
    lineage = json.loads(artifacts["lineage.json"])
    expected = {"run_id": request["run_id"], "context": context,
        "transfer": {"get_attempts": len(items), "response_bytes": sum(i["size_bytes"] for i in items)},
        "inventory_sha256": INVENTORY_SHA, "source_commit": request["source_commit"],
        "scope": "development_role_audit_only", "model_runs": 0, "final_test_access": False}
    if (set(lineage) != {*expected, "completed_at"}
            or canonical({k: lineage[k] for k in expected}) != canonical(expected)):
        raise ValueError("role execution lineage differs")
    completed = datetime.fromisoformat(lineage["completed_at"])
    if completed.utcoffset() != timedelta(0):
        raise ValueError("role completion timestamp must identify UTC")
    measurements = json.loads(artifacts["measurements.json"])
    constants = {"measurement_scope": "linux_worker_before_publication", "gpu_count": 0,
                 "model_runs": 0, "cost": "unknown_operator_managed"}
    numeric = {"elapsed_seconds", "cpu_seconds", "peak_rss_kib"}
    if (set(measurements) != {*constants, *numeric}
            or canonical({k: measurements[k] for k in constants}) != canonical(constants)):
        raise ValueError("role measurement scope differs")
    if any(type(measurements[k]) not in (int, float) or not math.isfinite(measurements[k])
           or measurements[k] < 0 for k in numeric) or measurements["elapsed_seconds"] >= 2940:
        raise ValueError("role measurements are invalid or outside execution bound")
    return {"job_id": expected_job_id, "audit": verified, "measurements": measurements,
            "gpu_ready": False, "execution_authorized": False}


def collect(s3, request, expected_job_id, expected_success_sha256, bundle_raw, inventory_path, output: Path):
    validate_request(request, request["source_commit"])
    items = load_inventory(inventory_path, INVENTORY_SHA)
    output.mkdir(parents=True, exist_ok=False)
    with deadline(300):
        success, success_receipt = read_result(s3, request, "SUCCESS", 4096)
        if digest(success) != expected_success_sha256:
            raise ValueError("SUCCESS differs from the independent provider Job log")
        terminal = json.loads(success)
        if (set(terminal) != {"request_sha256", "checksums_sha256", "checksums_version_id", "files"}
                or terminal["request_sha256"] != digest(canonical(request))
                or terminal["files"] != len(REQUIRED)):
            raise ValueError("terminal request or artifact count differs")
        envelope, envelope_receipt = read_result(s3, request, "execution-context.json", 16384)
        context = verify_context(json.loads(envelope), request)
        intent, intent_receipt = read_result(s3, request, "INTENT", 16384)
        if intent != canonical(request):
            raise ValueError("execution intent differs")
        version = terminal["checksums_version_id"]
        if not isinstance(version, str) or not version or version == "null":
            raise ValueError("checksum version absent")
        checksums, checksum_receipt = read_result(s3, request, "checksums.json", 65536, version)
        if digest(checksums) != terminal["checksums_sha256"]:
            raise ValueError("terminal checksum binding differs")
        inventory = json.loads(checksums)
        if set(inventory) != REQUIRED:
            raise ValueError("published artifact inventory differs")
        for item in inventory.values():
            if (set(item) != {"sha256", "size_bytes", "version_id"}
                    or type(item["size_bytes"]) is not int or item["size_bytes"] <= 0
                    or not isinstance(item["version_id"], str) or item["version_id"] in ("", "null")):
                raise ValueError("invalid versioned artifact receipt")
        if sum(i["size_bytes"] for i in inventory.values()) > 8 * 1024 * 1024 - 65536:
            raise ValueError("published result exceeds byte budget")
        artifacts = {}
        for name, item in inventory.items():
            raw, receipt = read_result(s3, request, name, item["size_bytes"], item["version_id"])
            if receipt != item:
                raise ValueError("published artifact checksum differs")
            artifacts[name] = raw
        verified = verify_artifacts(artifacts, request, context, expected_job_id, bundle_raw, items)
        verified["publication_receipts"] = {"SUCCESS": success_receipt, "INTENT": intent_receipt,
            "execution-context.json": envelope_receipt, "checksums.json": checksum_receipt}
        for name, raw in {**artifacts, "SUCCESS": success, "INTENT": intent,
                          "checksums.json": checksums, "execution-context.json": envelope}.items():
            (output / name).write_bytes(raw)
        publish_receipt(output / "verification.json", canonical(verified))
    return verified
