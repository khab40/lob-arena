"""Session-owned prepared research journey; browser input never selects private paths."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict, Field

from app.ceo_journey_store import ArtifactUnavailable, IDENTIFIER, InvalidSelection
from app.research.saved_score_io import canonical

router = APIRouter(prefix="/api/ceo-demo", tags=["ceo-demo"])
HEADERS = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}


class Capture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    detector: Literal["transformer", "lightgbm"]
    target_id: str = Field(pattern=r"^[a-f0-9]{64}$")


class Empty(BaseModel):
    model_config = ConfigDict(extra="forbid")


def authorized(request: Request):
    session = request.scope.get("ceo_user")
    auth = request.app.state.ceo_auth
    if (not auth.settings.ceo_demo_enabled or not auth.configured or not session
            or session.get("workspace_id") != "ceo-demo"):
        raise HTTPException(401, "Session required", headers=HEADERS)
    if request.query_params and request.url.path != "/api/ceo-demo/rows":
        raise HTTPException(400, "Unsupported request", headers=HEADERS)
    journey = getattr(request.app.state, "ceo_journey", None)
    if journey is None:
        raise HTTPException(503, "Prepared evidence is unavailable; operator inspection required", headers=HEADERS)
    return journey, session["user"]["id"]


def respond(action):
    try:
        return JSONResponse(action(), headers=HEADERS)
    except ArtifactUnavailable:
        raise HTTPException(503, "Verified evidence is unavailable; operator inspection required", headers=HEADERS) from None
    except InvalidSelection:
        raise HTTPException(422, "Select an original alert in the prepared window", headers=HEADERS) from None
    except LookupError:
        raise HTTPException(404, "Evidence unavailable", headers=HEADERS) from None
    except (OSError, ValueError, TypeError, KeyError, StopIteration):
        raise HTTPException(503, "Verified evidence is unavailable; operator inspection required", headers=HEADERS) from None


@router.get("/campaign")
def campaign(request: Request, access=Depends(authorized)):
    if request.query_params:
        raise HTTPException(400, "Unsupported request", headers=HEADERS)
    return respond(access[0].campaign)


@router.get("/rows")
def rows(request: Request, detector: Literal["transformer", "lightgbm"], access=Depends(authorized)):
    if list(request.query_params) != ["detector"] or len(request.query_params.getlist("detector")) != 1:
        raise HTTPException(400, "Unsupported request", headers=HEADERS)
    return respond(lambda: access[0].rows(detector))


@router.post("/anomalies")
def capture(body: Capture, access=Depends(authorized)):
    return respond(lambda: access[0].capture(access[1], body.detector, body.target_id))


@router.post("/anomalies/{identifier}/explanation")
def explanation(identifier: str, _body: Empty, access=Depends(authorized)):
    return respond(lambda: access[0].explain(access[1], identifier))


@router.post("/anomalies/{identifier}/save")
def save(identifier: str, _body: Empty, access=Depends(authorized)):
    return respond(lambda: access[0].save(access[1], identifier))


@router.get("/evidence")
def evidence(access=Depends(authorized)):
    return respond(lambda: access[0].listing(access[1]))


@router.get("/evidence/{identifier}")
def reopen(identifier: str, access=Depends(authorized)):
    return respond(lambda: access[0].record(access[1], identifier))


@router.get("/evidence/{identifier}/export")
def export(identifier: str, access=Depends(authorized)):
    if not IDENTIFIER.fullmatch(identifier):
        raise HTTPException(404, "Evidence unavailable", headers=HEADERS)
    result = respond(lambda: access[0].record(access[1], identifier))
    # Export the same canonical verified record; filename contains only a server-created ID.
    import json
    return Response(canonical(json.loads(result.body)), media_type="application/json", headers={**HEADERS,
        "Content-Disposition": f'attachment; filename="ceo-evidence-{identifier}.json"'})
