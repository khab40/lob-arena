"""Check the actual SDK path as well as failures before runtime readiness."""
import importlib.util
from importlib import metadata
import hashlib
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
from types import SimpleNamespace

import pytest


@pytest.fixture
def operator():
    script = Path(__file__).resolve().parents[2] / "scripts/collect_transformer_lineage_metadata.py"
    spec = importlib.util.spec_from_file_location("runtime_operator", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def inert(operator, monkeypatch):
    monkeypatch.setattr(operator.metadata, "version", lambda _: "fixture-version")
    monkeypatch.setattr(operator.metadata, "distributions", lambda: [])
    proposal = {"runtime_python": platform.python_version(), "runtime_dependencies": {"botocore": "fixture-version"}}
    config = SimpleNamespace(region_name="eu-north1", retries={"total_max_attempts": 1, "mode": "legacy"},
        connect_timeout=5, read_timeout=5, s3={"addressing_style": "path"},
        request_checksum_calculation="when_required", response_checksum_validation="when_required")
    closed = []
    client = SimpleNamespace(meta=SimpleNamespace(config=config, endpoint_url="https://storage.eu-north1.nebius.cloud",
        service_model=SimpleNamespace(service_name="s3")), close=lambda: closed.append(True))
    return proposal, client, closed


def test_missing_sdk_fails_before_client_creation(operator, monkeypatch):
    calls = []
    def missing(_):
        raise metadata.PackageNotFoundError("botocore")
    monkeypatch.setattr(operator.metadata, "version", missing)
    with pytest.raises(metadata.PackageNotFoundError):
        operator.runtime_probe(lambda: calls.append(True), {
            "runtime_python": platform.python_version(), "runtime_dependencies": {"botocore": "required"}})
    assert calls == []


@pytest.mark.parametrize("failure", ["python", "dependency", "missing_pin"])
def test_invalid_runtime_pins_do_not_construct_client(operator, inert, failure):
    proposal, _, _ = inert
    if failure == "python":
        proposal["runtime_python"] = "0.0.0"
    elif failure == "dependency":
        proposal["runtime_dependencies"]["botocore"] = "wrong"
    else:
        proposal["runtime_dependencies"] = {}
    with pytest.raises(ValueError):
        operator.runtime_probe(lambda: pytest.fail("client must not be created"), proposal)


@pytest.mark.parametrize("failure", ["endpoint", "retries", "timeout", "checksum"])
def test_invalid_client_config_is_rejected_and_closed(operator, inert, failure):
    proposal, client, closed = inert
    if failure == "endpoint":
        client.meta.endpoint_url = "https://example.invalid"
    elif failure == "retries":
        client.meta.config.retries = {"total_max_attempts": 2}
    elif failure == "timeout":
        client.meta.config.read_timeout = 50
    else:
        client.meta.config.response_checksum_validation = "when_supported"
    with pytest.raises(ValueError, match="configuration"):
        operator.runtime_probe(lambda: client, proposal)
    assert closed == [True]


@pytest.mark.parametrize("operation", ["socket", "subprocess"])
def test_probe_blocks_external_operations_and_restores_environment(operator, inert, monkeypatch, operation):
    proposal, _, _ = inert
    monkeypatch.setenv("OPERATOR_TEST_SENTINEL", "preserve-me")
    original = dict(os.environ)
    def external():
        assert "OPERATOR_TEST_SENTINEL" not in os.environ
        assert os.environ["AWS_ACCESS_KEY_ID"] == "offline-fixture"
        if operation == "socket":
            socket.create_connection(("example.invalid", 443))
        else:
            subprocess.Popen(["never-run"])
    with pytest.raises(RuntimeError, match="prohibited"):
        operator.runtime_probe(external, proposal)
    assert dict(os.environ) == original


@pytest.fixture
def real_client():
    # Default backend tests allow absent optional SDK; the dedicated CI step requires it.
    if os.environ.get("REQUIRE_REAL_METADATA_SDK") == "1":
        import botocore  # noqa: F401
    else:
        pytest.importorskip("botocore")
    from app.ml.transformer.verification_transport import client
    requirements = Path(__file__).resolve().parents[2] / "serverless/transformer_inputs/requirements.txt"
    sdk_version = next(line.split("==")[1] for line in requirements.read_text().splitlines()
        if line.startswith("botocore=="))
    return client, sdk_version


def test_real_pinned_s3_client_constructs_offline(operator, real_client):
    client, sdk_version = real_client
    receipt = operator.runtime_probe(client, {"runtime_python": platform.python_version(),
        "runtime_dependencies": {"botocore": sdk_version}})
    assert receipt["dependencies"]["botocore"] == sdk_version
    assert receipt["executable"] and receipt["prefix"]


@pytest.mark.parametrize("ambient", [(), ("AWS_SESSION_TOKEN",), ("AWS_SECURITY_TOKEN",),
    ("AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN"), ("AWS_PROFILE",), ("AWS_CREDENTIAL_EXPIRATION",)])
def test_real_live_client_ignores_ambient_credentials(operator, real_client, monkeypatch, ambient):
    client, sdk_version = real_client
    for name in ("AWS_SESSION_TOKEN", "AWS_SECURITY_TOKEN", "AWS_PROFILE", "AWS_CREDENTIAL_EXPIRATION"):
        monkeypatch.delenv(name, raising=False)
    for name in ambient:
        monkeypatch.setenv(name, "invalid-fixture")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "original-fixture")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "original-fixture")
    original = dict(os.environ)
    monkeypatch.setattr(operator, "READER_ID_SHA256", hashlib.sha256(b"fixture-reader").hexdigest())
    calls = []
    def lookup(*args, **kwargs):
        calls.append(args)
        value = "fixture-reader" if len(calls) == 1 else "fixture-secret"
        return SimpleNamespace(returncode=0, stdout=json.dumps({"data": [
            {"key": "secret", "string_value": value}]}).encode())
    def prohibited(*args, **kwargs):
        pytest.fail("offline SDK regression must not use network or subprocesses")
    monkeypatch.setattr(operator.subprocess, "run", lookup)
    for owner, name in ((socket.socket, "connect"), (socket.socket, "connect_ex"),
            (socket, "create_connection"), (socket, "getaddrinfo"), (subprocess, "Popen")):
        monkeypatch.setattr(owner, name, prohibited)
    operator.runtime_probe(client, {"runtime_python": platform.python_version(),
        "runtime_dependencies": {"botocore": sdk_version}})
    assert calls == []
    s3 = operator.authenticated_client(client)
    try:
        credentials = s3._request_signer._credentials.get_frozen_credentials()
        assert credentials.access_key == "fixture-reader"
        assert credentials.secret_key == "fixture-secret"
        assert credentials.token is None
        assert dict(os.environ) == original
        assert len(calls) == 2
    finally:
        s3.close()
