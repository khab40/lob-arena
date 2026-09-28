"""Execute the approved CPU-only development-input check exactly once."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys

from .verification_context import validate_request, wait_context
from .verification_measure import verify_parity
from .verification_spec import BATCH_SIZES, INVENTORY_SHA, RUN_ID, canonical, digest, load_inventory
from .verification_transport import claim, client, deadline, download, publish, put_new


def run_cases(inputs, work):
    records, directories = [], []
    for size in BATCH_SIZES:
        target = work / f"batch-{size}"
        subprocess.run([sys.executable, "-m", "app.ml.transformer.verification_measure",
            str(inputs), str(target), str(size)], timeout=600, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        records.append(json.loads((target / "measurement.json").read_bytes()))
        directories.append(target)
    verify_parity(records, directories)
    return records, directories[0]


def execute(s3, request, inventory_path, source_commit, work):
    validate_request(request, source_commit)
    items = load_inventory(inventory_path, INVENTORY_SHA)
    work.mkdir(parents=True, exist_ok=False)
    claim(s3, request)  # Refuse previous runs before accessing governed inputs.
    stage = "context"
    try:
        context = wait_context(s3, request)
        stage = "download"
        transfer = download(s3, items, work / "inputs")
        stage = "measurement"
        records, first = run_cases(work / "inputs", work)
        artifacts = {"configuration.json": canonical(request),
            "normalization.json": (first / "normalization.json").read_bytes(),
            "input-contract.json": (first / "input-contract.json").read_bytes(),
            "measurements.json": canonical(records),
            "inventory-reference.json": canonical({"sha256": INVENTORY_SHA, "objects": len(items)}),
            "lineage.json": canonical({"run_id": RUN_ID, "context": context, "transfer": transfer,
                "source_commit": source_commit, "completed_at": datetime.now(UTC).isoformat(),
                "scope": "development_input_preparation_only", "model_runs": 0})}
    except Exception as error:
        # Do not leak credential-bearing SDK errors or overwrite an earlier result.
        failure = {"request_sha256": digest(canonical(request)), "error_type": type(error).__name__,
                   "stage": stage, "automatic_retry": False}
        (work / "FAILED.json").write_bytes(canonical(failure))
        try:
            with deadline(30):
                put_new(s3, "FAILED", canonical(failure))
        except Exception:
            pass  # Job log + local diagnostic remain; never claim publication success.
        raise
    # Publication errors are ambiguous: never append FAILED after an uncertain SUCCESS.
    return publish(s3, artifacts, digest(canonical(request)))


def main():
    if len(sys.argv) != 4:
        raise SystemExit("usage: verification_runner REQUEST INVENTORY WORK_DIRECTORY")
    request = json.loads(Path(sys.argv[1]).read_bytes())
    source_commit = Path("/opt/verifier/source-commit").read_text().strip()
    try:
        result = execute(client(), request, Path(sys.argv[2]), source_commit, Path(sys.argv[3]))
    except Exception as error:
        print(canonical({"status": "failed", "error_type": type(error).__name__}).decode(), flush=True)
        raise SystemExit(1) from None
    print(canonical({"status": "published", "success_object": result}).decode(), flush=True)


if __name__ == "__main__":
    main()
