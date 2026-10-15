"""Invented AST/fixture checks only; no learned model or numerical runtime."""
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from scripts.ci_pytest_guard import select_items
from scripts.ci_workload_policy import canonical, sha, test_nodes as source_test_nodes, validate_inventory
from scripts.prepare_ci_workload_inventory import prepare

REPO = Path(__file__).resolve().parents[2]


def test_ast_hash_preserves_reviewed_format_and_literal_none():
    source = b"def test_empty(value=None):\n    assert value is None\n"
    assert source_test_nodes(source) == {
        "test_empty": "0481243d4120ed402eb9a9f4305b29b663a5ec501964a7c38bf2d1fc52f92eb5"
    }
    assert source_test_nodes(source.replace(b"is None", b"is False")) != source_test_nodes(source)


SOURCE = '''import sys, types
import pytest
sys.modules["lightgbm"] = types.ModuleType("lightgbm")
@pytest.fixture
def numerical_fixture(tmp_path):
    (tmp_path.parent / "MODEL_FIXTURE_STARTED").write_text("unexpected")
    raise AssertionError("excluded model fixture executed")
@pytest.mark.parametrize("case", [1, 2])
def test_model(numerical_fixture, case):
    raise AssertionError("excluded model test executed")
def test_metadata():
    assert "lightgbm" in sys.modules
'''


def fixture_inventory(tmp_path):
    root = tmp_path / "repo"
    path = root / "backend/tests/test_example.py"
    path.parent.mkdir(parents=True)
    path.write_text(SOURCE)
    support = root / "configs/benchmark/nasdaq-public-sample-v1.json"
    support.parent.mkdir(parents=True)
    support.write_text('{"schema_version":"invented-public-support"}')
    digest = source_test_nodes(SOURCE)["test_model"]
    audit = {"model_reaching_nodes": [{"node_id": "backend/tests/test_example.py::test_model", "ast_sha256": digest}],
             "model_reaching_test_definition_count": 1}
    audit_path = tmp_path / "audit.json"
    audit_path.write_bytes(canonical(audit))
    dest = root / "configs/ci/workloads"
    result = prepare(root, audit_path, sha(audit_path.read_bytes()), dest)
    assert result["model_definitions"] == 1
    (root / "configs/ci/workloads-pin.json").write_bytes(canonical({"schema_version": "reviewed_ci_workload_pin_v1",
        "index_sha256": result["inventory_sha256"]}))
    return root, path, dest


def test_default_selection_keeps_mixed_metadata_and_excludes_all_model_parameters(tmp_path):
    root, path, _ = fixture_inventory(tmp_path)
    inventory = validate_inventory(root)
    items = [SimpleNamespace(path=path, nodeid="backend/tests/test_example.py::" + name)
             for name in ("test_model[1]", "test_model[2]", "test_metadata")]
    selected, excluded = select_items(items, inventory, root)
    assert selected == [items[2]] and excluded == items[:2]


