"""D20 Agent RPG — Shared auth enforcement helpers.

Provides reusable dependencies and checks for router-level auth enforcement.
Uses optional auth (backward compatible) — authenticated users get ownership
checks, unauthenticated requests pass through with a warning event logged.
"""

from fastapi import Request, HTTPException
from app.services.database import get_db


def get_auth(request: Request) -> dict:
    """Extract auth identity from request state (set by AuthMiddleware).

    Returns dict with user_id, agent_id, auth_type (may all be None).
    Never raises — returns empty identity if no auth present.
    """
    return {
        "user_id": getattr(request.state, "user_id", None),
        "agent_id": getattr(request.state, "agent_id", None),
        "auth_type": getattr(request.state, "auth_type", None),
    }


def require_character_ownership(character_id: str, auth: dict, allow_agent: bool = True) -> None:
    """Raise 403 if authenticated identity doesn't own the character.

    Args:
        character_id: The character to check ownership for.
        auth: Auth dict from get_auth().
        allow_agent: If True, agents with 'operate' or 'full' permission are allowed.

    Raises:
        HTTPException 403: If authenticated but not the owner.
    """
    if auth["auth_type"] is None:
        return  # Unauthenticated — let router decide policy

    conn = get_db()
    try:
        row = conn.execute(
            "SELECT user_id, agent_id, agent_permission_level FROM characters WHERE id = ?",
            (character_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, f"Character not found: {character_id}")

        # User auth: must own the character
        if auth["auth_type"] == "user":
            if row["user_id"] != auth["user_id"]:
                raise HTTPException(403, "You don't own this character")
            return

        # Agent auth: must have operate/full permission
        if auth["auth_type"] == "agent" and allow_agent:
            if row["agent_id"] != auth["agent_id"]:
                raise HTTPException(403, "Agent not linked to this character")
            perm = row["agent_permission_level"] or "none"
            if perm not in ("operate", "full"):
                raise HTTPException(403, f"Agent lacks '{perm}' permission — need 'operate' or 'full'")
            return

    finally:
        conn.close()


def check_character_exists(character_id: str) -> dict:
    """Verify a character exists and return its row as dict.

    Raises 404 if not found.
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
        if not row:
            raise HTTPException(404, f"Character not found: {character_id}")
        return dict(row)
    finally:
        conn.close()
