import sqlite3

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.ceo_auth import AuthFailure

router = APIRouter(prefix="/api/auth", tags=["ceo-auth"])


class GoogleCredential(BaseModel):
    model_config = ConfigDict(extra="forbid")
    credential: str = Field(min_length=1, max_length=8192)


def set_cookie(response, auth, name, value, max_age):
    response.set_cookie(name, value, max_age=int(max_age), secure=not auth.local,
                        httponly=True, samesite="strict", path="/")


def clear_cookies(response, auth):
    for name in (auth.challenge_cookie, auth.session_cookie):
        response.delete_cookie(name, secure=not auth.local, httponly=True, samesite="strict", path="/")


def failure(status, detail):
    return JSONResponse({"detail": detail}, status_code=status, headers={"Cache-Control": "no-store"})


@router.get("/config")
def config(request: Request):
    auth = request.app.state.ceo_auth
    try:
        body, token = auth.challenge()
        response = JSONResponse(body, headers={"Cache-Control": "no-store"})
        if token is not None:
            set_cookie(response, auth, auth.challenge_cookie, token, 300)
        return response
    except (OSError, ValueError, sqlite3.Error):
        return failure(503, "Sign-in unavailable")


@router.post("/google")
def google(body: GoogleCredential, request: Request):
    auth = request.app.state.ceo_auth
    try:
        session, token, lifetime = auth.login(body.credential, request.cookies.get(auth.challenge_cookie, ""))
        auth.logout(request.cookies.get(auth.session_cookie, ""))
        response = JSONResponse(session, headers={"Cache-Control": "no-store"})
        response.delete_cookie(auth.challenge_cookie, secure=not auth.local, httponly=True,
                               samesite="strict", path="/")
        set_cookie(response, auth, auth.session_cookie, token, lifetime)
        return response
    except (AuthFailure, ValueError):
        response = failure(401, "Sign-in refused")
    except (OSError, sqlite3.Error, RuntimeError):
        response = failure(503, "Sign-in unavailable")
    response.delete_cookie(auth.challenge_cookie, secure=not auth.local, httponly=True,
                           samesite="strict", path="/")
    return response


@router.get("/session")
def session(request: Request):
    session = request.scope.get("ceo_user")
    return JSONResponse(session, headers={"Cache-Control": "no-store"}) if session else failure(401, "Session required")


@router.post("/logout", status_code=204)
def logout(request: Request):
    auth = request.app.state.ceo_auth
    try:
        auth.logout(request.cookies.get(auth.session_cookie, ""))
        if auth.store is not None:
            try:
                auth.store.consume(request.cookies.get(auth.challenge_cookie, ""), auth.origin, auth.clock())
            except ValueError:
                pass
    except (OSError, sqlite3.Error):
        return failure(503, "Sign-out unavailable")
    response = Response(status_code=204, headers={"Cache-Control": "no-store"})
    clear_cookies(response, auth)
    return response
