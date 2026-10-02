from types import SimpleNamespace as NS

import pytest

from deployments.mlflow.readiness_permissions import (
    MODEL, PRINCIPALS, apply_permissions, inspect_permissions,
)


class Auth:
    def __init__(self):
        self.users = {name: NS(id=i, username=name, is_admin=False, password_hash="REDACTED")
                      for i, name in enumerate(PRINCIPALS, 1)}
        self.roles = {name: [NS(id=i, name=f"__user_{i}__", workspace="default", description=None)]
                      for i, name in enumerate(PRINCIPALS, 1)}
        self.grants = {i: [NS(role_id=i, resource_type="experiment", resource_pattern="1",
                             permission=PRINCIPALS[name])]
                       for i, name in enumerate(PRINCIPALS, 1)}
        self.calls, self.fail_at, self.mutate = [], None, lambda: None

    def get_user(self, name):
        return self.users[name]

    def list_user_roles(self, name):
        return self.roles[name]

    def list_role_permissions(self, role):
        return self.grants[role]

    def get_user_permission(self, name, kind, resource):
        permissions = [g.permission for role in self.roles[name] for g in self.grants[role.id]
                       if (g.resource_type, g.resource_pattern) == (kind, resource)]
        return NS(permission=permissions[0] if permissions else "NO_PERMISSIONS")

    def grant_user_permission(self, name, kind, resource, permission):
        self.calls.append((name, kind, resource, permission))
        if self.fail_at == len(self.calls):
            raise TimeoutError("ambiguous grant")
        role_id = self.users[name].id
        if not any(role.id == role_id for role in self.roles[name]):
            self.roles[name].append(NS(id=role_id, name=f"__user_{role_id}__",
                                       workspace="default", description=None))
            self.grants[role_id] = []
        self.grants[role_id].append(NS(role_id=role_id, resource_type=kind,
                                       resource_pattern=resource, permission=permission))
        self.mutate()


def test_exact_additions_preserve_prior_state_and_are_idempotent():
    auth = Auth()
    plan = inspect_permissions(auth, "7")
    receipt = apply_permissions(auth, plan)
    assert len(auth.calls) == receipt["added_grants"] == 4
    assert receipt["observed_identity_and_grants_preserved"] and receipt["verified_grants"] == 4
    assert all(auth.grants[i][0].resource_pattern == "1" for i in (1, 2))
    assert "REDACTED" not in repr(plan) + repr(receipt)
    assert not any("credential" in key or "password" in key for key in receipt)
    assert apply_permissions(auth, inspect_permissions(auth, "7"))["added_grants"] == 0
    assert len(auth.calls) == 4


def test_inherited_matching_grants_need_no_direct_replacement():
    auth = Auth()
    auth.roles["prometheus"].append(NS(id=3, name="team", workspace="default", description=None))
    auth.grants[3] = [NS(role_id=3, resource_type="registered_model", resource_pattern=MODEL,
                         permission="READ")]
    assert apply_permissions(auth, inspect_permissions(auth, "7"))["added_grants"] == 3


def test_first_direct_grant_may_create_only_the_personal_role():
    auth = Auth()
    auth.roles["prometheus"] = []
    assert apply_permissions(auth, inspect_permissions(auth, "7"))["added_grants"] == 4


@pytest.mark.parametrize("conflict", ["admin", "wildcard", "workspace", "exact", "effective"])
def test_all_principals_are_preflighted_before_any_write(conflict):
    auth = Auth()
    if conflict == "admin":
        auth.users["prometheus"].is_admin = True
    elif conflict == "effective":
        auth.get_user_permission = lambda *args: NS(permission="READ")
    else:
        kind, pattern, permission = {
            "wildcard": ("experiment", "*", "READ"),
            "workspace": ("workspace", "*", "MANAGE"),
            "exact": ("experiment", "7", "EDIT"),
        }[conflict]
        auth.roles["prometheus"].append(NS(id=3, name="team", workspace="default", description=None))
        auth.grants[3] = [NS(role_id=3, resource_type=kind, resource_pattern=pattern,
                             permission=permission)]
    with pytest.raises(ValueError):
        apply_permissions(auth, inspect_permissions(auth, "7"))
    assert auth.calls == []


def test_changed_preflight_and_partial_failure_never_replay_grants():
    auth = Auth()
    plan = inspect_permissions(auth, "7")
    auth.fail_at = 2
    with pytest.raises(TimeoutError):
        apply_permissions(auth, plan)
    assert len(auth.calls) == 2 and len(auth.grants[1]) == 2
    with pytest.raises(ValueError, match="changed after preflight"):
        apply_permissions(auth, plan)
    assert len(auth.calls) == 2


@pytest.mark.parametrize("tamper", ["prior_grant", "identity", "role"])
def test_after_readback_rejects_unapproved_state_changes(tamper):
    auth = Auth()
    def mutate():
        if tamper == "prior_grant":
            auth.grants[1] = [g for g in auth.grants[1] if g.resource_pattern != "1"]
        elif tamper == "identity":
            auth.users["prometheus"].id = 999
        else:
            auth.roles["prometheus"][0].description = "changed"
    auth.mutate = mutate
    with pytest.raises(ValueError):
        apply_permissions(auth, inspect_permissions(auth, "7"))
    assert len(auth.calls) == 4
