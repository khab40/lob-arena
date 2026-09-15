"""Two-phase native synthetic rehearsal. Never a production replacement entrypoint."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

if __package__:
    from .g8_native_contract import PROJECT
    from .g8_native_runtime import actual_runtime, native_mount, observed_context, verify_package
else:
    from g8_native_contract import PROJECT
    from g8_native_runtime import actual_runtime, native_mount, observed_context, verify_package


def recovery_workers(deadline):
    """Share the parent's budget, leaving provider termination/evidence headroom."""
    for worker, expected in (("artifact-loss", 74), ("finish", 0)):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("native recovery budget exhausted before " + worker)
        timeout = min(900, remaining) if worker == "artifact-loss" else remaining
        result = subprocess.run([sys.executable, str(Path(__file__)), "--phase", "recover", "--worker", worker],
                                check=False, timeout=timeout)
        if result.returncode != expected:
            raise RuntimeError("native recovery child did not reach its reviewed outcome: " + worker)


def main():
    # Both children and all preflight/context waiting share 55 minutes; the
    # one-hour provider limit retains five minutes for final evidence/overhead.
    recovery_deadline = time.monotonic() + 3300
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", required=True, choices=("score", "recover"))
    parser.add_argument("--worker", choices=("artifact-loss", "finish"))
    args = parser.parse_args()
    if args.worker and args.phase != "recover":
        parser.error("only recovery has child processes")
    package = Path("/job/g8")
    trusted = os.environ.get("G8_NATIVE_REVIEWER_SHA256", "")
    plan = verify_package(package, phase=args.phase, trusted=trusted)
    runtime = actual_runtime(plan, package)
    mount = native_mount(plan)
    context, readback, signature = observed_context(plan, package, phase=args.phase, trusted=trusted)
    verify_package(package, phase=args.phase, trusted=trusted)
    if native_mount(plan) != mount or actual_runtime(plan, package) != runtime:
        raise ValueError("native mount or imported runtime changed during context wait")
    stat = os.statvfs(plan.mount_path)
    if not 9 * 1024**3 <= stat.f_blocks * stat.f_frsize <= 11 * 1024**3:
        raise ValueError("native capacity differs from the approved 10 GiB filesystem")
    # Import the model runtime only after package, Job and actual runtime gates.
    from app.ml.lightgbm.cloud_contracts import LightGbmCloudJobRequest, Wave1ExecutionContext
    from app.ml.lightgbm.g8_mlflow_recovery import ReservationSpec, _persist
    from app.ml.lightgbm.g8_scored_checkpoint import _directory_sync
    if __package__:
        from .g8_native_lifecycle import authentication_probe, score, recover
    else:
        from g8_native_lifecycle import authentication_probe, score, recover

    request = LightGbmCloudJobRequest.model_validate_json((package / "source-capsule/metadata-5.part").read_bytes())
    if request.canonical_hash() != plan.request_sha256:
        raise ValueError("native source request differs from the signed plan")
    evidence = Path(plan.mount_path) / "native-evidence"
    if evidence.absolute() != evidence.resolve():
        raise ValueError("native evidence directory must not traverse links")
    evidence.mkdir(mode=0o700, exist_ok=True)
    _persist(evidence / (args.phase + "-context.json"), context)
    sig_path = evidence / (args.phase + "-context.sig")
    if sig_path.exists():
        if sig_path.is_symlink() or sig_path.read_bytes() != signature:
            raise ValueError("retained context signature differs")
    else:
        with sig_path.open("xb") as stream:
            stream.write(signature)
            stream.flush()
            os.fsync(stream.fileno())
        _directory_sync(evidence)
    _persist(evidence / (args.phase + "-runtime.json"), {**readback, **runtime, "mount": mount})
    authentication_probe()
    original_tags = ReservationSpec.tags

    def synthetic_tags(spec):
        if spec.request_sha256 != plan.request_sha256 or spec.candidate_sha256 != plan.candidate_sha256:
            raise ValueError("native reservation escaped the frozen synthetic request")
        return {**original_tags(spec), "g8.synthetic_rehearsal": "true",
                "g8.dataset_lineage_kind": plan.dataset_lineage_kind,
                "g8.comparison_kind": plan.comparison_kind}

    with patch.object(ReservationSpec, "tags", synthetic_tags):
        if args.phase == "score":
            execution = Wave1ExecutionContext(project_id=PROJECT, image=plan.image, nebius_job_id=context["job_id"])
            score(plan, request, package, execution)
            raise AssertionError("score phase must terminate at the sealed checkpoint")
        if args.worker:
            receipt = recover(plan, request, interrupt=args.worker == "artifact-loss")
            _persist(evidence / "remote-recovery.json", {
                **receipt, "executing_job_id": context["job_id"], "execution_package_sha256": plan.identity(),
                "dataset_lineage_kind": plan.dataset_lineage_kind, "comparison_kind": plan.comparison_kind,
                "production_g8_complete": False,
            })
            print(json.dumps(receipt, sort_keys=True))
            return
        # Fresh processes in the second Job; no extra Job or resubmission is used.
        recovery_workers(recovery_deadline)
        _persist(evidence / "job-reattachment.json", {
            "original_job_id": context["previous_terminal"]["metadata"]["id"],
            "recovery_job_id": context["job_id"], "filesystem_id": plan.filesystem_id,
            "execution_package_sha256": plan.identity(), "original_job_terminal_verified": True,
            "native_checkpoint_reattachment_verified": True, "production_g8_complete": False,
        })
        print((evidence / "job-reattachment.json").read_text())


if __name__ == "__main__":
    main()
