"""Explicitly enabled loopback-only saved research evidence API."""
import ipaddress
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.research.saved_scores import CAMPAIGN_ID, load_campaign

router = APIRouter(prefix="/api/research/saved-scores", tags=["research"])


def local_host(host: str | None) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host or "").is_loopback
    except ValueError:
        return False


def local_url(value: str, *, host_header=False) -> bool:
    try:
        parsed = urlsplit("http://" + value if host_header else value)
        return (parsed.scheme in {"http", "https"} and local_host(parsed.hostname)
                and parsed.username is None and parsed.password is None
                and parsed.path in {"", "/"} and not parsed.query and not parsed.fragment
                and (parsed.port is None or 0 < parsed.port < 65536))
    except ValueError:
        return False


def private_campaign(request: Request, response: Response):
    settings = request.app.state.settings
    if not settings.research_saved_scores_enabled:
        raise HTTPException(404, "Saved research predictions are unavailable.")
    headers = request.headers
    if (request.client is None or not local_host(request.client.host)
            or not local_url(headers.get("host", ""), host_header=True)
            or any(key == "forwarded" or key.startswith("x-forwarded-") for key in headers)
            or ("origin" in headers and not local_url(headers["origin"]))
            or headers.get("sec-fetch-site") == "cross-site"):
        raise HTTPException(403, "Saved research predictions require a direct loopback connection.")
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    from pathlib import Path
    root = Path(__file__).resolve().parents[3]
    try:
        return load_campaign(settings.research_saved_scores_dir,
                             (request.app.state.store.output_dir, root / "assets/screenshots"))
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        raise HTTPException(503, "Verified saved evidence is unavailable; operator inspection required.") from None


@router.get("/campaigns")
def campaigns(campaign=Depends(private_campaign)):
    return campaign.catalog()


@router.get("/campaigns/{campaign_id}/rows")
def rows(campaign_id: str, session_id: str,
         detector: Literal["transformer", "lightgbm"],
         offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=100),
         campaign=Depends(private_campaign)):
    if campaign_id != CAMPAIGN_ID:
        raise HTTPException(404, "Saved campaign unavailable.")
    try:
        return campaign.page(session_id, detector, offset, limit)
    except LookupError:
        raise HTTPException(404, "Saved source or detector unavailable.") from None
    except ValueError:
        raise HTTPException(422, "Saved page outside bounds.") from None
