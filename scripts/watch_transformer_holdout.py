"""Preflight or supervise the externally submitted, exactly approved holdout Job."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
SUBMISSION = {"mode": "coordinated_v1", "admission_seconds": 120, "creation_seconds": 90,
              "observation_reserve_seconds": 30, "access_reserve_seconds": 300}
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
os.environ["AI_AGENT"] = os.environ.get("AI_AGENT") or "codex"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def durable_record(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def files(output, proposal):
    for name, expected in proposal["files"].items():
        path = output / name
        if path.is_symlink() or not path.resolve().is_relative_to(output) or sha(path) != expected:
            raise ValueError("execution package differs")


def access_deadline(proposal, buckets, now=time.time):
    if proposal.get("submission") != SUBMISSION:
        raise ValueError("exact coordinated submission bounds required")
    if set(buckets) != {"final", "results"}:
        raise ValueError("both policy observations required")
    starts = []
    for name, bucket in buckets.items():
        metadata = bucket["metadata"]
        if metadata["resource_version"] != str(int(proposal["policy_versions"][name]) + 1):
            raise ValueError("temporary policy resource version differs")
        stamp = datetime.fromisoformat(metadata["updated_at"].replace("Z", "+00:00"))
        if stamp.tzinfo is None or stamp.timestamp() > now() + 5:
            raise ValueError("invalid access start time")
        starts.append(stamp.timestamp())
    expires = min(starts) + proposal["access_seconds"]
    if expires - now() < proposal["create_to_terminal_seconds"] + SUBMISSION["access_reserve_seconds"]:
        raise TimeoutError("insufficient remaining access")
    return expires


def create_once(output, proposal, proposal_sha, remaining, expires, now=time.time, monotonic=time.monotonic):
    started = monotonic()
    if proposal.get("submission") != SUBMISSION:
        raise ValueError("exact coordinated submission bounds required")
    sources(proposal, loaded=True)
    files(output, proposal)
    argv_path = output / "create-argv.json"
    raw = argv_path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != proposal["files"]["create-argv.json"]:
        raise ValueError("creation argv differs")
    command = json.loads(raw)
    if not isinstance(command, list) or not all(isinstance(arg, str) for arg in command):
        raise ValueError("creation argv must be strings")
    timeout = min(SUBMISSION["creation_seconds"], int(remaining - (monotonic() - started) - 30))
    if timeout < 1 or expires - now() < proposal["create_to_terminal_seconds"] + 300:
        raise TimeoutError("insufficient creation or access reserve")
    durable_record(output / "creation-attempt.json", {"proposal_sha256": proposal_sha,
        "argv_sha256": hashlib.sha256(raw).hexdigest(), "started_at": now(),
        "timeout_seconds": timeout, "attempt": 1, "reconcile_required": True})
    timeout = min(SUBMISSION["creation_seconds"], int(remaining - (monotonic() - started) - 30))
    if timeout < 1 or expires - now() < proposal["create_to_terminal_seconds"] + 300:
        raise TimeoutError("reserve exhausted after durable intent; reconcile")
    # Preserve the exact approved workload --timeout 1h. Bound orchestration only
    # through subprocess timeout, without the generic read/cancel flag builder.
    outcome = {"reconcile_required": True, "retry_allowed": False}
    try:
        result = subprocess.run(["rtk", "proxy", *command], capture_output=True, timeout=timeout)
        outcome["returncode"] = result.returncode
        outcome["stdout_sha256"] = hashlib.sha256(result.stdout).hexdigest()
        outcome["stderr_sha256"] = hashlib.sha256(result.stderr).hexdigest()
        try:
            response = json.loads(result.stdout) if result.returncode == 0 else None
            outcome["status"] = ("nonzero_exit" if result.returncode else
                "async_returned" if isinstance(response, dict) else "uncertain_response")
        except (ValueError, UnicodeError):
            outcome["status"] = "uncertain_response"
    except subprocess.TimeoutExpired:
        outcome["status"] = "timeout"
    except OSError:
        outcome["status"] = "spawn_error"
    outcome["finished_at"] = now()
    try:
        durable_record(output / "creation-outcome.json", outcome)
    except OSError:
        # Intent already consumed the attempt. Loss of an advisory receipt must
        # not leave an accepted/ambiguous Job without observation and cancellation.
        outcome["outcome_receipt_durable"] = False
        print(json.dumps({"status": "creation_outcome_receipt_failed", "reconcile_required": True,
            "creation_intent_retained": True, "retry_allowed": False}), flush=True)
    return outcome  # Every outcome consumes creation; the watcher reconciles it.


def sources(proposal, loaded=False):
    pins = proposal["operator_files_sha256"]
    if "scripts/watch_transformer_holdout.py" not in pins:
        raise ValueError("supervisor is not pinned")
    for name, expected in pins.items():
        path = ROOT / name
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT) or sha(path) != expected:
            raise ValueError("reviewed supervisor source changed")
    if loaded:
        for name, module in tuple(sys.modules.items()):
            if name == "app" or name.startswith("app.") or name == "collect_transformer_lineage_metadata":
                path = getattr(module, "__file__", None)
                if path and str(Path(path).resolve().relative_to(ROOT)) not in pins:
                    raise ValueError("unexpected first-party source")


def argv(args, timeout):
    return ["rtk", "proxy", "nebius", *args, "--format", "json", "--no-browser", "--retries", "1",
            "--timeout", f"{timeout}s", "--auth-timeout", f"{timeout}s", "--per-retry-timeout", f"{timeout}s"]


def cli(*args, mutation=False, budget=300, now=time.monotonic):
    expires = now() + budget
    for scheduled in ((30,) if mutation else (30, 60, 90, 120)):
        timeout = min(scheduled, int(expires - now()))
        if timeout < 1:
            raise TimeoutError("provider polling budget exhausted")
        try:
            result = subprocess.run(argv(args, timeout),
                capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            if mutation or timeout == 120:
                raise TimeoutError("provider call requires reconciliation") from None
            continue
        if result.returncode == 0:
            return json.loads(result.stdout)
        if b"NotFound" in result.stderr and not mutation:
            return None
        if mutation or b"Unavailable" not in result.stderr or timeout == 120:
            raise RuntimeError("provider call failed; inspect without retrying mutation")
    raise TimeoutError("provider polling budget exhausted")


def cli_preflight():
    commands = [("storage", "bucket", "get", "--id", "storagebucket-preflight"),
        ("ai", "job", "get-by-name", "--parent-id", "project-preflight", "--name", "preflight"),
        ("ai", "job", "cancel", "--id", "aijob-preflight", "--async")]
    for args in commands:
        result = subprocess.run(argv(args, 30) + ["--help"], capture_output=True, timeout=30)
        if result.returncode:
            raise ValueError("installed Nebius CLI rejects supervisor arguments")


def preflight(output, proposal_sha):
    raw = (output / "proposal.json").read_bytes()
    if len(raw) > 65536 or hashlib.sha256(raw).hexdigest() != proposal_sha:
        raise ValueError("external proposal pin differs")
    proposal = json.loads(raw)
    sources(proposal)
    files(output, proposal)
    from collect_transformer_lineage_metadata import runtime_probe, verify_imports
    from app.ml.transformer.verification_transport import client
    from app.ml.transformer.holdout_runtime import load_request
    from app.ml.transformer.holdout_delivery import deliver_context
    from app.ml.transformer.holdout_storage import HoldoutStore
    from app.ml.transformer.holdout_supervision import supervise
    verify_imports(ROOT)
    sources(proposal, loaded=True)
    if Path(sys.executable).absolute() != Path(proposal["operator_python"]).absolute():
        raise ValueError("exact operator Python required")
    runtime_probe(client, proposal)
    cli_preflight()  # Local help only: no API calls, authentication or resource creation.
    sources(proposal, loaded=True)
    request = load_request(output / "request.json.gz")
    if request.sha256() != proposal["request_sha256"]:
        raise ValueError("request pin differs")
    return proposal, request, client, deliver_context, HoldoutStore, supervise


def run(output, proposal_sha, offline=False, submit=False):
    proposal, request, factory, deliver_context, Store, supervise = preflight(output, proposal_sha)
    if offline:
        return {"status": "offline_preflight_passed", "credentials_read": False, "jobs_created": 0}
    approval = json.loads((output / "operator-approval.json").read_bytes())
    if approval != {"approved": True, "proposal_sha256": proposal_sha}:
        raise ValueError("exact operator approval record required")
    for name in ("supervision-attempt.json", "creation-attempt.json", "creation-outcome.json", "context-receipt.json"):
        if (output / name).exists() or (output / name).is_symlink():
            raise ValueError("retained attempt consumes this execution directory")
    buckets = {}
    for name, identity in (("final", "storagebucket-e004963828556923796882"),
                           ("results", "storagebucket-e009132243970085528999")):
        bucket = cli("storage", "bucket", "get", "--id", identity)
        if bucket is None or bucket["spec"]["bucket_policy"]["rules"] != json.loads(
                (output / f"{name}-policy-temporary.json").read_bytes()):
            raise ValueError("approved temporary policy absent or different")
        buckets[name] = bucket
    expires = access_deadline(proposal, buckets) if submit else None
    durable_record(output / "supervision-attempt.json", {"proposal_sha256": proposal_sha,
        "started_at": time.time(), "coordinated_submission": submit})
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    from collect_transformer_lineage_metadata import authenticated_client
    from app.ml.transformer.verification_spec import canonical
    key = output / "context-private.key"
    if key.is_symlink() or key.stat().st_mode & 0o077:
        raise ValueError("context custody permissions differ")
    private = Ed25519PrivateKey.from_private_bytes(key.read_bytes())
    if private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex() != request.context_public_key:
        raise ValueError("context signing identity differs")
    pins = json.loads((output / "approval-preview.json").read_bytes())
    selectors = json.loads((output / "selectors.json").read_bytes())
    def emit(value):
        value = {**value, "pid": os.getpid()}
        with (output / "observations.jsonl").open("a") as stream:
            stream.write(json.dumps(value, sort_keys=True) + "\n")
        (output / "supervision-status.json").write_text(json.dumps(value, sort_keys=True))
        print(json.dumps(value, sort_keys=True), flush=True)
    def deliver(context, remaining):
        sources(proposal, loaded=True)
        from app.ml.transformer.role_deadline import deadline
        with deadline(remaining):
            s3 = authenticated_client(factory)
            try:
                store = Store(s3, request, expires=time.monotonic() + remaining)
                receipt = deliver_context(store, {"context": context,
                    "signature": private.sign(canonical(context)).hex()}, **pins)
                (output / "context-receipt.json").write_text(json.dumps(receipt, sort_keys=True))
            finally:
                s3.close()
    admission = (lambda remaining: create_once(output, proposal, proposal_sha, remaining, expires)) if submit else None
    return supervise(request, selectors, pins, admit=admission,
        read=lambda remaining: cli("ai", "job", "get-by-name", "--parent-id", "project-e00g6zvxpr00waz8t3y51k",
            "--name", request.run_id, budget=remaining),
        deliver=deliver, cancel=lambda identity: cli("ai", "job", "cancel", "--id", identity, "--async", mutation=True), emit=emit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--submit", action="store_true", help="Supervise and submit the exact first Job in one process")
    args = parser.parse_args()
    try:
        result = run(args.output.resolve(), args.proposal_sha256, args.offline, args.submit)
        if not args.offline:
            durable_record(args.output.resolve() / "supervision-terminal.json", result)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        raise SystemExit("Holdout supervision stopped: " + type(error).__name__ + "; reconcile, do not retry") from None
