"""Exercise the frozen SDK model and staging protocol without cloud credentials."""
import io
import signal
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest

pytest.importorskip("awscli")  # Registers the frozen CLI's vendored SDK.
from botocore.response import StreamingBody  # noqa: E402
from botocore.stub import Stubber  # noqa: E402

from serverless.jobs import g8_source_sdk as sdk  # noqa: E402
from serverless.jobs import stage_g8_native_sources as staging  # noqa: E402
from test_g8_source_staging import fake, prepared  # noqa: E402, F401 - shared sealed fixture


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic-not-a-real-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "synthetic-not-a-secret")
    with closing(sdk.SourceSDK().client) as client:
        yield client


def adapter(client):
    result = sdk.SourceSDK.__new__(sdk.SourceSDK)
    from botocore.exceptions import BotoCoreError, ClientError
    result.client, result.errors, result.client_error = client, (BotoCoreError, ClientError), ClientError
    return result


def test_client_has_one_attempt_and_bounded_socket_timeouts(client):
    config = client.meta.config
    assert config.retries["total_max_attempts"] == 1
    assert (config.connect_timeout, config.read_timeout) == (5, 15)
    assert client.meta.endpoint_url == sdk.transport.ENDPOINT
    assert config.s3["addressing_style"] == "path"


def test_sdk_maps_conditional_put_get_head_and_listing(client, tmp_path):
    s3 = adapter(client)
    source = tmp_path / "source"
    source.write_bytes(b"data")
    digest = staging.sha256_file(source)
    from botocore.stub import ANY
    with Stubber(client) as stub:
        stub.add_response("put_object", {}, {"Bucket": "bucket", "Key": "prefix/object", "Body": ANY,
                                           "IfNoneMatch": "*", "Metadata": {"sha256": digest}})
        s3._transfer_json(4, "s3api", "put-object", "--bucket", "bucket", "--key", "prefix/object",
                          "--body", str(source), "--metadata", "sha256=" + digest, "--if-none-match", "*")
        stub.add_response("head_object", {"ContentLength": 4, "Metadata": {"sha256": digest}},
                          {"Bucket": "bucket", "Key": "prefix/object"})
        stream = io.BytesIO(b"data")
        stub.add_response("get_object", {"Body": StreamingBody(stream, 4)},
                          {"Bucket": "bucket", "Key": "prefix/object"})
        s3._readback("bucket", "prefix/object", digest=digest, size=4)
        assert stream.closed
        stub.add_response("list_objects_v2", {"Contents": [{"Key": "prefix/object"}]},
                          {"Bucket": "bucket", "Prefix": "prefix/", "MaxKeys": 2})
        assert s3._listed_keys("bucket", "prefix", {"prefix/object"}) == {"prefix/object"}
        stub.assert_no_pending_responses()


def test_sdk_rejects_oversized_download_and_closes_stream(client, tmp_path):
    stream = io.BytesIO(b"oversized")
    with Stubber(client) as stub:
        stub.add_response("get_object", {"Body": StreamingBody(stream, 9)}, {"Bucket": "bucket", "Key": "key"})
        with pytest.raises(ValueError, match="sealed size"):
            adapter(client)._transfer_json(2, "s3api", "get-object", "--bucket", "bucket", "--key", "key",
                                           str(tmp_path / "download"))
    assert stream.closed


@pytest.mark.parametrize("code,status,accepted", [("403", 403, True), ("AccessDenied", 403, True),
    ("Forbidden", 403, True), ("404", 404, False), ("InvalidAccessKeyId", 403, False),
    ("SignatureDoesNotMatch", 403, False), ("AccessDenied", 500, False)])
def test_sdk_requires_explicit_production_head_denial(client, code, status, accepted):
    with Stubber(client) as stub:
        stub.add_client_error("head_object", service_error_code=code, http_status_code=status,
                              expected_params={"Bucket": "bucket", "Key": "key"})
        if accepted:
            adapter(client).production_head_denied("bucket", "key")
        else:
            with pytest.raises(ValueError, match="explicit access denial"):
                adapter(client).production_head_denied("bucket", "key")


def test_sdk_does_not_leak_service_errors(client):
    with Stubber(client) as stub:
        stub.add_client_error("head_object", service_message="must-not-appear")
        with pytest.raises(RuntimeError, match="^synthetic source S3 operation failed$"):
            adapter(client)._aws_json(sdk.transport.ENDPOINT, "s3api", "head-object", "--bucket", "bucket", "--key", "key")


@pytest.mark.parametrize("seconds", [0, -1, 1801])
def test_invalid_deadline_prevents_work(seconds):
    with pytest.raises(ValueError):
        with sdk.session_deadline(seconds):
            pytest.fail("invalid deadline entered")


def test_deadline_stops_a_blocked_process_and_restores_handler():
    code = ("import sys; sys.path.insert(0, 'backend')\n"
            "from serverless.jobs.g8_source_sdk import session_deadline; import time\n"
            "with session_deadline(1): time.sleep(20)\n")
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=8,
                            cwd=Path(__file__).resolve().parents[2])
    assert result.returncode != 0 and "session expired" in result.stderr
    previous = signal.getsignal(signal.SIGALRM)
    with sdk.session_deadline(1):
        pass
    assert signal.getsignal(signal.SIGALRM) == previous
    assert signal.getitimer(signal.ITIMER_REAL)[0] == 0


def test_full_protocol_uses_sdk_without_cli_and_preserves_partial_sources(prepared, fake, client, tmp_path):  # noqa: F811
    """Model-validated SDK calls, backed only by the explicit synthetic object store."""
    original = client._make_api_call

    def api(operation, params):
        # Validate every operation against the frozen service model first.
        client._serializer.serialize_to_request(params, client.meta.service_model.operation_model(operation))
        flags = {"Bucket": "--bucket", "Key": "--key", "Prefix": "--prefix", "MaxKeys": "--max-keys",
                 "ContinuationToken": "--continuation-token", "IfNoneMatch": "--if-none-match"}
        args = ["s3api", {"PutObject": "put-object", "GetObject": "get-object", "HeadObject": "head-object",
                          "ListObjectsV2": "list-objects-v2"}[operation]]
        for name, value in params.items():
            if name in flags:
                args += [flags[name], str(value)]
        if operation == "PutObject":
            args += ["--body", params["Body"].name, "--metadata", "sha256=" + params["Metadata"]["sha256"]]
        if operation == "GetObject":
            raw = fake.objects[params["Bucket"], params["Key"]]
            return {"Body": StreamingBody(io.BytesIO(raw), len(raw))}
        return fake.aws(sdk.transport.ENDPOINT, *args)

    client._make_api_call = api
    try:
        s3, (package, digest) = adapter(client), prepared
        _, _, plans = staging._plans(package, digest)
        _, bucket, prefix, _ = plans[1]
        fake.fail = bucket, prefix + "/SUCCESS"
        with pytest.raises(RuntimeError):
            staging.publish(package, expected_sha256=digest, s3=s3)
        retained = dict(fake.objects)
        assert len(retained) == 349
        fake.fail = None
        staging.publish(package, expected_sha256=digest, s3=s3)
        count = len(fake.puts)
        assert all(fake.objects[k] == v for k, v in retained.items())
        again = staging.publish(package, expected_sha256=digest, s3=s3)
        assert all(r["put_attempts"] == 0 for r in again["releases"])
        observed = staging.readback(package, tmp_path / "readback", expected_sha256=digest, s3=s3,
                                    head_denied=lambda: None)  # Denial itself is tested above.
        assert observed["remote_source_bytes_verified"] and len(fake.puts) == count
    finally:
        client._make_api_call = original
