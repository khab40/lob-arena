from urllib.parse import urlencode

from fastapi import APIRouter, HTTPException, Query, Request
from starlette.datastructures import QueryParams

from app.api.routes_java import java_http

from app.schemas.arena import ArenaState, ExchangeEventReplay

router = APIRouter(prefix="/api/arena", tags=["arena"])


@router.get("/state", response_model=ArenaState)
async def get_arena_state(request: Request) -> ArenaState:
    return await request.app.state.simulation.get_state()


@router.get("/exchange-events", response_model=ExchangeEventReplay)
async def get_exchange_events(
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
    after_sequence_java: int | None = Query(default=None, alias="afterSequence", ge=0),
    stream_id_java: str | None = Query(default=None, alias="streamId"),
) -> ExchangeEventReplay:
    params = getattr(request, "query_params", QueryParams())
    if ("after_sequence" in params and "afterSequence" in params
            or any(len(params.getlist(key)) > 1 for key in ("after_sequence", "afterSequence", "limit", "streamId"))):
        raise HTTPException(422, "Ambiguous replay parameters")
    if "afterSequence" in params or "streamId" in params:
        # Java callers retain raw status/bytes/stream behavior. A mixed legacy
        # cursor + Java stream must still advance, rather than silently reset.
        if "after_sequence" in params:
            scope = dict(request.scope)
            scope["query_string"] = urlencode([
                ("afterSequence" if key == "after_sequence" else key, value)
                for key, value in params.multi_items()
            ]).encode()
            request = Request(scope, request.receive)
        return await java_http(request)
    return await request.app.state.simulation.replay_exchange_events(
        after_sequence=after_sequence,
        limit=limit,
    )
