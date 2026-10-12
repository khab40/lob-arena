"""CEO-AC-01/02/02b/09: invented identities, no Google or model execution."""

import json
import os
import sqlite3
import subprocess
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.routes_ceo_auth import router
from app.ceo_auth import AuthFailure, CEOAuth, verify_google
from app.ceo_auth_boundary import CEOAccessBoundary
from app.ceo_auth_store import AuthStore
from app.config import Settings

ORIGIN = "http://localhost:5173"
EMAIL = "reviewer@example.com"


@pytest.fixture
def configured(tmp_path):
    state = tmp_path / "state"
    settings = Settings(_env_file=None, CEO_DEMO_ENABLED=True, CEO_DEMO_LOCAL=True,
                        CEO_DEMO_ORIGIN=ORIGIN, GOOGLE_CLIENT_ID="invented.apps.googleusercontent.com",
                        CEO_DEMO_ALLOWED_EMAILS=EMAIL, CEO_DEMO_STATE_DIR=state,
                        ARENA_OUTPUT_DIR=tmp_path / "generic", RESEARCH_SAVED_SCORES_DIR=tmp_path / "custody")
    now = [1000.0]
    claims = {"sub": "invented-sub", "email": EMAIL, "name": "Reviewer", "iss": "accounts.google.com",
              "aud": settings.google_client_id, "exp": 10000, "email_verified": True, "nonce": ""}
    calls = []

    def verifier(token, client_id):
        calls.append((token, client_id))
        return dict(claims)

    auth = CEOAuth(settings, verifier, lambda: now[0])
    assert auth.configured
    return auth, claims, now, calls


def challenge(configured):
    auth, claims, *_ = configured
    response, cookie = auth.challenge()
    claims["nonce"] = response["nonce"]
    return cookie


def make_client(auth, *, peer="127.0.0.1", base_url=ORIGIN):
    app = FastAPI()
    app.state.ceo_auth = auth
    app.state.reads = 0
    app.include_router(router)

    @app.exception_handler(RequestValidationError)
    async def invalid(_request, _exception):
        return JSONResponse({"detail": "Invalid request"}, status_code=400)

    @app.get("/api/ceo-demo/campaign")
    @app.post("/api/ceo-demo/capture")
    async def protected():
        app.state.reads += 1
        return {"real_handler": True}

    @app.get("/api/legacy-evidence")
    async def legacy():
        app.state.reads += 1
        return {"legacy": True}

    app.add_middleware(CEOAccessBoundary, auth=auth)
    return TestClient(app, base_url=base_url, client=(peer, 50000)), app


def sign_in(client, claims):
    config = client.get("/api/auth/config")
    assert config.status_code == 200
    claims["nonce"] = config.json()["nonce"]
    return client.post("/api/auth/google", json={"credential": "invented-id-token"}, headers={"Origin": ORIGIN})


def test_google_session_opaque_durable_logout(configured):
    auth, claims, now, _ = configured
    session, token, lifetime = auth.login("invented-id-token", challenge(configured))
    assert session == {"user": {"id": "invented-sub", "email": EMAIL, "name": "Reviewer"},
                       "workspace_id": "ceo-demo", "expires_at": "1970-01-01T00:46:40Z"}
    assert lifetime == 1800
    recovered = CEOAuth(auth.settings, auth.verifier, lambda: now[0])
    assert recovered.session(token) == session
    db_bytes = auth.store.path.read_bytes()
    assert token.encode() not in db_bytes and claims["nonce"].encode() not in db_bytes
    assert b"invented-id-token" not in db_bytes
    recovered.logout(token)
    assert auth.session(token) is None


@pytest.mark.parametrize("field,value", [
    ("iss", "other-issuer"), ("aud", "other-client"), ("exp", 1000), ("exp", True),
    ("exp", float("inf")), ("email_verified", False), ("email_verified", "true"),
    ("email", "unlisted@example.com"), ("sub", ""), ("nonce", "n" * 43), ("name", "n" * 201),
])
def test_refuse_invalid_claim_and_consume_nonce(configured, field, value):
    auth, claims, _, calls = configured
    cookie = challenge(configured)
    original = claims[field]
    claims[field] = value
    with pytest.raises((AuthFailure, ValueError)):
        auth.login("invented-id-token", cookie)
    claims[field] = original
    with pytest.raises(AuthFailure):
        auth.login("invented-id-token", cookie)
    assert len(calls) == 1


def test_expired_challenge_no_verifier(configured):
    auth, _, now, calls = configured
    cookie = challenge(configured)
    now[0] += 300
    with pytest.raises(AuthFailure):
        auth.login("invented-id-token", cookie)
    assert calls == []


def test_nonce_bound_to_cookie_origin(configured):
    auth, *_ = configured
    cookie = challenge(configured)
    assert auth.store.consume(cookie, "https://other.example", auth.clock()) is None
    with pytest.raises(AuthFailure):
        auth.login("invented-id-token", cookie)


@pytest.mark.parametrize("revoke", ["expiry", "allowlist"])
def test_session_expiry_and_current_allowlist_removal(configured, revoke):
    auth, _, now, _ = configured
    _, token, _ = auth.login("invented-id-token", challenge(configured))
    if revoke == "expiry":
        now[0] += 1800
    else:
        auth.settings.ceo_demo_allowed_emails = "other@example.com"
    assert auth.session(token) is None
    assert auth.store.session(token) is None


def test_http_login_cookie_session_and_logout(configured):
    auth, claims, _, _ = configured
    client, app = make_client(auth)
    assert client.get("/api/auth/session").status_code == 401
    assert client.get("/api/ceo-demo/campaign").status_code == 401
    assert app.state.reads == 0
    response = sign_in(client, claims)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie and "Secure" not in cookie
    assert auth.session_cookie == "ceo-local-session"
    assert client.get("/api/auth/session").json() == response.json()
    assert client.get("/api/ceo-demo/campaign").status_code == 200
    assert client.post("/api/auth/logout", headers={"Origin": ORIGIN}).status_code == 204
    assert client.get("/api/ceo-demo/campaign").status_code == 401


@pytest.mark.parametrize("path", ["/api/legacy-evidence", "/api/research/saved-scores", "/docs", "/metrics",
                                  "/api/auth/config/", "/api/auth/config%2f", "/api/auth/unknown"])
def test_alternative_routes_denied_even_after_login(configured, path):
    auth, claims, *_ = configured
    client, app = make_client(auth)
    assert sign_in(client, claims).status_code == 200
    assert client.get(path).status_code == 404
    assert app.state.reads == 0


@pytest.mark.parametrize("header,value", [("Origin", "https://other.example"), ("Forwarded", "for=127.0.0.1"),
                                          ("X-Forwarded-For", "127.0.0.1"), ("X-Real-IP", "127.0.0.1"),
                                          ("Sec-Fetch-Site", "cross-site"), ("Host", "other.example")])
def test_local_forwarded_origin_and_host_refusal_before_reads(configured, header, value):
    client, app = make_client(configured[0])
    assert client.get("/api/ceo-demo/campaign", headers={header: value}).status_code == 403
    assert app.state.reads == 0


@pytest.mark.parametrize("peer", ["192.0.2.1", "testclient"])
def test_direct_remote_peer_denied(configured, peer):
    client, app = make_client(configured[0], peer=peer)
    assert client.get("/api/auth/config").status_code == 403
    assert app.state.reads == 0
