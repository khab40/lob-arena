"""Preflight or supervise the externally submitted, exactly approved holdout Job."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]
os.environ["AI_AGENT"] = os.environ.get("AI_AGENT") or "codex"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    for name, expected in proposal["files"].items():
        path = output / name
        if path.is_symlink() or not path.resolve().is_relative_to(output) or sha(path) != expected:
            raise ValueError("execution package differs")
    from collect_transformer_lineage_metadata import runtime_probe, verify_imports
    from app.ml.transformer.verification_transport import client
    from app.ml.transformer.holdout_runtime import load_request
    from app.ml.transformer.holdout_delivery import context_for_job, deliver_context
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


def run(output, proposal_sha, offline=False):
    proposal, request, factory, deliver_context, Store, supervise = preflight(output, proposal_sha)
    if offline:
        return {"status": "offline_preflight_passed", "credentials_read": False, "jobs_created": 0}
    approval = json.loads((output / "operator-approval.json").read_bytes())
    if approval != {"approved": True, "proposal_sha256": proposal_sha}:
        raise ValueError("exact operator approval record required")
    for name, identity in (("final", "storagebucket-e004963828556923796882"),
                           ("results", "storagebucket-e009132243970085528999")):
        bucket = cli("storage", "bucket", "get", "--id", identity)
        if bucket is None or bucket["spec"]["bucket_policy"]["rules"] != json.loads(
                (output / f"{name}-policy-temporary.json").read_bytes()):
            raise ValueError("approved temporary policy absent or different")
    with (output / "supervision-attempt.json").open("x") as stream:
        json.dump({"proposal_sha256": proposal_sha, "started_at": time.time()}, stream)
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
    return supervise(request, selectors, pins,
        read=lambda remaining: cli("ai", "job", "get-by-name", "--parent-id", "project-e00g6zvxpr00waz8t3y51k",
            "--name", request.run_id, budget=remaining),
        deliver=deliver, cancel=lambda identity: cli("ai", "job", "cancel", "--id", identity, "--async", mutation=True), emit=emit)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--proposal-sha256", required=True)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    try:
        print(json.dumps(run(args.output.resolve(), args.proposal_sha256, args.offline), sort_keys=True))
    except Exception as error:
        raise SystemExit("Holdout supervision stopped: " + type(error).__name__ + "; reconcile, do not retry") from None
