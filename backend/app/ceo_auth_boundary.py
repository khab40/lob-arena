"""Outer ASGI boundary: deny before any legacy handler or evidence loader."""

import ipaddress
import sqlite3
from urllib.parse import urlsplit

from starlette.requests import cookie_parser
from starlette.responses import JSONResponse

from app.ceo_auth_store import TOKEN

AUTH_METHODS = {
    "/api/auth/config": "GET", "/api/auth/google": "POST",
    "/api/auth/session": "GET", "/api/auth/logout": "POST",
}


def application_cookies(raw, names):
    """Match Request.cookies, refusing ambiguous or malformed application values."""
    if len(raw) > 16384:
        raise ValueError("Invalid application cookies")
    seen = set()
    for chunk in raw.split(";"):
        key, separator, _ = chunk.partition("=")
        key = key.strip()
        if key in names:
            if not separator or key in seen:
                raise ValueError("Invalid application cookies")
            seen.add(key)
    cookies = cookie_parser(raw)
    if any(name in cookies and not TOKEN.fullmatch(cookies[name]) for name in names):
        raise ValueError("Invalid application cookies")
    return cookies


class CEOAccessBoundary:
    def __init__(self, app, auth):
        self.app, self.auth = app, auth

    async def __call__(self, scope, receive, send):
        if not self.auth.settings.ceo_demo_enabled or scope["type"] not in ("http", "websocket"):
            return await self.app(scope, receive, send)
        if scope["type"] == "websocket":
            return await send({"type": "websocket.close", "code": 1008})

        async def deny(status, detail):
            response = JSONResponse({"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"})
            await response(scope, receive, send)

        headers = scope.get("headers", [])
        values = {}
        for key, value in headers:
            values.setdefault(key.lower(), []).append(value.decode("latin-1"))
        if any(len(values.get(key, [])) > 1 for key in (b"host", b"origin", b"cookie", b"content-length")):
            return await deny(403, "Request refused")
        def header(key):
            return values.get(key, [""])[0]
        origin = urlsplit(self.auth.origin)
        if self.auth.local:
            try:
                peer = scope.get("client")
                loopback = bool(peer) and ipaddress.ip_address(peer[0]).is_loopback
            except ValueError:
                loopback = False
            forwarded = any(key == b"forwarded" or key == b"x-real-ip" or key.startswith(b"x-forwarded-")
                            for key, _ in headers)
            if not loopback or forwarded:
                return await deny(403, "Local access required")
        if (scope.get("scheme") != origin.scheme or header(b"host") != origin.netloc
                or header(b"origin") not in ("", self.auth.origin)
                or header(b"sec-fetch-site") not in ("", "same-origin", "none")):
            return await deny(403, "Origin refused")
        path, method = scope["path"], scope["method"]
        if scope.get("raw_path", path.encode()) != path.encode("utf-8"):
            return await deny(404, "Unavailable route")
        if path == "/healthz" and method == "GET":
            return await JSONResponse({"status": "ok"}, headers={"Cache-Control": "no-store"})(scope, receive, send)
        is_auth = AUTH_METHODS.get(path) == method
        is_demo = path.startswith("/api/ceo-demo/") and method in ("GET", "POST")
        if not is_auth and not is_demo:
            return await deny(404, "Unavailable route")
        if method == "POST" and header(b"origin") != self.auth.origin:
            return await deny(403, "Origin required")
        try:
            cookies = application_cookies(header(b"cookie"), (self.auth.session_cookie, self.auth.challenge_cookie))
        except ValueError:
            return await deny(403, "Request refused")
        try:
            session = self.auth.session(cookies.get(self.auth.session_cookie, ""))
        except (OSError, ValueError, sqlite3.Error):
            return await deny(503, "Session unavailable")
        scope["ceo_user"] = session
        if is_demo and not session:
            return await deny(401, "Session required")
        if method == "POST":
            if path == "/api/auth/google" and not self.auth.configured:
                return await deny(503, "Sign-in unavailable")
            maximum = 16384 if path == "/api/auth/google" else 8192
            try:
                if header(b"content-length") and not 0 <= int(header(b"content-length")) <= maximum:
                    return await deny(413, "Request too large")
            except ValueError:
                return await deny(400, "Invalid request")
            body = bytearray()
            while True:
                message = await receive()
                if message["type"] != "http.request":
                    return
                body.extend(message.get("body", b""))
                if len(body) > maximum:
                    return await deny(413, "Request too large")
                if not message.get("more_body", False):
                    break

            async def replay():
                return {"type": "http.request", "body": bytes(body), "more_body": False}

            receive = replay
        await self.app(scope, receive, send)
