"""D20 Agent RPG — Encounter reference endpoints.

Provides read-only access to encounter definitions (monster groups,
loot tables, special rules). Used by the DM runtime, portal, and
playtest surfaces to resolve location-specific threats and rewards.

Endpoints:
  GET /encounters           — list all encounters (optionally filter by location_id)
  GET /encounters/{id}      — full detail for a specific encounter
"""

import json
from fastapi import APIRouter, HTTPException, Depends
from app.services.database import get_db
from app.services.auth_helpers import get_auth

router = APIRouter(prefix="/encounters", tags=["encounters"])


def _encounter_to_response(row) -> dict:
    """Convert an encounters DB row to a response dict."""
    d = dict(row)
    # Parse JSON fields safely
    try:
        enemies = json.loads(d["enemies_json"]) if d.get("enemies_json") else []
    except (json.JSONDecodeError, TypeError):
        enemies = []

    try:
        loot = json.loads(d["loot_json"]) if d.get("loot_json") else []
    except (json.JSONDecodeError, TypeError):
        loot = []

    return {
        "id": d["id"],
        "location_id": d["location_id"],
        "name": d["name"],
        "description": d.get("description"),
        "image_url": d.get("image_url"),
        "enemies": enemies,
        "loot": loot,
        "min_level": d.get("min_level", 1),
        "max_level": d.get("max_level", 20),
        "is_opening_encounter": bool(d.get("is_opening_encounter", 0)),
        "mark_mechanic": d.get("mark_mechanic"),
        "wis_save_dc": d.get("wis_save_dc"),
        "save_failure_effect": d.get("save_failure_effect"),
        "save_success_effect": d.get("save_success_effect"),
        "campaign_id": d.get("campaign_id", "default"),
        "created_at": d.get("created_at"),
    }


@router.get("")
def list_encounters(location_id: str = None, auth: dict = Depends(get_auth)):
    """List all encounters, optionally filtered by location.

    Args:
        location_id: If provided, only encounters at this location are returned.

    Returns:
        encounters: list of encounter summaries (id, name, location_id, is_opening)
        count: number of encounters returned
    """
    conn = get_db()
    query = "SELECT * FROM encounters"
    params = []

    if location_id:
        query += " WHERE location_id = ?"
        params.append(location_id)

    query += " ORDER BY name"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    return {
        "encounters": [_encounter_to_response(r) for r in rows],
        "count": len(rows),
    }


@router.get("/{encounter_id}")
def get_encounter(encounter_id: str, auth: dict = Depends(get_auth)):
    """Get full details for a specific encounter.

    Returns the complete encounter record including enemies_json and
    loot_json parsed into native structures.
    """
    conn = get_db()
    row = conn.execute("SELECT * FROM encounters WHERE id = ?", (encounter_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, f"Encounter not found: {encounter_id}")

    return _encounter_to_response(row)
