"""Offline exact two-phase policy transitions; never mutates cloud permissions."""
from copy import deepcopy

from .lineage_inventory import phase_keys
from .provenance_policy import MAX_PATHS, same_rule, validate_policy

GROUP = "group-e00wb5ptvpq0q7dpaf"


def rules_for(phase):
    keys = phase_keys(phase)
    return [{"group_id": GROUP, "roles": ["storage.viewer"], "paths": keys[i:i + MAX_PATHS]}
            for i in range(0, len(keys), MAX_PATHS)]


def transition(current, *, before, after):
    """Only grant phase1, atomically replace1→2, or remove the active phase."""
    if (before, after) not in ((None, 1), (1, 2), (1, None), (2, None)):
        raise ValueError("unreviewed lineage permission transition")
    validate_policy(current)
    old = rules_for(before) if before else []
    for rule in old:
        if sum(same_rule(rule, existing) for existing in current) != 1:
            raise ValueError("active lineage grant missing, changed or duplicated")
    remaining = [rule for rule in current if not any(same_rule(rule, added) for added in old)]
    # Reject a second or partial grant rather than silently combining permissions.
    paths = set(phase_keys(1) + phase_keys(2))
    if any(rule.get("group_id") == GROUP and paths.intersection(rule["paths"]) for rule in remaining):
        raise ValueError("unexpected or partial lineage grant already present")
    result = deepcopy(remaining) + (rules_for(after) if after else [])
    validate_policy(result)
    return result
