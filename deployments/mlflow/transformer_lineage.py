"""One original tracking identity; injected authenticated adapters, no network client imports.

Tracking adapters expose MLflow 3.13 get/search/create/log/set signatures and run
objects. log_inputs accepts normalized metadata dictionaries: a scoped guest
adapter converts these to DatasetInput entities. Artifact adapters expose exact
list/read/write operations through the authenticated same-server proxy. Identity,
permissions and transport controls must be verified by that guest adapter; inert
protocol verification alone never establishes a live application receipt.
"""
from contextlib import contextmanager
import fcntl
import math
import os
from pathlib import Path
import stat
import tempfile
import time

from .transformer_lineage_plan import EXPERIMENT, RESERVATION, RUN, canonical, record, require, sha

CONTROLS = {"http_retries": 0, "http_timeout_seconds": 10, "async_logging": False,
            "telemetry_disabled": True, "active_model_absent": True}


class Budget:
    def __init__(self, expires):
        require(type(expires) in (int, float) and time.monotonic() < expires <= time.monotonic() + 900,
                "finite metadata deadline required")
        self.expires, self.calls = expires, 0

    def call(self, function, *args, **kwargs):
        if time.monotonic() >= self.expires or self.calls >= 2000:
            raise TimeoutError("metadata request/deadline bound exhausted")
        self.calls += 1
        result = function(*args, **kwargs)
        self.ensure()
        return result

    def ensure(self):
        if time.monotonic() >= self.expires or self.calls > 2000:
            raise TimeoutError("metadata request/deadline bound exhausted")


def persist(path, value):
    persist_bytes(path, canonical(value))


def persist_bytes(path, raw):
    require(not path.is_symlink(), "journal symlink")
    if path.exists():
        require(path.is_file() and path.stat().st_size == len(raw) and path.read_bytes() == raw, "journal conflict")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".intent-", delete=False) as stream:
        temporary = Path(stream.name)
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(directory, plan, plan_sha):
    root = Path(directory).absolute()
    require(root.is_dir() and not any(p.is_symlink() for p in (root, *root.parents))
            and root.resolve() == root and stat.S_IMODE(root.stat().st_mode) == 0o700
            and root.stat().st_uid == os.geteuid(), "existing private canonical journal required")
    descriptor = os.open(root / "LOCK", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        persist(root / "binding.json", {"reservation": plan["tags"][RESERVATION], "plan_sha256": plan_sha})
        persist(root / "plan.json", plan)
        yield root
    finally:
        os.close(descriptor)


def dataset_identity(entity):
    if isinstance(entity, dict):
        value = record(canonical(entity))
    else:
        tags = {}
        for item in entity.tags:
            require(item.key not in tags, "duplicate dataset input tag")
            tags[item.key] = item.value
        value = {"dataset": entity.dataset.to_dictionary(), "tags": tags}
        if isinstance(value["dataset"]["source"], str):
            value["dataset"]["source"] = record(value["dataset"]["source"])
    require(set(value) == {"dataset", "tags"} and set(value["dataset"])
            == {"name", "digest", "source_type", "source", "schema", "profile"}, "dataset shape differs")
    return canonical(value).decode()


def metric_identity(item):
    value = item if isinstance(item, dict) else {key: getattr(item, key) for key in ("key", "value", "step", "timestamp")}
    require(set(value) == {"key", "value", "step", "timestamp"}
            and type(value["value"]) in (int, float) and math.isfinite(value["value"])
            and type(value["step"]) is int and type(value["timestamp"]) is int, "metric history shape differs")
    return canonical({**value, "value": float(value["value"])}).decode()


def _read(client, artifacts, run_id, experiment_id, plan, budget, *, complete=False, retention=None):
    run = budget.call(client.get_run, run_id)
    require(str(run.info.run_id) == run_id and str(run.info.experiment_id) == experiment_id
            and run.info.lifecycle_stage == "active"
            and run.info.status in {"RUNNING", "FINISHED"} and run.info.start_time == plan["start_time"]
            and (run.info.end_time is None if run.info.status == "RUNNING" else run.info.end_time == plan["end_time"]),
            "original run lifecycle/time differs")
    tags = {key: value for key, value in run.data.tags.items() if not key.startswith("mlflow.")}
    require(run.data.tags.get("mlflow.runName") == RUN
            and not any(key not in plan["tags"] or value != plan["tags"][key] for key, value in tags.items())
            and not any(key not in plan["params"] or value != plan["params"][key]
                        for key, value in run.data.params.items()), "conflicting original params/tags")
    expected_metrics = {metric_identity(item): item for item in plan["metrics"]}
    observed_metrics = {}
    for key, latest in run.data.metrics.items():
        history = budget.call(client.get_metric_history, run_id, key)
        normalized = [metric_identity(item) for item in history]
        require(len(normalized) == len(set(normalized)) and normalized
                and all(item in expected_metrics and record(item)["key"] == key for item in normalized),
                "conflicting or duplicate metric histories")
        last = max((record(item) for item in normalized), key=lambda row: (row["step"], row["timestamp"]))
        require(type(latest) in (int, float) and math.isfinite(latest) and latest == last["value"],
                "metric latest/history differs")
        observed_metrics.update({item: expected_metrics[item] for item in normalized})
    expected_datasets = {dataset_identity(item): item for item in plan["datasets"]}
    inputs = getattr(getattr(run, "inputs", None), "dataset_inputs", [])
    datasets = [dataset_identity(item) for item in inputs]
    require(len(datasets) == len(set(datasets)) and not set(datasets) - expected_datasets.keys(),
            "conflicting or duplicate dataset inputs")
    paths = budget.call(artifacts.list, run_id)
    require(isinstance(paths, (list, tuple)) and len(paths) == len(set(paths))
            and not set(paths) - plan["artifacts"].keys(), "unexpected or duplicate metadata artifacts")
    observed_artifacts = {}
    for path in sorted(paths):
        expected = plan["artifacts"][path]
        raw = budget.call(artifacts.read, run_id, path, expected["size_bytes"])
        require(type(raw) is bytes and len(raw) == expected["size_bytes"] and sha(raw) == expected["sha256"],
                "metadata artifact readback differs")
        if retention is not None:
            persist_bytes(retention / path, raw)
        observed_artifacts[path] = expected
    missing = {"params": sorted(plan["params"].keys() - run.data.params.keys()),
               "tags": sorted(plan["tags"].keys() - tags.keys()),
               "metrics": sorted(expected_metrics.keys() - observed_metrics.keys()),
               "datasets": sorted(expected_datasets.keys() - set(datasets)),
               "artifacts": sorted(plan["artifacts"].keys() - observed_artifacts.keys())}
    if complete or run.info.status == "FINISHED":
        require(not any(missing.values()), "original tracking record incomplete")
    state = {"run_id": run_id, "experiment_id": str(run.info.experiment_id),
             "status": run.info.status, "start_time": run.info.start_time,
             "end_time": run.info.end_time, "tags": tags, "params": dict(run.data.params),
             "metrics": sorted(observed_metrics), "datasets": sorted(datasets), "artifacts": observed_artifacts}
    return state, missing


def _mutation(root, budget, function, operation, *args, **kwargs):
    intent = root / ("write-" + sha(canonical(operation)) + ".json")
    require(not intent.exists() and not intent.is_symlink(), "unresolved write intent; readback required, never retry")
    persist(intent, operation)
    return budget.call(function, *args, **kwargs)


