"""Exercise the complete operator path with inert credential/transport substitutes."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.fixture
def operator(tmp_path, monkeypatch):
    script = Path(__file__).resolve().parents[2] / "scripts/collect_transformer_lineage_metadata.py"
    spec = importlib.util.spec_from_file_location("metadata_operator", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in tuple(sys.modules):
        if name == "app" or name.startswith("app."):
            monkeypatch.delitem(sys.modules, name)
    original_path = sys.path[:]
    # Match an isolated operator process rather than pytest's backend search path.
    sys.path[:] = [p for p in sys.path if not (Path(p) / "app").is_dir()]
    out = tmp_path / "audit"
    package = out / "runtime-fixture/backend/app/ml/transformer"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "lineage_proposal.py").write_text("def require_proposal(sha):\n    assert sha == 'scope'\n")
    (package / "lineage_transport.py").write_text(
        "calls = []\ndef collect(*args):\n    calls.append(args)\n    return {'inert_transport': True}\n")
    (package / "verification_transport.py").write_text("def client():\n    return 'inert-client'\n")
    raw = json.dumps({"exact_scope_sha256": "scope", "backend_tree": "fixture-tree",
        "operator_python": str(Path(sys.executable).absolute()),
        "operator_script_sha256": hashlib.sha256(script.read_bytes()).hexdigest()}).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (out / "proposal.json").write_bytes(raw)
    (out / "operator-approval.json").write_text(json.dumps({"proposal_sha256": sha, "approved": True}))
    grant = {"proposal_sha256": sha, "phase": 1, "exact_policy_verified": True,
        "permission_started_at": datetime.now(timezone.utc).isoformat()}
    (out / "phase-1-policy-verification.json").write_text(json.dumps(grant))
    code = out / "runtime-fixture"
    module.real_pinned_backend = module.pinned_backend
    monkeypatch.setattr(module, "pinned_backend", lambda *_: code)
    monkeypatch.setattr(sys, "dont_write_bytecode", sys.dont_write_bytecode)
    monkeypatch.setattr(sys, "pycache_prefix", sys.pycache_prefix)
    credentials = []
    def fake_credentials(client_factory):
        credentials.append("inert")
        return client_factory()
    monkeypatch.setattr(module, "runtime_probe", lambda *_: {"inert_runtime": True})
    module.real_authenticated_client = getattr(module, "authenticated_client", None)
    monkeypatch.setattr(module, "authenticated_client", fake_credentials, raising=False)
    module.preflight(tmp_path, out, sha)
    grant["permission_started_at"] = datetime.now(timezone.utc).isoformat()
    (out / "phase-1-policy-verification.json").write_text(json.dumps(grant))
    yield module, tmp_path, out, sha, code, credentials
    sys.path[:] = original_path
    for name in tuple(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


def test_complete_wrapper_accepts_native_namespace(operator, monkeypatch):
    module, root, out, sha, _, credentials = operator
    monkeypatch.setattr(sys, "pycache_prefix", str(root / "external-cache"))
    assert module.run(root, out, sha, 1) == {"inert_transport": True}
    assert sys.pycache_prefix is None
    assert sys.modules["app"].__file__ is None
    assert not list((out / "runtime-fixture").rglob("*.pyc"))
    sys.path.insert(0, sys.path[0])
    module.verify_imports(out / "runtime-fixture")
    assert credentials == ["inert"]
    transport = sys.modules["app.ml.transformer.lineage_transport"]
    assert len(transport.calls) == 1 and transport.calls[0][0] == "inert-client"
    with pytest.raises(ValueError, match="consumed"):
        module.run(root, out, sha, 1)
    assert len(transport.calls) == len(credentials) == 1


@pytest.mark.parametrize("failure", ["aborted", "expired", "wrong_approval", "foreign_namespace", "foreign_module"])
def test_preflight_failure_never_looks_up_credentials(operator, failure, monkeypatch):
    module, root, out, sha, _, credentials = operator
    if failure == "aborted":
        (out / "wrapper-abort.json").write_text("{}")
    elif failure == "expired":
        p = out / "phase-1-policy-verification.json"
        grant = json.loads(p.read_text())
        grant["permission_started_at"] = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        p.write_text(json.dumps(grant))
    elif failure == "wrong_approval":
        sha = "0" * 64
    else:
        verify = module.verify_imports
        def foreign_imports(code):
            if failure == "foreign_namespace":
                sys.modules["app"].__path__ = [str(root / "foreign/app")]
            else:
                foreign = ModuleType("app.foreign")
                foreign.__file__ = str(root / "foreign.py")
                sys.modules["app.foreign"] = foreign
            verify(code)
        monkeypatch.setattr(module, "verify_imports", foreign_imports)
    with pytest.raises(ValueError):
        module.run(root, out, sha, 1)
    assert credentials == []
    if failure in {"expired", "foreign_namespace", "foreign_module"}:
        with pytest.raises(ValueError, match="consumed"):
            module.run(root, out, sha, 1)


def test_changed_operator_script_is_rejected(operator):
    module, root, out, _, _, credentials = operator
    proposal = json.loads((out / "proposal.json").read_bytes())
    proposal["operator_script_sha256"] = "0" * 64
    raw = json.dumps(proposal).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (out / "proposal.json").write_bytes(raw)
    with pytest.raises(ValueError, match="operator script"):
        module.run(root, out, sha, 1)
    assert credentials == []


@pytest.mark.parametrize("attack", ["top_level", "client_substitution"])
def test_ignored_helper_cannot_execute(operator, attack):
    module, root, out, sha, _, credentials = operator
    helper = root / "outputs/transformer-development-r2-20260928/cloud/verification_operator.py"
    helper.parent.mkdir(parents=True)
    sentinel = root / "unapproved-execution"
    payload = f"from pathlib import Path\nPath({str(sentinel)!r}).touch()\nraise RuntimeError('unapproved helper')\n"
    if attack == "client_substitution":
        payload = "def authenticated_client():\n" + "".join("    " + line + "\n" for line in payload.splitlines())
    helper.write_text(payload)
    assert module.run(root, out, sha, 1) == {"inert_transport": True}
    assert not sentinel.exists()
    assert credentials == ["inert"]


@pytest.mark.parametrize("failure", [None, "lookup", "ambiguous_id", "ambiguous_secret", "identity", "malformed", "client"])
def test_bound_credential_lookup_and_client(operator, monkeypatch, failure):
    module, root, out, sha, _, _ = operator
    monkeypatch.setattr(module, "authenticated_client", module.real_authenticated_client)
    # These are inert fixture values, never real credentials.
    monkeypatch.setattr(module, "READER_ID_SHA256", hashlib.sha256(b"fixture-reader").hexdigest())
    for name in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_EC2_METADATA_DISABLED"):
        monkeypatch.setenv(name, "fixture-original")
    original = dict(module.os.environ)
    if failure == "client":
        def failed_client():
            raise RuntimeError("fixture construction failure")
        monkeypatch.setattr(sys.modules["app.ml.transformer.verification_transport"], "client", failed_client)
    calls = []
    def lookup(args, **kwargs):
        assert kwargs == {"capture_output": True, "timeout": 45}
        calls.append(args)
        if failure == "lookup":
            return SimpleNamespace(returncode=1)
        if failure == "malformed":
            return SimpleNamespace(returncode=0, stdout=b"invalid-json")
        data = [{"string_value": "wrong-reader" if failure == "identity" else "fixture-reader"}]
        if len(calls) == 2:
            data = [{"key": "ignored", "string_value": "not-selected"},
                    {"key": "secret", "string_value": "fixture-secret"}]
        if (failure == "ambiguous_id" and len(calls) == 1
                or failure == "ambiguous_secret" and len(calls) == 2):
            data.append(data[-1])
        return SimpleNamespace(returncode=0, stdout=json.dumps({"data": data}).encode())
    monkeypatch.setattr(module.subprocess, "run", lookup)
    if failure:
        with pytest.raises((ValueError, RuntimeError)):
            module.run(root, out, sha, 1)
        assert sys.modules["app.ml.transformer.lineage_transport"].calls == []
        with pytest.raises(ValueError, match="consumed"):
            module.run(root, out, sha, 1)
    else:
        assert module.run(root, out, sha, 1) == {"inert_transport": True}
        assert sys.modules["app.ml.transformer.lineage_transport"].calls[0][0] == "inert-client"
    assert dict(module.os.environ) == original
    selectors = [("mbsec-e00arhndyprqr8egjw", "mbsecver-e00rjzerny1pf9qhna"),
                 ("mbsec-e00s7qtjj5n9ghacnh", "mbsecver-e00yfn5w54jc1ybkwv")]
    assert len(calls) == (1 if failure in {"lookup", "ambiguous_id", "malformed"} else 2)
    for args, (secret, version) in zip(calls, selectors, strict=False):
        assert args == ["rtk", "proxy", "nebius", "mysterybox", "payload", "get",
                        "--secret-id", secret, "--version-id", version, "--format", "json"]


@pytest.mark.parametrize("failure", ["missing_receipt", "interpreter", "dependencies", "late_preflight"])
def test_runtime_drift_blocks_credentials(operator, monkeypatch, failure):
    module, root, out, sha, _, credentials = operator
    if failure == "missing_receipt":
        (out / "runtime-readiness.json").unlink()
    elif failure == "late_preflight":
        module.preflight(root, out, sha)
    else:
        monkeypatch.setattr(module, "runtime_probe", lambda *_: {failure: "changed"})
    with pytest.raises((ValueError, FileNotFoundError)):
        module.run(root, out, sha, 1)
    assert credentials == []
    assert sys.modules["app.ml.transformer.lineage_transport"].calls == []
    with pytest.raises(ValueError, match="consumed"):
        module.run(root, out, sha, 1)


def test_failed_offline_preflight_never_arms_attempt(operator, monkeypatch):
    module, root, out, sha, _, credentials = operator
    (out / "runtime-readiness.json").unlink()
    def missing(*_):
        raise ModuleNotFoundError("botocore")
    monkeypatch.setattr(module, "runtime_probe", missing)
    with pytest.raises(ModuleNotFoundError):
        module.preflight(root, out, sha)
    assert not (out / "runtime-readiness.json").exists()
    assert not (out / "phase-1-attempt.json").exists()
    assert credentials == []


def test_successful_preflight_does_not_reset_aborted_attempt(operator):
    module, root, out, sha, _, credentials = operator
    (out / "wrapper-abort.json").write_text("{}")
    module.preflight(root, out, sha)
    with pytest.raises(ValueError, match="consumed"):
        module.run(root, out, sha, 1)
    assert credentials == []
