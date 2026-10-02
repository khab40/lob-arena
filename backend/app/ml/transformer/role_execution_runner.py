"""One bounded, source-bound role audit; no fitting, scoring or training."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import resource
import sys
import time

from .role_audit import audit_package
from .role_audit_bundle import MAX_BUNDLE, read_bounded, verify
from .role_deadline import deadline
from .role_execution_context import wait_context
from .role_execution_spec import BUNDLE_SHA, SOURCE_RECEIPT_SHA, validate_request
from .role_execution_transport import claim, client, download, publish, put_new
from .verification_spec import INVENTORY_SHA, canonical, digest, load_inventory


def execute(s3, request, inventory_path, bundle_raw, source_raw, source_commit, work):
    validate_request(request, source_commit)
    if digest(bundle_raw) != BUNDLE_SHA or digest(source_raw) != SOURCE_RECEIPT_SHA:
        raise ValueError("role audit evidence differs from reviewed pins")
    verify(bundle_raw)  # Authenticate evidence before any governed object read.
    items = load_inventory(inventory_path, INVENTORY_SHA)
    work.mkdir(parents=True, exist_ok=False)
    started, cpu = time.monotonic(), time.process_time()
    with deadline(3540):  # Leave room for the provider's terminal log/teardown.
        claim(s3, request)
        stage = "context"
        try:
            with deadline(2940 - (time.monotonic() - started)):
                context = wait_context(s3, request)
                stage = "download"
                transfer = download(s3, items, work / "inputs")
                stage = "role_audit"
                artifacts = audit_package(work / "inputs", bundle_raw, source_raw)
                artifacts.update({
                    "configuration.json": canonical(request),
                    "source-separation.json": source_raw,
                    "measurements.json": canonical({
                        "elapsed_seconds": time.monotonic() - started,
                        "cpu_seconds": time.process_time() - cpu,
                        "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                        "measurement_scope": "linux_worker_before_publication",
                        "gpu_count": 0, "model_runs": 0, "cost": "unknown_operator_managed"}),
                    "lineage.json": canonical({
                        "run_id": request["run_id"], "context": context, "transfer": transfer,
                        "inventory_sha256": INVENTORY_SHA, "source_commit": source_commit,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "scope": "development_role_audit_only", "model_runs": 0,
                        "final_test_access": False}),
                })
        except Exception as error:
            failure = {"request_sha256": digest(canonical(request)),
                       "error_type": type(error).__name__, "stage": stage,
                       "automatic_retry": False}
            (work / "FAILED.json").write_bytes(canonical(failure))
            try:
                with deadline(30):
                    put_new(s3, request, "FAILED", canonical(failure))
            except Exception:
                pass  # Keep diagnostics without exposing credential-bearing SDK errors.
            raise
        # Any publication error is ambiguous. Never append FAILED after this point.
        return publish(s3, request, artifacts)


def main():
    if len(sys.argv) != 6:
        raise SystemExit("usage: role_execution_runner REQUEST INVENTORY BUNDLE SOURCE_RECEIPT WORK")
    request_path, inventory, bundle, source, work = map(Path, sys.argv[1:])
    try:
        request = json.loads(read_bounded(request_path, 16384))
        result = execute(client(), request, inventory, read_bounded(bundle, MAX_BUNDLE),
            read_bounded(source, 16384), Path("/opt/role-audit/source-commit").read_text().strip(), work)
    except Exception as error:
        print(canonical({"status": "failed", "error_type": type(error).__name__}).decode(), flush=True)
        raise SystemExit(1) from None
    print(canonical({"status": "published", "success_object": result}).decode(), flush=True)


if __name__ == "__main__":
    main()
