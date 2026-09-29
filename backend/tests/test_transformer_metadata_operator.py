"""Exercise the complete operator path with inert credential/transport substitutes."""
from datetime import datetime, timedelta, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from types import ModuleType

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
    raw = json.dumps({"exact_scope_sha256": "scope",
        "operator_script_sha256": hashlib.sha256(script.read_bytes()).hexdigest()}).encode()
    sha = hashlib.sha256(raw).hexdigest()
    (out / "proposal.json").write_bytes(raw)
    (out / "operator-approval.json").write_text(json.dumps({"proposal_sha256": sha, "approved": True}))
    grant = {"proposal_sha256": sha, "phase": 1, "exact_policy_verified": True,
        "permission_started_at": datetime.now(timezone.utc).isoformat()}
    (out / "phase-1-policy-verification.json").write_text(json.dumps(grant))
    code = out / "runtime-fixture"
    monkeypatch.setattr(module, "pinned_backend", lambda *_: code)
    credentials = []
    def fake_credentials():
        credentials.append("inert")
        return "inert-client"
    monkeypatch.setattr(module.runpy, "run_path", lambda _: {"authenticated_client": fake_credentials})
    yield module, tmp_path, out, sha, code, credentials
    sys.path[:] = original_path
    for name in tuple(sys.modules):
        if name == "app" or name.startswith("app."):
            del sys.modules[name]


def test_complete_wrapper_accepts_native_namespace(operator):
    module, root, out, sha, _, credentials = operator
    assert module.run(root, out, sha, 1) == {"inert_transport": True}
    assert sys.modules["app"].__file__ is None
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
        def foreign_helper(_):
            if failure == "foreign_namespace":
                sys.modules["app"].__path__ = [str(root / "foreign/app")]
            else:
                foreign = ModuleType("app.foreign")
                foreign.__file__ = str(root / "foreign.py")
                sys.modules["app.foreign"] = foreign
            return {"authenticated_client": lambda: credentials.append("must not happen")}
        monkeypatch.setattr(module.runpy, "run_path", foreign_helper)
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


def test_helper_search_path_is_restored_before_credentials(operator, monkeypatch):
    module, root, out, sha, code, credentials = operator
    def helper(_):
        sys.path.insert(0, str(root / "foreign"))
        def client():
            assert sys.path[0] == str(code / "backend")
            credentials.append("inert")
        return {"authenticated_client": client}
    monkeypatch.setattr(module.runpy, "run_path", helper)
    module.run(root, out, sha, 1)
    assert credentials == ["inert"]
