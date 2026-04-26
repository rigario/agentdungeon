"""D20 Agent RPG — Portal Router.

Endpoints for the Player Portal:
- POST /portal/token — create share token for a character
- GET /portal/tokens/{character_id} — list tokens for a character
- GET /portal/token/{token}/validate — validate a share token
- DELETE /portal/token/{token} — revoke a share token
- GET /portal/{token}/state — aggregated character state (public, token-authenticated)
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Optional
import os

from app.services.portal import (
    create_share_token,
    validate_share_token,
    revoke_share_token,
    list_character_tokens,
    get_portal_state,
)

router = APIRouter(prefix="/portal", tags=["portal"])


@router.get("/", response_class=HTMLResponse)
def portal_home():
    """Serve the player portal landing page."""
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    home_html = os.path.join(static_dir, "portal-home.html")
    if os.path.exists(home_html):
        from fastapi.responses import FileResponse
        return FileResponse(home_html)
    return HTMLResponse("<h1>Portal home not found</h1>", status_code=500)


class CreateTokenRequest(BaseModel):
    character_id: str
    label: Optional[str] = None
    expires_hours: Optional[int] = None  # None = never expires


class CreateTokenResponse(BaseModel):
    id: str
    character_id: str
    character_name: str
    token: str
    label: Optional[str]
    expires_at: Optional[str]
    created_at: str


@router.post("/token", status_code=201, response_model=CreateTokenResponse)
def create_token(req: CreateTokenRequest):
    """Create a share token for a character.
    
    The token can be used to view the character's state via the portal
    without authentication. Useful for sharing playtest progress.
    """
    result = create_share_token(
        character_id=req.character_id,
        label=req.label,
        expires_hours=req.expires_hours,
    )
    if "error" in result:
        if result["error"] == "character_not_found":
            raise HTTPException(404, detail=result)
        raise HTTPException(400, detail=result)
    return result


@router.get("/tokens/{character_id}")
def list_tokens(character_id: str):
    """List all share tokens for a character."""
    tokens = list_character_tokens(character_id)
    return {"character_id": character_id, "tokens": tokens}


@router.get("/token/{token}/validate")
def validate_token(token: str):
    """Validate a share token. Returns basic info if valid."""
    result = validate_share_token(token)
    if not result.get("valid"):
        raise HTTPException(404, detail=result)
    return result


@router.delete("/token/{token}")
def revoke_token(token: str):
    """Revoke a share token."""
    result = revoke_share_token(token)
    if not result.get("ok"):
        raise HTTPException(404, detail=result)
    return result




@router.get("/{token}", response_class=HTMLResponse)
def portal_page(token: str):
    """Serve the portal HTML page for a share token.
    
    This endpoint is the main human-facing portal — token-authenticated.
    Renders portal.html with real-time state via client-side JavaScript
    that polls /portal/{token}/state.
    """
    # Validate token (check exists, not revoked, not expired)
    from app.services.database import get_db
    db = get_db()
    try:
        row = db.execute(
            "SELECT revoked, expires_at FROM share_tokens WHERE token = ?",
            (token,)
        ).fetchone()
        if not row or row["revoked"]:
            raise HTTPException(status_code=404, detail="Token not found or revoked")
        if row["expires_at"]:
            from datetime import datetime
            if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
                raise HTTPException(status_code=404, detail="Token expired")
    finally:
        db.close()

    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    portal_html = os.path.join(static_dir, "portal.html")
    if os.path.exists(portal_html):
        from fastapi.responses import FileResponse
        return FileResponse(portal_html)
    return HTMLResponse("<h1>Portal page not found</h1>", status_code=500)


@router.get("/{token}/state")
def portal_state(token: str):
    """Get aggregated character state for portal view.
    
    This is the main portal endpoint — token-authenticated, returns
    everything needed to render the player portal page:
    - Character sheet
    - Current location
    - Active quests
    - Recent events
    - Doom clock status
    - Inventory
    """
    # Validate token first
    validation = validate_share_token(token)
    if not validation.get("valid"):
        raise HTTPException(403, detail=validation)

    # Get aggregated state
    state = get_portal_state(validation["character_id"])
    if "error" in state:
        raise HTTPException(404, detail=state)

    # Include token metadata
    state["token_info"] = {
        "label": validation.get("label"),
        "view_count": validation.get("view_count"),
    }
    return state


@router.get("/{token}/view", response_class=HTMLResponse)
def portal_view(token: str):
    """Serve the portal HTML page for a share token."""
    # Validate token (just check it exists and is valid, don't increment view count here)
    from app.services.database import get_db
    db = get_db()
    try:
        row = db.execute(
            "SELECT revoked, expires_at FROM share_tokens WHERE token = ?",
            (token,)
        ).fetchone()
        if not row or row["revoked"]:
            raise HTTPException(404, detail="Invalid or revoked token")
        if row["expires_at"]:
            from datetime import datetime
            if datetime.utcnow() > datetime.fromisoformat(row["expires_at"]):
                raise HTTPException(404, detail="Token expired")
    finally:
        db.close()

    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
    portal_html = os.path.join(static_dir, "portal.html")
    if os.path.exists(portal_html):
        from fastapi.responses import FileResponse
        return FileResponse(portal_html)
    return HTMLResponse("<h1>Portal page not found</h1>", status_code=500)
