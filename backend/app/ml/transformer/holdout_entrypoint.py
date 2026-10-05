"""Authorize and inspect startup before constructing the inference consumer."""
import os
from pathlib import Path
import time

from .holdout_context import verify_context
from .holdout_runtime import bounded_read, inspect_runtime, load_request
from .holdout_spec import OUTPUT_ROOT
from .holdout_storage import HoldoutStore
from .role_deadline import deadline
from .role_execution_transport import client
from .settings_release import json_record
from .verification_spec import canonical, digest


def context_key(request):
    # Control-plane delivery is outside the unused immutable result prefix.
    return OUTPUT_ROOT + "contexts/" + request.run_id + "/" + request.nonce + ".json"


def wait_context(store, *, pause=time.sleep):
    request = store.request
    with deadline(min(request.startup_seconds, store.expires - time.monotonic())):
        for _ in range(request.startup_seconds // 5):
            try:
                raw, _ = store.get({"Bucket": request.output_bucket, "Key": context_key(request)},
                                   16384, metadata=True)
                envelope = json_record(raw)
                if canonical(envelope) != raw:
                    raise ValueError("signed control context must be canonical")
                return envelope
            except Exception as error:
                if getattr(error, "response", {}).get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
                    raise
                pause(5)
    raise TimeoutError("holdout context delivery expired")


def run(root, request_path, *, env=None, client_factory=client, inspect=inspect_runtime, execute_fn=None):
    root, env = Path(root), os.environ if env is None else env
    request = load_request(request_path)
    approved = env.get("HOLDOUT_APPROVED_REQUEST_SHA256")
    trusted = env.get("HOLDOUT_TRUSTED_PUBLIC_KEY")
    source = bounded_read(root / "source-commit", 40).decode()
    package = bounded_read(root / "portable-package.json", 512 * 1024)
    if (approved != request.sha256() or trusted != request.context_public_key
            or source != request.source_commit or digest(package) != request.package_sha256):
        raise ValueError("holdout startup lacks matching external pins")
    inspect(root)  # Static source/dependency checks precede credentials and any IO.
    expires = time.monotonic() + request.timeout_seconds
    with deadline(request.timeout_seconds):
        s3 = client_factory()
        store = HoldoutStore(s3, request, expires=expires)
        envelope = wait_context(store)
        verify_context(request, envelope, approved_request_sha256=approved, trusted_public_key=trusted)
        if execute_fn is None:
            from .holdout_worker import execute
            execute_fn = execute
        return execute_fn(s3, request, package, envelope, approved_request_sha256=approved,
            trusted_public_key=trusted, work="/job/holdout", source_commit=source, store=store)


if __name__ == "__main__":
    import json
    import sys
    try:
        receipt = run("/opt/research", "/opt/research/holdout-request.json.gz")
        print(json.dumps({"status": "published", "success": receipt}, sort_keys=True), flush=True)
    except Exception as error:
        # No exceptions/payloads/credentials in output. Provider logs persist even
        # when admission fails before any immutable result prefix can be claimed.
        print(json.dumps({"status": "failed", "stage": "holdout_entrypoint",
                          "error_type": type(error).__name__}), flush=True)
        sys.exit(1)
