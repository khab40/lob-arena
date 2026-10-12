"""Google identity and opaque application sessions for the bounded CEO surface."""

import hmac
import json
import math
import re
import secrets
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from app.ceo_auth_store import AuthStore, token_hash
from app.config import Settings


class AuthFailure(Exception):
    pass


def verify_google(credential: str, client_id: str) -> dict:
    started = time.monotonic()
    child = subprocess.Popen(
        [sys.executable, "-I", str(Path(__file__).with_name("ceo_google_worker.py"))],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env={}, close_fds=True,
    )
    try:
        payload = json.dumps({"credential": credential, "client_id": client_id}).encode()
        output, _ = child.communicate(payload, timeout=max(0.001, 10 - (time.monotonic() - started)))
        if child.returncode != 0 or len(output) > 8192 or time.monotonic() - started > 10:
            raise AuthFailure()
        claims = json.loads(output)
        if not isinstance(claims, dict):
            raise AuthFailure()
        return claims
    except (subprocess.SubprocessError, ValueError, OSError) as exc:
        raise AuthFailure() from exc
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=0.5)
            except subprocess.TimeoutExpired:
                child.kill()
                try:
                    child.wait(timeout=0.5)
                except subprocess.TimeoutExpired as exc:
                    raise AuthFailure() from exc


class CEOAuth:
    def __init__(self, settings: Settings, verifier=verify_google, clock=time.time):
        self.settings, self.verifier, self.clock = settings, verifier, clock
        self.store = None
        self.origin = settings.ceo_demo_origin or ""
        self.local = settings.ceo_demo_local
        prefix = "ceo-local-" if self.local else "__Host-ceo-"
        self.challenge_cookie, self.session_cookie = prefix + "challenge", prefix + "session"
        parsed = urlsplit(self.origin)
        valid_origin = self.origin in ("http://localhost:5173", "http://127.0.0.1:5173") if self.local else (
            parsed.scheme == "https" and bool(parsed.hostname) and not parsed.username and not parsed.password
            and parsed.path == "" and not parsed.query and not parsed.fragment
            and self.origin == f"https://{parsed.netloc}"
        )
        if (not settings.ceo_demo_enabled or not valid_origin or not settings.google_client_id
                or len(settings.google_client_id) > 512 or not self.allowed_emails()
                or settings.ceo_demo_state_dir is None):
            return
        try:
            excluded = [settings.arena_output_dir, Path(__file__).resolve().parents[2] / "assets/screenshots"]
            if settings.research_saved_scores_dir is not None:
                excluded.append(settings.research_saved_scores_dir)
            self.store = AuthStore(settings.ceo_demo_state_dir, tuple(excluded))
        except (OSError, ValueError, sqlite3.Error):
            self.store = None

    @property
    def configured(self):
        return self.store is not None and bool(self.allowed_emails()) and bool(self.settings.google_client_id)

    def allowed_emails(self):
        return {email.strip().lower() for email in self.settings.ceo_demo_allowed_emails.split(",")
                if re.fullmatch(r"[^\s@,]+@[^\s@,]+", email.strip())}

    def challenge(self):
        if not self.configured:
            return {"configured": False, "client_id": None, "nonce": None}, None
        token, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        self.store.challenge(token, nonce, self.origin, self.clock())
        return {"configured": True, "client_id": self.settings.google_client_id, "nonce": nonce}, token

    def login(self, credential: str, challenge: str):
        if not self.configured or not isinstance(credential, str) or not 1 <= len(credential) <= 8192:
            raise AuthFailure()
        nonce_hash = self.store.consume(challenge, self.origin, self.clock())
        if nonce_hash is None:
            raise AuthFailure()
        claims = self.verifier(credential, self.settings.google_client_id)
        now = self.clock()
        expires = claims.get("exp")
        if (claims.get("iss") not in ("accounts.google.com", "https://accounts.google.com")
                or claims.get("aud") != self.settings.google_client_id or claims.get("email_verified") is not True
                or type(expires) not in (int, float) or not math.isfinite(expires) or expires <= now):
            raise AuthFailure()
        for key, maximum in (("sub", 255), ("email", 320), ("nonce", 43)):
            if not isinstance(claims.get(key), str) or not 1 <= len(claims[key]) <= maximum:
                raise AuthFailure()
        if not hmac.compare_digest(token_hash(claims["nonce"]), nonce_hash):
            raise AuthFailure()
        email = claims["email"].lower()
        if email not in self.allowed_emails():
            raise AuthFailure()
        name = claims.get("name") or email
        if not isinstance(name, str) or len(name) > 200:
            raise AuthFailure()
        user = {"id": claims["sub"], "email": email, "name": name}
        expiry = min(expires, now + self.settings.ceo_demo_session_seconds)
        token = secrets.token_urlsafe(32)
        self.store.create_session(token, user, expiry, now)
        return self.public_session(user, expiry), token, expiry - now

    def session(self, token: str):
        if not self.configured:
            return None
        try:
            row = self.store.session(token)
            if row is None:
                return None
            sub, email, name, expiry = row
            if expiry <= self.clock() or email not in self.allowed_emails():
                self.store.revoke(token)
                return None
            return self.public_session({"id": sub, "email": email, "name": name}, expiry)
        except ValueError:
            return None

    def logout(self, token: str):
        if self.store is not None:
            try:
                self.store.revoke(token)
            except ValueError:
                pass

    @staticmethod
    def public_session(user, expires):
        return {"user": user, "workspace_id": "ceo-demo",
                "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat().replace("+00:00", "Z")}
