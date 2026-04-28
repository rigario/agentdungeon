"""Queued live-tick turn receipt/status API.

These endpoints are intentionally separate from synchronous /dm/turn. In locked
live-tick mode an agent can submit a turn, receive HTTP 202 immediately, then
poll status_url to prove the request was not lost while the world tick runs.
"""

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from typing import Optional

from app.config import BASE_URL
from app.services.queued_turns import enqueue_turn, get_turn_status

router = APIRouter(prefix="/turns", tags=["turns"])


class QueueTurnRequest(BaseModel):
    character_id: str = Field(..., description="Character whose next live tick should process this action")
    message: str = Field(..., description="Player/agent action to queue for the next world tick")
    idempotency_key: Optional[str] = Field(
        None,
        description="Stable retry key. Reusing it for the same character returns the same turn_id.",
    )
    session_id: Optional[str] = Field(None, description="Optional DM session id for narration continuity")


def _public_base_url(request: Request) -> str:
    """Build externally useful base URL, honoring proxy headers when present."""
    forwarded_host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    forwarded_proto = request.headers.get("x-forwarded-proto")
    if forwarded_host:
        proto = forwarded_proto or request.url.scheme
        return f"{proto}://{forwarded_host}".rstrip("/")
    return BASE_URL.rstrip("/")


@router.post("/queue", status_code=status.HTTP_202_ACCEPTED)
def queue_turn(req: QueueTurnRequest, request: Request, response: Response):
    """Queue a turn for the next world tick and return immediate receipt."""
    try:
        receipt = enqueue_turn(
            character_id=req.character_id,
            message=req.message,
            idempotency_key=req.idempotency_key,
            session_id=req.session_id,
            base_url=_public_base_url(request),
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if receipt.get("duplicate"):
        # Still successful; 200 says this was a replayed receipt, not a new queued turn.
        response.status_code = status.HTTP_200_OK
    return receipt


@router.get("/{turn_id}/status")
def turn_status(turn_id: str, request: Request):
    """Poll queued/processing/completed/failed state for a queued live-tick turn."""
    try:
        return get_turn_status(turn_id, base_url=_public_base_url(request))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
