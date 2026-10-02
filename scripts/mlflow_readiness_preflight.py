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

DIAGNOSTIC_CHECKS = {
    'HTTP_retries_must_be_zero',
    'HTTP_timeout_must_be_ten_seconds',
    'active_in-process_model_is_forbidden',
    'active_model_environment_is_forbidden',
    'active_model_state',
    'async_logging_must_be_disabled',
    'disable_telemetry_before_SDK_import',
    'exact_deployed_MLflow_3_13_0_required',
    'import_auth_client',
    'import_mlflow',
    'import_psycopg2',
    'import_sqlalchemy',
    'matching_private_tracking_and_registry_endpoints_required',
    'runtime_endpoint_differs_from_explicit_environment',
    'runtime_endpoints',
    'starting',
} | {"signature_tracking_" + name for name in TRACKING} | {"signature_auth_" + name for name in AUTH}


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


def verify(importer=importlib.import_module, record=lambda name: None):
    def check(ok, reason):
        record(reason.replace(" ", "_").replace(".", "_"))
        require(ok, reason)
    check(os.environ.get("MLFLOW_DISABLE_TELEMETRY") == "true", "disable telemetry before SDK import")
    check(os.environ.get("MLFLOW_HTTP_REQUEST_MAX_RETRIES") == "0", "HTTP retries must be zero")
    check(os.environ.get("MLFLOW_ENABLE_ASYNC_LOGGING") == "false", "async logging must be disabled")
    check(os.environ.get("MLFLOW_HTTP_REQUEST_TIMEOUT") == "10", "HTTP timeout must be ten seconds")
    check(not any(os.environ.get(k) for k in ("MLFLOW_ACTIVE_MODEL_ID", "_MLFLOW_ACTIVE_MODEL_ID")),
            "active model environment is forbidden")
    uri = os.environ.get("MLFLOW_TRACKING_URI", "")
    check(private_endpoint(uri) and os.environ.get("MLFLOW_REGISTRY_URI") == uri,
            "matching private tracking and registry endpoints required")
    record("import_mlflow")
    mlflow = importer("mlflow")
    check(mlflow.__version__ == "3.13.0", "exact deployed MLflow 3.13.0 required")
    record("import_auth_client")
    auth = importer("mlflow.server.auth.client")
    record("import_sqlalchemy")
    importer("sqlalchemy")
    record("import_psycopg2")
    importer("psycopg2")
    record("active_model_state")
    check(mlflow.get_active_model_id() is None, "active in-process model is forbidden")
    record("runtime_endpoints")
    check(mlflow.get_tracking_uri() == uri and mlflow.get_registry_uri() == uri,
            "runtime endpoint differs from explicit environment")
    for cls, methods, label in ((mlflow.MlflowClient, TRACKING, "tracking"), (auth.AuthServiceClient, AUTH, "auth")):
        for name, names in methods.items():
            record("signature_" + label + "_" + name)
            require(set(names.split()) <= set(inspect.signature(getattr(cls, name)).parameters),
                    "required SDK signature unavailable")
    return {"schema_version": "mlflow_readiness_runtime_preflight_v1", "status": "verified",
            "mlflow_version": mlflow.__version__, "python_version": platform.python_version(),
            "required_imports_verified": True, "helper_signatures_verified": True,
            "http_timeout_seconds": 10, "http_retries": 0, "async_logging": False,
            "telemetry_disabled": True,
            "active_model_absent": True, "api_calls": 0, "credentials_read": False}


if __name__ == "__main__":
    progress = {"failed_check": "starting"}
    try:
        receipt = verify(record=lambda name: progress.update(failed_check=name))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__, **progress}))
        raise SystemExit(1) from None
    print(json.dumps(receipt, sort_keys=True))
