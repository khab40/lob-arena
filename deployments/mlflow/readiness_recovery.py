"""Authenticated metadata probe for an isolated restored MLflow 3.13 database.

The caller must bind the image, backup and network-isolated restored database,
disable SDK HTTP retries, and retain an attempt marker before calling. This
helper neither creates containers nor proves their isolation. No artifact API,
model loading, historical mutation, password update or cleanup is performed.
"""
from __future__ import annotations

import hashlib
import json
import os
import re

RESTORED_URI = "http://mlflow-restored:5000"
FROZEN_RUN = "1bd94569914748db8bbde21b13e83d05"
EXPERIMENT = "lob-arena/restore-readiness-20261002-r1"
MODEL = "lob-arena-restore-readiness-20261002-r1"
USER = "restore-readiness-20261002-r1"
SOURCE = "file:///restore-readiness/inert-metadata-only"
STAMP = 1790899200000


def require(condition, message):
    if not condition:
        raise ValueError(message)


def snapshot(run):
    return {"run_id": run.info.run_id, "experiment_id": run.info.experiment_id,
            "status": run.info.status, "params": dict(run.data.params),
            "metrics": dict(run.data.metrics), "tags": dict(run.data.tags)}


def absent(read):
    try:
        read()
    except Exception as error:
        if getattr(error, "error_code", None) == "RESOURCE_DOES_NOT_EXIST":
            return
        raise
    raise ValueError("restoration probe already exists; no replacement or overwrite")


def active_model_id():
    from mlflow import get_active_model_id
    return get_active_model_id()


def verify_application(client, auth, baseline, *, admin_username, probe_password,
                       get_active_model=active_model_id):
    """Return redacted evidence; baseline maxima/snapshot come from restored SQL.

    Experiment/user IDs must exceed their pre-probe table maxima. Registry
    versions are per-model counters, not PostgreSQL sequences: only the new
    probe's 1 -> 2 counter is exercised; existing model counters are untouched.
    Exactly ten application mutations occur on success, with no retry here.
    """
    require(client.tracking_uri == RESTORED_URI and client._registry_uri == RESTORED_URI
            and auth.tracking_uri == RESTORED_URI, "restored endpoint binding required")
    require(os.environ.get("MLFLOW_HTTP_REQUEST_MAX_RETRIES") == "0",
            "disable SDK HTTP retries before constructing clients")
    require(not any(os.environ.get(key) for key in ("MLFLOW_ACTIVE_MODEL_ID", "_MLFLOW_ACTIVE_MODEL_ID"))
            and get_active_model() is None, "active model state is forbidden")
    require(set(baseline) == {"backup_sha256", "experiment_max_id", "user_max_id",
                             "frozen_run"}, "invalid restored baseline fields")
    require(re.fullmatch(r"[a-f0-9]{64}", baseline["backup_sha256"]) is not None,
            "backup digest required")
    for name in ("experiment_max_id", "user_max_id"):
        require(type(baseline[name]) is int and baseline[name] >= 0,
                "SQL table maxima must be nonnegative integers")
    expected = baseline["frozen_run"]
    require(set(expected) == {"run_id", "experiment_id", "status", "params", "metrics", "tags"}
            and expected["run_id"] == FROZEN_RUN and expected["status"] == "FINISHED"
            and all(isinstance(expected[name], dict) for name in ("params", "metrics", "tags")),
            "exact retained frozen-run snapshot required")
    encoded = json.dumps(expected, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    require(len(encoded) <= 65536, "frozen metadata snapshot exceeds bound")
    require(isinstance(probe_password, str) and len(probe_password) >= 32,
            "private one-use probe credential required")
    administrator = auth.get_user(admin_username)
    require(administrator.is_admin is True and 0 < administrator.id <= baseline["user_max_id"],
            "existing restored administrator required")
    require(snapshot(client.get_run(FROZEN_RUN)) == expected, "restored frozen metadata differs")
    require(client.get_experiment_by_name(EXPERIMENT) is None, "probe experiment exists")
    absent(lambda: client.get_registered_model(MODEL))
    absent(lambda: auth.get_user(USER))

    experiment_id = client.create_experiment(EXPERIMENT, artifact_location=SOURCE)
    require(re.fullmatch(r"[0-9]+", experiment_id) is not None
            and int(experiment_id) > baseline["experiment_max_id"], "experiment sequence regressed")
    experiment = client.get_experiment(experiment_id)
    require(experiment.experiment_id == experiment_id and experiment.name == EXPERIMENT
            and experiment.artifact_location == SOURCE, "experiment readback differs")
    created = client.create_run(experiment_id, start_time=STAMP)
    run_id = created.info.run_id
    require(re.fullmatch(r"[a-f0-9]{32}", run_id) is not None and run_id != FROZEN_RUN,
            "invalid probe run identity")
    version_source = f"{SOURCE}/{run_id}/artifacts"
    require(created.info.artifact_uri == version_source, "probe artifact directory differs")
    client.log_param(run_id, "probe", "metadata-only", synchronous=True)
    client.log_metric(run_id, "restore_ready", 1.0, timestamp=STAMP, step=0, synchronous=True)
    client.set_tag(run_id, "lob_arena.restore_probe", "true", synchronous=True)
    client.set_terminated(run_id, status="FINISHED", end_time=STAMP + 1)
    run = snapshot(client.get_run(run_id))
    require(run["run_id"] == run_id and run["experiment_id"] == experiment_id
            and run["status"] == "FINISHED" and run["params"] == {"probe": "metadata-only"}
            and run["metrics"] == {"restore_ready": 1.0}
            and run["tags"].get("lob_arena.restore_probe") == "true", "probe run readback differs")
    history = client.get_metric_history(run_id, "restore_ready")
    require(len(history) == 1 and (history[0].value, history[0].step, history[0].timestamp)
            == (1.0, 0, STAMP), "probe metric history differs")
    client.create_registered_model(MODEL)
    for number in (1, 2):
        version = client.create_model_version(MODEL, version_source, run_id=run_id, await_creation_for=0)
        require(version.version == str(number), "new registry counter differs")
        stored = client.get_model_version(MODEL, str(number))
        require((stored.name, stored.version, stored.source, stored.run_id, stored.status)
                == (MODEL, str(number), version_source, run_id, "READY"), "registry readback differs")
    user = auth.create_user(USER, probe_password)
    require(type(user.id) is int and user.id > baseline["user_max_id"], "user sequence regressed")
    stored_user = auth.get_user(USER)
    require((stored_user.id, stored_user.username, stored_user.is_admin) == (user.id, USER, False),
            "probe user readback differs")
    require(snapshot(client.get_run(FROZEN_RUN)) == expected, "historical run changed")
    return {"schema_version": "mlflow_restored_application_v1", "status": "verified",
            "backup_sha256": baseline["backup_sha256"],
            "frozen_run_metadata_sha256": hashlib.sha256(encoded).hexdigest(),
            "preserved_frozen_run_fields": sorted(expected),
            "full_database_preservation_verified": False,
            "experiment_id": experiment_id, "run_id": run_id, "user_id": user.id,
            "experiment_max_before": baseline["experiment_max_id"],
            "user_max_before": baseline["user_max_id"], "probe_model_versions": ["1", "2"],
            "restored_existing_registry_counter_verified": False, "artifact_io": False}
