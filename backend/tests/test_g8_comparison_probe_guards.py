"""Inert orchestration fixtures only; never import or execute the frozen runtime."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest


WORKER = Path(__file__).resolve().parents[2] / "scripts/g8_comparison_semantics_probe.py"
HARNESS = r'''
import hashlib, json, os, runpy, sys
from pathlib import Path
from types import SimpleNamespace

worker, base, case = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
module = runpy.run_path(str(worker))
audit = module['audit']
namespace = audit.__globals__
digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
mount = base / 'mount'
package = mount / 'transport-probes/g8-production-probe-20260921/unsigned-production'
package.mkdir(parents=True)
code = package / 'inert.txt'
code.write_bytes(b'inert code fixture')
manifest = package.parent / 'manifest.json'
manifest.write_text(json.dumps({'files': {'inert.txt': {
    'size_bytes': code.stat().st_size, 'sha256': digest(code)}}}))
comparison = mount / 'comparison'
comparison.mkdir()
refs = []
for index in range(377):
    path = comparison / str(index)
    path.write_bytes(b'inert payload fixture')
    refs.append({'path': path.name, 'size_bytes': path.stat().st_size, 'sha256': digest(path)})
inventory = base / 'expected-inventory.json'
inventory.write_text(json.dumps(refs))
scope = {'worker_sha256': digest(worker), 'internal_timeout_seconds': 10,
         'transport_manifest_sha256': digest(manifest), 'inventory_sha256': digest(inventory),
         'comparison_relative_root': 'comparison'}
if case in {'worker', 'manifest', 'inventory'}:
    field = {'worker': 'worker_sha256', 'manifest': 'transport_manifest_sha256',
             'inventory': 'inventory_sha256'}[case]
    scope[field] = '0' * 64
if case == 'package':
    code.write_bytes(b'changed code bytes')
if case == 'payload':
    (comparison / '376').write_bytes(b'changed payload')
proposal = base / 'scope.json'
proposal.write_text(json.dumps(scope))
os.environ['G8_SEMANTIC_APPROVED_PROPOSAL_SHA256'] = digest(proposal)
if case == 'approval':
    os.environ['G8_SEMANTIC_APPROVED_PROPOSAL_SHA256'] = '0' * 64
namespace['Path'] = lambda value: mount if str(value) == '/g8-package' else Path(value)
namespace['os'].statvfs = lambda _: SimpleNamespace(f_flag=0 if case == 'writable' else os.ST_RDONLY)
namespace['signal'].alarm = lambda _: None
class RuntimeBoundary(Exception):
    pass
def stop_before_runtime(_):
    raise RuntimeBoundary()
namespace['sys'].addaudithook = stop_before_runtime
sys.argv = [str(worker), str(proposal)]
try:
    audit()
except (ValueError, RuntimeBoundary) as error:
    print(type(error).__name__)
else:
    raise RuntimeError('Audit unexpectedly passed the runtime boundary')
'''


@pytest.mark.parametrize("optimization", [(), ("-O",), ("-OO",), ("env",)])
@pytest.mark.parametrize("case", ["valid", "approval", "worker", "manifest", "inventory",
                                 "package", "payload", "writable"])
def test_integrity_gates_survive_optimization(tmp_path, optimization, case):
    env = {key: value for key, value in os.environ.items()
           if not key.startswith(("AWS_", "MLFLOW_", "PYTHONOPTIMIZE"))}
    flags = list(optimization)
    if optimization == ("env",):
        flags = []
        env["PYTHONOPTIMIZE"] = "2"
    result = subprocess.run([sys.executable, *flags, "-c", HARNESS, str(WORKER), str(tmp_path), case],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ("RuntimeBoundary" if case == "valid" else "ValueError")


def test_optimized_cli_rejects_missing_approval_without_exposing_input(tmp_path):
    proposal = tmp_path / "scope.json"
    proposal.write_text('{"private_fixture": "must not appear in output"}')
    env = dict(os.environ)
    env.pop("G8_SEMANTIC_APPROVED_PROPOSAL_SHA256", None)
    result = subprocess.run([sys.executable, "-O", str(WORKER), str(proposal)],
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 1 and not result.stderr
    assert json.loads(result.stdout) == {"audit_passed": False, "error_type": "ValueError"}
