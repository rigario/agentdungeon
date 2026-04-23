"""D20 Agent RPG — Map endpoints.

Returns world map data for the visual map UI.
"""

import json
from fastapi import APIRouter
from app.services.database import get_db
from app.services.auth_helpers import get_auth  # noqa: F401 — available for future auth enforcement

router = APIRouter(tags=["map"])


@router.get("/api/map/data")
def get_map_data():
    """Get all locations and their connections for the world map, including NPC positions."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, biome, description, hostility_level, "
            "encounter_threshold, recommended_level, connected_to, image_url "
            "FROM locations ORDER BY hostility_level, name"
        ).fetchall()

        # Get NPC locations
        npc_rows = conn.execute(
            "SELECT id, name, current_location_id FROM npcs WHERE current_location_id IS NOT NULL"
        ).fetchall()
        npcs_by_location = {}
        for nr in npc_rows:
            loc_id = nr["current_location_id"]
            if loc_id not in npcs_by_location:
                npcs_by_location[loc_id] = []
            npcs_by_location[loc_id].append({"id": nr["id"], "name": nr["name"]})

        locations = []
        for r in rows:
            # Parse connected_to JSON
            raw_conns = r["connected_to"]
            try:
                conns = json.loads(raw_conns) if raw_conns else []
            except (json.JSONDecodeError, TypeError):
                conns = [c.strip() for c in str(raw_conns).split(",") if c.strip()]

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
                "npcs": npcs_by_location.get(r["id"], []),
            })

        return {
            "locations": locations,
            "current_location": "rusty-tankard",  # Default starting location
            "total": len(locations),
        }
    finally:
        conn.close()
