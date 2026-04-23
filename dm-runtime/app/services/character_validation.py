"""DM Runtime — Character validation gateway.

Calls the rules-server /characters/{id}/validate endpoint to gate turn
processing before intent routing or narration. Prevents dead/archived
characters or characters in active combat from taking turns.
"""

from __future__ import annotations

import httpx
from typing import Dict, Any

from app.services.rules_client import _client, RULES_SERVER_URL


async def validate_character_for_turn(character_id: str) -> Dict[str, Any]:
    """Query rules-server pre-turn validation endpoint.

    Returns the validation JSON directly: {
        "valid": bool,
        "reason": str | None,
        "code": str | None,
        "checks_run": List[str]
    }

    Raises:
        HTTPException: on network error or non-200 response from rules-server.
    """
    url = f"{RULES_SERVER_URL}/characters/{character_id}/validate"
    try:
        resp = await _client.get(url, timeout=30.0)
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text[:200] if e.response else str(e)
        raise httpx.HTTPException(status_code=502, detail=f"rules_server validation error: {detail}")
    except Exception as e:
        raise httpx.HTTPException(status_code=502, detail=f"validation error: {str(e)}")
