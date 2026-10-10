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


def reconcile(sealed, *, approved_plan_sha256, journal, writer, reader, writer_artifacts, reader_artifacts, expires):
    """Read/write only the sealed original record; no namespace, permission or model APIs.

    Adapters must disable retries and prove their authenticated named principal
    and exact experiment access. They are separate writer/reader sessions; do not
    supply a writer session as the independent reader. This function imports no
    SDK and its receipt is protocol evidence until used with reviewed live adapters.
    """
    plan, files = sealed.checked(approved_plan_sha256)
    require(writer is not reader and writer_artifacts is not reader_artifacts, "independent reader required")
    budget = Budget(expires)
    for client, identity in ((writer, "governed-writer"), (reader, "prometheus"),
                             (writer_artifacts, "governed-writer"), (reader_artifacts, "prometheus")):
        require(client.transport_controls == CONTROLS
                and budget.call(client.authenticated_identity) == identity, "scoped authenticated adapter required")
    with locked(journal, plan, approved_plan_sha256) as root:
        for identity in ("writer", "reader"):
            directory = root / (identity + "-artifacts")
            require(not directory.is_symlink(), "artifact custody path changed")
            directory.mkdir(mode=0o700, exist_ok=True)
            require(not (directory / "lineage").is_symlink(), "artifact custody path changed")
            (directory / "lineage").mkdir(mode=0o700, exist_ok=True)
            require(not directory.is_symlink() and not (directory / "lineage").is_symlink()
                    and directory.resolve() == directory and stat.S_IMODE(directory.stat().st_mode) == 0o700,
                    "artifact custody path changed")
        experiments = [budget.call(client.get_experiment_by_name, EXPERIMENT) for client in (writer, reader)]
        require(all(item is not None and item.lifecycle_stage == "active" for item in experiments)
                and str(experiments[0].experiment_id) == str(experiments[1].experiment_id),
                "active existing Transformer experiment required")
        experiment_id = str(experiments[0].experiment_id)
        budget.call(writer.require_permission, experiment_id, "EDIT")
        budget.call(reader.require_permission, experiment_id, "READ")
        runs = budget.call(writer.search_runs, [experiment_id],
            filter_string=f"tags.`{RESERVATION}` = '{plan['tags'][RESERVATION]}'", run_view_type=3, max_results=2)
        require(len(runs) <= 1 and not getattr(runs, "token", None), "ambiguous original run search")
        named = budget.call(writer.search_runs, [experiment_id],
            filter_string=f"tags.`mlflow.runName` = '{RUN}'", run_view_type=3, max_results=2)
        require(len(named) <= 1 and not getattr(named, "token", None), "ambiguous original named run search")
        require(not named or runs and named[0].info.run_id == runs[0].info.run_id,
                "existing original named record requires source-bound adoption; no replacement")
        require(not runs or named, "reserved run lacks exact original name")
        intent = root / "create-intent.json"
        if not runs:
            require(not intent.exists() and not (root / "run.json").exists(), "unresolved create; never recreate")
            persist(intent, {"reservation": plan["tags"][RESERVATION], "start_time": plan["start_time"]})
            run = budget.call(writer.create_run, experiment_id, start_time=plan["start_time"],
                              tags=plan["tags"], run_name=RUN)
            runs = budget.call(writer.search_runs, [experiment_id],
                filter_string=f"tags.`{RESERVATION}` = '{plan['tags'][RESERVATION]}'", run_view_type=3, max_results=2)
            require(len(runs) == 1 and not getattr(runs, "token", None)
                    and runs[0].info.run_id == run.info.run_id, "create response not uniquely visible")
        require(intent.is_file() and not intent.is_symlink(), "original run has no durable creation intent")
        run = runs[0]
        require(str(run.info.experiment_id) == experiment_id
                and run.data.tags.get(RESERVATION) == plan["tags"][RESERVATION], "original reservation differs")
        run_id = str(run.info.run_id)
        persist(root / "run.json", {"run_id": run_id, "reservation": plan["tags"][RESERVATION]})
        state, missing = _read(writer, writer_artifacts, run_id, experiment_id, plan, budget,
                               retention=root / "writer-artifacts")
        metrics = {metric_identity(item): item for item in plan["metrics"]}
        datasets = {dataset_identity(item): item for item in plan["datasets"]}
        for kind in ("params", "tags", "metrics", "datasets", "artifacts"):
            for key in missing[kind]:
                operation = {"plan_sha256": approved_plan_sha256, "run_id": run_id, "kind": kind, "key": key}
                if kind == "params":
                    _mutation(root, budget, writer.log_param, operation, run_id, key, plan[kind][key], synchronous=True)
                elif kind == "tags":
                    _mutation(root, budget, writer.set_tag, operation, run_id, key, plan[kind][key], synchronous=True)
                elif kind == "metrics":
                    item = metrics[key]
                    _mutation(root, budget, writer.log_metric, operation, run_id, item["key"], item["value"],
                              timestamp=item["timestamp"], step=item["step"], synchronous=True)
                elif kind == "datasets":
                    _mutation(root, budget, writer.log_inputs, operation, run_id, datasets=[datasets[key]])
                else:
                    _mutation(root, budget, writer_artifacts.write, operation, run_id, key, files[key])
        first, _ = _read(writer, writer_artifacts, run_id, experiment_id, plan, budget, complete=True,
                         retention=root / "writer-artifacts")
        independent, _ = _read(reader, reader_artifacts, run_id, experiment_id, plan, budget, complete=True,
                               retention=root / "reader-artifacts")
        require(canonical(first) == canonical(independent), "independent metadata readback differs")
        if state["status"] != "FINISHED":
            persist(root / "readback-before-finish.json", {"plan_sha256": approved_plan_sha256,
                    "metadata_sha256": sha(canonical(first)), "run_id": run_id,
                    "writer": first, "reader": independent})
            _mutation(root, budget, writer.set_terminated, {"plan_sha256": approved_plan_sha256,
                "run_id": run_id, "kind": "finish", "end_time": plan["end_time"]},
                run_id, status="FINISHED", end_time=plan["end_time"])
        final, _ = _read(writer, writer_artifacts, run_id, experiment_id, plan, budget, complete=True,
                         retention=root / "writer-artifacts")
        independent, _ = _read(reader, reader_artifacts, run_id, experiment_id, plan, budget, complete=True,
                               retention=root / "reader-artifacts")
        require(final["status"] == "FINISHED" and canonical(final) == canonical(independent),
                "independent completed readback differs")
        receipt = {"schema_version": "original_transformer_metadata_protocol_receipt_v1", "run_id": run_id,
                   "plan_sha256": approved_plan_sha256, "readback_sha256": sha(canonical(final)),
                   "writer_identity": "governed-writer", "reader_identity": "prometheus",
                   "live_application_acceptance": "requires reviewed live adapters and retained authenticated evidence",
                   "start_time": plan["start_time"], "end_time": plan["end_time"],
                   "counts": {key: len(plan[key]) for key in ("params", "tags", "metrics", "datasets", "artifacts")}}
        budget.ensure()
        persist(root / "writer-readback.json", final)
        persist(root / "reader-readback.json", independent)
        budget.ensure()
        persist(root / "complete.json", receipt)
        budget.ensure()
        return receipt
