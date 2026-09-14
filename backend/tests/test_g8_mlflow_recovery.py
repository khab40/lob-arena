import json
from pathlib import Path

import pytest

mlflow = pytest.importorskip("mlflow")

from app.ml.dataset_lineage import GovernedDatasetInput  # noqa: E402
from app.ml.lightgbm import g8_mlflow_recovery as recovery  # noqa: E402


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_ALLOW_FILE_STORE", "true")
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    root = tmp_path / "ledger"
    root.mkdir()
    spec = recovery.ReservationSpec(
        execution_package_sha256="a" * 64, request_sha256="b" * 64,
        candidate_sha256="c" * 64, evaluation_profile_sha256="d" * 64,
        request_run_id="synthetic-final", tracking_uri=(tmp_path / "mlruns").as_uri(),
    )
    target = recovery.ResumeTarget(root, spec)
    client = recovery._client(spec)
    experiment = client.create_experiment(recovery.EXPERIMENT)
    monkeypatch.setattr(recovery, "_client", lambda spec: client)
    return target, client, experiment


def arguments(tmp_path):
    artifacts = {}
    for relative in ("governed/model-bundle.json", "governed/checksums.sha256",
                     "governed/prediction-manifest.json", "governed-evaluation/c4.json"):
        source = tmp_path / relative
        source.parent.mkdir(exist_ok=True)
        source.write_text(relative)
        artifacts[relative] = (source, recovery._sha(source.read_bytes()))
    return dict(
        tags={"candidate_hash": "c" * 64, "evaluation_profile_sha256": "d" * 64,
              "evaluation_contract": "g8_c4_supervised_observations_v1",
              "same_observations_verified": "true"},
        metrics={"c4.test.lightgbm.row_f1": 0.75, "test_row_count": 20.0},
        inputs=(GovernedDatasetInput(
            name="test-shard", digest="e" * 64, context="evaluation",
            source_uri="s3://synthetic-only/test/shard.parquet", tags={"fold": "test"},
        ),),
        artifacts=artifacts,
    )


def test_reservation_reuses_one_run_and_retains_identity(setup):
    target, client, experiment = setup
    run_id = recovery.reserve_run(target)
    assert recovery.reserve_run(target) == run_id
    assert len(client.search_runs([experiment])) == 1
    assert client.get_run(run_id).info.status == "RUNNING"
    assert not client.get_run(run_id).data.metrics
    ledger = target.ledger_root / target.spec.identity()
    assert json.loads((ledger / "run.json").read_text())["run_id"] == run_id


@pytest.mark.parametrize("created", [False, True])
def test_lost_create_response_never_reissues_create(setup, monkeypatch, created):
    target, client, experiment = setup
    original = client.create_run
    calls = []

    def lose(*args, **kwargs):
        calls.append(1)
        if created:
            original(*args, **kwargs)
        raise TimeoutError("simulated ambiguous creation")

    monkeypatch.setattr(client, "create_run", lose)
    with pytest.raises(TimeoutError):
        recovery.reserve_run(target)
    if created:
        run_id = recovery.reserve_run(target)
        assert client.get_run(run_id).info.status == "RUNNING"
    else:
        with pytest.raises(ValueError, match="unresolved MLflow creation"):
            recovery.reserve_run(target)
    assert calls == [1]
    assert len(client.search_runs([experiment])) == int(created)


@pytest.mark.parametrize("variant", ["duplicate", "deleted", "failed", "killed", "tag", "ledger"])
def test_bad_reservation_fails_closed(setup, variant):
    target, client, experiment = setup
    run_id = recovery.reserve_run(target)
    if variant == "duplicate":
        client.create_run(experiment, tags=target.spec.tags())
    elif variant == "deleted":
        client.delete_run(run_id)
    elif variant in {"failed", "killed"}:
        client.set_terminated(run_id, status=variant.upper())
    elif variant == "tag":
        client.set_tag(run_id, "g8.request_sha256", "f" * 64)
    else:
        (target.ledger_root / target.spec.identity() / "run.json").write_text("{}")
    with pytest.raises(ValueError, match="ambiguous|differs|immutable"):
        recovery.reserve_run(target)


