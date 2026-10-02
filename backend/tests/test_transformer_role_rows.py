"""Inert IDs and labels only; no model or governed payload execution."""
import json
from types import SimpleNamespace as NS

import pytest

from app.ml.transformer import role_rows as r


def fixture(positive=20):
    windows, groups = [], []
    for index, role in enumerate(r.ROLES):
        shards = []
        for part in range(2):
            run = f"r{index}-{part}"
            ids = [r.digest(f"{run}-{row}".encode()) for row in range(20)]
            windows.extend(NS(fold="validation", run_id=run, target_id=target,
                label=int(part * 20 + row < positive)) for row, target in enumerate(ids))
            shards.append({"run_id": run, "row_count": len(ids),
                "row_identity_sha256": r.digest("".join(target + "\n" for target in ids).encode())})
        groups.append({"role": role, "row_count": 40, "shards": shards})
    return windows, {"groups": groups}


def test_counts_recomputed_from_exact_canonical_restricted_rows():
    windows, metadata = fixture()
    raw, result = r.collect(windows, metadata)
    assert result == r.verify_rows(raw, metadata)
    assert result["row_count"] == 120 and result["class_support_passed"]
    assert all(role["positive_rows"] == role["negative_rows"] == 20 for role in result["roles"].values())
    assert all(set(json.loads(line)) == {"run_id", "target_id", "label"} for line in raw.splitlines())
    assert result["ledger_size_bytes"] == len(raw) and result["ledger_sha256"] == r.digest(raw)


@pytest.mark.parametrize("positive", [19, 21])
def test_both_class_boundaries_retain_negative_result_without_reassignment(positive):
    windows, metadata = fixture(positive)
    raw, result = r.collect(windows, metadata)
    assert not result["class_support_passed"]
    assert set(result["roles"]) == set(r.ROLES)
    assert result == r.verify_rows(raw, metadata)


@pytest.mark.parametrize("defect", ["duplicate", "missing", "extra", "run", "order", "run_order",
    "interleaved", "boolean", "nonbinary", "target", "fold", "unknown_field", "spaces", "newline"])
def test_corrupt_ledger_cannot_reproduce_bound_row_inventory(defect):
    windows, metadata = fixture()
    if defect == "fold":
        windows[-1].fold = "test"
        with pytest.raises(ValueError):
            r.collect(windows, metadata)
        return
    raw, _ = r.collect(windows, metadata)
    rows = [json.loads(line) for line in raw.splitlines()]
    if defect == "duplicate":
        rows[-1]["target_id"] = rows[0]["target_id"]
    elif defect == "missing":
        rows.pop()
    elif defect == "extra":
        rows.append({**rows[-1], "target_id": "a" * 64})
    elif defect == "run":
        rows[-1]["run_id"] = "unknown"
    elif defect == "order":
        rows[0], rows[1] = rows[1], rows[0]
    elif defect == "run_order":
        rows = rows[20:40] + rows[:20] + rows[40:]
    elif defect == "interleaved":
        rows[0], rows[20] = rows[20], rows[0]
    elif defect in ("boolean", "nonbinary"):
        rows[-1]["label"] = True if defect == "boolean" else 2
    elif defect == "target":
        rows[-1]["target_id"] = "invalid"
    elif defect == "unknown_field":
        rows[-1]["role"] = "selection"
    altered = b"".join(r.canonical(row) + b"\n" for row in rows)
    if defect == "spaces":
        altered = b" " + altered
    elif defect == "newline":
        altered = altered[:-1]
    with pytest.raises(ValueError):
        r.verify_rows(altered, metadata)


def test_byte_row_and_metadata_bounds_are_fail_closed(monkeypatch):
    windows, metadata = fixture()
    raw, _ = r.collect(windows, metadata)
    monkeypatch.setattr(r, "MAX_LEDGER", len(raw) - 1)
    for operation in (lambda: r.verify_rows(raw, metadata), lambda: r.collect(windows, metadata)):
        with pytest.raises(ValueError, match="byte bound"):
            operation()
    monkeypatch.setattr(r, "MAX_LEDGER", len(raw))
    monkeypatch.setattr(r, "MAX_ROWS", 119)
    with pytest.raises(ValueError, match="row bound"):
        r.collect(windows, metadata)
    with pytest.raises(ValueError, match="inventory exceeds"):
        r.verify_rows(raw, metadata)
