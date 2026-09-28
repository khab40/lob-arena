"""Offline rendering of the approved grant within Nebius policy limits."""
from copy import deepcopy
import hashlib
import json

# nebius/storage/v1/bucket_policy.proto: both repeated fields have max_items=10.
MAX_RULES = MAX_PATHS = 10
PROPOSAL_SHA256 = "0c7a32442a95d04deedcb12798eb466eb3786273f1c30e0c97cca10b388ef414"


def validate_policy(rules):
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise ValueError("bucket policy exceeds provider rule limit")
    for rule in rules:
        paths = rule.get("paths")
        if (not isinstance(paths, list) or len(paths) > MAX_PATHS
                or not all(isinstance(path, str) for path in paths)):
            raise ValueError("bucket policy exceeds provider path limit")


def temporary_rules(proposal_bytes):
    if hashlib.sha256(proposal_bytes).hexdigest() != PROPOSAL_SHA256:
        raise ValueError("proposal differs from operator approval")
    rule = json.loads(proposal_bytes)["added_rule"]
    paths = rule["paths"]
    if len(paths) != 29 or len(set(paths)) != 29 or any("*" in path for path in paths):
        raise ValueError("expected 29 distinct exact metadata keys")
    return [{**deepcopy(rule), "paths": paths[offset:offset + MAX_PATHS]}
            for offset in range(0, len(paths), MAX_PATHS)]


def same_rule(left, right):
    def normalize(rule):
        return {key: sorted(value) if key in ("paths", "roles") else value
                for key, value in rule.items()}
    return normalize(left) == normalize(right)


def grant_policy(current, proposal_bytes):
    validate_policy(current)
    added = temporary_rules(proposal_bytes)
    if any(same_rule(rule, candidate) for rule in current for candidate in added):
        raise ValueError("temporary grant is already present or partially applied")
    result = deepcopy(current) + added
    validate_policy(result)
    return result


def removal_policy(current, proposal_bytes):
    validate_policy(current)
    added = temporary_rules(proposal_bytes)
    for candidate in added:
        if sum(same_rule(rule, candidate) for rule in current) != 1:
            raise ValueError("temporary grant missing, changed or duplicated")
    return deepcopy([rule for rule in current
                     if not any(same_rule(rule, candidate) for candidate in added)])