def test_missing_root_and_sdk_retries_are_not_silent_fallbacks(setup, monkeypatch):
    target, client, experiment = setup
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "3")
    with pytest.raises(ValueError, match="MAX_RETRIES=0"):
        recovery.reserve_run(target)
    monkeypatch.setenv("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "0")
    with pytest.raises(ValueError, match="already exist"):
        recovery.reserve_run(recovery.ResumeTarget(target.ledger_root / "missing", target.spec))
    assert not client.search_runs([experiment])


def test_same_ledger_cannot_be_used_concurrently(setup):
    target, _, _ = setup
    with recovery._locked(target), pytest.raises(BlockingIOError):
        recovery.reserve_run(target)


@pytest.mark.parametrize("fault", ["tags", "metrics", "lineage", "artifact", "finish", None])
def test_real_mlflow_partial_logging_and_lost_responses_recover_once(setup, tmp_path, monkeypatch, fault):
    target, client, experiment = setup
    run_id = recovery.reserve_run(target)
    kwargs = arguments(tmp_path)
    injected = []
    methods = {"tags": "log_batch", "metrics": "log_batch", "lineage": "log_inputs",
               "artifact": "log_artifact", "finish": "set_terminated"}
    if fault:
        method = methods[fault]
        original = getattr(client, method)

        def lose(*args, **kwargs):
            result = original(*args, **kwargs)
            eligible = fault not in {"tags", "metrics"} or bool(kwargs.get(fault))
            if eligible and not injected:
                injected.append(1)
                raise TimeoutError("simulated successful write with lost response")
            return result

        monkeypatch.setattr(client, method, lose)
        with pytest.raises(TimeoutError):
            recovery.resume_verified_logging(target, **kwargs)
        assert injected == [1]
    assert recovery.resume_verified_logging(target, **kwargs) == run_id
    assert client.get_run(run_id).info.status == "FINISHED"
    assert len(client.search_runs([experiment])) == 1
    assert len(client.get_run(run_id).inputs.dataset_inputs) == 1
    for key in kwargs["metrics"]:
        assert len(client.get_metric_history(run_id, key)) == 1
    for method in ("create_run", "log_batch", "log_inputs", "log_artifact", "set_terminated"):
        monkeypatch.setattr(client, method, lambda *a, **kw: pytest.fail("completed recovery wrote MLflow"))
    assert recovery.resume_verified_logging(target, **kwargs) == run_id
    receipt = json.loads((target.ledger_root / target.spec.identity() / "logging-complete.json").read_text())
    assert receipt["remote_state_verified"] is True
    assert receipt["tracking_scope"] == "offline"


@pytest.mark.parametrize("conflict", ["tag", "metric", "history", "lineage", "artifact", "unexpected", "finished"])
def test_remote_conflicts_never_overwrite_or_create_new_run(setup, tmp_path, monkeypatch, conflict):
    target, client, experiment = setup
    run_id = recovery.reserve_run(target)
    kwargs = arguments(tmp_path)
    if conflict == "tag":
        client.set_tag(run_id, "candidate_hash", "0" * 64)
    elif conflict in {"metric", "history"}:
        client.log_metric(run_id, "test_row_count", 999 if conflict == "metric" else 20)
        if conflict == "history":
            client.log_metric(run_id, "test_row_count", 20)
    elif conflict == "lineage":
        item = recovery._dataset_entities(kwargs["inputs"])[0]
        item.tags.append(mlflow.entities.InputTag("unexpected", "true"))
        client.log_inputs(run_id, datasets=[item])
    elif conflict in {"artifact", "unexpected"}:
        source = tmp_path / ("c4.json" if conflict == "artifact" else "extra.json")
        source.write_text("wrong content")
        client.log_artifact(run_id, str(source), artifact_path="governed-evaluation")
    else:
        client.set_terminated(run_id)
    for method in ("create_run", "log_batch", "log_inputs", "log_artifact", "set_terminated"):
        monkeypatch.setattr(client, method, lambda *a, **kw: pytest.fail("conflict reached a write"))
    with pytest.raises(ValueError, match="conflicting|unexpected|incomplete|history"):
        recovery.resume_verified_logging(target, **kwargs)
    assert len(client.search_runs([experiment])) == 1


def test_log_only_cannot_create_run_and_requires_bound_evidence(setup, tmp_path):
    target, client, experiment = setup
    kwargs = arguments(tmp_path)
    with pytest.raises(ValueError, match="reserve before scoring"):
        recovery.resume_verified_logging(target, **kwargs)
    assert not client.search_runs([experiment])
    recovery.reserve_run(target)
    kwargs["tags"]["candidate_hash"] = "f" * 64
    with pytest.raises(ValueError, match="differs from MLflow reservation"):
        recovery.resume_verified_logging(target, **kwargs)


def test_changed_local_bytes_or_logging_plan_rejected(setup, tmp_path):
    target, client, _ = setup
    run_id = recovery.reserve_run(target)
    kwargs = arguments(tmp_path)
    path = kwargs["artifacts"]["governed-evaluation/c4.json"][0]
    content = path.read_bytes()
    path.write_text("swapped")
    with pytest.raises(ValueError, match="changed before MLflow snapshot"):
        recovery.resume_verified_logging(target, **kwargs)
    assert not client.get_run(run_id).data.metrics
    path.write_bytes(content)
    kwargs["metrics"]["test_row_count"] = 21
    with pytest.raises(ValueError, match="immutable MLflow ledger record differs"):
        recovery.resume_verified_logging(target, **kwargs)


def test_artifact_upload_uses_immutable_snapshot(setup, tmp_path, monkeypatch):
    target, client, _ = setup
    run_id = recovery.reserve_run(target)
    kwargs = arguments(tmp_path)
    original = client.log_artifact

    def mutate(run_id, local_path, artifact_path):
        relative = artifact_path + "/" + Path(local_path).name
        source, digest = kwargs["artifacts"][relative]
        source.write_text("concurrent source mutation")
        assert Path(local_path) != source
        assert recovery._sha(Path(local_path).read_bytes()) == digest
        return original(run_id, local_path, artifact_path)

    monkeypatch.setattr(client, "log_artifact", mutate)
    assert recovery.resume_verified_logging(target, **kwargs) == run_id
    assert client.get_run(run_id).info.status == "FINISHED"


def test_complete_c4_scoring_recovers_logging_into_reserved_run(tmp_path):
    pytest.importorskip("lightgbm")
    from serverless.jobs.g8_mlflow_rehearsal import rehearse_mlflow

    receipt = rehearse_mlflow(tmp_path / "complete-c4")
    assert receipt["create_run_call_count"] == 1
    assert receipt["final_scoring_call_count"] == 1
    assert receipt["reserved_before_scoring"]
    assert receipt["local_mlflow_status"] == "FINISHED"
    assert receipt["completed_recovery_write_count"] == 0
    assert receipt["verified_dataset_input_count"] == 30
    assert receipt["logging_attempts"] == 4
    assert receipt["faults_recovered"] == ["create_response", "metric_response", "artifact_response", "finish_response"]
    assert not receipt["production_g8_complete"]
    assert not receipt["pre_logging_payload_retention_verified"]


@pytest.mark.parametrize("response", ["drop", "503"])
def test_actual_sdk_does_not_retry_ambiguous_create_post(setup, monkeypatch, response):
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from threading import Thread
    from types import SimpleNamespace

    target, _, _ = setup
    posts = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            posts.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            # A real server may commit creation before either response failure.
            if response == "503":
                self.send_response(503)
                self.send_header("Content-Length", "0")
                self.end_headers()
            self.close_connection = True

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        client = mlflow.MlflowClient(tracking_uri=f"http://127.0.0.1:{server.server_port}")
        monkeypatch.setattr(recovery, "_client", lambda spec: client)
        monkeypatch.setattr(recovery, "_find", lambda *a: (SimpleNamespace(experiment_id="1"), None))
        with pytest.raises(mlflow.exceptions.MlflowException):
            recovery.reserve_run(target)
        with pytest.raises(ValueError, match="unresolved MLflow creation"):
            recovery.reserve_run(target)
        assert posts == ["/api/2.0/mlflow/runs/create"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_create_intent_is_durable_before_remote_creation(setup, monkeypatch):
    target, client, _ = setup
    original = client.create_run

    def check(*args, **kwargs):
        ledger = target.ledger_root / target.spec.identity()
        assert (ledger / "spec.json").is_file()
        assert json.loads((ledger / "create-intent.json").read_text()) == {
            "reservation_sha256": target.spec.identity(),
        }
        assert not (ledger / "run.json").exists()
        return original(*args, **kwargs)

    monkeypatch.setattr(client, "create_run", check)
    recovery.reserve_run(target)
