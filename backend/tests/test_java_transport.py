"""Invented socket responses only; this module never connects to Java."""

from io import BytesIO

import pytest

from app.arena.java_client import JavaArenaClient
from app.arena.java_transport import JavaResponse, JavaTransport


@pytest.mark.parametrize("base,timeout", [("http://user:secret@java", 1), ("file:///private", 1),
    ("http://java/internal", 1), ("http://java?secret=x", 1), ("http://java", 0),
    ("http://java", float("inf"))])
def test_invalid_owner_configuration_refused(base, timeout):
    with pytest.raises(ValueError):
        JavaTransport(base, timeout)


def connection_fixture(monkeypatch, *, status=200, headers=None, body=b"invented"):
    observations = {"timeouts": [], "closed": []}
    class Reply(BytesIO):
        def getheader(self, key, default=None):
            return (headers or {}).get(key, default)
        def close(self):
            observations["closed"].append("response")
            super().close()
    reply = Reply(body)
    observations["reply_type"] = Reply
    reply.status = status
    class Socket:
        def settimeout(self, timeout):
            observations["timeouts"].append(timeout)
        def shutdown(self, how):
            observations["shutdown"] = how
    class Connection:
        sock = Socket()
        def __init__(self, host, port, timeout):
            observations["owner"] = (host, port, timeout)
        def request(self, method, path, **kwargs):
            observations["request"] = (method, path, kwargs)
        def getresponse(self):
            return reply
        def close(self):
            observations["closed"].append("connection")
    monkeypatch.setattr("app.arena.java_transport.http.client.HTTPConnection", Connection)
    return observations


def test_single_bounded_raw_transport_preserves_bytes_and_drops_credentials(monkeypatch):
    observed = connection_fixture(monkeypatch, headers={"Content-Type": "application/x-protobuf",
        "Content-Length": "8", "Set-Cookie": "invented-secret", "Location": "http://private"})
    response = JavaTransport("http://java:8080", 0.5).request("POST", "/api/kernel/run?a=1",
                                                           b"invented", "application/x-protobuf")
    assert response == JavaResponse(200, b"invented", "application/x-protobuf")
    assert observed["owner"] == ("java", 8080, 0.5)
    assert observed["request"] == ("POST", "/api/kernel/run?a=1",
        {"body": b"invented", "headers": {"Accept": "*/*", "Content-Type": "application/x-protobuf"}})
    assert observed["closed"] == ["response", "connection"]


@pytest.mark.parametrize("status,headers", [(302, {"Location": "http://private"}),
    (200, {"Content-Length": "-1"}), (200, {"Content-Length": "9"}),
    (200, {"Content-Length": "invalid"}), (200, {"Content-Type": "text/plain\r\nSecret: invented"})])
def test_invalid_response_closed_no_redirect_or_error_text(monkeypatch, status, headers):
    observed = connection_fixture(monkeypatch, status=status, headers=headers)
    with pytest.raises(RuntimeError, match="^Java service unavailable$"):
        JavaTransport("http://java", 0.5).request("GET", "/api/arena/state")
    assert observed["closed"] == ["response", "connection"]


def test_socket_idle_timeout_closes_response_without_total_export_cap(monkeypatch):
    observed = connection_fixture(monkeypatch)
    def timed_out(_self, _amount):
        raise TimeoutError("invented-secret/http://private")
    # Patch only this invented response's class, never a real socket.
    monkeypatch.setattr(observed["reply_type"], "read1", timed_out)
    with pytest.raises(RuntimeError, match="^Java service unavailable$"):
        JavaTransport("http://java", 0.5).request("GET", "/api/arena/state")
    assert observed["closed"] == ["response", "connection"]


def test_raw_stream_has_no_aggregate_or_total_duration_cap(monkeypatch):
    total = 33 * 1024**2
    observed = connection_fixture(monkeypatch, headers={"Content-Length": str(total)})
    remaining = [total]
    invented_elapsed = [0]
    def read1(_self, amount):
        assert amount == 65536
        if remaining[0] == 0:
            return b""
        remaining[0] -= amount
        invented_elapsed[0] += 1
        return b"x" * amount
    monkeypatch.setattr(observed["reply_type"], "read1", read1)
    stream = JavaTransport("http://java", 2).open("GET", "/api/arena/exchange-events", timeout=60)
    assert sum(len(chunk) for chunk in stream.chunks()) == total
    assert invented_elapsed[0] > 60 and observed["owner"] == ("java", None, 60)
    assert observed["closed"] == ["response", "connection"]


@pytest.mark.parametrize("status,exception", [(404, LookupError), (422, ValueError)])
def test_original_adapter_error_contract_retained(monkeypatch, status, exception):
    client = JavaArenaClient("http://java")
    monkeypatch.setattr(client.transport, "request", lambda *_: JavaResponse(status, b"invented", "text/plain"))
    with pytest.raises(exception):
        client._request("GET", "/api/incidents/invented")


def test_kernel_owner_proof_headers_survive_raw_stream_without_internal_headers(monkeypatch):
    from app.api.routes_java import JavaProxyResponse
    observed = connection_fixture(monkeypatch, headers={"Content-Type": "application/x-protobuf",
        "X-Kernel-Authority": "java", "X-Kernel-Decision": "java", "Cache-Control": "no-store",
        "Set-Cookie": "invented-secret", "Authorization": "invented-secret", "Location": "http://private"})
    stream = JavaTransport("http://java", 2).open("POST", "/api/kernel/run", b"invented")
    response = JavaProxyResponse(stream)
    assert dict(response.headers) == {"x-kernel-authority": "java", "x-kernel-decision": "java",
        "content-type": "application/x-protobuf", "cache-control": "no-store"}
    stream.close()
    assert observed["closed"] == ["response", "connection"]


def test_kernel_proof_cannot_forward_arbitrary_value_or_credential(monkeypatch):
    observed = connection_fixture(monkeypatch, headers={"X-Kernel-Authority": "invented-secret"})
    with pytest.raises(RuntimeError, match="^Java service unavailable$"):
        JavaTransport("http://java", 2).open("POST", "/api/kernel/run", b"invented")
    assert observed["closed"] == ["response", "connection"]
