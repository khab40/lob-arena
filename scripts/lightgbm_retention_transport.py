"""Bounded GET-only transport; never imports a model runtime."""

import base64
import hashlib
import json
import os
import signal
from contextlib import contextmanager
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from lightgbm_retention_contract import decode, relative, require

S3_ENDPOINT = "https://storage.eu-north1.nebius.cloud"


def fingerprint(stream, expected_size):
    digest, size = hashlib.sha256(), 0
    while chunk := stream.read(min(65536, expected_size + 1 - size)):
        size += len(chunk)
        require(size <= expected_size, "response exceeds expected size")
        digest.update(chunk)
    return {"sha256": digest.hexdigest(), "size_bytes": size}


def error_code(exc):
    # Never emit exception messages, URLs, response bodies or credentials.
    if isinstance(exc, HTTPError):
        return "HTTP_" + str(exc.code)
    response = getattr(exc, "response", {})
    code = response.get("Error", {}).get("Code")
    if code in {"AccessDenied", "NoSuchKey", "InvalidAccessKeyId", "ExpiredToken"}:
        return code
    return type(exc).__name__


@contextmanager
def deadline(seconds):
    require(1 <= seconds <= 600, "audit deadline must be 1..600 seconds")
    def expired(*_):
        raise TimeoutError("audit deadline")
    previous = signal.signal(signal.SIGALRM, expired)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, previous)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class TrackingReader:
    def __init__(self, endpoint):
        parsed = urlsplit(endpoint)
        require(parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
                and parsed.port is not None and parsed.path in {"", "/"}
                and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment, "MLflow requires explicit loopback tunnel")
        self.endpoint = endpoint.rstrip("/")
        username = os.environ["MLFLOW_TRACKING_USERNAME"]
        password = os.environ["MLFLOW_TRACKING_PASSWORD"]
        require(bool(username) and bool(password), "missing tracking credentials")
        self.auth = "Basic " + base64.b64encode((username + ":" + password).encode()).decode()
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def get(self, route, query=None):
        url = self.endpoint + "/api/2.0/" + route
        if query:
            url += "?" + urlencode(query)
        return self.opener.open(Request(url, headers={"Authorization": self.auth}, method="GET"), timeout=10)

    def metadata(self, route, query):
        with self.get(route, query) as response:
            raw = response.read(4 * 1024**2 + 1)
        require(len(raw) <= 4 * 1024**2, "metadata response limit")
        return decode(raw)

    def artifact(self, root_uri, path, size):
        root = urlsplit(root_uri)
        require(root.scheme == "mlflow-artifacts" and not root.netloc
                and not root.query and not root.fragment, "unsupported artifact proxy root")
        route = relative(root.path.removeprefix("/")) + "/" + relative(path)
        with self.get("mlflow-artifacts/artifacts/" + quote(route, safe="/")) as response:
            return fingerprint(response, size)


class StorageReader:
    def __init__(self):
        import boto3
        from botocore.config import Config
        # Explicit injected credentials; no fallback to instance credentials/profile discovery.
        key, secret = os.environ["AWS_ACCESS_KEY_ID"], os.environ["AWS_SECRET_ACCESS_KEY"]
        require(bool(key) and bool(secret), "missing storage credentials")
        self.client = boto3.client(
            "s3", endpoint_url=S3_ENDPOINT, region_name="eu-north1",
            aws_access_key_id=key, aws_secret_access_key=secret,
            aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
            config=Config(connect_timeout=5, read_timeout=10, retries={"total_max_attempts": 1},
                          s3={"addressing_style": "path"}),
        )

    def object(self, obj):
        parsed = urlsplit(obj["uri"])
        result = self.client.get_object(Bucket=parsed.netloc, Key=parsed.path.removeprefix("/"))
        body = result["Body"]
        try:
            require(result["ContentLength"] == obj["size_bytes"], "remote object size mismatch")
            return fingerprint(body, obj["size_bytes"])
        finally:
            body.close()


def audit_storage(inv, reader):
    checked = []
    for obj in inv["result_objects"]:
        try:
            actual = reader.object(obj)
            require(actual == {k: obj[k] for k in ("sha256", "size_bytes")}, "remote hash mismatch")
        except TimeoutError:
            raise
        except Exception as exc:
            return {"verified": False, "objects": checked, "count": len(checked),
                    "failed_path": obj["path"], "error": error_code(exc)}
        checked.append({"path": obj["path"], **actual})
    return {"verified": True, "objects": checked, "count": len(checked)}


def audit_tracking(inv, reader):
    from lightgbm_retention_contract import tracking_mismatches
    run_id = inv["lineage"]["mlflow_run_id"]
    run = reader.metadata("mlflow/runs/get", {"run_id": run_id})["run"]
    experiment = reader.metadata("mlflow/experiments/get", {"experiment_id": run["info"]["experiment_id"]})
    require(experiment["experiment"]["name"] == "lob-arena/lightgbm-development", "wrong experiment")
    failures = tracking_mismatches(inv, run)
    if failures:
        return {"verified": False, "mismatches": failures, "artifacts_checked": 0}
    files, token, tokens = {}, None, set()
    for _ in range(10):
        query = {"run_id": run_id, "path": "governed"}
        if token:
            query["page_token"] = token
        page = reader.metadata("mlflow/artifacts/list", query)
        for item in page.get("files", []):
            require(item["path"] not in files, "duplicate artifact listing")
            files[item["path"]] = item
        token = page.get("next_page_token")
        if not token:
            break
        require(token not in tokens, "repeated pagination token")
        tokens.add(token)
    require(not token, "artifact pagination limit")
    objects = {x["path"]: x for x in inv["result_objects"]}
    checked = []
    for role in ("training_manifest", "calibration_manifest", "validation_metrics", "feature_importance",
                 "reliability_bins", "reliability_diagram", "model"):
        obj = objects[inv["artifact_roles"][role]]
        path = "governed/" + obj["path"].rsplit("/", 1)[1]
        item = files.get(path, {})
        require(not item.get("is_dir", True) and int(item.get("file_size", -1)) == obj["size_bytes"],
                "missing artifact or wrong size")
        actual = reader.artifact(run["info"]["artifact_uri"], path, obj["size_bytes"])
        require(actual == {k: obj[k] for k in ("sha256", "size_bytes")}, "MLflow artifact hash mismatch")
        checked.append({"path": path, **actual})
    return {"verified": True, "artifacts": checked, "artifacts_checked": len(checked),
            "dataset_inputs_checked": len(inv["lineage"]["feature_inputs"]),
            "extra_governed_artifacts": sorted(set(files) - {x["path"] for x in checked}),
            "metadata_response_sha256": hashlib.sha256(json.dumps(run, sort_keys=True).encode()).hexdigest()}
