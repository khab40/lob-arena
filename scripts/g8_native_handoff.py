"""Render and verify the existing MLflow VM's temporary native attachment.

No cloud mutation, SSH or model execution. Preserve raw API readbacks as inputs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from serverless.jobs.g8_native_contract import PROJECT, canonical  # noqa: E402
from serverless.jobs.g8_native_runtime import bounded, verify_filesystem  # noqa: E402

VM = "computeinstance-e00xq8hqrzks2pf3gn"
TAG = "g8-native-rehearsal"
MOUNT = "/mnt/g8-native-rehearsal"


def identity(vm):
    metadata = vm["metadata"]
    version = metadata.get("resource_version")
    if (metadata.get("id") != VM or metadata.get("parent_id") != PROJECT
            or metadata.get("name") != "aimada-wave1-mlflow"
            or type(version) not in (int, str) or not str(version).isdigit() or int(version) <= 0):
        raise ValueError("exact MLflow VM identity and resource version required")


def attachment(filesystem_id):
    if re.fullmatch(r"computefilesystem-[a-z0-9]+", filesystem_id) is None:
        raise ValueError("returned filesystem ID required")
    return {"attach_mode": "READ_WRITE", "existing_filesystem": {"id": filesystem_id}, "mount_tag": TAG}


def baseline(before):
    identity(before)
    if (before["status"]["state"] != "STOPPED" or before["spec"].get("stopped") is not True
            or before["spec"].get("filesystems", [])):
        raise ValueError("baseline must be the stopped VM without filesystem attachments")


def verify_vm(before, current, filesystem_id, *, attached, stopped=True):
    baseline(before)
    identity(current)
    expected = [attachment(filesystem_id)] if attached else []
    if current["spec"].get("filesystems", []) != expected:
        raise ValueError("VM native attachment differs")
    for field in ("spec", "metadata"):
        ignored = {"filesystems", "stopped"} if field == "spec" else {"resource_version"}
        if ({k: v for k, v in before[field].items() if k not in ignored}
                != {k: v for k, v in current[field].items() if k not in ignored}):
            raise ValueError("unrelated VM configuration changed")
    if int(current["metadata"]["resource_version"]) < int(before["metadata"]["resource_version"]):
        raise ValueError("VM resource version moved backwards")
    if (current["status"]["state"] != ("STOPPED" if stopped else "RUNNING")
            or current["spec"].get("stopped", False) is not stopped
            or current["status"].get("network_interfaces") != before["status"].get("network_interfaces")):
        raise ValueError("VM state or observed network changed")
    return {"vm_id": VM, "filesystem_id": filesystem_id, "attached": attached,
            "stopped": stopped, "mount_tag": TAG, "mount_path": MOUNT,
            "before_sha256": hashlib.sha256(canonical(before)).hexdigest(),
            "current_sha256": hashlib.sha256(canonical(current)).hexdigest(),
            "native_mount_verified": False, "context_delivery_verified": False}


def render(before, current, filesystem, *, detach=False):
    filesystem_id = filesystem["metadata"]["id"]
    verify_filesystem(filesystem, filesystem_id)
    verify_vm(before, current, filesystem_id, attached=detach)
    status = filesystem["status"]
    if (status.get("read_only_attachments", [])
            or status.get("read_write_attachments", []) != ([VM] if detach else [])):
        raise ValueError("unexpected filesystem attachment owners")
    command = ["nebius", "compute", "instance", "update", "--id", VM, "--patch",
               "--resource-version", str(current["metadata"]["resource_version"])]
    # Clearing an empty repeated field explicitly avoids patch-mode omission.
    command += (["--clear-mask", "spec.filesystems"] if detach else
                ["--filesystems", json.dumps([attachment(filesystem_id)], separators=(",", ":"))])
    return {"command": command, "vm_id": VM, "filesystem_id": filesystem_id,
            "mount_tag": TAG, "mount_path": MOUNT, "submitted": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("attach", "detach", "verify-attached", "verify-restored"))
    for name in ("before", "current", "filesystem"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--running", action="store_true")
    args = parser.parse_args()
    before, current, filesystem = [json.loads(bounded(getattr(args, n))) for n in ("before", "current", "filesystem")]
    if args.action.startswith("verify-"):
        verify_filesystem(filesystem, filesystem["metadata"]["id"])
        result = verify_vm(before, current, filesystem["metadata"]["id"],
                           attached=args.action == "verify-attached", stopped=not args.running)
    else:
        if args.running:
            parser.error("attachment changes require the stopped VM")
        result = render(before, current, filesystem, detach=args.action == "detach")
    print(json.dumps(result, indent=2))
