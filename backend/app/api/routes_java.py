"""Authenticated transport bridge; Java keeps ownership of all live behavior."""

import asyncio

from fastapi import APIRouter, HTTPException, Request, WebSocket
from starlette.responses import StreamingResponse
from starlette.websockets import WebSocketDisconnect
from websockets.asyncio.client import connect as websocket_connect
from websockets.exceptions import WebSocketException

from app.arena.java_transport import MAX_REQUEST

router = APIRouter()
BRIDGE_IDLE_TIMEOUT = 60  # Existing edge idle timeout; no total export deadline.


class DirectJavaConnect(websocket_connect):
    def process_redirect(self, exc):
        return exc  # Never dial a different owner or retry a failed handshake.


connect = DirectJavaConnect


class JavaProxyResponse(StreamingResponse):
    def __init__(self, stream):
        self.stream = stream
        super().__init__(stream.chunks(), status_code=stream.status,
                         headers={**getattr(stream, "headers", {}), "Content-Type": stream.content_type,
                                  "Cache-Control": "no-store"})

    async def __call__(self, scope, receive, send):
        try:
            await super().__call__(scope, receive, send)
        finally:
            self.stream.close()


async def java_http(request: Request, path: str = ""):
    if ".." in request.url.path.split("/") or "\\" in request.url.path:
        raise HTTPException(404, "Unavailable route")
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_REQUEST:
            raise HTTPException(413, "Request too large")
    try:
        query = request.scope.get("query_string", b"").decode("ascii")
    except UnicodeDecodeError:
        raise HTTPException(400, "Invalid request") from None
    target = request.url.path + ("?" + query if query else "")
    check = request.scope.get("ceo_session_check")
    if check is not None and not check():
        raise HTTPException(401, "Session required")
    opening = asyncio.create_task(asyncio.to_thread(request.app.state.simulation.transport.open,
        request.method, target, bytes(body) or None,
        request.headers.get("content-type", "application/json"), timeout=BRIDGE_IDLE_TIMEOUT))
    try:
        result = await asyncio.shield(opening)
    except (RuntimeError, ValueError):
        raise HTTPException(502, "Java service unavailable") from None
    except BaseException:
        def close_late_result(task):
            try:
                task.result().close()
            except Exception:
                pass
        opening.add_done_callback(close_late_result)
        raise
    return JavaProxyResponse(result)


for prefix in ("arena", "kernel", "simulation", "scenarios"):
    router.add_api_route(f"/api/{prefix}/{{path:path}}", java_http,
                         methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])


class SessionEnded(Exception):
    pass


async def relay_arena(websocket: WebSocket, upstream):
    """Recheck current persisted authority before every command/frame and while idle."""
    def authorized():
        check = websocket.scope.get("ceo_session_check")
        if check is not None and not check():
            raise SessionEnded

    async def commands():
        while True:
            message = await websocket.receive()
            authorized()
            if message["type"] == "websocket.disconnect":
                return
            payload = message.get("text") if "text" in message else message.get("bytes", b"")
            await upstream.send(payload)

    async def frames():
        while True:
            payload = await upstream.recv()
            authorized()
            if isinstance(payload, str):
                await websocket.send_text(payload)
            else:
                await websocket.send_bytes(payload)

    async def authority():
        while True:
            await asyncio.sleep(0.5)
            authorized()

    authorized()
    await websocket.accept()
    tasks = [asyncio.create_task(job()) for job in (commands, frames, authority)]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=1)


@router.websocket("/ws/arena")
async def java_websocket(websocket: WebSocket):
    transport = websocket.app.state.simulation.transport
    upstream = None
    code = 1000
    try:
        check = websocket.scope.get("ceo_session_check")
        if check is not None and not check():
            raise SessionEnded
        # No retry iterator, environmental proxy, browser cookies or credentials.
        upstream = await connect(transport.websocket_url, proxy=None, open_timeout=transport.timeout,
                                 close_timeout=0.5, max_size=None, max_queue=4,
                                 compression=None, user_agent_header=None)
        await relay_arena(websocket, upstream)
    except SessionEnded:
        code = 1008
    except (OSError, ValueError, RuntimeError, WebSocketException, WebSocketDisconnect, TimeoutError):
        code = 1011
    finally:
        if upstream is not None:
            try:
                await asyncio.wait_for(upstream.close(), timeout=1)
            except (OSError, RuntimeError, WebSocketException, TimeoutError):
                pass
        try:
            await websocket.close(code=code)
        except (RuntimeError, WebSocketDisconnect):
            pass
