"""DM Runtime — Session management and async recap.

Exposes endpoints for retrieving DM session state and generating
recap summaries for async play (resuming after a break).

Endpoints:
  GET  /dm/session/{session_id}/recap  — return session metadata + world context
  GET  /dm/character/{character_id}/session  — lookup current session for character
"""

from fastapi import APIRouter, HTTPException

from app.services.database import get_db
from app.services.dm_proxy import build_world_context

router = APIRouter(prefix="/dm", tags=["dm"])


@router.get("/session/{session_id}/recap")
async def get_session_recap(session_id: str):
    """Get a full recap of the current DM session state.

    Returns the session metadata and the complete world_context
    for the character attached to this session.

    Args:
        session_id: The Hermes agent session ID.

    Returns:
        200 with {session_id, character_id, updated_at, world_context} or 404.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT character_id, updated_at FROM dm_sessions WHERE session_id = ?",
        (session_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Session not found")

    character_id = row["character_id"]

    try:
        world_context = await build_world_context(character_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to build world context: {e}")

    return {
        "session_id": session_id,
        "character_id": character_id,
        "updated_at": row["updated_at"],
        "world_context": world_context,
    }


@router.get("/character/{character_id}/session")
async def get_character_session(character_id: str):
    """Get the current DM session for a character.

    Returns the active Hermes session ID if one exists within the
    30-minute window; otherwise returns null.

    Args:
        character_id: The character ID.

    Returns:
        200 with {character_id, session_id, updated_at} or null.
    """
    conn = get_db()
    row = conn.execute(
        "SELECT session_id, updated_at FROM dm_sessions "
        "WHERE character_id = ? AND updated_at >= datetime('now', '-30 minutes')",
        (character_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {"character_id": character_id, "session_id": None, "updated_at": None}

    return {
        "character_id": character_id,
        "session_id": row["session_id"],
        "updated_at": row["updated_at"],
    }
