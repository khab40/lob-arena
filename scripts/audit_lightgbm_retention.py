#!/usr/bin/env python3
"""Read exact development objects and an existing MLflow run; never write remotely."""

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from lightgbm_retention_contract import load_inventory, require
from lightgbm_retention_transport import (
    StorageReader, TrackingReader, audit_storage, audit_tracking, deadline, error_code,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", required=True, type=Path)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--results-bucket", required=True)
    parser.add_argument("--input-bucket", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--tracking-endpoint", default="http://127.0.0.1:5500")
    parser.add_argument("--timeout-seconds", type=int, default=300)
    parser.add_argument("--execute", action="store_true", help="perform bounded remote GETs; default is plan only")
    args = parser.parse_args()
    raw = args.inventory.read_bytes()
    inv = load_inventory(raw, args.inventory_sha256, args.results_bucket, args.input_bucket)
    require(1 <= args.timeout_seconds <= 600, "invalid timeout")
    output = args.output.absolute()
    require(output.parent.resolve() == output.parent and not output.is_symlink(), "noncanonical output")
    require(output != args.inventory.resolve(), "cannot overwrite inventory")
    report = {
        "schema_version": "lightgbm_retention_audit_v1",
        "started_at": datetime.now(timezone.utc).isoformat(),
        "inventory_sha256": args.inventory_sha256,
        "candidate_sha256": inv["candidate_sha256"], "freeze_sha256": inv["freeze_sha256"],
        "mlflow_run_id": inv["lineage"]["mlflow_run_id"],
        "result_uri": inv["result_uri"],
        "tool_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            Path(__file__), Path(__file__).with_name("lightgbm_retention_contract.py"),
            Path(__file__).with_name("lightgbm_retention_transport.py"))},
        "bounds": {"timeout_seconds": args.timeout_seconds, "jobs": 0,
                   "result_objects": len(inv["result_objects"]),
                   "result_bytes": sum(x["size_bytes"] for x in inv["result_objects"]),
                   "mlflow_artifacts": 7, "mlflow_list_pages": 10, "retries": 0},
        "scope": {"remote_writes": False, "model_loaded": False, "rows_parsed": False,
                  "final_access": False, "final_evaluation_authorized": False},
        "storage": {"verified": False, "status": "not_attempted"},
        "mlflow": {"verified": False, "status": "not_attempted"},
        "remaining": ["External input manifests are references, not downloaded by this audit.",
                      "No search for unlisted S3 objects; verifies the exact anchored inventory only.",
                      "Per-iteration learning curves, registry versions and promotion are separate work.",
                      "G8 comparison, execution package and final authorization remain separate."],
    }
    # Reserve an exclusive, private output before making any network request.
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as handle:
        try:
            if args.execute:
                with deadline(args.timeout_seconds):
                    for name, action in (
                        ("storage", lambda: audit_storage(inv, StorageReader())),
                        ("mlflow", lambda: audit_tracking(inv, TrackingReader(args.tracking_endpoint))),
                    ):
                        try:
                            report[name] = action()
                        except TimeoutError:
                            report[name] = {"verified": False, "error": "TimeoutError"}
                            raise
                        except Exception as exc:
                            report[name] = {"verified": False, "error": error_code(exc)}
        except TimeoutError:
            report["deadline_exceeded"] = True
        finally:
            report["completed_at"] = datetime.now(timezone.utc).isoformat()
            report["status"] = ("verified" if all(report[k]["verified"] for k in ("storage", "mlflow"))
                                else "incomplete" if args.execute else "planned")
            json.dump(report, handle, indent=2, sort_keys=True)
            handle.write("\n")
    print(json.dumps({"status": report["status"], "output": str(output)}))
    return 0 if report["status"] in {"planned", "verified"} else 2


if __name__ == "__main__":
    raise SystemExit(main())