def test_default_pytest_excludes_model_fixture_even_with_model_dependency_present(tmp_path):
    root, path, _ = fixture_inventory(tmp_path)
    conftest = root / "backend/conftest.py"
    conftest.write_text('''from pathlib import Path
from scripts.ci_workload_policy import validate_inventory
from scripts.ci_pytest_guard import select_items
def pytest_configure(config):
    config.inventory = validate_inventory(Path(__file__).parents[1])
def pytest_collection_modifyitems(config, items):
    selected, excluded = select_items(items, config.inventory, Path(__file__).parents[1])
    config.hook.pytest_deselected(items=excluded)
    items[:] = selected
''')
    # Prepare the complete proposal including the pure guard before collection.
    rows = json.loads((root / "configs/ci/workloads/source-01.json").read_bytes())
    rows.append({"path": "backend/conftest.py", "sha256": sha(conftest.read_bytes()), "tests": []})
    chunk = canonical(rows)
    (root / "configs/ci/workloads/source-01.json").write_bytes(chunk)
    index_path = root / "configs/ci/workloads/index.json"
    index = json.loads(index_path.read_bytes())
    index["chunks"][0]["sha256"] = sha(chunk)
    index_path.write_bytes(canonical(index))
    (root / "configs/ci/workloads-pin.json").write_bytes(canonical({"schema_version": "reviewed_ci_workload_pin_v1",
        "index_sha256": sha(index_path.read_bytes())}))
    env = {**os.environ, "PYTHONPATH": str(REPO), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    result = subprocess.run([sys.executable, "-m", "pytest", "-q", str(path), "--basetemp", str(root / "test-temp")],
                            cwd=root, env=env, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
    assert b"1 passed, 2 deselected" in result.stdout
    assert not list(root.rglob("MODEL_FIXTURE_STARTED"))


@pytest.mark.parametrize("change", ["test", "helper", "new_test", "missing_test", "application", "support_config", "classification"])
def test_unknown_or_changed_source_is_refused_before_collection(tmp_path, change):
    root, path, dest = fixture_inventory(tmp_path)
    if change == "test":
        path.write_text(SOURCE + "\ndef test_unknown(): pass\n")
    elif change == "helper":
        path.write_text(SOURCE.replace("unexpected", "changed"))
    elif change == "new_test":
        path.with_name("test_unknown.py").write_text("def test_unknown(): pass\n")
    elif change == "missing_test":
        path.unlink()
    elif change == "application":
        application = root / "backend/app/unknown.py"
        application.parent.mkdir()
        application.write_text("def fake_train(): pass\n")
    elif change == "support_config":
        (root / "configs/benchmark/nasdaq-public-sample-v1.json").write_text("{}")
    else:
        rows = json.loads((dest / "source-01.json").read_bytes())
        rows[0]["tests"][0]["classification"] = "inert"
        (dest / "source-01.json").write_bytes(canonical(rows))
    with pytest.raises(ValueError, match="workload|classification|inventory"):
        validate_inventory(root)


def test_unknown_collected_node_is_refused(tmp_path):
    root, path, _ = fixture_inventory(tmp_path)
    inventory = validate_inventory(root)
    item = SimpleNamespace(path=path, nodeid="backend/tests/test_example.py::test_unknown")
    with pytest.raises(ValueError, match="unknown collected"):
        select_items([item], inventory, root)
    assert inventory["classification"]["backend/tests/test_example.py::test_model"] == "nebius_cpu_model_workload"


def test_model_selection_override_is_refused_before_any_fixture(tmp_path):
    root, path, _ = fixture_inventory(tmp_path)
    inventory = validate_inventory(root)
    item = SimpleNamespace(path=path, nodeid="backend/tests/test_example.py::test_model[1]")
    with pytest.raises(ValueError, match="separately reviewed Nebius runner"):
        select_items([item], inventory, root, authorization=SimpleNamespace())


def test_rehashed_classification_cannot_replace_external_review_pin(tmp_path):
    root, _, dest = fixture_inventory(tmp_path)
    rows = json.loads((dest / "source-01.json").read_bytes())
    rows[0]["tests"][0]["classification"] = "inert"
    chunk = canonical(rows)
    (dest / "source-01.json").write_bytes(chunk)
    index = json.loads((dest / "index.json").read_bytes())
    index["chunks"][0]["sha256"] = sha(chunk)
    index["model_definition_count"] = 0
    (dest / "index.json").write_bytes(canonical(index))
    with pytest.raises(ValueError, match="externally pinned"):
        validate_inventory(root)


def test_proposal_refuses_changed_audited_model_function(tmp_path):
    root, path, _ = fixture_inventory(tmp_path)
    path.write_text(SOURCE.replace("excluded model test executed", "changed numerical assertion"))
    audit_path = tmp_path / "audit.json"
    with pytest.raises(ValueError, match="model function changed"):
        prepare(root, audit_path, sha(audit_path.read_bytes()), tmp_path / "new-proposal")


def test_proposal_refuses_foreign_audit_hash_and_symlink_source(tmp_path):
    root, path, _ = fixture_inventory(tmp_path)
    audit_path = tmp_path / "audit.json"
    with pytest.raises(ValueError, match="audit hash"):
        prepare(root, audit_path, "0" * 64, tmp_path / "new-proposal")
    external = tmp_path / "external.py"
    external.write_text(SOURCE)
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(ValueError, match="symlink"):
        validate_inventory(root)
