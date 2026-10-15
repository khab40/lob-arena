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


@pytest.mark.parametrize("path", ["/api/research/saved-scores", "/metrics",
                                  "/api/auth/config/", "/api/auth/config%2f", "/api/auth/unknown"])
def test_unavailable_routes_remain_unavailable_after_login(configured, path):
    auth, claims, *_ = configured
    client, app = make_client(auth)
    assert sign_in(client, claims).status_code == 200
    assert client.get(path).status_code == 404
    assert app.state.reads == 0


def test_existing_routes_are_session_protected_and_preserved(configured):
    auth, claims, now, _ = configured
    client, app = make_client(auth)
    assert client.get("/api/legacy-evidence").status_code == 401
    assert client.get("/docs").status_code == 401
    assert sign_in(client, claims).status_code == 200
    assert client.get("/api/legacy-evidence").json() == {"legacy": True}
    assert client.get("/docs").status_code == 200
    now[0] += 1800
    assert client.get("/api/legacy-evidence").status_code == 401
    assert app.state.reads == 1


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


def test_cross_site_mutation_and_websocket_refusal(configured):
    auth, claims, *_ = configured
    client, app = make_client(auth)
    assert sign_in(client, claims).status_code == 200
    assert client.post("/api/ceo-demo/capture").status_code == 403
    assert client.post("/api/auth/logout", headers={"Origin": "https://other.example"}).status_code == 403
    assert app.state.reads == 0
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/arena"):
            pass
    assert exc.value.code == 1008


def test_shared_secure_cookie_and_https_required(configured):
    local, claims, now, _ = configured
    local.settings.ceo_demo_local = False
    local.settings.ceo_demo_origin = "https://demo.example"
    auth = CEOAuth(local.settings, local.verifier, lambda: now[0])
    client, app = make_client(auth, peer="192.0.2.1", base_url="https://demo.example")
    config = client.get("/api/auth/config")
    claims["nonce"] = config.json()["nonce"]
    response = client.post("/api/auth/google", json={"credential": "invented-id-token"},
                           headers={"Origin": "https://demo.example"})
    assert response.status_code == 200
    assert "__Host-ceo-session=" in response.headers["set-cookie"] and "Secure" in response.headers["set-cookie"]
    assert client.get("/api/ceo-demo/campaign").status_code == 200
    assert client.get("http://demo.example/api/ceo-demo/campaign").status_code == 403
    assert app.state.reads == 1


@pytest.mark.parametrize("field,value", [("google_client_id", None), ("ceo_demo_allowed_emails", ""),
                                        ("ceo_demo_state_dir", None)])
def test_missing_google_config_visible_and_denies(configured, field, value):
    original = configured[0]
    setattr(original.settings, field, value)
    auth = CEOAuth(original.settings, original.verifier)
    client, app = make_client(auth)
    assert client.get("/api/auth/config").json() == {"configured": False, "client_id": None, "nonce": None}
    assert client.get("/api/auth/session").status_code == 401
    assert client.get("/api/ceo-demo/campaign").status_code == 401
    assert app.state.reads == 0


def test_default_mode_preserves_legacy_and_creates_no_state(tmp_path):
    settings = Settings(_env_file=None)
    auth = CEOAuth(settings)
    assert not auth.configured and auth.store is None
    client, app = make_client(auth)
    assert client.get("/api/legacy-evidence").status_code == 200
    assert app.state.reads == 1


def test_bound_body_and_validation_no_token_echo(configured):
    client, _ = make_client(configured[0])
    assert client.post("/api/auth/google", content="x" * 16385, headers={"Origin": ORIGIN}).status_code == 413
    response = client.post("/api/auth/google", json={"credential": "invented-id-token", "extra": "secret-example"},
                           headers={"Origin": ORIGIN})
    assert response.status_code == 400 and "invented-id-token" not in response.text and "secret-example" not in response.text


@pytest.mark.parametrize("unsafe", ["permissions", "symlink", "overlap", "db_permissions", "hardlink", "replacement"])
def test_private_state_boundary(tmp_path, unsafe):
    directory = tmp_path / "state"
    directory.mkdir(mode=0o700)
    if unsafe == "permissions":
        directory.chmod(0o755)
    elif unsafe == "symlink":
        (tmp_path / "link").symlink_to(directory, target_is_directory=True)
        directory = tmp_path / "link"
    excluded = (directory / "custody",) if unsafe == "overlap" else ()
    if unsafe in ("permissions", "symlink", "overlap"):
        with pytest.raises(ValueError):
            AuthStore(directory, excluded)
        return
    store = AuthStore(directory, excluded)
    if unsafe == "db_permissions":
        store.path.chmod(0o644)
    elif unsafe == "hardlink":
        os.link(store.path, tmp_path / "linked")
    else:
        store.path.rename(directory / "old")
        store.path.write_bytes(b"")
        store.path.chmod(0o600)
    with pytest.raises(ValueError):
        store.session("a" * 43)


