"""CEO-AC-02/09/11/12: invented sessions/bytes/upstreams, no live services."""

import asyncio
import threading
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api import routes_java
from app.api.routes_ceo_auth import router as auth_router
from app.arena.java_client import JavaArenaClient
from app.arena.java_transport import MAX_REQUEST
from app.ceo_auth_boundary import CEOAccessBoundary
from test_ceo_auth import ORIGIN, configured as auth_fixture, sign_in

configured = auth_fixture


class RawReply:
    status = 201
    content_type = "application/x-protobuf"
    def chunks(self):
        yield b"invented-protobuf-result"
    def close(self):
        pass


def product(auth, *, peer="127.0.0.1"):
    app = FastAPI()
    app.state.ceo_auth = auth
    app.state.simulation = JavaArenaClient("http://invented-java:8080", 0.2)
    app.state.reads = []
    app.include_router(auth_router)
    app.include_router(routes_java.router)

    @app.api_route("/api/legacy-evidence", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
    async def original(request: Request):
        app.state.reads.append(request.method)
        return {"method": request.method, "bytes": len(await request.body())}

    app.add_middleware(CEOAccessBoundary, auth=auth)
    return TestClient(app, base_url=ORIGIN, client=(peer, 12345)), app


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE"])
def test_all_original_methods_protected_without_prepared_body_cap(configured, method):
    auth, claims, now, _ = configured
    client, app = product(auth)
    headers = {"Origin": ORIGIN}
    assert client.request(method, "/api/legacy-evidence", headers=headers).status_code == 401
    assert app.state.reads == []
    assert sign_in(client, claims).status_code == 200
    body = b"invented" * 2000
    response = client.request(method, "/api/legacy-evidence", content=body, headers=headers)
    assert response.json() == {"method": method, "bytes": len(body)}
    if method != "GET":
        assert client.request(method, "/api/legacy-evidence", content=body).status_code == 403
    now[0] += 1800
    assert client.request(method, "/api/legacy-evidence", headers=headers).status_code == 401
    assert app.state.reads == [method]


@pytest.mark.parametrize("path,method", [("/api/arena/state?afterSequence=9", "GET"),
    ("/api/kernel/run", "POST"), ("/api/simulation/reset", "POST"), ("/api/scenarios/spoofing-like", "POST")])
def test_java_paths_bytes_methods_queries_and_credentials_isolation(configured, monkeypatch, path, method):
    auth, claims, *_ = configured
    client, app = product(auth)
    calls = []
    def request(*args, **kwargs):
        calls.append((args, kwargs))
        return RawReply()
    monkeypatch.setattr(app.state.simulation.transport, "open", request)
    assert client.request(method, path, headers={"Origin": ORIGIN}).status_code == 401
    assert calls == []
    sign_in(client, claims)
    body = b"invented-protobuf" * 1000
    response = client.request(method, path, content=body, headers={"Origin": ORIGIN,
        "Content-Type": "application/x-protobuf", "Authorization": "invented-browser-credential"})
    assert response.status_code == 201 and response.content == b"invented-protobuf-result"
    assert response.headers["content-type"] == "application/x-protobuf"
    assert calls == [((method, path, body, "application/x-protobuf"), {"timeout": 60})]
    assert "credential" not in repr(calls)


def test_java_oversize_and_upstream_failure_do_not_leak_or_retry(configured, monkeypatch):
    auth, claims, *_ = configured
    client, app = product(auth)
    sign_in(client, claims)
    calls = []
    def request(*args, **kwargs):
        calls.append(args)
        raise RuntimeError("invented-secret/http://private-upstream")
    monkeypatch.setattr(app.state.simulation.transport, "open", request)
    assert client.post("/api/kernel/run", content=b"x" * (MAX_REQUEST + 1),
                       headers={"Origin": ORIGIN}).status_code == 413
    assert calls == []
    response = client.get("/api/arena/state")
    assert response.status_code == 502 and response.json() == {"detail": "Java service unavailable"}
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["missing", "origin", "host", "forwarded", "remote", "expired", "revoked"])
def test_websocket_denied_before_upstream(configured, monkeypatch, failure):
    auth, claims, now, _ = configured
    client, _ = product(auth, peer="192.0.2.1" if failure == "remote" else "127.0.0.1")
    if failure not in ("missing", "remote"):
        sign_in(client, claims)
    if failure == "expired":
        now[0] += 1800
    if failure == "revoked":
        auth.logout(client.cookies.get(auth.session_cookie))
    headers = {"Origin": ORIGIN}
    headers.update({"origin": {"Origin": "https://other.example"}, "host": {"Host": "other.example"},
                    "forwarded": {"Forwarded": "for=127.0.0.1"}}.get(failure, {}))
    calls = []
    async def connect(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("No upstream allowed")
    monkeypatch.setattr(routes_java, "connect", connect)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("ws://localhost:5173/ws/arena", headers=headers):
            pass
    assert exc.value.code == 1008 and calls == []


@pytest.mark.parametrize("ending", ["expiry", "logout", "allowlist", "store_failure"])
def test_active_websocket_refuses_command_after_authority_ends(configured, monkeypatch, ending):
    auth, claims, now, _ = configured
    client, _ = product(auth)
    sign_in(client, claims)
    calls, sent, closed = [], [], []
    class Upstream:
        def __init__(self):
            self.queue = asyncio.Queue()
        async def recv(self):
            return await self.queue.get()
        async def send(self, payload):
            sent.append(payload)
            await self.queue.put("invented-frame")
        async def close(self):
            closed.append(True)
    async def connect(*args, **kwargs):
        calls.append((args, kwargs))
        return Upstream()
    monkeypatch.setattr(routes_java, "connect", connect)
    with client.websocket_connect("ws://localhost:5173/ws/arena", headers={"Origin": ORIGIN}) as ws:
        ws.send_text("invented-command")
        assert ws.receive_text() == "invented-frame"
        if ending == "expiry":
            now[0] += 1800
        elif ending == "logout":
            auth.logout(client.cookies.get(auth.session_cookie))
        elif ending == "allowlist":
            auth.settings.ceo_demo_allowed_emails = "other@example.com"
        else:
            monkeypatch.setattr(auth, "session", lambda _: (_ for _ in ()).throw(OSError("invented-secret")))
        ws.send_text("refused-command")
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == 1008
    assert sent == ["invented-command"] and closed == [True]
    args, kwargs = calls[0]
    assert args == ("ws://invented-java:8080/ws/arena",)
    assert kwargs["proxy"] is None and kwargs["open_timeout"] == 0.2
    assert kwargs["close_timeout"] == 0.5 and "additional_headers" not in kwargs
    assert kwargs["max_size"] is None  # Preserve Java-owned state frame limits.


