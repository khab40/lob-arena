"""Add only the four approved Transformer grants; never repair conflicting access.

The caller resolves the namespaces, verifies server defaults and journals one
application attempt. An exception retains partial state and confers no retry.
Never serialize a plan. REST redacts password hashes; the caller must separately
compare the full private SQL users table before/after, retaining only a boolean.
"""
from dataclasses import dataclass, field

MODEL = "lob-arena-transformer-attack-active"
PRINCIPALS = {"governed-writer": "EDIT", "prometheus": "READ"}


@dataclass(frozen=True, repr=False)
class PermissionPlan:
    experiment_id: str
    model_name: str
    snapshots: dict = field(repr=False)
    missing: tuple


def _snapshot(auth, username):
    user = auth.get_user(username)
    if user.username != username or user.is_admin is not False:
        raise ValueError("readiness requires existing non-admin service users")
    roles, permissions = {}, set()
    for role in auth.list_user_roles(username):
        if role.id in roles or role.workspace != "default":
            raise ValueError("duplicate role or unsupported workspace")
        roles[role.id] = (role.name, role.workspace, role.description)
        for grant in auth.list_role_permissions(role.id):
            value = (role.id, grant.resource_type, grant.resource_pattern, grant.permission)
            if value in permissions or grant.role_id != role.id:
                raise ValueError("duplicate or mismatched role permission")
            permissions.add(value)
    return {
        "user": (user.id, user.username, user.is_admin),
        "roles": roles,
        "permissions": permissions,
    }


def inspect_permissions(auth, experiment_id, model_name=MODEL):
    """Read all assigned grants and all target permissions before any mutation."""
    if not isinstance(experiment_id, str) or not experiment_id.isdecimal() or model_name != MODEL:
        raise ValueError("exact Transformer resource identities are required")
    resources = (("experiment", experiment_id), ("registered_model", model_name))
    snapshots, missing = {}, []
    for username, desired in PRINCIPALS.items():
        snapshot = snapshots[username] = _snapshot(auth, username)
        grants = snapshot["permissions"]
        for _, kind, pattern, permission in grants:
            if (kind in {"experiment", "registered_model"} and "*" in pattern
                    or kind == "workspace" and permission == "MANAGE"):
                raise ValueError("broader service-user permission conflicts with readiness")
        for kind, resource in resources:
            matching = {value for _, typ, pattern, value in grants if (typ, pattern) == (kind, resource)}
            effective = auth.get_user_permission(username, kind, resource).permission
            if matching - {desired} or effective != (desired if matching else "NO_PERMISSIONS"):
                raise ValueError("existing or effective permission conflicts with readiness")
            if not matching:
                missing.append((username, kind, resource, desired))
    return PermissionPlan(experiment_id, model_name, snapshots, tuple(missing))


def apply_permissions(auth, plan):
    """Apply a preflighted plan once and verify the exact additive state change."""
    if inspect_permissions(auth, plan.experiment_id, plan.model_name) != plan:
        raise ValueError("permission state changed after preflight")
    for username, kind, resource, permission in plan.missing:
        auth.grant_user_permission(username, kind, resource, permission)
    after = inspect_permissions(auth, plan.experiment_id, plan.model_name)
    if after.missing:
        raise ValueError("approved permissions were not observable after application")
    for username, before in plan.snapshots.items():
        current = after.snapshots[username]
        if before["user"] != current["user"]:
            raise ValueError("service-user identity changed")
        if any(current["roles"].get(key) != value for key, value in before["roles"].items()):
            raise ValueError("existing role assignments changed")
        new_roles = current["roles"].keys() - before["roles"].keys()
        personal = f"__user_{before['user'][0]}__"
        if any(current["roles"][key][:2] != (personal, "default") for key in new_roles):
            raise ValueError("unexpected role assignment added")
        expected = {item[1:] for item in plan.missing if item[0] == username}
        added = current["permissions"] - before["permissions"]
        if (not before["permissions"] <= current["permissions"]
                or len(new_roles) > 1 or not new_roles <= {item[0] for item in added}
                or len(added) != len(expected)
                or {item[1:] for item in added} != expected
                or any(current["roles"][item[0]][0] != personal for item in added)):
            raise ValueError("permission changes differ from the approved additions")
    return {
        "schema_version": "transformer_mlflow_permission_readback_v1",
        "experiment_id": plan.experiment_id,
        "registered_model": plan.model_name,
        "added_grants": len(plan.missing),
        "verified_grants": 4,
        "observed_identity_and_grants_preserved": True,
    }
