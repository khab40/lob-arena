"""Bounded GPU research worker with durable evidence before successful exit."""
from datetime import UTC, datetime
import json
from pathlib import Path
import resource
import sys
import time

from .research_baseline import align, load as load_baseline
from .research_context import wait
from .research_execution_spec import BUNDLE_SHA, SOURCE_RECEIPT_SHA, request_sha, validate
from .research_inputs import prepare
from .research_readback import collect
from .research_storage import Store
from .role_audit import audit_package
from .role_deadline import deadline
from .role_execution_transport import PublicationUncertain, client, download
from .role_source import authenticate
from .verification_spec import INVENTORY_SHA, canonical, digest, load_inventory


def execute(s3, request, package, work):
    source_commit = (package / "source-commit").read_text().strip()
    validate(request, source_commit)
    bundle, source = (package / "bundle.json").read_bytes(), (package / "source-separation.json").read_bytes()
    if digest(bundle) != BUNDLE_SHA or digest(source) != SOURCE_RECEIPT_SHA:
        raise ValueError("research evidence package differs")
    metadata, *_ = authenticate(bundle, source)
    baseline, thresholds, baseline_receipt = load_baseline((package / "baseline.parquet").read_bytes(),
        (package / "baseline-calibration.json").read_bytes(), metadata)
    items = load_inventory(package / "inventory.jsonl", INVENTORY_SHA)
    work.mkdir(parents=True, exist_ok=False)
    store = Store(s3, request)
    started, cpu = time.monotonic(), time.process_time()
    expires = started + request["resources"]["timeout_seconds"] - 60
    with deadline(expires - started):
        store.claim()
        stage = "context"
        try:
            context = wait(store)
            store.put("configuration.json", canonical(request))
            store.event("started", {"job_id": context["job_id"], "source_commit": source_commit})
            prior = {}
            stage = "dependencies"
            with deadline(600):
                for slot, item in request["prior"].items():
                    prior[slot] = collect(store, slot, item["success"], item["request"]["sha256"],
                        bundle, source, metadata)
            stage = "inputs"
            transfer = download(s3, items, work / "inputs")
            with deadline(expires - time.monotonic() - 600):
                audit = audit_package(work / "inputs", bundle, source)
                for name, raw in audit.items():
                    store.put(name, raw)
                store.put("baseline-verification.json", canonical(baseline_receipt))
                if request["slot"] == "inference":
                    store.put("baseline-predictions.parquet", (package / "baseline.parquet").read_bytes())
                    store.put("baseline-calibration.json", (package / "baseline-calibration.json").read_bytes())
                splits, bindings = prepare(work / "inputs", bundle, source)
                for role in baseline:
                    align(splits[role], baseline[role])
                bindings.update(source_commit=source_commit, image_digest=request["image_digest"])
                store.event("inputs_verified", {"bindings": bindings, "transfer": transfer})
                stage = "gpu"
                from .research_run import run
                result = run(request["slot"], splits, bindings, baseline, thresholds,
                             prior, store, work, expires)
            result.update(request_sha256=request_sha(request), job_id=context["job_id"],
                completed_at=datetime.now(UTC).isoformat(),
                measurements={"elapsed_seconds": time.monotonic() - started,
                    "cpu_seconds": time.process_time() - cpu,
                    "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                    "cost": "unknown_operator_managed", "transfer": transfer},
                mlflow_reconciliation="pending_retained_artifacts", final_test_access=False)
        except PublicationUncertain:
            raise  # Do not write another terminal marker after an ambiguous PUT.
        except Exception as error:
            failure = {"request_sha256": request_sha(request), "stage": stage,
                "error_type": type(error).__name__, "automatic_replacement": False}
            try:
                with deadline(30):
                    store.put("FAILED", canonical(failure), artifact=False)
            except Exception:
                pass
            raise
        return store.finish(result)


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: research_worker REQUEST WORK")
    request_path, work = map(Path, sys.argv[1:])
    try:
        if request_path.stat().st_size > 16384:
            raise ValueError("request exceeds injection envelope")
        result = execute(client(), json.loads(request_path.read_bytes()), Path("/opt/research"), work)
    except Exception as error:
        print(canonical({"status": "failed", "error_type": type(error).__name__}).decode(), flush=True)
        raise SystemExit(1) from None
    print(canonical({"status": "published", "success_object": result}).decode(), flush=True)


if __name__ == "__main__":
    main()
