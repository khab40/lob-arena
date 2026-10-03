"""Prepare, attest and read back the approved research slots; never create Jobs."""
import argparse
from datetime import UTC, datetime
import importlib.metadata
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.ml.transformer.research_context import observed
from app.ml.transformer.research_execution_spec import PROJECT, dependencies, request_sha, template, validate
from app.ml.transformer.research_readback import collect
from app.ml.transformer.research_storage import Store
from app.ml.transformer.role_execution_spec import secret_selectors
from app.ml.transformer.role_execution_transport import client
from app.ml.transformer.role_source import authenticate
from app.ml.transformer.verification_spec import canonical


def cli(*args):
    env = {**os.environ, "AI_AGENT": os.environ.get("AI_AGENT") or "codex"}
    # Read-only calls: the operator permits three retries, capped at two minutes.
    for seconds in (30, 60, 90, 120):
        try:
            process = subprocess.run(["rtk", "proxy", "nebius", *args, "--format", "json", "--retries", "1",
                "--no-browser", "--auth-timeout", f"{seconds}s", "--timeout", f"{seconds}s",
                "--per-retry-timeout", f"{seconds}s"], capture_output=True, timeout=seconds, env=env)
        except subprocess.TimeoutExpired:
            continue
        if not process.returncode:
            return json.loads(process.stdout)
        if b"code = NotFound" in process.stderr:
            return None
        if not any(code in process.stderr for code in (b"code = Unavailable", b"code = DeadlineExceeded")):
            break
    raise RuntimeError("Nebius operator read failed; inspect authentication/network without printing payloads")


def authenticated_client():
    # Dependency checks happen before touching credentials or object storage.
    import botocore.session  # noqa: F401
    for name, version in {"botocore": "1.43.103", "cryptography": "50.0.0", "numpy": "2.4.6",
                          "pyarrow": "25.0.0", "pydantic": "2.13.5"}.items():
        if importlib.metadata.version(name) != version:
            raise RuntimeError("operator dependency differs from pinned runtime")
    for name, selector in secret_selectors().items():
        payload = cli("mysterybox", "payload", "get", "--secret-id", selector["secret_id"],
                      "--version-id", selector["version_id"])
        entries = [item["string_value"] for item in payload["data"] if item.get("string_value")
                   and (name != "AWS_SECRET_ACCESS_KEY" or item.get("key") == "secret")]
        if len(entries) != 1:
            raise ValueError("ambiguous pinned development credential selector")
        os.environ[name] = entries[0]
    os.environ["AWS_EC2_METADATA_DISABLED"] = "true"
    return client()


def write(path, value):
    with path.open("xb") as stream:
        stream.write(canonical(value))


