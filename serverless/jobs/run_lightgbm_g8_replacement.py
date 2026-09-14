"""Signed replacement entrypoint. Verification is the default; execution/recovery are explicit."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path

from app.ml.lightgbm.artifacts import sha256_file
from app.ml.lightgbm.cloud_contracts import Wave1ExecutionContext
from app.ml.lightgbm.cloud_runner import _verify_signature
from app.ml.lightgbm.g8_replacement import CODE_PATHS, job_command, reservation, verify_mount, verify_package


def observed_context(plan, package, trusted_key, *, recovery=False):
    """Wait for an operator-signed API readback, not a guessed/preassigned Job ID.

    The operator stages this in the approved filesystem after create returns.
    No final access occurs while waiting; expiry fails closed. No create retry.
    """
    purpose = "recover" if recovery else "execute"
    suffix = "-recovery" if recovery else ""
    path = Path(plan.mount_path) / "contexts" / f"{plan.run_id}{suffix}.json"
    signature = path.with_suffix(".sig")
    deadline = time.monotonic() + 300
    while not (path.is_file() and signature.is_file()):
        if time.monotonic() >= deadline or datetime.now(UTC) >= (plan.cleanup_deadline if recovery else plan.expires_at):
            raise ValueError("signed Job readback unavailable before execution deadline")
        time.sleep(1)
    if (path.resolve() != path.absolute() or signature.resolve() != signature.absolute()
            or path.stat().st_size > 64 * 1024 or signature.stat().st_size > 1024):
        raise ValueError("signed Job context must use bounded canonical files")
    content, signature_bytes = path.read_bytes(), signature.read_bytes()
    if len(content) > 64 * 1024 or len(signature_bytes) > 1024:
        raise ValueError("signed Job context grew beyond bounds")
    # Verify the exact bytes parsed, even if a shared-storage writer changes the source.
    with tempfile.TemporaryDirectory(prefix="g8-context-") as directory:
        snapshot = Path(directory) / "context.json"
        sig_snapshot = Path(directory) / "context.sig"
        snapshot.write_bytes(content)
        sig_snapshot.write_bytes(signature_bytes)
        _verify_signature(snapshot, sig_snapshot, package / "authorization-public.pem", trusted_public_key_sha256=trusted_key)
    raw = json.loads(content)
    if (set(raw) != {"execution_package_sha256", "filesystem_id", "context", "job_readback_sha256", "purpose"}
            or raw["execution_package_sha256"] != plan.identity() or raw["filesystem_id"] != plan.filesystem_id
            or raw["purpose"] != purpose):
        raise ValueError("signed Job readback differs from replacement package/storage")
    import re
    if re.fullmatch(r"[a-f0-9]{64}", raw["job_readback_sha256"]) is None:
        raise ValueError("original API Job readback digest required")
    context = Wave1ExecutionContext.model_validate(raw["context"])
    if not context.nebius_job_id or not context.nebius_job_id.startswith("aijob-"):
        raise ValueError("actual Nebius Job identity required before final access")
    return context


def main():
    # Importing the injected legacy runner must not add __pycache__ to the exact
    # immutable package allowlist before the final expiry/signature recheck.
    sys.dont_write_bytecode = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--execute", action="store_true")
    mode.add_argument("--recover", action="store_true")
    mode.add_argument("--command", action="store_true", help="Print a reviewed command; do not submit")
    mode.add_argument("--recovery-command", action="store_true", help="Print a recovery command; do not submit")
    args = parser.parse_args()
    trusted = os.environ.get("WAVE1_TRUSTED_AUTHORIZATION_PUBLIC_KEY_SHA256", "")
    recovery = args.recover or args.recovery_command
    plan, request = verify_package(args.package, trusted_key=trusted, recovery=recovery)
    if args.command or args.recovery_command:
        print(json.dumps(job_command(plan, args.package, trusted, recovery=recovery)))
        return
    if not (args.execute or args.recover):
        print(json.dumps({"package_sha256": plan.identity(), "verified": True, "remote_accessed": False}))
        return
    # Verify actual imports/entrypoints, not just copies included beside the manifest.
    for name, path in CODE_PATHS.items():
        if sha256_file(Path(path)) != plan.files[name].sha256:
            raise ValueError("runtime overlay differs from signed package: " + name)
    mount_identity = verify_mount(plan)
    from app.ml.lightgbm.g8_live_recovery import execution_lock, finish_retained, run_live
    from app.ml.lightgbm.g8_mlflow_recovery import ResumeTarget
    from app.nebius.object_storage import TransferLimits

    if args.recover:
        context = observed_context(plan, args.package, trusted, recovery=True)
        verify_package(args.package, trusted_key=trusted, recovery=True)
        from app.ml.lightgbm.cloud_runner import _validate_execution_context
        _validate_execution_context(request, context)
        root = Path(plan.mount_path) / plan.run_id
        target = ResumeTarget(root / "ledger", reservation(plan, request))
        if verify_mount(plan) != mount_identity:
            raise ValueError("durable mount changed while waiting for signed Job context")
        with execution_lock(root, create=False):
            receipt = finish_retained(root, target, limits=TransferLimits(
                max_files=plan.max_checkpoint_files, max_bytes=plan.max_checkpoint_bytes))
    else:
        spec = importlib.util.spec_from_file_location("g8_signed_legacy", args.package / "run_lightgbm_g8.py")
        legacy = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = legacy
        spec.loader.exec_module(legacy)
        legacy._validate_request(request, request.input_release_uri, plan.candidate_release_uri)
        legacy._verify_injected_authorization(request, argparse.Namespace(
            authorization=args.package / "authorization.json", authorization_signature=args.package / "authorization.sig",
            authorization_public_key=args.package / "authorization-public.pem"), trusted)
        context = observed_context(plan, args.package, trusted)
        legacy._execution_context = lambda: context
        # Recheck expiry and native mount identity after the potentially long
        # context wait, immediately before the single-use live entry.
        verify_package(args.package, trusted_key=trusted)
        if verify_mount(plan) != mount_identity:
            raise ValueError("durable mount changed while waiting for signed Job context")
        receipt = run_live(plan, request, args.package, legacy)
    print(json.dumps({**receipt, "executing_job_id": context.nebius_job_id,
                      "execution_purpose": "recover" if args.recover else "execute"}, sort_keys=True))


if __name__ == "__main__":
    main()
