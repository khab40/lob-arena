"""Exercise rejected maintenance runtimes without importing MLflow or contacting services."""
import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("readiness_preflight",
    Path(__file__).resolve().parents[2] / "scripts/mlflow_readiness_preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class InertSDK:
    def __init__(self, *args, **kwargs):
        raise AssertionError("preflight must never construct a client")

    def get_run(self, run_id): raise AssertionError("API called")
    def get_experiment(self, experiment_id): raise AssertionError("API called")
    def get_experiment_by_name(self, name): raise AssertionError("API called")
    def create_experiment(self, name, artifact_location=None): raise AssertionError("API called")
    def create_run(self, experiment_id, start_time=None, tags=None, run_name=None): raise AssertionError("API called")
    def search_runs(self, experiment_ids, filter_string, run_view_type, max_results): raise AssertionError("API called")
    def log_param(self, run_id, key, value, synchronous=None): raise AssertionError("API called")
    def log_metric(self, run_id, key, value, timestamp=None, step=None, synchronous=None): raise AssertionError("API called")
    def set_tag(self, run_id, key, value, synchronous=None): raise AssertionError("API called")
    def set_terminated(self, run_id, status=None, end_time=None): raise AssertionError("API called")
    def get_metric_history(self, run_id, key): raise AssertionError("API called")
    def get_registered_model(self, name): raise AssertionError("API called")
    def create_registered_model(self, name): raise AssertionError("API called")
    def search_model_versions(self, filter_string, max_results): raise AssertionError("API called")
    def get_model_version(self, name, version): raise AssertionError("API called")
    def create_model_version(self, name, source, run_id=None, tags=None, await_creation_for=None): raise AssertionError("API called")
    def set_registered_model_alias(self, name, alias, version): raise AssertionError("API called")
    def get_user(self, username): raise AssertionError("API called")
    def create_user(self, username, password): raise AssertionError("API called")
    def list_user_roles(self, username): raise AssertionError("API called")
    def list_role_permissions(self, role_id): raise AssertionError("API called")
    def get_user_permission(self, username, resource_type, resource_id): raise AssertionError("API called")
    def grant_user_permission(self, username, resource_type, resource_id, permission): raise AssertionError("API called")


@pytest.fixture
def runtime(monkeypatch):
    for key, value in {"MLFLOW_DISABLE_TELEMETRY": "true", "MLFLOW_HTTP_REQUEST_MAX_RETRIES": "0", "MLFLOW_HTTP_REQUEST_TIMEOUT": "10",
                       "MLFLOW_ENABLE_ASYNC_LOGGING": "false", "MLFLOW_TRACKING_URI": "http://10.4.0.54:5500",
                       "MLFLOW_REGISTRY_URI": "http://10.4.0.54:5500"}.items():
        monkeypatch.setenv(key, value)
    for key in ("MLFLOW_ACTIVE_MODEL_ID", "_MLFLOW_ACTIVE_MODEL_ID"):
        monkeypatch.delenv(key, raising=False)
    mlflow = SimpleNamespace(__version__="3.13.0", MlflowClient=InertSDK,
        get_active_model_id=lambda: None, get_tracking_uri=lambda: os.environ["MLFLOW_TRACKING_URI"],
        get_registry_uri=lambda: os.environ["MLFLOW_REGISTRY_URI"])
    modules = {"mlflow": mlflow, "mlflow.server.auth.client": SimpleNamespace(AuthServiceClient=InertSDK),
               "sqlalchemy": object(), "psycopg2": object()}
    imported = []
    def importer(name):
        imported.append(name)
        if name not in modules:
            raise ModuleNotFoundError("auth extra unavailable")
        return modules[name]
    return SimpleNamespace(modules=modules, imported=imported, importer=importer)


def test_preflight_checks_real_interfaces_without_constructing_clients(runtime):
    receipt = preflight.verify(runtime.importer)
    assert receipt["helper_signatures_verified"]
    assert receipt["api_calls"] == 0 and receipt["credentials_read"] is False
    assert runtime.imported == ["mlflow", "mlflow.server.auth.client", "sqlalchemy", "psycopg2"]
    assert "10.4.0.54" not in str(receipt)


@pytest.mark.parametrize("key,value", [("MLFLOW_ENABLE_ASYNC_LOGGING", "true"),
    ("MLFLOW_DISABLE_TELEMETRY", "false"),
    ("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "1"), ("MLFLOW_HTTP_REQUEST_TIMEOUT", "inf"),
    ("MLFLOW_REGISTRY_URI", "http://10.4.0.99:5500"), ("MLFLOW_ACTIVE_MODEL_ID", "m-existing"),
    ("_MLFLOW_ACTIVE_MODEL_ID", "m-existing")])
def test_unsafe_settings_fail_before_sdk_import(runtime, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError):
        preflight.verify(runtime.importer)
    assert runtime.imported == []


@pytest.mark.parametrize("failure", ["version", "auth", "signature", "global-model", "global-uri"])
def test_incompatible_or_incomplete_runtime_cannot_pass(runtime, monkeypatch, failure):
    mlflow = runtime.modules["mlflow"]
    if failure == "version":
        mlflow.__version__ = "3.16.1"
    if failure == "auth":
        del runtime.modules["mlflow.server.auth.client"]
    if failure == "signature":
        monkeypatch.setattr(InertSDK, "log_metric", lambda self, run_id: None)
    if failure == "global-model":
        mlflow.get_active_model_id = lambda: "m-existing"
    if failure == "global-uri":
        mlflow.get_tracking_uri = lambda: "http://8.8.8.8:5000"
    with pytest.raises((ValueError, ModuleNotFoundError)):
        preflight.verify(runtime.importer)


@pytest.mark.parametrize("uri", ["http://8.8.8.8:5000", "http://169.254.169.254:80",
    "http://0.0.0.0:5000", "http://public.example:5000", "http://u:p@10.4.0.54:5500",
    "http://10.4.0.54:5500/path", "http://10.4.0.54:5500?token=x"])
def test_public_credential_or_nonendpoint_uri_rejected(uri):
    assert preflight.private_endpoint(uri) is False


@pytest.mark.parametrize("uri", ["http://mlflow-restored:5000", "http://mlflow:5000",
                                  "http://127.0.0.1:5500", "http://10.4.0.54:5500"])
def test_explicit_private_or_isolated_service_endpoint(uri):
    assert preflight.private_endpoint(uri) is True
