"""Inert cache behavior; real C4 verification is exercised on Nebius only."""
import ast
from copy import deepcopy
from pathlib import Path

import pytest


def helper():
    source = Path(__file__).resolve().parents[1] / "app/ml/lightgbm/c4_replay_evidence.py"
    tree = ast.parse(source.read_text())
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_reuse_comparison")
    namespace = {"deepcopy": deepcopy, "_VERIFIED_COMPARISON": None}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), namespace)
    return namespace["_reuse_comparison"]


def test_identical_identity_reuses_success_without_exposing_mutable_state():
    reuse = helper()
    calls = []
    result = {"coverage": {"count": 3}}

    def compute():
        calls.append(1)
        return result

    first = reuse(("profile", "predictions"), compute)
    result["coverage"]["count"] = 99
    first["coverage"]["count"] = 12
    assert reuse(("profile", "predictions"), compute) == {"coverage": {"count": 3}}
    assert calls == [1]


@pytest.mark.parametrize("changed", [("other-profile", "predictions"), ("profile", "other-predictions")])
def test_identity_change_recomputes_and_evicts_previous_entry(changed):
    reuse = helper()
    calls = []

    def compute():
        calls.append(1)
        return {"count": len(calls)}

    assert reuse(("profile", "predictions"), compute)["count"] == 1
    assert reuse(changed, compute)["count"] == 2
    assert reuse(("profile", "predictions"), compute)["count"] == 3


def test_failed_computation_never_becomes_reusable():
    reuse = helper()
    for _ in range(2):
        with pytest.raises(ValueError, match="inert failure"):
            reuse(("profile", "predictions"), lambda: (_ for _ in ()).throw(ValueError("inert failure")))
    assert reuse(("profile", "predictions"), lambda: {"count": 1}) == {"count": 1}


def test_fresh_module_has_no_reusable_comparison():
    first, fresh = helper(), helper()
    assert first(("p", "d"), lambda: {"count": 1}) == {"count": 1}
    assert fresh(("p", "d"), lambda: {"count": 2}) == {"count": 2}
