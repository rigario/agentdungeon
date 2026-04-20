"""D20 Agent RPG — NPC endpoints with location tracking and movement.

Provides NPC detail inspection, location queries, and movement operations.
NPCs move between locations based on narrative flags, quest completion,
and scheduled patrol/travel patterns.
"""

import json
from fastapi import APIRouter, HTTPException, Depends
from app.services.database import get_db
from app.services.auth_helpers import get_auth
from app.services.npc_movement import (
    get_all_npc_locations,
    get_npcs_at_location,
    move_npc,
    reset_npc_to_default,
    get_npcs_visible_to_character,
    process_movement_triggers,
)
from pydantic import BaseModel

router = APIRouter(prefix="/npcs", tags=["npcs"])


class MoveNPCRequest(BaseModel):
    location_id: str | None = None  # None = remove from world
    reason: str = "manual"


def _npc_to_response(row) -> dict:
    """Convert an NPC DB row to a response dict."""
    d = dict(row)
    return {
        "id": d["id"],
        "name": d["name"],
        "archetype": d["archetype"],
        "biome": d["biome"],
        "personality": d.get("personality"),
        "image_url": d.get("image_url"),
        "is_quest_giver": bool(d.get("is_quest_giver", 0)),
        "is_spirit": bool(d.get("is_spirit", 0)),
        "is_enemy": bool(d.get("is_enemy", 0)),
        "notes": d.get("notes"),
        "current_location_id": d.get("current_location_id"),
        "default_location_id": d.get("default_location_id"),
        "created_at": d.get("created_at"),
    }


@router.get("/locations")
def list_npc_locations():
    """Get current location of every NPC in the world."""
    locations = get_all_npc_locations()
    return {"npcs": locations, "count": len(locations)}


@router.get("/at/{location_id}")
def npcs_at_location(location_id: str):
    """Get all NPCs currently at a specific location."""
    conn = get_db()
    loc = conn.execute("SELECT name FROM locations WHERE id = ?", (location_id,)).fetchone()
    conn.close()
    if not loc:
        raise HTTPException(404, f"Location not found: {location_id}")

    npcs = get_npcs_at_location(location_id)
    return {
        "location_id": location_id,
        "location_name": loc[0],
        "npcs": npcs,
        "count": len(npcs),
    }


@router.post("/{npc_id}/move")
def move_npc_endpoint(npc_id: str, body: MoveNPCRequest):
    """Move an NPC to a new location (or remove from world with location_id=null)."""
    conn = get_db()
    npc = conn.execute("SELECT id, name FROM npcs WHERE id = ?", (npc_id,)).fetchone()

    if body.location_id:
        loc = conn.execute("SELECT id FROM locations WHERE id = ?", (body.location_id,)).fetchone()
        if not loc:
            conn.close()
            raise HTTPException(404, f"Location not found: {body.location_id}")

    conn.close()

    if not npc:
        raise HTTPException(404, f"NPC not found: {npc_id}")

    result = move_npc(npc_id, body.location_id, reason=body.reason)
    return result


@router.post("/{npc_id}/reset")
def reset_npc_endpoint(npc_id: str):
    """Reset an NPC to their default location."""
    conn = get_db()
    npc = conn.execute("SELECT id FROM npcs WHERE id = ?", (npc_id,)).fetchone()
    conn.close()
    if not npc:
        raise HTTPException(404, f"NPC not found: {npc_id}")

    return reset_npc_to_default(npc_id)


@router.post("/movement/check")
def check_movement_triggers():
    """Evaluate all NPC movement triggers against current narrative state.

    Checks narrative flags and completed quests, then executes any
    pending NPC movements. Returns list of movements that fired.
    """
    conn = get_db()

    # Get all narrative flags
    flag_rows = conn.execute("SELECT flag_key, flag_value FROM narrative_flags").fetchall()
    narrative_flags = {row[0]: row[1] for row in flag_rows}

    # Get completed quests
    quest_rows = conn.execute("""
        SELECT DISTINCT quest_id FROM character_quests WHERE status = 'completed'
    """).fetchall()
    completed_quests = [row[0] for row in quest_rows]

    conn.close()

    movements = process_movement_triggers(narrative_flags, completed_quests)
    return {"movements": movements, "count": len(movements)}


@router.get("/{npc_id}")
def get_npc(npc_id: str):
    """Get NPC details including portrait, personality, and current location."""
    conn = get_db()
    row = conn.execute("SELECT * FROM npcs WHERE id = ?", (npc_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, f"NPC not found: {npc_id}")

    d = dict(row)
    result = _npc_to_response(row)

    # Parse JSON fields
    if d.get("dialogue_templates"):
        try:
            result["dialogue_templates"] = json.loads(d["dialogue_templates"])
        except (json.JSONDecodeError, TypeError):
            result["dialogue_templates"] = []
    else:
        result["dialogue_templates"] = []

    if d.get("trades_json"):
        try:
            result["trades"] = json.loads(d["trades_json"])
        except (json.JSONDecodeError, TypeError):
            result["trades"] = []
    else:
        result["trades"] = []

    if d.get("quests_json"):
        try:
            result["quests"] = json.loads(d["quests_json"])
        except (json.JSONDecodeError, TypeError):
            result["quests"] = []
    else:
        result["quests"] = []

    if d.get("movement_rules_json"):
        try:
            result["movement_rules"] = json.loads(d["movement_rules_json"])
        except (json.JSONDecodeError, TypeError):
            result["movement_rules"] = {}
    else:
        result["movement_rules"] = {}

    return result


@router.get("")
def list_npcs(biome: str = None, has_image: bool = False, location_id: str = None):
    """List all NPCs, optionally filtering by biome, image availability, or location."""
    conn = get_db()
    query = "SELECT * FROM npcs"
    params = []

    conditions = []
    if biome:
        conditions.append("biome = ?")
        params.append(biome)
    if has_image:
        conditions.append("image_url IS NOT NULL")
    if location_id:
        conditions.append("current_location_id = ?")
        params.append(location_id)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY name"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {
        "npcs": [_npc_to_response(r) for r in rows],
        "count": len(rows),
    }
