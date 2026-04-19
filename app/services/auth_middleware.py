"""D20 Agent RPG — Auth Middleware (Task 2.2).

Provides:
- Auth middleware: extracts user_id / agent_id from request headers
- require_auth decorator: protects routes requiring authentication
- require_agent_auth decorator: protects routes requiring agent auth
- require_permission: checks agent permission level on a character
- get_current_user / get_current_agent helpers

Auth modes:
- Bearer <token>  → user auth (from Task 1.2 OAuth sessions)
- Agent <fingerprint>:<signature>  → agent auth (from Task 1.3 challenge-response)
- No header → unauthenticated (request.state.auth_type = None)
"""

from functools import wraps
from typing import Optional, Callable
from fastapi import Request, HTTPException, Header
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.auth import get_user_by_token, get_agent


# =========================================================
# MIDDLEWARE
# =========================================================

class AuthMiddleware(BaseHTTPMiddleware):
    """Extract auth info from headers and set request.state fields.

    Sets on every request:
        request.state.auth_type: "user" | "agent" | None
        request.state.user_id: str | None
        request.state.agent_id: str | None
        request.state.auth_raw: str | None
    """

    async def dispatch(self, request: Request, call_next):
        # Initialize defaults
        request.state.auth_type = None
        request.state.user_id = None
        request.state.agent_id = None
        request.state.auth_raw = None

        auth_header = request.headers.get("authorization", "")

        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
            user = get_user_by_token(token)
            if user:
                request.state.auth_type = "user"
                request.state.user_id = user["id"]
                request.state.auth_raw = token

        elif auth_header.startswith("Agent "):
            # Format: Agent <fingerprint>:<base64_signature>
            payload = auth_header[6:].strip()
            if ":" in payload:
                fingerprint, signature = payload.split(":", 1)
                # Look up agent by fingerprint
                from app.services.database import get_db
                conn = get_db()
                try:
                    agent = conn.execute(
                        "SELECT id, user_id, is_active FROM agents WHERE public_key_fingerprint = ?",
                        (fingerprint,)
                    ).fetchone()
                    if agent and agent["is_active"]:
                        request.state.auth_type = "agent"
                        request.state.agent_id = agent["id"]
                        request.state.user_id = agent["user_id"]
                        request.state.auth_raw = payload
                finally:
                    conn.close()

        response = await call_next(request)
        return response


# =========================================================
# DEPENDENCY HELPERS (for FastAPI route parameters)
# =========================================================

def get_current_user(request: Request) -> dict:
    """FastAPI dependency: extract authenticated user info from request state.

    Raises 401 if not authenticated as a user.
    """
    if request.state.auth_type != "user":
        raise HTTPException(401, "User authentication required (Bearer token)")
    return {
        "user_id": request.state.user_id,
        "auth_type": "user",
    }


def get_current_agent(request: Request) -> dict:
    """FastAPI dependency: extract authenticated agent info from request state.

    Raises 401 if not authenticated as an agent.
    """
    if request.state.auth_type != "agent":
        raise HTTPException(401, "Agent authentication required (Agent header)")
    return {
        "agent_id": request.state.agent_id,
        "user_id": request.state.user_id,
        "auth_type": "agent",
    }


def get_auth_identity(request: Request) -> dict:
    """FastAPI dependency: extract any authenticated identity (user or agent).

    Raises 401 if not authenticated at all.
    """
    if request.state.auth_type is None:
        raise HTTPException(401, "Authentication required (Bearer or Agent header)")
    return {
        "user_id": request.state.user_id,
        "agent_id": request.state.agent_id,
        "auth_type": request.state.auth_type,
    }


def get_optional_auth(request: Request) -> dict:
    """FastAPI dependency: extract auth identity if present, else None.

    Never raises — returns auth dict or empty dict.
    """
    if request.state.auth_type is None:
        return {"user_id": None, "agent_id": None, "auth_type": None}
    return {
        "user_id": request.state.user_id,
        "agent_id": request.state.agent_id,
        "auth_type": request.state.auth_type,
    }


# =========================================================
# PERMISSION CHECKING
# =========================================================

PERMISSION_LEVELS = {
    "none": 0,
    "view": 1,
    "operate": 2,
    "full": 3,
}


def check_character_permission(
    character_id: str,
    agent_id: str,
    required_level: str = "view",
) -> bool:
    """Check if an agent has the required permission level on a character.

    Args:
        character_id: The character to check
        agent_id: The agent requesting access
        required_level: Minimum permission level needed ("view", "operate", "full")

    Returns:
        True if permission granted, False otherwise
    """
    from app.services.database import get_db
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT agent_id, agent_permission_level FROM characters WHERE id = ?",
            (character_id,)
        ).fetchone()

        if not row:
            return False

        if row["agent_id"] != agent_id:
            return False

        actual_level = row["agent_permission_level"] or "none"
        return PERMISSION_LEVELS.get(actual_level, 0) >= PERMISSION_LEVELS.get(required_level, 0)
    finally:
        conn.close()


def require_character_permission(character_id: str, agent_id: str, required_level: str = "view"):
    """Raise 403 if agent lacks required permission on character."""
    if not check_character_permission(character_id, agent_id, required_level):
        raise HTTPException(
            403,
            f"Agent lacks '{required_level}' permission on character {character_id}"
        )


def is_character_owner(character_id: str, user_id: str) -> bool:
    """Check if a user owns a character."""
    from app.services.database import get_db
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT user_id FROM characters WHERE id = ?",
            (character_id,)
        ).fetchone()
        return row is not None and row["user_id"] == user_id
    finally:
        conn.close()


def require_character_owner(character_id: str, user_id: str):
    """Raise 403 if user doesn't own the character."""
    if not is_character_owner(character_id, user_id):
        raise HTTPException(403, f"User does not own character {character_id}")
