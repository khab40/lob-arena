"""Approved metadata orchestration; pin code and verify grants before credentials."""
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
from importlib import metadata
import json
from pathlib import Path
import os
import platform
import socket
import subprocess
import sys
from unittest.mock import patch


READER_ID_SHA256 = "4f129534101211604ce259cd5ded383065384b86797e8f7b407a810750062d5d"

def pinned_backend(root, out, proposal):
    commit = proposal["implementation_commit"]
    code = out / ("runtime-" + commit[:7])
    tree = subprocess.check_output(["rtk", "proxy", "git", "rev-parse", commit + ":backend"],
        cwd=root, text=True).strip()
    if tree != proposal["backend_tree"]:
        raise ValueError("pinned backend tree differs from proposal")
    entries = subprocess.check_output(["rtk", "proxy", "git", "ls-tree", "-r", "-z", commit, "backend"], cwd=root)
    expected = set()
    for entry in entries.split(b"\0"):
        if not entry:
            continue
        meta, name = entry.split(b"\t")
        mode, kind, oid = meta.split()
        if kind != b"blob" or mode not in (b"100644", b"100755"):
            raise ValueError("unexpected pinned file type")
        path = name.decode()
        expected.add(path)
        target = code / path
        if target.is_symlink() or not target.resolve().is_relative_to(code.resolve()):
            raise ValueError("pinned file escapes snapshot")
        content = target.read_bytes()
        observed = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if observed != oid.decode():
            raise ValueError("runtime file differs from pinned Git object")
    actual = {str(path.relative_to(code)) for path in (code / "backend").rglob("*")
        if path.is_file()}
    if actual != expected:
        raise ValueError("runtime contains unexpected files")
    return code


def verify_imports(code):
    """Native namespaces have no __file__; validate every package search path."""
    backend = (code / "backend").resolve()
    if "app" not in sys.modules:
        raise ValueError("app package has not been imported")
    for name, module in tuple(sys.modules.items()):
        if name != "app" and not name.startswith("app."):
            continue
        filename = getattr(module, "__file__", None)
        paths = getattr(module, "__path__", None)
        if filename is None and paths is None:
            raise ValueError("app module lacks a verifiable origin")
        if filename is not None and not Path(filename).resolve().is_relative_to(backend):
            raise ValueError("app module imported outside pinned runtime")
        if paths is not None and {Path(p).resolve() for p in paths} != {backend.joinpath(*name.split("."))}:
            raise ValueError("app package searches outside pinned runtime")


def authenticated_client(client_factory):
    selectors = {
        'AWS_ACCESS_KEY_ID': ('mbsec-e00arhndyprqr8egjw', 'mbsecver-e00rjzerny1pf9qhna'),
        'AWS_SECRET_ACCESS_KEY': ('mbsec-e00s7qtjj5n9ghacnh', 'mbsecver-e00yfn5w54jc1ybkwv'),
    }
    for name, (secret, version) in selectors.items():
        result = subprocess.run(['rtk', 'proxy', 'nebius', 'mysterybox', 'payload', 'get',
            '--secret-id', secret, '--version-id', version, '--format', 'json'],
            capture_output=True, timeout=45)
        if result.returncode:
            raise RuntimeError('Pinned development credential lookup failed')
        entries = [item['string_value'] for item in json.loads(result.stdout)['data']
            if item.get('string_value') and (name != 'AWS_SECRET_ACCESS_KEY' or item.get('key') == 'secret')]
        if len(entries) != 1:
            raise ValueError('Ambiguous credential selector')
        os.environ[name] = entries[0]
    if hashlib.sha256(os.environ['AWS_ACCESS_KEY_ID'].encode()).hexdigest() != READER_ID_SHA256:
        raise ValueError('Wrong development reader identity')
    os.environ['AWS_EC2_METADATA_DISABLED'] = 'true'
    return client_factory()


