"""Test portal state map locations include per-location NPCs (loc.npcs) for map.html."""

from pathlib import Path
import sqlite3
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.database import get_db, init_db
from app.services.portal import get_portal_state


class FakeDB:
    """Wraps a sqlite3 connection but suppresses close() so it stays open across calls."""
    def __init__(self, conn):
        self.conn = conn
    def execute(self, *args, **kwargs):
        return self.conn.execute(*args, **kwargs)
    def commit(self):
        return self.conn.commit()
    def close(self):
        pass


def test_portal_state_locations_include_npcs():
    """Test that portal state map.locations include per-location npcs compatible with map.html."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    with open(str(Path(__file__).resolve().parents[1] / "app/services/database_schema.sql"), "r") as f:
        schema = f.read()
    conn.executescript(schema)

    char_id = "test-char-1"
    conn.execute(
        "INSERT INTO characters (id, name, race, class, level, hp_current, hp_max, "
        "ac_value, ability_scores_json, mark_of_dreamer_stage, location_id, player_id) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            char_id,
            "Test Hero",
            "halfling",
            "rogue",
            1,
            9,
            9,
            13,
            json.dumps({"STR": 8, "DEX": 16, "CON": 14, "INT": 10, "WIS": 12, "CHA": 11}),
            0,
            "town-square",
            "player-1",
        ),
    )

    conn.execute("INSERT INTO locations (id, name, biome, hostility_level, connected_to) VALUES "
                 "('town-square', 'Town Square', 'urban', 1, '[]'),"
                 "('forest-edge', 'Forest Edge', 'forest', 3, '[\"town-square\"]')")

    conn.execute("""
        INSERT INTO npcs (id, name, current_location_id, archetype, image_url, personality, is_quest_giver, biome, campaign_id)
        VALUES ('npc-aldric', 'Aldric', 'town-square', 'innkeeper', '/static/aldric.png', 'Friendly', 1, 'urban', 'default'),
               ('npc-marta', 'Marta', 'town-square', 'serving', '/static/marta.png', 'Shy', 0, 'urban', 'default')
    """)

    conn.commit()

    # Patch module-local get_db references so portal + NPC movement helpers use the in-memory DB.
    import app.services.portal as portal_module
    import app.services.npc_movement as npc_movement_module
    original_portal_get_db = portal_module.get_db
    original_npc_movement_get_db = npc_movement_module.get_db
    fake_get_db = lambda: FakeDB(conn)
    portal_module.get_db = fake_get_db
    npc_movement_module.get_db = fake_get_db

    try:
        state = get_portal_state(char_id)
    finally:
        portal_module.get_db = original_portal_get_db
        npc_movement_module.get_db = original_npc_movement_get_db

    assert "map" in state, "map key missing"
    assert "locations" in state["map"], "map.locations missing"

    loc_lookup = {loc["id"]: loc for loc in state["map"]["locations"]}
    assert "town-square" in loc_lookup, "town-square missing"
    assert "forest-edge" in loc_lookup, "forest-edge missing"

    town = loc_lookup["town-square"]
    assert "npcs" in town, "town-square missing npcs field"
    assert len(town["npcs"]) == 2, f"Expected 2 NPCs, got {len(town['npcs'])}"

    # Verify npc shape matches what map.html expects
    aldric = next((n for n in town["npcs"] if n["id"] == "npc-aldric"), None)
    assert aldric is not None, "Aldric missing"
    assert aldric["name"] == "Aldric"
    assert aldric["archetype"] == "innkeeper"
    assert aldric["image_url"] == "/static/aldric.png"
    assert aldric["personality"] == "Friendly"
    assert aldric["is_quest_giver"] is True

    forest = loc_lookup["forest-edge"]
    assert "npcs" in forest, "forest-edge missing npcs field"
    assert len(forest["npcs"]) == 0, f"Expected 0 NPCs, got {len(forest['npcs'])}"

    # Verify top-level npcs_at_location still present
    assert "npcs_at_location" in state, "top-level npcs_at_location missing"
    assert len(state["npcs_at_location"]) == 2, "top-level npcs_at_location should still have 2"

    print("✅ Portal state locations include per-location npcs")
    conn.close()


if __name__ == "__main__":
    test_portal_state_locations_include_npcs()
    print("All checks passed")