def prepare(args):
    directory = args.evidence / args.slot
    directory.mkdir(parents=True, exist_ok=False)
    custody = args.evidence / "context-private.key"
    if not custody.exists():
        private = Ed25519PrivateKey.generate()
        descriptor = os.open(custody, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(private.private_bytes_raw())
    key = Ed25519PrivateKey.from_private_bytes(custody.read_bytes())
    prior = {}
    for name in dependencies(args.slot):
        previous = args.evidence / name
        verified = json.loads((previous / "verification.json").read_bytes())
        if verified["status"] != "verified":
            raise ValueError("previous slot not independently verified")
        prior[name] = {"success": json.loads((previous / "success-receipt.json").read_bytes()),
                       "request": {"sha256": request_sha(json.loads((previous / "request.json").read_bytes()))}}
    request = template(args.slot, args.source_commit, args.image_digest,
        key.public_key().public_bytes_raw().hex(), secrets.token_hex(16), prior)
    validate(request)
    write(directory / "request.json", request)
    return {"request_sha256": request_sha(request), "request_file": str(directory / "request.json")}


def attest(store, directory, key):
    request = store.request
    if key.public_key().public_bytes_raw().hex() != request["context_public_key"]:
        raise ValueError("signing custody differs from prepared request")
    # Image provisioning is separate from the worker's five-minute handshake.
    expires = time.monotonic() + request["resources"]["timeout_seconds"]
    for _ in range(request["resources"]["timeout_seconds"] // 5):
        if time.monotonic() >= expires:
            break
        job = cli("ai", "job", "get-by-name", "--parent-id", PROJECT, "--name", request["run_id"])
        if job is None:
            time.sleep(5)
            continue
        context = observed(job, request)
        try:
            intent, item = store.read(request["slot"], "INTENT", limit=16384)
        except Exception as error:
            if getattr(error, "response", {}).get("Error", {}).get("Code") not in ("NoSuchKey", "404"):
                raise
            time.sleep(5)
            continue
        if intent != canonical(request):
            raise ValueError("worker intent differs")
        head = store.s3.head_object(Bucket=request["output_bucket"],
            Key=request["output_prefix"] + "INTENT", VersionId=item["version_id"])
        if not 0 <= (datetime.now(UTC) - head["LastModified"]).total_seconds() < 240:
            raise ValueError("worker intent expired")
        fresh = cli("ai", "job", "get-by-name", "--parent-id", PROJECT, "--name", request["run_id"])
        fresh_context = observed(fresh, request)
        if fresh_context["job_id"] != context["job_id"]:
            raise ValueError("provider Job changed before signing")
        context, job = fresh_context, fresh
        envelope = {"context": context, "signature": key.sign(canonical(context)).hex()}
        store.put("execution-context.json", canonical(envelope), artifact=False)
        write(directory / "provider-context.json", {"job": job, "envelope": envelope})
        return {"job_id": context["job_id"], "context_delivered": True}
    raise TimeoutError("operator attestation window expired")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "preflight", "attest", "collect"))
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--slot", required=True)
    parser.add_argument("--source-commit")
    parser.add_argument("--image-digest")
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--source-receipt", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        return prepare(args)
    directory = args.evidence / args.slot
    request = json.loads((directory / "request.json").read_bytes())
    store = Store(authenticated_client(), request)
    if args.action == "preflight":
        job = cli("ai", "job", "get-by-name", "--parent-id", PROJECT, "--name", request["run_id"])
        if job is not None:
            raise ValueError("slot already has a provider Job")
        response = store.s3.list_objects_v2(Bucket=request["output_bucket"], Prefix=request["output_prefix"], MaxKeys=1)
        if response.get("Contents") or response.get("KeyCount", 0):
            raise ValueError("slot prefix is occupied")
        return {"slot_absent": True, "output_empty": True, "checked_at": datetime.now(UTC).isoformat()}
    if args.action == "attest":
        key = Ed25519PrivateKey.from_private_bytes((args.evidence / "context-private.key").read_bytes())
        return attest(store, directory, key)
    bundle, source = args.bundle.read_bytes(), args.source_receipt.read_bytes()
    job = cli("ai", "job", "get-by-name", "--parent-id", PROJECT, "--name", request["run_id"])
    terminal_context = observed(job, request, allowed_states={"COMPLETED"})
    metadata, *_ = authenticate(bundle, source)
    success = json.loads((directory / "success-receipt.json").read_bytes())
    result = collect(store, args.slot, success, request_sha(request), bundle, source, metadata,
                     output=directory / "artifacts")
    if result["context"]["job_id"] != terminal_context["job_id"]:
        raise ValueError("completed provider Job differs from artifact context")
    write(directory / "provider-terminal.json", job)
    report = {k: result[k] for k in ("status", "context", "result", "audit", "inventory")}
    write(directory / "verification.json", report)
    return {"status": report["status"], "job_id": report["context"]["job_id"]}


if __name__ == "__main__":
    try:
        print(canonical(main()).decode())
    except Exception as error:
        print(canonical({"status": "failed", "error_type": type(error).__name__}).decode())
        sys.exit(1)