def test_challenge_capacity_and_db_error_fixed_response(configured, monkeypatch):
    auth, *_ = configured
    with auth.store.connection() as db:
        db.executemany("INSERT INTO challenges VALUES (?, ?, ?, ?)",
                       [(str(i), "nonce-hash", ORIGIN, 9999) for i in range(1000)])
    client, _ = make_client(auth)
    response = client.get("/api/auth/config")
    assert response.status_code == 503 and str(auth.store.path) not in response.text
    monkeypatch.setattr(auth.store, "session", lambda _: (_ for _ in ()).throw(sqlite3.OperationalError("private-path")))
    response = client.get("/api/auth/session")
    assert response.status_code == 503 and "private-path" not in response.text


def test_verifier_child_is_single_bounded_and_token_not_argv(monkeypatch):
    observed = {}

    class Child:
        returncode = 0
        def communicate(self, payload, timeout):
            observed.update(payload=json.loads(payload), timeout=timeout)
            return b'{"sub":"invented"}', None
        def poll(self):
            return 0

    def popen(argv, **kwargs):
        observed.update(argv=argv, kwargs=kwargs)
        return Child()

    monkeypatch.setattr(subprocess, "Popen", popen)
    assert verify_google("invented-id-token", "invented-client") == {"sub": "invented"}
    assert "invented-id-token" not in str(observed["argv"])
    assert observed["payload"]["credential"] == "invented-id-token"
    assert 0 < observed["timeout"] <= 10
    assert observed["kwargs"]["env"] == {} and observed["kwargs"]["stderr"] == subprocess.DEVNULL


def test_verifier_timeout_terminates_and_kills_without_retry(monkeypatch):
    actions = []
    class Child:
        def communicate(self, *_args, **_kwargs):
            raise subprocess.TimeoutExpired("verifier", 10)
        def poll(self):
            return None
        def terminate(self):
            actions.append("terminate")
        def wait(self, timeout):
            actions.append(timeout)
            if len(actions) == 2:
                raise subprocess.TimeoutExpired("verifier", timeout)
        def kill(self):
            actions.append("kill")
    monkeypatch.setattr(subprocess, "Popen", lambda *_args, **_kwargs: Child())
    with pytest.raises(AuthFailure):
        verify_google("invented-id-token", "invented-client")
    assert actions == ["terminate", 0.5, "kill", 0.5]


@pytest.fixture
def signing_material():
    from datetime import datetime, timedelta, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "invented.example")])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(1).not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=1))
            .sign(key, hashes.SHA256()))
    private = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    return private, cert.public_bytes(serialization.Encoding.PEM).decode()


@pytest.mark.parametrize("invalid", [None, "signature", "audience", "issuer", "expiry"])
def test_official_google_verifier_signature_and_claims_without_network(signing_material, invalid):
    import time
    from google.auth import crypt, jwt
    from google.oauth2.id_token import verify_oauth2_token
    private, cert = signing_material
    signer = crypt.RSASigner.from_string(private, key_id="invented-kid")
    now = int(time.time())
    claims = {"sub": "invented-sub", "iss": "accounts.google.com", "aud": "invented-client",
              "iat": now - 100, "exp": now + 3600}
    if invalid == "audience":
        claims["aud"] = "different-client"
    if invalid == "issuer":
        claims["iss"] = "other-issuer"
    if invalid == "expiry":
        claims["exp"] = now - 1
    token = jwt.encode(signer, claims).decode()
    if invalid == "signature":
        # Replace the signature with another structurally valid RSA signature.
        token = token.rsplit(".", 1)[0] + "." + jwt.encode(signer, {**claims, "sub": "other"}).decode().rsplit(".", 1)[1]
    calls = []
    def request(url, method):
        calls.append((url, method))
        return SimpleNamespace(status=200, data=json.dumps({"invented-kid": cert}).encode())
    if invalid is None:
        assert verify_oauth2_token(token, request, audience="invented-client")["sub"] == "invented-sub"
    else:
        with pytest.raises(Exception):
            verify_oauth2_token(token, request, audience="invented-client")
    assert calls == [("https://www.googleapis.com/oauth2/v1/certs", "GET")]


@pytest.mark.parametrize("response", [{"keys": []}, {}, {"kid": "not-a-certificate"}])
def test_certificate_transport_rejects_unbounded_jwk_branch_and_retries(monkeypatch, response):
    from app.ceo_google_worker import CERTS_URL, CertificateRequest
    requests = []
    class Response:
        status = 200
        def __enter__(self):
            return self
        def __exit__(self, *_args):
            pass
        def read(self, maximum):
            assert maximum == 1024 * 1024 + 1
            return json.dumps(response).encode()
    class Opener:
        def open(self, request, timeout):
            requests.append((request.full_url, timeout))
            return Response()
    monkeypatch.setattr("app.ceo_google_worker.build_opener", lambda *_args: Opener())
    transport = CertificateRequest()
    with pytest.raises(ValueError):
        transport(CERTS_URL)
    with pytest.raises(ValueError):
        transport(CERTS_URL)
    assert requests == [(CERTS_URL, 10)]


