"""No MLflow process, database, model, artifact or cloud operation is executed."""
import copy
import importlib.util
from pathlib import Path
from types import SimpleNamespace as Entity
from unittest.mock import Mock
from urllib.parse import unquote, urlsplit

import pytest

spec = importlib.util.spec_from_file_location(
    "readiness_recovery", Path(__file__).resolve().parents[2]
    / "deployments/mlflow/readiness_recovery.py")
recovery = importlib.util.module_from_spec(spec)
spec.loader.exec_module(recovery)


class Missing(Exception):
    error_code = "RESOURCE_DOES_NOT_EXIST"


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    monkeypatch.delenv("MLFLOW_ACTIVE_MODEL_ID", raising=False)
    monkeypatch.delenv("_MLFLOW_ACTIVE_MODEL_ID", raising=False)
    baseline = {"backup_sha256": "a" * 64, "experiment_max_id": 7, "user_max_id": 3,
                "frozen_run": {"run_id": recovery.FROZEN_RUN, "experiment_id": "2",
                               "status": "FINISHED", "params": {"frozen": "yes"},
                               "metrics": {"score": .5}, "tags": {"candidate": "frozen"}}}
    def entity(snapshot):
        return Entity(info=Entity(**snapshot), data=Entity(**snapshot))
    run = entity({"run_id": "b" * 32, "experiment_id": "8", "status": "FINISHED",
                  "artifact_uri": recovery.SOURCE + "/" + "b" * 32 + "/artifacts",
                  "params": {"probe": "metadata-only"}, "metrics": {"restore_ready": 1.0},
                  "tags": {"lob_arena.restore_probe": "true"}})
    client = Mock(tracking_uri=recovery.RESTORED_URI, _registry_uri=recovery.RESTORED_URI)
    client.get_run.side_effect = lambda rid: entity(copy.deepcopy(baseline["frozen_run"])) \
        if rid == recovery.FROZEN_RUN else run
    client.get_experiment_by_name.return_value = None
    client.get_registered_model.side_effect = Missing()
    client.create_experiment.return_value = "8"
    client.get_experiment.return_value = Entity(experiment_id="8", name=recovery.EXPERIMENT,
                                              artifact_location=recovery.SOURCE)
    client.create_run.return_value = run
    client.get_metric_history.return_value = [Entity(value=1.0, step=0, timestamp=recovery.STAMP)]
    versions = [Entity(name=recovery.MODEL, version=str(n), source=run.info.artifact_uri,
                       run_id="b" * 32, status="READY") for n in (1, 2)]
    def create_version(name, source, *, run_id, await_creation_for):
        # MLflow v3.13.0 handlers._validate_source_run: a local version source
        # must be contained in the given run's artifact directory, not its parent.
        source_path = Path(unquote(urlsplit(source).path)).resolve()
        run_path = Path(unquote(urlsplit(run.info.artifact_uri).path)).resolve()
        if run_id != run.info.run_id or run_path not in [source_path, *source_path.parents]:
            raise ValueError("local source is outside run artifacts")
        return versions[client.create_model_version.call_count - 1]
    client.create_model_version.side_effect = create_version
    client.get_model_version.side_effect = versions
    auth = Mock(tracking_uri=recovery.RESTORED_URI)
    auth.get_user.side_effect = [Entity(id=1, is_admin=True), Missing(),
                                Entity(id=4, username=recovery.USER, is_admin=False)]
    auth.create_user.return_value = Entity(id=4)
    return client, auth, baseline, run


def call(setup, active_model=None):
    client, auth, baseline, _ = setup
    return recovery.verify_application(client, auth, baseline, admin_username="admin",
        probe_password="inert-fixture-credential-" + "x" * 16,
        get_active_model=lambda: active_model)


def test_success_binds_sequences_persisted_data_and_no_artifacts(setup):
    result = call(setup)
    client, auth, _, _ = setup
    assert (result["experiment_id"], result["user_id"]) == ("8", 4)
    assert result["probe_model_versions"] == ["1", "2"]
    assert result["restored_existing_registry_counter_verified"] is False
    assert result["preserved_frozen_run_fields"] == sorted(setup[2]["frozen_run"])
    assert result["full_database_preservation_verified"] is False
    assert "password" not in str(result)
    assert client.create_model_version.call_count == 2
    assert all(call.args == (recovery.MODEL, setup[3].info.artifact_uri)
               for call in client.create_model_version.call_args_list)
    assert auth.create_user.call_count == 1
    assert not client.log_artifact.called
    assert not auth.update_user_password.called
    assert all(call.args[0] != recovery.FROZEN_RUN for call in client.log_param.call_args_list)


