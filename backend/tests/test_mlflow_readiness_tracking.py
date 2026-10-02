"""Inert SDK boundary and ambiguous-write regressions; no model workload."""
from types import SimpleNamespace as NS

import pytest

from deployments.mlflow import readiness_tracking as tracking


class Client:
    def __init__(self):
        self.runs = {}
        self.creates = 0
        self.lose_response = False
        self.experiment = NS(experiment_id="7", lifecycle_stage="active")

    def get_experiment_by_name(self, name):
        return self.experiment

    def search_runs(self, ids, filter_string, **kwargs):
        identity = filter_string.split("'")[1]
        return [r for r in self.runs.values() if r.data.tags[tracking.RESERVATION] == identity]

    def create_run(self, experiment_id, tags, **kwargs):
        self.creates += 1
        run_id = str(self.creates)
        run = NS(info=NS(run_id=run_id, experiment_id=experiment_id,
                        lifecycle_stage="active", status="RUNNING"),
                 data=NS(tags=tags.copy(), params={}, metrics={}))
        self.runs[run_id] = run
        if self.lose_response:
            self.lose_response = False
            raise TimeoutError("inert lost response")
        return run

    def get_run(self, run_id):
        return self.runs[run_id]

    def log_param(self, run_id, key, value, *, synchronous):
        assert synchronous
        self.runs[run_id].data.params[key] = value

    def log_metric(self, run_id, key, value, *, timestamp, step, synchronous):
        assert synchronous and step == 0 and timestamp > 0
        self.runs[run_id].data.metrics[key] = value

    def set_tag(self, run_id, key, value, *, synchronous):
        assert synchronous
        raise Denied()

    def set_terminated(self, run_id, status):
        self.runs[run_id].info.status = status


class Denied(Exception):
    error_code = "PERMISSION_DENIED"

    def get_http_status_code(self):
        return 403


BINDING = {"proposal_sha256": "a" * 64, "source_commit": "b" * 40,
           "purpose": "mlflow-readiness-20261002"}


def test_pair_lost_response_reconciles_same_run_and_parent(tmp_path):
    client = Client()
    client.lose_response = True
    with pytest.raises(TimeoutError):
        tracking.reserve_pair(client, tmp_path, BINDING)
    assert client.creates == 1
    parent, child = tracking.reserve_pair(client, tmp_path, BINDING)
    assert client.creates == 2
    assert client.runs[child].data.tags["mlflow.parentRunId"] == parent
    assert tracking.reserve_pair(client, tmp_path, BINDING) == (parent, child)
    assert client.creates == 2


def test_unresolved_intent_binding_change_or_deleted_run_cannot_create(tmp_path):
    client = Client()
    ids = tracking.reserve_pair(client, tmp_path, BINDING)
    with pytest.raises(ValueError, match="journal conflict"):
        tracking.reserve_pair(client, tmp_path, {**BINDING, "source_commit": "c" * 40})
    client.runs.pop(ids[1])
    with pytest.raises(ValueError, match="never repeat"):
        tracking.reserve_pair(client, tmp_path, BINDING)
    assert client.creates == 2


def test_success_and_second_probe_cannot_repeat_writes(tmp_path):
    client = Client()
    ids = tracking.reserve_pair(client, tmp_path, BINDING)
    uploads = []
    result = tracking.verify_tracking(client, client, ids, lambda *a: uploads.append(a),
                                      lambda *a: tracking.PAYLOAD, tmp_path)
    assert result["exporter_write_denied"] and len(uploads) == 1
    assert all(r.info.status == "FINISHED" for r in client.runs.values())
    with pytest.raises(FileExistsError):
        tracking.verify_tracking(client, client, ids, lambda *a: uploads.append(a),
                                  lambda *a: tracking.PAYLOAD, tmp_path)
    assert len(uploads) == 1


@pytest.mark.parametrize("failure", ["artifact", "write_allowed", "unauthenticated", "timeout"])
def test_failures_never_establish_readiness(tmp_path, failure):
    client = Client()
    ids = tracking.reserve_pair(client, tmp_path, BINDING)
    def mutate(*args, **kwargs):
        if failure == "write_allowed":
            return
        if failure == "timeout":
            raise TimeoutError()
        error = Denied()
        error.error_code = "UNAUTHENTICATED"
        raise error
    if failure != "artifact":
        client.set_tag = mutate
    with pytest.raises(ValueError):
        tracking.verify_tracking(client, client, ids, lambda *a: None,
            lambda *a: b"corrupt" if failure == "artifact" else tracking.PAYLOAD, tmp_path)
    assert (tmp_path / "probe-intent.json").is_file()
    assert client.get_run(ids[1]).info.status == "RUNNING"


def test_symlink_journal_rejected_before_api(tmp_path):
    link = tmp_path / "link"
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="canonical"):
        tracking.reserve_pair(Client(), link, BINDING)
