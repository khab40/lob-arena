"""Approved metadata orchestration; pin code and verify grants before credentials."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import runpy
import subprocess
import sys


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
        if path.is_file() and "__pycache__" not in path.parts}
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


def run(root, out, approved_sha, phase):
    if phase not in (1, 2):
        raise ValueError("expected phase one or two")
    raw = (out / "proposal.json").read_bytes()
    if hashlib.sha256(raw).hexdigest() != approved_sha:
        raise ValueError("proposal differs from explicit approval")
    proposal = json.loads(raw)
    if proposal.get("operator_script_sha256") != hashlib.sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError("operator script differs from approved proposal")
    if json.loads((out / "operator-approval.json").read_bytes()) != {"proposal_sha256": approved_sha, "approved": True}:
        raise ValueError("missing exact replacement approval")
    # No invocation, including a wrapper failure, silently reuses an attempt.
    if (out / "wrapper-abort.json").exists() or (out / f"phase-{phase}-attempt.json").exists():
        raise ValueError("attempt consumed; new exact authorization required")
    with (out / f"phase-{phase}-attempt.json").open("x") as stream:
        json.dump({"proposal_sha256": approved_sha, "phase": phase,
            "started_at": datetime.now(timezone.utc).isoformat()}, stream)
    code = pinned_backend(root, out, proposal)
    verified = json.loads((out / f"phase-{phase}-policy-verification.json").read_bytes())
    started = datetime.fromisoformat(verified["permission_started_at"].replace("Z", "+00:00"))
    if (verified["proposal_sha256"] != approved_sha or verified["phase"] != phase
            or verified["exact_policy_verified"] is not True
            or not 0 <= (datetime.now(timezone.utc) - started).total_seconds() < 3000):
        raise ValueError("missing current approved grant verification")
    if (out / f"phase-{phase}").exists():
        raise ValueError("phase output already exists")
    sys.path.insert(0, str(code / "backend"))
    from app.ml.transformer.lineage_proposal import require_proposal
    from app.ml.transformer.lineage_transport import collect
    verify_imports(code)
    require_proposal(proposal["exact_scope_sha256"])
    # Historical credential helper mutates sys.path; restore it and check origins
    # again before invoking its credential lookup function.
    search_path = sys.path[:]
    try:
        helper = runpy.run_path(str(root / "outputs/transformer-development-r2-20260928/cloud/verification_operator.py"))
    finally:
        sys.path[:] = search_path
    verify_imports(code)
    return collect(helper["authenticated_client"](),
        root / "outputs/transformer-role-provenance-20260928/cpu-role-audit-evidence-20260929.json",
        phase, out / f"phase-{phase}", out / "phase-1" if phase == 2 else None)


def main():
    if len(sys.argv) != 5:
        raise SystemExit("usage: collect_transformer_lineage_metadata APPROVED_SHA ROOT AUDIT_DIRECTORY PHASE")
    try:
        result = run(Path(sys.argv[2]).resolve(), Path(sys.argv[3]).resolve(), sys.argv[1], int(sys.argv[4]))
    except Exception as error:
        raise SystemExit(f"Metadata orchestration failed: {type(error).__name__}") from None
    print(json.dumps(result))


if __name__ == "__main__":
    main()
