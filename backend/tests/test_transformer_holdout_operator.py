"""Exercise the actual import boundary in fresh processes with inert credentials."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
FILES = (
    "scripts/collect_transformer_holdout_metadata.py",
    "scripts/collect_transformer_lineage_metadata.py",
    "backend/app/ml/__init__.py", "backend/app/ml/transformer/__init__.py",
    "backend/app/ml/transformer/holdout_metadata.py",
    "backend/app/ml/transformer/holdout_reference.py",
    "backend/app/ml/transformer/verification_spec.py",
    "backend/app/ml/transformer/verification_transport.py",
)
CHILD = '''
import builtins, hashlib, json, os, sys, types
from pathlib import Path
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if "research_" in name or name.endswith("role_source"):
        raise AssertionError("unrelated research module imported")
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
import collect_transformer_holdout_metadata as wrapper
import collect_transformer_lineage_metadata as helper
calls = []
helper.READER_ID_SHA256 = hashlib.sha256(b"inert-reader").hexdigest()
def lookup(*args, **kwargs):
    calls.append("credential")
    return types.SimpleNamespace(returncode=0, stdout=json.dumps({"data": [
        {"key": "secret", "string_value": "inert-reader"}]}).encode())
helper.subprocess.run = lookup
def probe(*args):
    if sys.argv[1] == "postprobe_change":
        path = Path("backend/app/ml/transformer/holdout_reference.py")
        path.write_bytes(path.read_bytes() + b"\\n")
    return {"inert": True}
helper.runtime_probe = probe
if sys.argv[1] == "helper_origin":
    helper.__file__ = str(Path("../outside-helper.py").resolve())
if sys.argv[1] == "unreviewed_module":
    unknown = types.ModuleType("app.ml.transformer.unreviewed")
    unknown.__file__ = str(Path("backend/app/ml/transformer/unreviewed.py").resolve())
    sys.modules[unknown.__name__] = unknown
from app.ml.transformer import verification_transport, holdout_metadata
class Client:
    def close(self):
        calls.append("close")
def client():
    assert os.environ["AWS_ACCESS_KEY_ID"] == "inert-reader"
    calls.append("client")
    return Client()
verification_transport.client = client
def collect(*args):
    calls.append("collect")
    return {"status": "inert_collection"}
holdout_metadata.collect = collect
before = dict(os.environ)
try:
    result = wrapper.run("proposal.json", "new-output", sys.argv[2], sys.argv[1] == "preflight")
except Exception as error:
    result = {"error": type(error).__name__}
print(json.dumps({"result": result, "calls": calls, "environment_restored": before == dict(os.environ)}))
'''


@pytest.fixture
def copied(tmp_path):
    pins = {}
    for name in FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, path)
        pins[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    raw = json.dumps({"operator_files_sha256": pins}).encode()
    (tmp_path / "proposal.json").write_bytes(raw)
    return tmp_path, hashlib.sha256(raw).hexdigest()


def invoke(copied, mode="live", pin=None):
    root, expected = copied
    env = {**os.environ, "PYTHONPATH": str(root / "backend") + os.pathsep + str(root / "scripts")}
    process = subprocess.run([sys.executable, "-c", CHILD, mode, pin or expected],
                             cwd=root, env=env, capture_output=True, text=True, timeout=15)
    assert process.returncode == 0, process.stderr
    return json.loads(process.stdout)


def test_live_helper_uses_only_metadata_sources_and_restores_environment(copied):
    result = invoke(copied)
    assert result == {"result": {"status": "inert_collection"},
        "calls": ["credential", "credential", "client", "collect", "close"], "environment_restored": True}


def test_offline_preflight_never_obtains_credentials(copied):
    result = invoke(copied, "preflight")
    assert result["result"]["status"] == "offline_preflight_passed"
    assert result["calls"] == [] and result["environment_restored"]


@pytest.mark.parametrize("name", FILES)
def test_changed_source_fails_before_imports_or_credentials(copied, name):
    path = copied[0] / name
    path.write_bytes(path.read_bytes() + b"\n")
    result = invoke(copied)
    assert result["result"] == {"error": "ValueError"} and result["calls"] == []


@pytest.mark.parametrize("mode", ["helper_origin", "unreviewed_module", "postprobe_change"])
def test_unapproved_import_or_postprobe_change_fails_before_credentials(copied, mode):
    result = invoke(copied, mode)
    assert result["result"] == {"error": "ValueError"} and result["calls"] == []


def test_wrong_approval_fails_before_credentials(copied):
    result = invoke(copied, pin="0" * 64)
    assert result["result"] == {"error": "ValueError"} and result["calls"] == []

