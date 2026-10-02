import hashlib
import json
import os
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from deployments.mlflow import readiness_live as live


def test_preflight_precedes_credentials_and_clients(tmp_path):
    def fail():
        raise ValueError("runtime unavailable")
    def forbidden():
        pytest.fail("client constructed before runtime verification")
    with pytest.raises(ValueError, match="runtime"):
        live.execute(tmp_path, tmp_path, "a" * 64, "b" * 40, preflight=fail, make_clients=forbidden)


def test_identity_is_scoped_at_construction_and_every_method(monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_USERNAME", "original")
    monkeypatch.delenv("MLFLOW_TRACKING_PASSWORD", raising=False)
    observed = []
    def read():
        observed.append((os.environ["MLFLOW_TRACKING_USERNAME"], os.environ["MLFLOW_TRACKING_PASSWORD"]))
    def factory():
        read()
        return NS(read=read)
    writer = live.ScopedClient(factory, ("writer", "fixture"))
    exporter = live.ScopedClient(factory, ("exporter", "other"))
    writer.read()
    exporter.read()
    assert observed == [("writer", "fixture"), ("exporter", "other")] * 2
    assert os.environ["MLFLOW_TRACKING_USERNAME"] == "original"
    assert "MLFLOW_TRACKING_PASSWORD" not in os.environ
    errors = []
    def worker():
        try:
            writer.read()
        except ValueError:
            errors.append("blocked")
    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert errors == ["blocked"] and len(observed) == 4


@pytest.mark.parametrize("status,body", [(302, b"ok"), (200, b"too long"), (200, b"ok")])
def test_artifact_download_is_bounded_and_never_follows_redirects(status, body, tmp_path):
    run = "a" * 32
    class Response:
        status_code, headers = status, {}
        raw = NS(read=lambda amount, **kwargs: body[:amount])
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    def get(url, **kwargs):
        assert url == f"{live.URI}/api/2.0/mlflow-artifacts/artifacts/7/{run}/artifacts/readiness/probe.txt"
        assert kwargs == dict(auth=("writer", "fixture"), timeout=10, stream=True,
                              allow_redirects=False, headers={"Accept-Encoding": "identity"})
        return Response()
    artifacts = live.Artifacts.__new__(live.Artifacts)
    artifacts.retained = tmp_path
    artifacts.client = NS(get_run=lambda _: NS(info=NS(artifact_uri=f"mlflow-artifacts:/7/{run}/artifacts")))
    artifacts.credentials, artifacts.session = ("writer", "fixture"), NS(get=get)
    if status == 200 and len(body) <= 2:
        assert artifacts.download(run, "readiness/probe.txt", 2) == body
        assert (tmp_path / run / "readiness/probe.txt").read_bytes() == body
    else:
        with pytest.raises(ValueError):
            artifacts.download(run, "readiness/probe.txt", 2)
        assert not list(tmp_path.iterdir())
    artifacts.client.get_run = lambda _: NS(info=NS(artifact_uri=f"mlflow-artifacts://unapproved/7/{run}/artifacts"))
    with pytest.raises(ValueError, match="same-server"):
        artifacts.url(run, "readiness/probe.txt")


def test_completed_artifacts_are_private_exclusive_and_not_a_verification_claim(tmp_path):
    artifacts = live.Artifacts.__new__(live.Artifacts)
    artifacts.retained = tmp_path
    destination = artifacts.destination("a" * 32, "governed/model.txt")
    artifacts.retain(destination, b"unverified bytes")
    assert destination.read_bytes() == b"unverified bytes"
    assert destination.stat().st_mode & 0o777 == 0o600
    assert destination.parent.stat().st_mode & 0o777 == 0o700
    assert not (tmp_path / "live-receipt.json").exists()
    with pytest.raises(FileExistsError):
        artifacts.retain(destination, b"replacement")
    with pytest.raises(FileExistsError):
        artifacts.download("a" * 32, "governed/model.txt", 20)
    assert destination.read_bytes() == b"unverified bytes"
    assert not list(destination.parent.glob(".download-*"))


def test_namespace_conflict_aborts_before_creation(tmp_path):
    admin = NS(get_experiment_by_name=lambda _: NS(name=live.EXPERIMENT, lifecycle_stage="deleted"),
               get_registered_model=lambda _: NS(name=live.MODEL, aliases={}))
    with pytest.raises(ValueError, match="experiment conflicts"):
        live.namespaces(admin, tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("has_version,token", [(True, None), (False, "unread-page")])
def test_existing_transformer_versions_abort_before_namespace_writes_grants_or_probe(tmp_path, monkeypatch,
                                                                                   has_version, token):
    class Versions(list):
        pass
    versions = Versions([NS(version="1")] if has_version else [])
    versions.token = token
    admin = Mock()
    admin.get_experiment_by_name.return_value = None
    admin.get_registered_model.return_value = NS(name=live.MODEL, aliases={})
    admin.search_model_versions.return_value = versions
    journal, inputs = tmp_path / "journal", tmp_path / "inputs"
    journal.mkdir(mode=0o700)
    inputs.mkdir()
    raw = b"{}"
    manifest = json.dumps({"inventory_sha256": hashlib.sha256(raw).hexdigest(),
                           "dataset_source_proof_sha256": hashlib.sha256(raw).hexdigest()}).encode()
    for name, content in (("manifest.json", manifest), ("inventory.json", raw), ("source-proof.json", raw)):
        (inputs / name).write_bytes(content)
    monkeypatch.setattr(live, "MANIFEST_SHA256", hashlib.sha256(manifest).hexdigest())
    forbidden = Mock(side_effect=AssertionError("live mutation reached after namespace conflict"))
    for name in ("inspect_permissions", "apply_permissions", "Artifacts", "register_baseline", "reserve_pair"):
        monkeypatch.setattr(live, name, forbidden)
    auth = NS(get_user=lambda _: NS(is_admin=True))
    with pytest.raises(ValueError, match="model namespace has versions"):
        live.execute(inputs, journal, "a" * 64, "b" * 40, preflight=lambda: {},
                     make_clients=lambda: (admin, auth, None, None, None))
    admin.create_experiment.assert_not_called()
    admin.create_registered_model.assert_not_called()
    forbidden.assert_not_called()
    assert not (journal / "live-receipt.json").exists()


def test_empty_existing_transformer_namespace_remains_usable(tmp_path):
    admin = Mock()
    admin.get_experiment_by_name.return_value = NS(name=live.EXPERIMENT, lifecycle_stage="active", experiment_id="7")
    admin.get_registered_model.return_value = NS(name=live.MODEL, aliases={})
    admin.search_model_versions.return_value = []
    assert live.namespaces(admin, tmp_path) == "7"
    admin.search_model_versions.assert_called_once_with(f"name = '{live.MODEL}'", max_results=1)
    admin.create_experiment.assert_not_called()
    admin.create_registered_model.assert_not_called()


def test_new_namespace_version_readback_conflict_is_not_accepted(tmp_path):
    class Missing(Exception):
        error_code = "RESOURCE_DOES_NOT_EXIST"
    admin = Mock()
    admin.get_experiment_by_name.return_value = NS(name=live.EXPERIMENT, lifecycle_stage="active", experiment_id="7")
    admin.get_registered_model.side_effect = [Missing(), NS(name=live.MODEL, aliases={})]
    admin.search_model_versions.return_value = [NS(version="1")]
    with pytest.raises(ValueError, match="model namespace has versions"):
        live.namespaces(admin, tmp_path)
    admin.create_registered_model.assert_called_once_with(live.MODEL)


def test_failed_version_lookup_prevents_namespace_creation(tmp_path):
    admin = Mock()
    admin.get_experiment_by_name.return_value = None
    admin.get_registered_model.return_value = NS(name=live.MODEL, aliases={})
    admin.search_model_versions.side_effect = PermissionError("lookup unavailable")
    with pytest.raises(PermissionError):
        live.namespaces(admin, tmp_path)
    admin.create_experiment.assert_not_called()
    admin.create_registered_model.assert_not_called()


@pytest.mark.parametrize("fail_registry", [False, True])
def test_live_attempt_journal_precedes_mutations_and_blocks_reentry(tmp_path, monkeypatch, fail_registry):
    journal, inputs = tmp_path / "journal", tmp_path / "inputs"
    journal.mkdir(mode=0o700)
    inputs.mkdir()
    raw = b"{}"
    manifest = json.dumps({"inventory_sha256": hashlib.sha256(raw).hexdigest(),
                           "dataset_source_proof_sha256": hashlib.sha256(raw).hexdigest()}).encode()
    for name, content in (("manifest.json", manifest), ("inventory.json", raw), ("source-proof.json", raw)):
        (inputs / name).write_bytes(content)
    monkeypatch.setattr(live, "MANIFEST_SHA256", hashlib.sha256(manifest).hexdigest())
    events = []
    def namespaces(*args):
        assert (journal / "live-intent.json").exists()
        events.append("namespaces")
        return "7"
    monkeypatch.setattr(live, "namespaces", namespaces)
    monkeypatch.setattr(live, "inspect_permissions", lambda *args: None)
    monkeypatch.setattr(live, "apply_permissions", lambda *args: {"verified_grants": 4})
    monkeypatch.setattr(live, "Artifacts", lambda *args: NS(download=None, upload=None, session=NS(close=lambda: None)))
    def registry(*args):
        if fail_registry:
            raise RuntimeError("registry interruption")
        return {"verified": True}
    monkeypatch.setattr(live, "register_baseline", registry)
    monkeypatch.setattr(live, "reserve_pair", lambda *args: ("parent", "child"))
    monkeypatch.setattr(live, "verify_tracking", lambda *args: {"status": "verified"})
    def clients():
        events.append("clients")
        return None, NS(get_user=lambda _: NS(is_admin=True)), None, None, None
    kwargs = dict(preflight=lambda: {"status": "verified"}, make_clients=clients)
    if fail_registry:
        with pytest.raises(RuntimeError):
            live.execute(inputs, journal, "a" * 64, "b" * 40, **kwargs)
        assert not (journal / "live-receipt.json").exists()
    else:
        receipt = live.execute(inputs, journal, "a" * 64, "b" * 40, **kwargs)
        assert not receipt["overall_readiness_verified"] and (journal / "live-receipt.json").exists()
    with pytest.raises(FileExistsError):
        live.execute(inputs, journal, "a" * 64, "b" * 40, **kwargs)
    assert events == ["clients", "namespaces"]
