"""D20 Agent RPG — Map endpoints.

Returns world map data for the visual map UI.
With character context: includes availability-filtered NPC lists.
"""

import json
from fastapi import APIRouter, Query
from app.services.database import get_db
from app.services.npc_movement import get_available_npcs_at_location
from app.services.auth_helpers import get_auth  # noqa: F401 — available for future auth enforcement

router = APIRouter(tags=["map"])


@router.get("/api/map/data")
def get_map_data(character_id: str = None):
    """Get world map data for a campaign.

    If character_id is provided, returns only locations/NPCs belonging to that
    character's campaign (scoped world) AND splits NPCs into available/unavailable
    based on current game state (time, flags, quests).

    Otherwise returns all locations/NPCs (legacy single-campaign mode) without
    availability filtering.
    """
    conn = get_db()
    try:
        # Derive campaign_id if character_id provided
        campaign_id = None
        if character_id:
            cur = conn.execute("SELECT campaign_id FROM characters WHERE id = ?", (character_id,))
            row = cur.fetchone()
            if row:
                campaign_id = row["campaign_id"]

        # Build location query
        if campaign_id:
            rows = conn.execute(
                "SELECT id, name, biome, description, hostility_level, "
                "encounter_threshold, recommended_level, connected_to, image_url "
                "FROM locations WHERE campaign_id = ? ORDER BY hostility_level, name",
                (campaign_id,),
            ).fetchall()
            # NPCs filtered by campaign
            npc_rows = conn.execute(
                "SELECT id, name, current_location_id, archetype, image_url, personality, "
                "is_quest_giver, is_spirit, is_enemy "
                "FROM npcs "
                "WHERE current_location_id IS NOT NULL AND campaign_id = ?",
                (campaign_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, name, biome, description, hostility_level, "
                "encounter_threshold, recommended_level, connected_to, image_url "
                "FROM locations ORDER BY hostility_level, name"
            ).fetchall()
            npc_rows = conn.execute(
                "SELECT id, name, current_location_id, archetype, image_url, personality, "
                "is_quest_giver, is_spirit, is_enemy "
                "FROM npcs WHERE current_location_id IS NOT NULL"
            ).fetchall()

        npcs_by_location = {}
        for nr in npc_rows:
            loc_id = nr["current_location_id"]
            if loc_id not in npcs_by_location:
                npcs_by_location[loc_id] = []
            npcs_by_location[loc_id].append({
                "id": nr["id"],
                "name": nr["name"],
                "archetype": nr.get("archetype"),
                "image_url": nr.get("image_url"),
                "personality": nr.get("personality"),
                "is_quest_giver": bool(nr.get("is_quest_giver", 0)),
                "is_spirit": bool(nr.get("is_spirit", 0)),
                "is_enemy": bool(nr.get("is_enemy", 0)),
            })

        locations = []
        for r in rows:
            # Parse connected_to JSON
            raw_conns = r["connected_to"]
            try:
                conns = json.loads(raw_conns) if raw_conns else []
            except (json.JSONDecodeError, TypeError):
                conns = [c.strip() for c in str(raw_conns).split(",") if c.strip()]

            loc_id = r["id"]
            base_npcs = npcs_by_location.get(loc_id, [])

            # If character context: compute availability-split NPC lists
            available_npcs = None
            unavailable_npcs = None
            if character_id:
                # Build character context (hour + flags)
                char_ctx = _build_character_context(character_id, conn)
                if char_ctx:
                    avail_data = get_available_npcs_at_location(loc_id, char_ctx)
                    available_npcs = avail_data["available"]
                    unavailable_npcs = avail_data["unavailable"]

            locations.append({
                "id": r["id"],
                "name": r["name"],
                "biome": r["biome"],
                "description": r["description"],
                "hostility_level": r["hostility_level"],
                "encounter_threshold": r["encounter_threshold"],
                "recommended_level": r["recommended_level"],
                "connected_to": conns,
                "image_url": r["image_url"],
                "npcs": base_npcs,  # legacy flat list (kept for backward compat)
                # New enriched fields when character context available
                "npcs_available": available_npcs,
                "npcs_unavailable": unavailable_npcs,
            })

        return {
            "locations": locations,
            "current_location": "rusty-tankard",  # Default starting location
            "total": len(locations),
        }
    finally:
        conn.close()


def _build_character_context(character_id: str, existing_conn=None) -> dict | None:
    """
    Build character context dict needed for NPC availability: {game_hour, narrative_flags}.
    Returns None if character not found.
    """
    owns_conn = existing_conn is None
    conn = existing_conn if existing_conn else get_db()
    try:
        char_row = conn.execute(
            "SELECT current_location_id, game_hour FROM characters WHERE id = ?",
            (character_id,)
        ).fetchone()
        if not char_row:
            return None

        game_hour = char_row[1] if char_row[1] is not None else 8

        flag_rows = conn.execute(
            "SELECT flag_key, flag_value FROM narrative_flags WHERE character_id = ?",
            (character_id,)
        ).fetchall()
        narrative_flags = {r[0]: r[1] for r in flag_rows}

        return {
            "game_hour": game_hour,
            "narrative_flags": narrative_flags,
            "character_id": character_id,
        }
    finally:
        if owns_conn and conn:
            conn.close()