def load_proposal(out, approved_sha):
    raw = (out / "proposal.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != approved_sha:
        raise ValueError("proposal differs from explicit approval")
    proposal = json.loads(raw)
    if proposal.get("operator_script_sha256") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("operator script differs from approved proposal")
    return proposal


def runtime_probe(client_factory, proposal):
    """Use the real client with no live credential provider, socket or subprocess."""
    expected = proposal["runtime_dependencies"]
    if not isinstance(expected, dict) or not expected.get("botocore"):
        raise ValueError("proposal must pin the S3 SDK dependency")
    if platform.python_version() != proposal["runtime_python"]:
        raise ValueError("Python version differs from proposal")
    for name, version in expected.items():
        if metadata.version(name) != version:
            raise ValueError("runtime dependency version differs: " + name)
    environment = {"AWS_ACCESS_KEY_ID": "offline-fixture", "AWS_SECRET_ACCESS_KEY": "offline-fixture",
        "AWS_EC2_METADATA_DISABLED": "true", "AWS_SHARED_CREDENTIALS_FILE": os.devnull,
        "AWS_CONFIG_FILE": os.devnull}
    def prohibited(*args, **kwargs):
        raise RuntimeError("network or subprocess prohibited during offline preflight")
    with ExitStack() as stack:
        stack.enter_context(patch.dict(os.environ, environment, clear=True))
        for owner, name in ((socket.socket, "connect"), (socket.socket, "connect_ex"),
                (socket, "create_connection"), (socket, "getaddrinfo"), (subprocess, "Popen")):
            stack.enter_context(patch.object(owner, name, prohibited))
        s3 = client_factory()
        try:
            config = s3.meta.config
            if (s3.meta.service_model.service_name != "s3"
                    or s3.meta.endpoint_url != "https://storage.eu-north1.nebius.cloud"
                    or config.region_name != "eu-north1"
                    or config.retries.get("total_max_attempts") != 1
                    or config.connect_timeout != 5 or config.read_timeout != 5
                    or config.s3.get("addressing_style") != "path"
                    or config.request_checksum_calculation != "when_required"
                    or config.response_checksum_validation != "when_required"):
                raise ValueError("S3 client configuration differs from the approved transport")
        finally:
            s3.close()
    return {"python": platform.python_version(), "executable": str(Path(sys.executable).absolute()),
        "prefix": str(Path(sys.prefix).resolve()), "dependencies": {
            d.metadata["Name"].lower().replace("_", "-"): d.version for d in metadata.distributions()}}


def load_runtime(root, out, proposal):
    if Path(sys.executable).absolute() != (root / proposal["operator_python"]).absolute():
        raise ValueError("use the exact operator_python executable from the proposal")
    code = pinned_backend(root, out, proposal)
    sys.dont_write_bytecode = True
    sys.pycache_prefix = None
    sys.path.insert(0, str(code / "backend"))
    from app.ml.transformer.lineage_proposal import require_proposal
    from app.ml.transformer.lineage_transport import collect
    from app.ml.transformer.verification_transport import client
    verify_imports(code)
    require_proposal(proposal["exact_scope_sha256"])
    return client, collect


def readiness(proposal, approved_sha, client_factory):
    return {"schema_version": "transformer_metadata_runtime_v1", "proposal_sha256": approved_sha,
        "operator_script_sha256": proposal["operator_script_sha256"], "backend_tree": proposal["backend_tree"],
        "runtime": runtime_probe(client_factory, proposal)}


def preflight(root, out, approved_sha):
    proposal = load_proposal(out, approved_sha)
    client, _ = load_runtime(root, out, proposal)
    receipt = readiness(proposal, approved_sha, client)
    receipt["verified_at"] = datetime.now(timezone.utc).isoformat()
    (out / "runtime-readiness.json").write_text(json.dumps(receipt, indent=2) + "\n")
    return receipt


def run(root, out, approved_sha, phase):
    if phase not in (1, 2):
        raise ValueError("expected phase one or two")
    proposal = load_proposal(out, approved_sha)
    if json.loads((out / "operator-approval.json").read_bytes()) != {"proposal_sha256": approved_sha, "approved": True}:
        raise ValueError("missing exact replacement approval")
    # No invocation, including a wrapper failure, silently reuses an attempt.
    if (out / "wrapper-abort.json").exists() or (out / f"phase-{phase}-attempt.json").exists():
        raise ValueError("attempt consumed; new exact authorization required")
    with (out / f"phase-{phase}-attempt.json").open("x") as stream:
        json.dump({"proposal_sha256": approved_sha, "phase": phase,
            "started_at": datetime.now(timezone.utc).isoformat()}, stream)
    verified = json.loads((out / f"phase-{phase}-policy-verification.json").read_bytes())
    started = datetime.fromisoformat(verified["permission_started_at"].replace("Z", "+00:00"))
    if (verified["proposal_sha256"] != approved_sha or verified["phase"] != phase
            or verified["exact_policy_verified"] is not True
            or not 0 <= (datetime.now(timezone.utc) - started).total_seconds() < 3000):
        raise ValueError("missing current approved grant verification")
    if (out / f"phase-{phase}").exists():
        raise ValueError("phase output already exists")
    recorded = json.loads((out / "runtime-readiness.json").read_bytes())
    checked = datetime.fromisoformat(recorded.pop("verified_at"))
    if checked > started:
        raise ValueError("runtime readiness must precede the temporary grant")
    client, collect = load_runtime(root, out, proposal)
    if recorded != readiness(proposal, approved_sha, client):
        raise ValueError("runtime changed since pregrant readiness; stop and remove access")
    return collect(authenticated_client(client),
        root / "outputs/transformer-role-provenance-20260928/cpu-role-audit-evidence-20260929.json",
        phase, out / f"phase-{phase}", out / "phase-1" if phase == 2 else None)


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: collect_transformer_lineage_metadata APPROVED_SHA ROOT AUDIT_DIRECTORY preflight|PHASE")
    try:
        args = (Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve(), sys.argv[1])
        result = preflight(*args) if sys.argv[4] == "preflight" else run(*args, int(sys.argv[4]))
    except Exception as error:
        raise SystemExit(f"Metadata orchestration failed: {type(error).__name__}") from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