@pytest.mark.parametrize("artifact_uri", [recovery.SOURCE, "file:///unexpected/artifacts",
    recovery.SOURCE + "/" + "c" * 32 + "/artifacts"])
def test_unexpected_run_artifact_directory_stops_before_probe_metadata(setup, artifact_uri):
    client, _, _, run = setup
    run.info.artifact_uri = artifact_uri
    with pytest.raises(ValueError, match="artifact directory differs"):
        call(setup)
    client.log_param.assert_not_called()
    client.create_model_version.assert_not_called()


@pytest.mark.parametrize("target", ["tracking_uri", "_registry_uri", "auth"])
def test_rejects_nonisolated_client_before_writes(setup, target):
    client, auth, _, _ = setup
    setattr(auth if target == "auth" else client,
            "tracking_uri" if target == "auth" else target, "http://live:5000")
    with pytest.raises(ValueError, match="endpoint"):
        call(setup)
    client.create_experiment.assert_not_called()


@pytest.mark.parametrize("mutation", ["experiment", "user", "metric", "param", "version"])
def test_rejects_regression_or_nonpersisted_metadata(setup, mutation):
    client, auth, _, run = setup
    if mutation == "experiment":
        client.create_experiment.return_value = "7"
    elif mutation == "user":
        auth.create_user.return_value = Entity(id=3)
    elif mutation == "metric":
        client.get_metric_history.return_value[0].step = 1
    elif mutation == "param":
        run.data.params = {}
    else:
        client.create_model_version.side_effect = [Entity(version="2")]
    with pytest.raises(ValueError):
        call(setup)


@pytest.mark.parametrize("kind", ["experiment", "model", "user", "permission"])
def test_existing_probe_or_failed_read_prevents_all_mutations(setup, kind):
    client, auth, _, _ = setup
    if kind == "experiment":
        client.get_experiment_by_name.return_value = Entity()
    elif kind == "model":
        client.get_registered_model.side_effect = None
    elif kind == "user":
        auth.get_user.side_effect = [Entity(id=1, is_admin=True), Entity()]
    else:
        client.get_registered_model.side_effect = PermissionError()
    with pytest.raises((ValueError, PermissionError)):
        call(setup)
    client.create_experiment.assert_not_called()
    auth.create_user.assert_not_called()


def test_ambiguous_write_is_not_retried(setup):
    client, auth, _, _ = setup
    client.create_run.side_effect = TimeoutError()
    with pytest.raises(TimeoutError):
        call(setup)
    client.create_run.assert_called_once()
    client.log_param.assert_not_called()
    auth.create_user.assert_not_called()


def test_restored_frozen_run_mismatch_and_retry_configuration_fail_before_writes(setup, monkeypatch):
    client, _, _, _ = setup
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "3")
    with pytest.raises(ValueError, match="retries"):
        call(setup)
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    client.get_run.return_value = None
    client.get_run.side_effect = lambda _: Entity(info=Entity(run_id="c" * 32,
        experiment_id="2", status="FINISHED"), data=Entity(params={}, metrics={}, tags={}))
    with pytest.raises(ValueError, match="metadata differs"):
        call(setup)
    client.create_experiment.assert_not_called()


@pytest.mark.parametrize("field,value", [("experiment_max_id", True), ("user_max_id", -1),
                                         ("backup_sha256", "unbound")])
def test_rejects_invalid_baseline_before_writes(setup, field, value):
    client, _, baseline, _ = setup
    baseline[field] = value
    with pytest.raises(ValueError):
        call(setup)
    client.create_experiment.assert_not_called()


def test_detects_historical_change_after_probe(setup):
    client, _, _, _ = setup
    original = client.get_run.side_effect
    def read(run_id):
        run = original(run_id)
        if run_id == recovery.FROZEN_RUN and client.create_model_version.called:
            run.data.tags["candidate"] = "changed"
        return run
    client.get_run.side_effect = read
    with pytest.raises(ValueError, match="historical run changed"):
        call(setup)


@pytest.mark.parametrize("source", ["MLFLOW_ACTIVE_MODEL_ID", "_MLFLOW_ACTIVE_MODEL_ID", "memory"])
def test_active_model_context_is_rejected_before_even_reading_credentials(setup, monkeypatch, source):
    client, auth, _, _ = setup
    if source != "memory":
        monkeypatch.setenv(source, "m-existing-model")
    with pytest.raises(ValueError, match="active model"):
        call(setup, active_model="m-existing-model" if source == "memory" else None)
    auth.get_user.assert_not_called()
    client.create_experiment.assert_not_called()
