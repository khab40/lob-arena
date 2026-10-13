"""Startup verification uses only invented temporary directories and stub services."""

import importlib.util
from pathlib import Path

import pytest

from app.config import Settings
from app.runtime_roots import validate_runtime_roots


def settings_for(tmp_path):
    return Settings(_env_file=None, CEO_DEMO_ENABLED=True, CEO_DEMO_LOCAL=True,
        CEO_DEMO_ORIGIN="http://localhost:5173", CEO_DEMO_STATE_DIR=tmp_path / "state",
        ARENA_OUTPUT_DIR=tmp_path / "output", RESEARCH_SAVED_SCORES_DIR=tmp_path / "missing-custody",
        ARENA_LOBSTER_RAW_DIR=tmp_path / "raw", ARENA_HISTORICAL_DATA_DIR=tmp_path / "historical",
        ARENA_ITCH_RAW_DIR=tmp_path / "itch")


@pytest.mark.parametrize("unsafe", ["custody_child", "output_child", "state_child", "state_parent",
                                    "state_custody", "screenshots", "symlink", "relative"])
def test_private_overlap_and_aliases_fail_before_writable_services(tmp_path, unsafe):
    settings = settings_for(tmp_path)
    screenshots = tmp_path / "screenshots"
    if unsafe == "custody_child":
        settings.research_saved_scores_dir = settings.arena_output_dir / "custody"
    elif unsafe == "output_child":
        settings.arena_output_dir = settings.research_saved_scores_dir / "generic"
    elif unsafe == "state_child":
        settings.ceo_demo_state_dir = settings.arena_output_dir / "state"
    elif unsafe == "state_parent":
        settings.ceo_demo_state_dir = tmp_path
    elif unsafe == "state_custody":
        settings.ceo_demo_state_dir = settings.research_saved_scores_dir / "state"
    elif unsafe == "screenshots":
        settings.research_saved_scores_dir = screenshots
    elif unsafe == "symlink":
        settings.ceo_demo_state_dir.symlink_to(settings.arena_output_dir, target_is_directory=True)
    else:
        settings.ceo_demo_state_dir = Path("relative-state")
    with pytest.raises(ValueError):
        validate_runtime_roots(settings, screenshots)
    assert not settings.arena_output_dir.exists()


def execute_startup(monkeypatch, settings):
    from app import config
    from app.data_ingestion import service
    from app.storage import local_store, retention
    from app.arena import java_client
    from app.nebius import client as nebius_client
    monkeypatch.setattr(config, "get_settings", lambda: settings)
    monkeypatch.setattr(nebius_client, "get_settings", lambda: settings)
    calls = []
    class Store:
        def __init__(self, root):
            calls.append("store")
            self.output_dir = root
    monkeypatch.setattr(local_store, "LocalStore", Store)
    monkeypatch.setattr(retention, "cleanup_output_data", lambda *_: calls.append("retention"))
    monkeypatch.setattr(service, "DataIngestionService", lambda *_: calls.append("ingestion"))
    monkeypatch.setattr(java_client, "JavaArenaClient", lambda *_, **__: calls.append("java"))
    path = Path(__file__).parents[1] / "app/main.py"
    spec = importlib.util.spec_from_file_location("invented_startup", path)
    module = importlib.util.module_from_spec(spec)
    return spec, module, calls


@pytest.mark.parametrize("configured", [False, True])
def test_enabled_demo_preserves_normal_initialization_when_custody_missing(tmp_path, monkeypatch, configured):
    settings = settings_for(tmp_path)
    if configured:
        settings.google_client_id = "invented-client"
        settings.ceo_demo_allowed_emails = "reviewer@example.com"
    spec, module, calls = execute_startup(monkeypatch, settings)
    spec.loader.exec_module(module)
    assert calls == ["store", "retention", "ingestion", "java"]
    assert (module.app.state.ceo_journey is not None) == configured
    if configured:
        with pytest.raises((OSError, ValueError)):
            module.app.state.ceo_journey.campaign()
    assert not settings.research_saved_scores_dir.exists()


def test_unsafe_configuration_cannot_be_swallowed_before_retention(tmp_path, monkeypatch):
    settings = settings_for(tmp_path)
    settings.research_saved_scores_dir = settings.arena_output_dir / "private"
    spec, module, calls = execute_startup(monkeypatch, settings)
    with pytest.raises(ValueError):
        spec.loader.exec_module(module)
    assert calls == [] and not settings.arena_output_dir.exists()


@pytest.mark.parametrize("root", ["custody", "state"])
def test_existing_generic_artifact_resolver_refuses_private_files(tmp_path, root):
    from fastapi import HTTPException
    from types import SimpleNamespace
    from app.api.routes_experiments import _resolve_readable_artifact
    settings = settings_for(tmp_path)
    directory = settings.research_saved_scores_dir if root == "custody" else settings.ceo_demo_state_dir
    directory.mkdir(mode=0o700)
    private = directory / "invented.json"
    private.write_bytes(b"invented-private-body")
    validate_runtime_roots(settings, tmp_path / "screenshots")
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        store=SimpleNamespace(output_dir=settings.arena_output_dir))))
    with pytest.raises(HTTPException) as exc:
        _resolve_readable_artifact(request, str(private))
    assert exc.value.status_code == 403
