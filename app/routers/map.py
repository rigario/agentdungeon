"""D20 Agent RPG — Map endpoints.

Returns world map data for the visual map UI.
"""

import json
from fastapi import APIRouter
from app.services.database import get_db

router = APIRouter(tags=["map"])


@router.get("/api/map/data")
def get_map_data():
    """Get all locations and their connections for the world map."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT id, name, biome, description, hostility_level, "
            "encounter_threshold, recommended_level, connected_to "
            "FROM locations ORDER BY hostility_level, name"
        ).fetchall()

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
            })

        return {
            "locations": locations,
            "current_location": "thornhold",  # Default starting location
            "total": len(locations),
        }
    finally:
        conn.close()
