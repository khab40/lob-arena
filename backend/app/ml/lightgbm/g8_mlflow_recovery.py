"""One-ledger MLflow reservation and log-only recovery (not execution authority).

The reviewed caller must retain the ledger on durable, exclusively locked storage
and provide the same binding on recovery. Losing that ledger is a hard stop, not
permission to create another run. No final data loading or scoring happens here.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.ml.dataset_lineage import GovernedDatasetInput, log_dataset_inputs

EXPERIMENT = "lob-arena/governed-evaluation"
RESERVATION_TAG = "g8.reservation_sha256"
PLAN_TAG = "g8.logging_plan_sha256"
SHA = r"^[0-9a-f]{64}$"


class ReservationSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["g8_mlflow_reservation_v1"] = "g8_mlflow_reservation_v1"
    execution_package_sha256: str = Field(pattern=SHA)
    request_sha256: str = Field(pattern=SHA)
    candidate_sha256: str = Field(pattern=SHA)
    evaluation_profile_sha256: str = Field(pattern=SHA)
    request_run_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,127}$")
    tracking_uri: str

    @field_validator("tracking_uri")
    @classmethod
    def restricted_uri(cls, value):
        parsed = urlsplit(value)
        if value == "http://10.4.0.54:5500":
            return value
        if (parsed.scheme == "file" and not parsed.netloc and parsed.path.startswith("/")
                and not parsed.query and not parsed.fragment):
            return value  # Offline engineering tests only; never production evidence.
        raise ValueError("reservation requires the governed private URI or an offline file store")

    def identity(self) -> str:
        return _sha(_canonical(self.model_dump(mode="json")))

    def tags(self) -> dict[str, str]:
        return {
            RESERVATION_TAG: self.identity(),
            **{f"g8.{key}": str(value) for key, value in self.model_dump(mode="json").items()},
        }


@dataclass(frozen=True)
class ResumeTarget:
    ledger_root: Path
    spec: ReservationSpec


def _canonical(value) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def _sha(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _client(spec):
    from mlflow import MlflowClient

    return MlflowClient(tracking_uri=spec.tracking_uri)


def _no_http_retries():
    from mlflow.environment_variables import MLFLOW_HTTP_REQUEST_MAX_RETRIES

    # SDK create-run POST retries can create duplicates after a lost response.
    # Do not silently mutate a process-global SDK setting in a library function.
    if MLFLOW_HTTP_REQUEST_MAX_RETRIES.get() != 0:
        raise ValueError("G8 recovery requires MLFLOW_HTTP_REQUEST_MAX_RETRIES=0")


def _persist(path: Path, value):
    content = _canonical(value)
    if path.is_symlink():
        raise ValueError("MLflow ledger record must not be a symlink")
    if path.exists():
        if path.is_symlink() or path.read_bytes() != content:
            raise ValueError("immutable MLflow ledger record differs: " + path.name)
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".pending-", delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.replace(temporary, path)  # Caller holds the ledger's exclusive lock.
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _locked(target: ResumeTarget):
    root = target.ledger_root.absolute()
    if any(path.is_symlink() for path in (root, *root.parents)):
        raise ValueError("MLflow ledger must not traverse symlinks")
    # Parent is prepared by the reviewed caller; don't create an implicit new
    # recovery root if the durable mount disappeared.
    if not root.is_dir():
        raise ValueError("MLflow ledger root must already exist")
    ledger = root / target.spec.identity()
    ledger.mkdir(mode=0o700, exist_ok=True)
    if ledger.is_symlink():
        raise ValueError("MLflow ledger must not be a symlink")
    root_descriptor = os.open(root, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(root_descriptor)
    finally:
        os.close(root_descriptor)
    descriptor = os.open(ledger / "LOCK", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        _persist(ledger / "spec.json", target.spec.model_dump(mode="json"))
        yield ledger
    finally:
        os.close(descriptor)


def _find(client, spec):
    from mlflow.entities import ViewType

    experiment = client.get_experiment_by_name(EXPERIMENT)
    if experiment is None or experiment.lifecycle_stage != "active":
        raise ValueError("governed MLflow experiment must already exist and be active")
    runs = client.search_runs(
        [experiment.experiment_id],
        filter_string=f"tags.`{RESERVATION_TAG}` = '{spec.identity()}'",
        run_view_type=ViewType.ALL, max_results=2,
    )
    if len(runs) > 1 or getattr(runs, "token", None):
        raise ValueError("ambiguous MLflow reservation: multiple runs")
    if runs:
        run = runs[0]
        if (run.info.lifecycle_stage != "active" or run.info.status not in {"RUNNING", "FINISHED"}
                or str(run.info.experiment_id) != str(experiment.experiment_id)
                or any(run.data.tags.get(key) != value for key, value in spec.tags().items())):
            raise ValueError("MLflow reservation identity, lifecycle or status differs")
    return experiment, runs[0] if runs else None


def reserve_run(target: ResumeTarget) -> str:
    """Reserve before scoring; an ambiguous creation is reconciled by search only.

    This is *not* a scoring permission or a scoring-once guard. After creation was
    attempted, zero matches is unresolved and never triggers another create POST.
    """
    _no_http_retries()
    with _locked(target) as ledger:
        client = _client(target.spec)
        experiment, run = _find(client, target.spec)
        intent = ledger / "create-intent.json"
        recorded = ledger / "run.json"
        if run is None:
            if intent.exists() or recorded.exists():
                raise ValueError("unresolved MLflow creation; refusing another create-run request")
            _persist(intent, {"reservation_sha256": target.spec.identity()})
            run = client.create_run(experiment.experiment_id, tags=target.spec.tags(),
                                    run_name=target.spec.request_run_id)
            # Reconcile server state even when the create response was received.
            _, found = _find(client, target.spec)
            if found is None or found.info.run_id != run.info.run_id:
                raise ValueError("MLflow creation not uniquely visible; preserve ledger and reconcile")
            run = found
        _persist(intent, {"reservation_sha256": target.spec.identity()})
        _persist(recorded, {"run_id": run.info.run_id, "reservation_sha256": target.spec.identity()})
        return str(run.info.run_id)


def _dataset_entities(inputs):
    import mlflow
    from mlflow.entities import Dataset, DatasetInput, InputTag

    entities = []

    class Collector:
        data = mlflow.data

        @staticmethod
        def log_input(dataset, context, tags):
            entities.append(DatasetInput(
                Dataset(**dataset.to_dict()),
                [InputTag(key, value) for key, value in (tags | {"mlflow.data.context": context}).items()],
            ))

    log_dataset_inputs(Collector, inputs)
    return entities


def _dataset_identity(entity):
    value = entity.to_dictionary()
    if len(value["tags"]) != len(entity.tags):
        raise ValueError("duplicate MLflow dataset input tags")
    value["dataset"]["source"] = json.loads(value["dataset"]["source"])
    return _canonical(value).decode()


def _artifact_paths(client, run_id, path=""):
    found = []
    for item in client.list_artifacts(run_id, path):
        relative = PurePosixPath(item.path)
        if (relative.is_absolute() or ".." in relative.parts or len(relative.parts) > 2
                or relative.as_posix() != item.path):
            raise ValueError("unexpected MLflow artifact path")
        if item.is_dir:
            if item.path not in {"governed", "governed-evaluation"}:
                raise ValueError("unexpected MLflow artifact directory")
            found.extend(_artifact_paths(client, run_id, item.path))
        else:
            found.append(item.path)
    if len(found) != len(set(found)):
        raise ValueError("duplicate MLflow artifact paths")
    return set(found)


def _read_state(client, run_id, tags, metrics, datasets, artifacts, *, complete=False):
    run = client.get_run(run_id)
    if run.info.lifecycle_stage != "active" or run.info.status not in {"RUNNING", "FINISHED"}:
        raise ValueError("MLflow run is deleted or has an unsupported terminal status")
    if run.data.params:
        raise ValueError("unexpected MLflow evaluation parameters")
    present_tags = {key: value for key, value in run.data.tags.items() if not key.startswith("mlflow.")}
    if any(key not in tags or tags[key] != value for key, value in present_tags.items()):
        raise ValueError("conflicting MLflow evaluation tags")
    if any(key not in metrics or metrics[key] != value for key, value in run.data.metrics.items()):
        raise ValueError("conflicting MLflow evaluation metrics")
    for key in run.data.metrics:
        history = client.get_metric_history(run_id, key)
        if len(history) != 1 or history[0].step != 0 or history[0].value != metrics[key]:
            raise ValueError("MLflow metric history is not one immutable evaluation value")
    observed_datasets = [_dataset_identity(item) for item in run.inputs.dataset_inputs]
    if len(observed_datasets) != len(set(observed_datasets)) or set(observed_datasets) - datasets.keys():
        raise ValueError("conflicting or duplicate MLflow dataset lineage")
    present_artifacts = _artifact_paths(client, run_id)
    if present_artifacts - artifacts.keys():
        raise ValueError("unexpected MLflow evaluation artifact")
    for relative in present_artifacts:
        with tempfile.TemporaryDirectory() as temporary:
            downloaded = Path(client.download_artifacts(run_id, relative, temporary))
            if _sha(downloaded.read_bytes()) != artifacts[relative][1]:
                raise ValueError("conflicting MLflow artifact bytes: " + relative)
    missing = (
        tags.keys() - present_tags.keys(), metrics.keys() - run.data.metrics.keys(),
        datasets.keys() - set(observed_datasets), artifacts.keys() - present_artifacts,
    )
    if (complete or run.info.status == "FINISHED") and any(missing):
        raise ValueError("MLflow evaluation is incomplete")
    return run, missing


def resume_verified_logging(
    target: ResumeTarget, *, tags: dict[str, str], metrics: dict[str, float],
    inputs: tuple[GovernedDatasetInput, ...], artifacts: dict[str, tuple[Path, str]],
) -> str:
    """Internal logger sink: caller MUST independently verify the complete C4 release.

    No create-run, start-run, training, scoring or final-input APIs are called.
    Immutable plan and remote readback make partial writes repeatable, not mutable.
    """
    _no_http_retries()
    if (tags.get("candidate_hash") != target.spec.candidate_sha256
            or tags.get("evaluation_profile_sha256") != target.spec.evaluation_profile_sha256
            or tags.get("evaluation_contract") != "g8_c4_supervised_observations_v1"
            or tags.get("same_observations_verified") != "true"):
        raise ValueError("verified C4 evidence differs from MLflow reservation")
    if any(key.startswith(("g8.", "mlflow.")) for key in tags):
        raise ValueError("evaluation tags cannot replace reserved identity tags")
    if any(not math.isfinite(value) for value in metrics.values()):
        raise ValueError("evaluation metrics must be finite")
    datasets = {_dataset_identity(entity): entity for entity in _dataset_entities(inputs)}
    if len(datasets) != len(inputs):
        raise ValueError("duplicate expected dataset lineage")
    if len(artifacts) != 4:
        raise ValueError("C4 recovery requires exactly four governed artifacts")
    tags = tags | target.spec.tags()
    plan = {
        "tags": tags, "metrics": metrics, "datasets": sorted(datasets),
        "artifacts": {key: digest for key, (_, digest) in artifacts.items()},
    }
    plan_sha = _sha(_canonical(plan))
    tags = tags | {PLAN_TAG: plan_sha}
    with _locked(target) as ledger, tempfile.TemporaryDirectory() as temporary:
        recorded = ledger / "run.json"
        if not recorded.is_file() or recorded.is_symlink():
            raise ValueError("no durable MLflow reservation; reserve before scoring")
        client = _client(target.spec)
        _, run = _find(client, target.spec)
        if run is None:
            raise ValueError("reserved MLflow run is not visible; no creation permitted")
        run_id = str(run.info.run_id)
        _persist(recorded, {"run_id": run_id, "reservation_sha256": target.spec.identity()})
        _persist(ledger / "logging-plan.json", plan)
        snapshots = {}
        for relative, (source, expected_sha) in artifacts.items():
            path = PurePosixPath(relative)
            if (len(path.parts) != 2 or path.parts[0] not in {"governed", "governed-evaluation"}
                    or path.as_posix() != relative or ".." in path.parts):
                raise ValueError("invalid governed artifact destination")
            content = source.read_bytes()
            if _sha(content) != expected_sha:
                raise ValueError("verified artifact changed before MLflow snapshot")
            snapshot = Path(temporary) / relative
            snapshot.parent.mkdir(exist_ok=True)
            snapshot.write_bytes(content)
            snapshot.chmod(0o400)
            snapshots[relative] = (snapshot, expected_sha)
        run, missing = _read_state(client, run_id, tags, metrics, datasets, snapshots)
        if run.info.status != "FINISHED":
            from mlflow.entities import Metric, RunTag

            tag_keys, metric_keys, dataset_keys, artifact_keys = missing
            # Synchronous calls only. A lost response is reconciled on the next
            # invocation by readback; never blindly replay a write in this one.
            for key in sorted(tag_keys):
                client.log_batch(run_id, tags=[RunTag(key, tags[key])], synchronous=True)
            for key in sorted(metric_keys):
                client.log_batch(run_id, metrics=[Metric(key, metrics[key], int(time.time() * 1000), 0)],
                                 synchronous=True)
            for key in sorted(dataset_keys):
                client.log_inputs(run_id, datasets=[datasets[key]])
            for relative in sorted(artifact_keys):
                client.log_artifact(run_id, str(snapshots[relative][0]),
                                    artifact_path=PurePosixPath(relative).parent.as_posix())
            _read_state(client, run_id, tags, metrics, datasets, snapshots, complete=True)
            client.set_terminated(run_id, status="FINISHED")
        final, _ = _read_state(client, run_id, tags, metrics, datasets, snapshots, complete=True)
        if final.info.status != "FINISHED":
            raise ValueError("MLflow completion status not verified")
        _persist(ledger / "logging-complete.json", {
            "run_id": run_id, "reservation_sha256": target.spec.identity(),
            "logging_plan_sha256": plan_sha, "remote_state_verified": True,
            "tracking_scope": "offline" if target.spec.tracking_uri.startswith("file:") else "governed",
        })
        return run_id
