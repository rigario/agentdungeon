"""D20 Agent RPG — Time API endpoints.

Provides character game time info and time-aware NPC availability.
"""

from fastapi import APIRouter, HTTPException, Depends
from app.services.database import get_db
from app.services.time_of_day import (
    get_character_time, get_time_period, get_period_description,
    get_time_atmosphere, is_npc_available, get_encounter_threshold_modifier,
    format_game_time, PERIOD_DESCRIPTIONS,
)
from app.services.auth_helpers import get_auth, require_character_ownership

router = APIRouter(prefix="/characters/{character_id}", tags=["time"])


@router.get("/time")
def get_character_game_time(character_id: str, auth: dict = Depends(get_auth)):
    """Get the current in-game time and period for a character.
    
    Returns game_hour, period name, period description, and encounter modifier.
    """
    require_character_ownership(character_id, auth)
    
    conn = get_db()
    row = conn.execute("SELECT id, game_hour, location_id FROM characters WHERE id = ?", (character_id,)).fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(404, f"Character not found: {character_id}")
    
    time_state = get_character_time(character_id)
    
    # Get location biome for atmosphere
    loc_row = None
    if row["location_id"]:
        conn2 = get_db()
        loc_row = conn2.execute("SELECT biome FROM locations WHERE id = ?", (row["location_id"],)).fetchone()
        conn2.close()
    
    biome = loc_row["biome"] if loc_row else "forest"
    time_atmosphere = get_time_atmosphere(time_state["game_hour"], biome)
    
    return {
        **time_state,
        "time_atmosphere": time_atmosphere,
    }


@router.get("/npcs/available")
def get_available_npcs(character_id: str, auth: dict = Depends(get_auth)):
    """Get NPCs available at the character's current time of day.
    
    Filters out NPCs whose hours don't match the current game time.
    """
    require_character_ownership(character_id, auth)
    
    time_state = get_character_time(character_id)
    game_hour = time_state["game_hour"]
    
    conn = get_db()
    # Get character's current location biome
    char = conn.execute("SELECT location_id FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not char:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")
    
    location_id = char["location_id"]
    loc = conn.execute("SELECT biome FROM locations WHERE id = ?", (location_id,)).fetchone()
    biome = loc["biome"] if loc else ""
    
    npcs = conn.execute(
        "SELECT * FROM npcs WHERE current_location_id = ? OR biome = ?",
        (location_id, biome)
    ).fetchall()
    conn.close()
    
    available = []
    unavailable = []
    
    for npc in npcs:
        npc_dict = dict(npc)
        if is_npc_available(npc_dict["id"], game_hour):
            available.append({
                "id": npc_dict["id"],
                "name": npc_dict["name"],
                "archetype": npc_dict["archetype"],
                "location_id": npc_dict.get("current_location_id"),
                "available": True,
            })
        else:
            unavailable.append({
                "id": npc_dict["id"],
                "name": npc_dict["name"],
                "archetype": npc_dict["archetype"],
                "location_id": npc_dict.get("current_location_id"),
                "available": False,
                "reason": f"Not available during {time_state['period']}",
            })
    
    return {
        "game_hour": game_hour,
        "period": time_state["period"],
        "available_npcs": available,
        "unavailable_npcs": unavailable,
    }


@router.post("/time/advance")
def advance_character_time(character_id: str, hours: int = 1, auth: dict = Depends(get_auth)):
    """Manually advance a character's game clock (for DM/agent use).
    
    Query param: hours (default 1, max 24)
    """
    require_character_ownership(character_id, auth)
    
    hours = max(1, min(24, hours))
    minutes = hours * 60
    
    from app.services.time_of_day import advance_time as _advance_time
    result = _advance_time(character_id, minutes)
    
    return result