def test_google_worker_does_not_serialize_failure_or_credential(monkeypatch):
    import io
    from app import ceo_google_worker
    output = io.StringIO()
    monkeypatch.setattr(ceo_google_worker.sys, "stdin", SimpleNamespace(buffer=io.BytesIO(
        b'{"credential":"invented-id-token","client_id":"invented-client"}')))
    monkeypatch.setattr(ceo_google_worker.sys, "stdout", output)
    def refuse(*_args, **_kwargs):
        raise ValueError("invented-id-token/private-path")
    monkeypatch.setattr(ceo_google_worker, "verify_oauth2_token", refuse)
    assert ceo_google_worker.main() == 1
    assert output.getvalue() == ""


@pytest.mark.parametrize("position", ["before", "after"])
def test_unrelated_unquoted_json_cookie_preserves_login_poll_expiry_and_logout(configured, position):
    auth, claims, now, _ = configured
    client, app = make_client(auth)
    if position == "before":
        client.cookies.set("unrelated", '{"flag":0,"time":123}', domain="localhost.local", path="/")
    assert sign_in(client, claims).status_code == 200
    if position == "after":
        client.cookies.set("unrelated", '{"flag":0,"time":123}', domain="localhost.local", path="/")
    assert client.get("/api/auth/session").status_code == 200
    assert client.get("/api/ceo-demo/campaign").status_code == 200
    now[0] += 1800
    assert client.get("/api/auth/session").status_code == 401
    assert client.get("/api/ceo-demo/campaign").status_code == 401
    assert sign_in(client, claims).status_code == 200
    assert client.post("/api/auth/logout", headers={"Origin": ORIGIN}).status_code == 204
    assert client.get("/api/auth/session").status_code == 401
    assert app.state.reads == 1


@pytest.mark.parametrize("kind", ["session", "challenge"])
@pytest.mark.parametrize("path", ["session", "google", "logout"])
def test_duplicate_application_cookies_refused_before_session_or_google(configured, kind, path, monkeypatch):
    auth, claims, _, calls = configured
    client, app = make_client(auth)
    config = client.get("/api/auth/config")
    claims["nonce"] = config.json()["nonce"]
    monkeypatch.setattr(auth, "session", lambda _: pytest.fail("Ambiguous cookies reached session lookup"))
    name = auth.session_cookie if kind == "session" else auth.challenge_cookie
    raw = f'{name}={"a" * 43}; unrelated={{"flag":0}}; {name}={"b" * 43}'
    headers = {"Cookie": raw, "Origin": ORIGIN}
    response = client.get("/api/auth/session", headers=headers) if path == "session" else client.post(
        "/api/auth/" + path, json={"credential": "example"} if path == "google" else {}, headers=headers)
    assert response.status_code == 403 and response.json() == {"detail": "Request refused"}
    assert calls == [] and app.state.reads == 0


@pytest.mark.parametrize("kind", ["session", "challenge"])
@pytest.mark.parametrize("value", [None, "", "short", "a" * 42, "a" * 44, "a" * 42 + "/", '"not-opaque"', "%61" * 43])
def test_malformed_application_cookie_refused_without_verifier(configured, kind, value, monkeypatch):
    auth, _, _, calls = configured
    client, app = make_client(auth)
    monkeypatch.setattr(auth, "session", lambda _: pytest.fail("Malformed cookies reached session lookup"))
    name = auth.session_cookie if kind == "session" else auth.challenge_cookie
    app_cookie = name if value is None else f"{name}={value}"
    response = client.get("/api/auth/session", headers={"Cookie": f'unrelated={{"flag":0}}; {app_cookie}'})
    assert response.status_code == 403 and calls == [] and app.state.reads == 0


def test_quoted_valid_cookie_uses_same_decoded_value_as_request_cookies(configured):
    auth, claims, *_ = configured
    client, _ = make_client(auth)
    assert sign_in(client, claims).status_code == 200
    token = client.cookies.get(auth.session_cookie)
    response = client.get("/api/auth/session", headers={"Cookie": f'unrelated={{"flag":0}}; {auth.session_cookie}="{token}"'})
    assert response.status_code == 200


def test_unbounded_cookie_header_is_refused_without_session_lookup(configured, monkeypatch):
    auth, *_ = configured
    client, _ = make_client(auth)
    monkeypatch.setattr(auth, "session", lambda _: pytest.fail("Unbounded header reached session lookup"))
    assert client.get("/api/auth/session", headers={"Cookie": "unrelated=" + "x" * 16384}).status_code == 403
