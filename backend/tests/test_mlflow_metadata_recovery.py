"""Inert recovery contracts; the actual PostgreSQL restore runs on Nebius."""
import importlib.util
import json
from pathlib import Path

import pytest


spec = importlib.util.spec_from_file_location(
    "mlflow_metadata_recovery",
    Path(__file__).resolve().parents[2] / "scripts/mlflow_metadata_recovery.py",
)
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


@pytest.mark.parametrize("mutation", ["content", "count", "missing", "extra"])
def test_restore_comparison_rejects_corruption(mutation):
    source = {"runs": {"rows": 1, "sha256": "a"}, "users": {"rows": 1, "sha256": "b"}}
    restored = json.loads(json.dumps(source))
    if mutation == "content":
        restored["runs"]["sha256"] = "c"
    elif mutation == "count":
        restored["runs"]["rows"] = 2
    elif mutation == "missing":
        del restored["users"]
    else:
        restored["unexpected"] = {"rows": 0, "sha256": "d"}
    with pytest.raises(ValueError, match="differ"):
        recovery.compare(source, restored)


def test_identical_inventory_is_required_and_empty_does_not_pass():
    recovery.compare({"runs": {"rows": 0, "sha256": "a"}},
                     {"runs": {"rows": 0, "sha256": "a"}})
    with pytest.raises(ValueError):
        recovery.compare({}, {})


def test_snapshot_is_read_only_and_used_for_each_query(monkeypatch):
    calls = []
    monkeypatch.setattr(recovery, "command", lambda args, **kw: calls.append((args, kw)))
    recovery.sql("source", "SELECT 1;", "00000003-0000001A-1")
    query = calls[0][1]["data"].decode()
    assert "REPEATABLE READ READ ONLY" in query
    assert "SET TRANSACTION SNAPSHOT '00000003-0000001A-1'" in query
    assert calls[0][0][3] == "source"
    with pytest.raises(ValueError):
        recovery.sql("source", "SELECT 1;", "x'; DROP TABLE runs; --")
    assert len(calls) == 1


def test_inventory_requires_authentication_metadata(monkeypatch):
    monkeypatch.setattr(recovery, "sql", lambda *args: b'["runs", "experiments", "registered_models"]')
    with pytest.raises(ValueError, match="authentication"):
        recovery.inventory("source", "00000003-0000001A-1")


def test_existing_backup_directory_is_never_overwritten(tmp_path):
    with pytest.raises(FileExistsError):
        recovery.recover("source", tmp_path)
