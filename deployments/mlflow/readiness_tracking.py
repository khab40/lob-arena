"""Metadata-only parent/child reservation and least-privilege tracking probe.

The caller supplies identity-scoped clients with HTTP retries disabled and a
pre-existing durable journal directory. These functions grant no execution authority.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

EXPERIMENT = "lob-arena/transformer-development"
RESERVATION = "readiness.reservation_sha256"
PAYLOAD = b"LOB Arena MLflow readiness; inert metadata only.\n"


def persist(path, value):
    """Durable publication; caller holds the directory lock."""
    raw = (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()
    if path.is_symlink():
        raise ValueError("journal symlink")
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError("journal conflict")
        return
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        tmp = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        os.link(tmp, path)
        descriptor = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        tmp.unlink(missing_ok=True)


def reserve_pair(client, directory, binding):
    """At most one create POST per slot, including after a lost response."""
    directory = Path(directory).absolute()
    if not directory.is_dir() or any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("pre-existing canonical durable journal required")
    if (set(binding) != {"proposal_sha256", "source_commit", "purpose"}
            or binding["purpose"] != "mlflow-readiness-20261002"
            or any(len(binding[k]) != n or any(c not in "0123456789abcdef" for c in binding[k])
                   for k, n in (("proposal_sha256", 64), ("source_commit", 40)))):
        raise ValueError("exact readiness binding required")
    descriptor = os.open(directory / "LOCK", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        persist(directory / "binding.json", binding)
        experiment = client.get_experiment_by_name(EXPERIMENT)
        if experiment is None or experiment.lifecycle_stage != "active":
            raise ValueError("active Transformer experiment required")
        ids = []
        for slot in ("parent", "child"):
            identity = hashlib.sha256(json.dumps([binding, slot], sort_keys=True).encode()).hexdigest()
            tags = {RESERVATION: identity, "readiness.slot": slot,
                    "readiness.purpose": binding["purpose"],
                    "readiness.proposal_sha256": binding["proposal_sha256"],
                    "readiness.source_commit": binding["source_commit"]}
            if ids:
                tags["mlflow.parentRunId"] = ids[0]
            intent = directory / (slot + "-intent.json")
            record = directory / (slot + "-run.json")
            runs = client.search_runs([experiment.experiment_id],
                filter_string=f"tags.`{RESERVATION}` = '{identity}'", run_view_type=3, max_results=2)
            if len(runs) > 1 or getattr(runs, "token", None):
                raise ValueError("ambiguous reservation")
            if not runs:
                if intent.exists() or record.exists():
                    raise ValueError("unresolved creation; never repeat POST")
                persist(intent, {"tags": tags})
                created = client.create_run(experiment.experiment_id, tags=tags,
                                            run_name="readiness-" + slot)
                runs = [client.get_run(created.info.run_id)]
            run = runs[0]
            if (str(run.info.experiment_id) != str(experiment.experiment_id)
                    or run.info.lifecycle_stage != "active"
                    or run.info.status not in {"RUNNING", "FINISHED"}
                    or any(run.data.tags.get(k) != v for k, v in tags.items())):
                raise ValueError("reservation identity differs")
            # A matching server run without local intent cannot be adopted.
            if not intent.exists():
                raise ValueError("reservation has no durable creation intent")
            persist(intent, {"tags": tags})
            persist(record, {"run_id": run.info.run_id, "reservation_sha256": identity})
            ids.append(run.info.run_id)
        return tuple(ids)
    finally:
        os.close(descriptor)


def verify_tracking(writer, exporter, run_ids, upload, download, directory):
    """Callbacks retain identity isolation and enforce transfer limits.

    upload(run_id, path, bytes); download(run_id, path, maximum_bytes) -> bytes.
    Exporter denial is attempted on the same child, never by creating another run.
    """
    directory = Path(directory).absolute()
    if not directory.is_dir() or any(p.is_symlink() for p in (directory, *directory.parents)):
        raise ValueError("pre-existing canonical durable journal required")
    # Exclusive creation is the one-attempt guard, including process death after
    # any POST. Subsequent invocations are read-only operator reconciliation.
    descriptor = os.open(directory / "probe-intent.json",
                         os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        json.dump({"run_ids": list(run_ids)}, stream)
        stream.flush()
        os.fsync(stream.fileno())
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    parent, child = run_ids
    before = writer.get_run(child)
    if before.data.tags.get("mlflow.parentRunId") != parent:
        raise ValueError("child lineage differs")
    if before.info.status != "RUNNING" or writer.get_run(parent).info.status != "RUNNING":
        raise ValueError("tracking probe requires running reservations")
    writer.log_param(child, "readiness_kind", "metadata-only", synchronous=True)
    writer.log_metric(child, "readiness_probe", 1.0, timestamp=1790899200000,
                      step=0, synchronous=True)
    path = "readiness/probe.txt"
    upload(child, path, PAYLOAD)
    if download(child, path, len(PAYLOAD)) != PAYLOAD:
        raise ValueError("artifact readback differs")
    observed = exporter.get_run(child)
    if (observed.info.run_id != child
            or observed.data.params.get("readiness_kind") != "metadata-only"
            or observed.data.metrics.get("readiness_probe") != 1.0
            or observed.data.tags.get("mlflow.parentRunId") != parent):
        raise ValueError("exporter readback differs")
    if "readiness.denied_write" in observed.data.tags:
        raise ValueError("denial probe tag already exists")
    try:
        exporter.set_tag(child, "readiness.denied_write", "must-not-persist", synchronous=True)
    except Exception as exc:
        if getattr(exc, "error_code", None) != "PERMISSION_DENIED":
            raise ValueError("exporter failure is not permission denial") from None
        response = getattr(exc, "get_http_status_code", lambda: None)()
        if response != 403:
            raise ValueError("exporter denial must be HTTP 403") from None
    else:
        raise ValueError("exporter unexpectedly wrote metadata")
    if "readiness.denied_write" in writer.get_run(child).data.tags:
        raise ValueError("denied tag persisted")
    for run_id in (child, parent):
        writer.set_terminated(run_id, status="FINISHED")
        if exporter.get_run(run_id).info.status != "FINISHED":
            raise ValueError("termination readback differs")
    return {"status": "verified", "parent_run_id": parent, "child_run_id": child,
            "artifact_bytes": len(PAYLOAD), "artifact_sha256": hashlib.sha256(PAYLOAD).hexdigest(),
            "exporter_write_denied": True, "model_workloads": 0}
