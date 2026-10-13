"""Invented import inventory; no application startup or Google verifier calls."""

import sys
from importlib.machinery import ModuleSpec
from types import ModuleType, SimpleNamespace

import pytest

from app import runtime_smoke


@pytest.fixture
def inventory(monkeypatch):
    present = {"google", "google.oauth2", "google.oauth2.id_token"}
    calls = []
    modules = {name: ModuleType(name) for name in present}
    modules["google"].__path__ = []
    modules["google.oauth2"].__path__ = []

    def verifier(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Verifier must never run during smoke validation")

    token = modules["google.oauth2.id_token"]
    token.verify_oauth2_token = verifier
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    monkeypatch.setitem(sys.modules, "app.main", ModuleType("app.main"))
    monkeypatch.delitem(sys.modules, "app.arena.engine", raising=False)
    monkeypatch.setattr(sys, "argv", ["runtime_smoke", "--minimal-image"])
    monkeypatch.setattr(runtime_smoke.importlib.util, "find_spec", lambda name:
                        ModuleSpec(name, loader=None) if name in present or
                        any(item.startswith(name + ".") for item in present) else None)
    return SimpleNamespace(present=present, token=token, calls=calls)


def test_minimal_smoke_accepts_google_auth_without_verifier_invocation(inventory):
    runtime_smoke.main()
    assert inventory.calls == []


@pytest.mark.parametrize("module", ["grpc", "google.protobuf", "app.websocket.routes",
                                    "app.contracts.python_reference"])
def test_minimal_smoke_rejects_retired_or_protobuf_runtime(inventory, module):
    inventory.present.add(module)
    with pytest.raises(AssertionError):
        runtime_smoke.main()
    assert inventory.calls == []


def test_minimal_smoke_requires_google_verifier_import(inventory):
    del inventory.token.verify_oauth2_token
    with pytest.raises(ImportError):
        runtime_smoke.main()
    assert inventory.calls == []


def test_minimal_smoke_requires_callable_google_verifier(inventory):
    inventory.token.verify_oauth2_token = None
    with pytest.raises(AssertionError):
        runtime_smoke.main()
    assert inventory.calls == []


@pytest.mark.parametrize("minimal", [False, True])
def test_smoke_keeps_java_engine_authority(inventory, monkeypatch, minimal):
    monkeypatch.setattr(sys, "argv", ["runtime_smoke"] + (["--minimal-image"] if minimal else []))
    monkeypatch.setitem(sys.modules, "app.arena.engine", ModuleType("app.arena.engine"))
    with pytest.raises(AssertionError):
        runtime_smoke.main()
    assert inventory.calls == []
