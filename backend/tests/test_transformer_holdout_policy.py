from copy import deepcopy

import pytest

from app.ml.transformer.holdout_policy import access_rules, permissions, temporary_policy


def rule(group, role, path):
    return {"group_id": group, "roles": [role], "paths": [path]}


def test_consolidation_fits_two_additions_without_baseline_write():
    original = [rule("reader", "storage.viewer", "a/*"),
                rule("reader", "storage.viewer", "b/*")]
    original += [rule(f"principal-{i}", "storage.object-editor", f"retained-{i}/*")
                 for i in range(7)]
    saved = deepcopy(original)
    added = [rule("reader", "storage.viewer", "baseline.parquet"),
             rule("reader", "storage.object-editor", "one-run/*")]
    result = temporary_policy(original, added)
    assert len(result) == 10
    assert original == saved
    assert permissions(result) == permissions(original) | permissions(added)
    assert not any("baseline.parquet" in r["paths"] and "storage.object-editor" in r["roles"]
                   for r in result)


def test_different_principal_or_conditions_are_never_consolidated():
    original = [rule("a", "storage.viewer", "x"), rule("b", "storage.viewer", "y")]
    original.append({**rule("a", "storage.viewer", "z"), "condition": "retained"})
    assert len(temporary_policy(original, [])) == 3


def test_each_rule_has_at_most_ten_paths():
    added = access_rules("reader", "storage.viewer", [f"key-{i}" for i in range(62)])
    assert list(map(lambda r: len(r["paths"]), added)) == [10, 10, 10, 10, 10, 10, 2]
    assert len(temporary_policy([rule("a", "storage.viewer", "original")], added)) == 8


def test_overflow_and_duplicates_fail_before_any_cloud_call():
    with pytest.raises(ValueError, match="unique"):
        access_rules("a", "storage.viewer", ["same", "same"])
    with pytest.raises(ValueError, match="envelope"):
        temporary_policy([rule(str(i), "storage.viewer", "x") for i in range(10)],
                         [rule("new", "storage.viewer", "y")])
