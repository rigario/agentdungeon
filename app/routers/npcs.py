"""D20 Agent RPG — NPC detail endpoints with image support.

Provides NPC detail inspection with portraits and dialogue templates.
Part of the hackathon sprint Task 4.3: NPC/Item Images.
"""

import json
from fastapi import APIRouter, HTTPException, Depends
from app.services.database import get_db
from app.services.auth_helpers import get_auth

router = APIRouter(prefix="/npcs", tags=["npcs"])


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
        "created_at": d.get("created_at"),
    }


@router.get("/{npc_id}")
def get_npc(npc_id: str):
    """Get NPC details including portrait and personality."""
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

    return result


@router.get("")
def list_npcs(biome: str = None, has_image: bool = False):
    """List all NPCs, optionally filtering by biome or image availability."""
    conn = get_db()
    query = "SELECT * FROM npcs"
    params = []

    conditions = []
    if biome:
        conditions.append("biome = ?")
        params.append(biome)
    if has_image:
        conditions.append("image_url IS NOT NULL")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY name"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {
        "npcs": [_npc_to_response(r) for r in rows],
        "count": len(rows),
    }
