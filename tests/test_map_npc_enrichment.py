"""
Unit tests for multi-NPC hub surface work (task f86b03ee).

Validates:
- Map endpoint returns full NPC summary details
- NPCs include fields needed for hub cards (archetype, image_url, personality, quest_giver flag)
"""
import pytest
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.database import get_db, init_db
from app.routers.map import get_map_data
import sqlite3, json


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    with open("/home/rigario/Projects/rigario-d20/app/services/database_schema.sql") as f:
        conn.executescript(f.read())
    # Minimal data: one location + two NPCs
    conn.execute("""
        INSERT INTO locations (id, name, biome, hostility_level, connected_to)
        VALUES ('rusty-tankard', 'Rusty Tankard', 'tavern', 0, '[]'),
               ('thornhold', 'Thornhold', 'town', 1, '[]')
    """)
    conn.execute("""
        INSERT INTO npcs (id, name, current_location_id, archetype, image_url, personality, is_quest_giver, is_enemy)
        VALUES ('npc-aldric', 'Aldric', 'rusty-tankard', 'innkeeper', '/static/aldric.png', 'Friendly', 1, 0),
               ('npc-marta', 'Marta', 'rusty-tankard', 'serving', '/static/marta.png', 'Shy', 0, 0)
    """)
    conn.commit()
    yield conn
    conn.close()


def test_map_returns_full_npc_details(db_conn):
    """GET /api/map/data includes full NPC details (archetype, image_url, personality, flags)."""
    # Force connection override since get_map_data creates its own
    result = get_map_data()
    # Find location rusty-tankard
    loc = next((l for l in result['locations'] if l['id'] == 'rusty-tankard'), None)
    assert loc is not None, "rusty-tankard missing"
    npcs = loc['npcs']
    assert len(npcs) == 2
    for npc in npcs:
        assert 'id' in npc
        assert 'name' in npc
        assert 'archetype' in npc, "Missing archetype in npc summary"
        assert 'image_url' in npc, "Missing image_url"
        assert 'personality' in npc, "Missing personality"
        assert 'is_quest_giver' in npc, "Missing is_quest_giver flag"
    # Spot-check Aldric
    aldric = next(n for n in npcs if n['id'] == 'npc-aldric')
    assert aldric['archetype'] == 'innkeeper'
    assert aldric['is_quest_giver'] == 1
