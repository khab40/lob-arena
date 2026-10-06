"""Prepare bounded access policies without broadening retained permissions."""
from copy import deepcopy
import json


def permissions(rules):
    """Include every principal/condition field when comparing effective access."""
    return {(json.dumps({k: v for k, v in rule.items() if k != "paths"}, sort_keys=True), path)
            for rule in rules for path in rule["paths"]}


def temporary_policy(original, additions):
    groups = {}
    for rule in deepcopy(original):
        if not rule.get("paths") or len(rule["paths"]) > 10:
            raise ValueError("existing policy violates path envelope")
        key = json.dumps({k: v for k, v in rule.items() if k != "paths"}, sort_keys=True)
        groups.setdefault(key, []).extend(rule["paths"])
    retained = []
    for key, paths in groups.items():
        unique = list(dict.fromkeys(paths))
        retained.extend({**json.loads(key), "paths": unique[i:i + 10]}
                        for i in range(0, len(unique), 10))
    if permissions(retained) != permissions(original):
        raise ValueError("policy consolidation changed retained access")
    result = retained + deepcopy(additions)
    if (len(result) > 10 or any(not r.get("paths") or len(r["paths"]) > 10 for r in result)
            or permissions(result) != permissions(original) | permissions(additions)):
        raise ValueError("temporary policy exceeds approved envelope")
    return result


def access_rules(group, role, paths):
    if not paths or len(set(paths)) != len(paths):
        raise ValueError("access requires unique exact paths")
    return [{"group_id": group, "roles": [role], "paths": list(paths[i:i + 10])}
            for i in range(0, len(paths), 10)]
