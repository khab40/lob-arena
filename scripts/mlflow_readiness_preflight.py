"""Offline probe inside the exact maintenance interpreter, before credentials/API calls."""
import importlib
import inspect
import ipaddress
import json
import os
import platform
from urllib.parse import urlsplit

TRACKING = {
    "get_run": "run_id", "get_experiment": "experiment_id", "get_experiment_by_name": "name",
    "create_experiment": "name artifact_location", "create_run": "experiment_id start_time tags run_name",
    "search_runs": "experiment_ids filter_string run_view_type max_results",
    "log_param": "run_id key value synchronous", "log_metric": "run_id key value timestamp step synchronous",
    "set_tag": "run_id key value synchronous", "set_terminated": "run_id status end_time",
    "get_metric_history": "run_id key", "get_registered_model": "name",
    "create_registered_model": "name", "search_model_versions": "filter_string max_results",
    "get_model_version": "name version", "create_model_version": "name source run_id tags await_creation_for",
    "set_registered_model_alias": "name alias version",
}
AUTH = {"get_user": "username", "create_user": "username password", "list_user_roles": "username",
        "list_role_permissions": "role_id", "get_user_permission": "username resource_type resource_id",
        "grant_user_permission": "username resource_type resource_id permission"}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def private_endpoint(uri):
    parsed = urlsplit(uri)
    if (parsed.scheme not in {"http", "https"} or parsed.username is not None
            or parsed.password is not None or parsed.query or parsed.fragment
            or parsed.path not in {"", "/"} or parsed.port is None):
        return False
    if parsed.hostname in {"mlflow", "mlflow-restored"}:
        return parsed.port == 5000
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        return False
    return address.is_loopback or any(address in ipaddress.ip_network(network) for network in (
        "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7"))


def verify(importer=importlib.import_module):
    require(os.environ.get("MLFLOW_DISABLE_TELEMETRY") == "true", "disable telemetry before SDK import")
    require(os.environ.get("MLFLOW_HTTP_REQUEST_MAX_RETRIES") == "0", "HTTP retries must be zero")
    require(os.environ.get("MLFLOW_ENABLE_ASYNC_LOGGING") == "false", "async logging must be disabled")
    require(os.environ.get("MLFLOW_HTTP_REQUEST_TIMEOUT") == "10", "HTTP timeout must be ten seconds")
    require(not any(os.environ.get(k) for k in ("MLFLOW_ACTIVE_MODEL_ID", "_MLFLOW_ACTIVE_MODEL_ID")),
            "active model environment is forbidden")
    uri = os.environ.get("MLFLOW_TRACKING_URI", "")
    require(private_endpoint(uri) and os.environ.get("MLFLOW_REGISTRY_URI") == uri,
            "matching private tracking and registry endpoints required")
    mlflow = importer("mlflow")
    require(mlflow.__version__ == "3.13.0", "exact deployed MLflow 3.13.0 required")
    auth = importer("mlflow.server.auth.client")
    importer("sqlalchemy")
    importer("psycopg2")
    require(mlflow.get_active_model_id() is None, "active in-process model is forbidden")
    require(mlflow.get_tracking_uri() == uri and mlflow.get_registry_uri() == uri,
            "runtime endpoint differs from explicit environment")
    for cls, methods in ((mlflow.MlflowClient, TRACKING), (auth.AuthServiceClient, AUTH)):
        for name, names in methods.items():
            require(set(names.split()) <= set(inspect.signature(getattr(cls, name)).parameters),
                    "required SDK signature unavailable")
    return {"schema_version": "mlflow_readiness_runtime_preflight_v1", "status": "verified",
            "mlflow_version": mlflow.__version__, "python_version": platform.python_version(),
            "required_imports_verified": True, "helper_signatures_verified": True,
            "http_timeout_seconds": 10, "http_retries": 0, "async_logging": False,
            "telemetry_disabled": True,
            "active_model_absent": True, "api_calls": 0, "credentials_read": False}


if __name__ == "__main__":
    try:
        receipt = verify()
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps(receipt, sort_keys=True))
