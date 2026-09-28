from copy import deepcopy
from pathlib import Path

import pytest

from app.ml.transformer.provenance_policy import (
    grant_policy, removal_policy, temporary_rules, validate_policy,
)


def proposal():
    return (Path(__file__).resolve().parents[2] / "docs/evidence/"
        "transformer-validation-metadata-access-proposal-20260928.json").read_bytes()


def existing(count=2):
    return [{"group_id": f"existing-{i}", "roles": ["storage.viewer"],
             "paths": [f"existing/{i}/*"]} for i in range(count)]


def test_approved_keys_partition_without_broadening_or_mutating_existing_rules():
    import json
    raw = proposal()
    before = existing()
    retained = deepcopy(before)
    result = grant_policy(before, raw)
    assert len(result) == 5 and result[:2] == retained and before == retained
    chunks = result[2:]
    assert [len(rule["paths"]) for rule in chunks] == [10, 10, 9]
    approved = json.loads(raw)["added_rule"]
    assert [path for rule in chunks for path in rule["paths"]] == approved["paths"]
    assert all(rule["roles"] == approved["roles"] and rule["group_id"] == approved["group_id"]
               for rule in chunks)


def test_provider_rule_capacity_boundary():
    assert len(grant_policy(existing(7), proposal())) == 10
    with pytest.raises(ValueError, match="rule limit"):
        grant_policy(existing(8), proposal())


def test_original_oversized_rule_is_rejected():
    import json
    with pytest.raises(ValueError, match="path limit"):
        validate_policy(existing() + [json.loads(proposal())["added_rule"]])


def test_changed_approval_and_partial_application_are_rejected():
    with pytest.raises(ValueError, match="operator approval"):
        grant_policy(existing(), proposal() + b" ")
    with pytest.raises(ValueError, match="partially applied"):
        grant_policy(existing() + temporary_rules(proposal())[:1], proposal())


def test_removal_preserves_unrelated_current_rules_and_handles_path_order():
    original = existing()
    current = grant_policy(original, proposal()) + existing(3)[2:]
    for rule in current[2:5]:
        rule["paths"].reverse()
    retained = deepcopy(current)
    assert removal_policy(current, proposal()) == original + existing(3)[2:]
    assert current == retained


@pytest.mark.parametrize("defect", ["missing", "changed", "duplicate"])
def test_removal_requires_exact_complete_temporary_grant(defect):
    current = grant_policy(existing(), proposal())
    if defect == "missing":
        current.pop()
    elif defect == "changed":
        current[-1]["roles"] = ["storage.editor"]
    else:
        current.append(deepcopy(current[-1]))
    with pytest.raises(ValueError, match="missing, changed or duplicated"):
        removal_policy(current, proposal())
