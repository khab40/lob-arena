"""One authorized live metadata attempt; overall readiness needs external checks."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import threading
from urllib.parse import urlsplit

from deployments.mlflow.readiness_permissions import MODEL, apply_permissions, inspect_permissions
from deployments.mlflow.readiness_registry import MANIFEST_SHA256, register_baseline
from deployments.mlflow.readiness_tracking import EXPERIMENT, PAYLOAD, persist, reserve_pair, verify_tracking
from scripts.mlflow_readiness_preflight import verify

URI = "http://10.4.0.54:5500"
LOCK = threading.RLock()


@contextmanager
def identity(credentials):
    if threading.current_thread() is not threading.main_thread():
        raise ValueError("identity-scoped SDK calls must be synchronous on the main thread")
    with LOCK:
        names = ("MLFLOW_TRACKING_USERNAME", "MLFLOW_TRACKING_PASSWORD")
        before = {key: os.environ.get(key) for key in names}
        os.environ.update(dict(zip(names, credentials)))
        try:
            yield
        finally:
            for key, value in before.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


class ScopedClient:
    def __init__(self, factory, credentials):
        self.credentials = credentials
        with identity(credentials):
            self.client = factory()

    def __getattr__(self, name):
        def call(*args, **kwargs):
            with identity(self.credentials):
                return getattr(self.client, name)(*args, **kwargs)
        return call


def clients():
    from mlflow import MlflowClient
    from mlflow.server.auth.client import AuthServiceClient

    if (os.environ.get("MLFLOW_TRACKING_URI") != URI
            or os.environ.get("MLFLOW_REGISTRY_URI") != URI
            or any(value for key, value in os.environ.items()
                   if key.startswith("AWS_") or key == "MLFLOW_TRACKING_TOKEN")):
        raise ValueError("exact private endpoint and application-only credentials required")
    credentials = {}
    for role, expected in (("ADMIN", "admin"), ("WRITER", "governed-writer"), ("EXPORTER", "prometheus")):
        pair = tuple(os.environ.get(f"MLFLOW_{role}_{part}", "") for part in ("USERNAME", "PASSWORD"))
        if pair[0] != expected or not pair[1]:
            raise ValueError("existing named application credentials required")
        credentials[role] = pair
    def factory():
        return MlflowClient(tracking_uri=URI, registry_uri=URI)
    admin, writer, exporter = [ScopedClient(factory, credentials[role])
                               for role in ("ADMIN", "WRITER", "EXPORTER")]
    auth = ScopedClient(lambda: AuthServiceClient(URI), credentials["ADMIN"])
    return admin, auth, writer, exporter, credentials["WRITER"]


class Artifacts:
    def __init__(self, client, credentials, retained_directory):
        import requests
        self.client, self.credentials = client, credentials
        self.retained = Path(retained_directory)
        if not self.retained.is_absolute() or self.retained.parent.resolve(strict=True) != self.retained.parent:
            raise ValueError("canonical artifact retention directory required")
        self._private_directory(self.retained)
        self.session = requests.Session()
        self.session.trust_env = False

    @staticmethod
    def _private_directory(path):
        path.mkdir(mode=0o700, exist_ok=True)
        if (path.resolve(strict=True) != path or not path.is_dir()
                or stat.S_IMODE(path.stat().st_mode) != 0o700 or path.stat().st_uid != os.geteuid()):
            raise ValueError("private artifact retention directory required")
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    def destination(self, run_id, path):
        if not re.fullmatch(r"[a-f0-9]{32}", run_id) or not re.fullmatch(r"[a-z-]+/[a-z0-9.-]+", path):
            raise ValueError("exact artifact identity required")
        if path.split("/")[1] in {".", ".."}:
            raise ValueError("artifact traversal rejected")
        return self.retained / run_id / path

    def url(self, run_id, path):
        self.destination(run_id, path)
        uri = urlsplit(self.client.get_run(run_id).info.artifact_uri)
        expected = rf"/[0-9]+/{run_id}/artifacts"
        if (uri.scheme != "mlflow-artifacts" or uri.netloc or uri.query or uri.fragment
                or not re.fullmatch(expected, uri.path)):
            raise ValueError("same-server artifact proxy required")
        return URI + "/api/2.0/mlflow-artifacts/artifacts" + uri.path + "/" + path

    def retain(self, destination, raw):
        self._private_directory(destination.parent.parent)
        self._private_directory(destination.parent)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=".download-", delete=False) as stream:
                temporary = Path(stream.name)
                os.fchmod(stream.fileno(), 0o600)
                if stream.write(raw) != len(raw):
                    raise OSError("incomplete retained artifact")
                stream.flush()
                os.fsync(stream.fileno())
            os.link(temporary, destination)  # Atomic and exclusive; never replace evidence.
            descriptor = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        finally:
            if temporary is not None:
                temporary.unlink()

    def download(self, run_id, path, limit):
        if type(limit) is not int or not 0 < limit <= 1024 * 1024:
            raise ValueError("artifact byte bound required")
        destination = self.destination(run_id, path)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("artifact already retained; no repeated transfer")
        with self.session.get(self.url(run_id, path), auth=self.credentials, timeout=10,
                              stream=True, allow_redirects=False,
                              headers={"Accept-Encoding": "identity"}) as response:
            if response.status_code != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
                raise ValueError("artifact response rejected")
            if "Content-Length" in response.headers and int(response.headers["Content-Length"]) > limit:
                raise ValueError("artifact exceeds byte bound")
            content = response.raw.read(limit + 1, decode_content=False)
            if len(content) > limit:
                raise ValueError("artifact exceeds byte bound")
            self.retain(destination, content)
            return content

    def upload(self, run_id, path, raw):
        if path != "readiness/probe.txt" or raw != PAYLOAD:
            raise ValueError("only the inert readiness artifact may be uploaded")
        with self.session.put(self.url(run_id, path), auth=self.credentials, timeout=10,
                              data=raw, stream=True, allow_redirects=False) as response:
            if response.status_code not in {200, 201, 204}:
                raise ValueError("artifact upload rejected")


def require_empty_model_namespace(admin, model):
    if model.name != MODEL or model.aliases:
        raise ValueError("existing model namespace conflicts")
    versions = admin.search_model_versions(f"name = '{MODEL}'", max_results=1)
    if versions or getattr(versions, "token", None):
        raise ValueError("model namespace has versions; readiness requires an empty namespace")


def namespaces(admin, journal):
    experiment = admin.get_experiment_by_name(EXPERIMENT)
    try:
        model = admin.get_registered_model(MODEL)
    except Exception as exc:
        if getattr(exc, "error_code", None) != "RESOURCE_DOES_NOT_EXIST":
            raise
        model = None
    if experiment is not None and (experiment.name != EXPERIMENT or experiment.lifecycle_stage != "active"):
        raise ValueError("existing experiment conflicts")
    if model is not None:
        require_empty_model_namespace(admin, model)
    if experiment is None:
        persist(journal / "experiment-intent.json", {"name": EXPERIMENT})
        admin.create_experiment(EXPERIMENT)
        experiment = admin.get_experiment_by_name(EXPERIMENT)
    if model is None:
        persist(journal / "model-intent.json", {"name": MODEL})
        admin.create_registered_model(MODEL)
        model = admin.get_registered_model(MODEL)
        require_empty_model_namespace(admin, model)
    if (experiment is None or experiment.name != EXPERIMENT or experiment.lifecycle_stage != "active"
            or model.name != MODEL or model.aliases):
        raise ValueError("namespace readback differs")
    return str(experiment.experiment_id)


def execute(input_dir, journal, proposal_sha256, source_commit, *, preflight=verify, make_clients=clients):
    runtime = preflight()  # Must precede credentials and client construction.
    if not re.fullmatch(r"[a-f0-9]{64}", proposal_sha256) or not re.fullmatch(r"[a-f0-9]{40}", source_commit):
        raise ValueError("exact execution binding required")
    journal = Path(journal)
    if (not journal.is_absolute() or journal.resolve(strict=True) != journal or not journal.is_dir()
            or stat.S_IMODE(journal.stat().st_mode) != 0o700 or journal.stat().st_uid != os.geteuid()):
        raise ValueError("pre-existing canonical private journal required")
    if (journal / "live-intent.json").exists() or (journal / "live-intent.json").is_symlink():
        raise FileExistsError("live attempt already consumed")
    raw = []
    for name in ("manifest.json", "inventory.json", "source-proof.json"):
        path = Path(input_dir) / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError("bounded regular lineage inputs required")
        raw.append(path.read_bytes())
    manifest = json.loads(raw[0])
    if (hashlib.sha256(raw[0]).hexdigest() != MANIFEST_SHA256
            or hashlib.sha256(raw[1]).hexdigest() != manifest["inventory_sha256"]
            or hashlib.sha256(raw[2]).hexdigest() != manifest["dataset_source_proof_sha256"]):
        raise ValueError("lineage input digests differ")
    binding = {"proposal_sha256": proposal_sha256, "source_commit": source_commit,
               "purpose": "mlflow-readiness-20261002"}
    admin, auth, writer, exporter, credentials = make_clients()
    if auth.get_user("admin").is_admin is not True:
        raise ValueError("existing admin identity required")
    descriptor = os.open(journal / "live-intent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump(binding, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(journal, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    experiment_id = namespaces(admin, journal)
    permissions = apply_permissions(auth, inspect_permissions(auth, experiment_id))
    artifacts = Artifacts(writer, credentials, journal / "artifacts")
    try:
        registry = register_baseline(writer, artifacts.download, *raw, journal / "registry")
        runs = reserve_pair(writer, journal, binding)
        tracking = verify_tracking(writer, exporter, runs, artifacts.upload, artifacts.download, journal)
    finally:
        artifacts.session.close()
    receipt = {"schema_version": "mlflow_live_readiness_phase_v1", "binding": binding,
               "runtime": runtime, "permissions": permissions, "registry": registry, "tracking": tracking,
               "overall_readiness_verified": False, "external_checks_required": [
                   "private_sql_preservation", "restored_application_readwrite", "vm_stopped"]}
    persist(journal / "live-receipt.json", receipt)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    for name in ("input-dir", "journal", "proposal-sha256", "source-commit"):
        parser.add_argument("--" + name, required=True)
    try:
        execute(**vars(parser.parse_args()))
    except Exception as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}))
        raise SystemExit(1) from None
    print(json.dumps({"status": "live_phase_verified", "overall_readiness_verified": False}))


if __name__ == "__main__":
    main()
