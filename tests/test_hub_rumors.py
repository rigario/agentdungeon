"""
Tests for hub_rumorservice — cross-NPC social state (fbe3830a).

Pattern: Set D20_DB_PATH to a temp file, init_db, then use real get_db.
This matches existing test_dm_sessions approach for isolation.
"""

import sys
import os
import tempfile

# Set test database path BEFORE importing app modules
TEST_DB = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
os.environ["D20_DB_PATH"] = TEST_DB.name
TEST_DB.close()

# Add project root to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

import pytest
import sqlite3

from app.services.database import init_db, get_db
from app.services import hub_rumors
from app.services import affinity


# ---------------------------------------------------------------------------
# Fixture: initialize fresh schema + minimal data before each test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_db():
    """Reset DB schema and seed minimal world data for each test."""
    init_db()
    conn = get_db()
    # Seed minimal locations for hubs used in tests
    conn.execute(
        "INSERT OR REPLACE INTO locations (id, name, biome, hostility_level, connected_to) "
        "VALUES "
        "  ('thornhold', 'Thornhold', 'town', 1, '[]'),"
        "  ('rusty-tankard', 'Rusty Tankard', 'town', 1, '[]')"
    )
    # Seed NPCs for Thornhold + Rusty Tankard (covers all test source_npc_id refs)
    conn.execute(
        "INSERT OR REPLACE INTO npcs (id, name, archetype, biome, current_location_id, default_location_id) "
        "VALUES "
        "  ('npc-marta', 'Marta the Merchant', 'merchant', 'town', 'thornhold', 'thornhold'),"
        "  ('npc-ser-maren', 'Ser Maren', 'guard', 'town', 'thornhold', 'thornhold'),"
        "  ('npc-aldric', 'Aldric the Innkeeper', 'innkeeper', 'town', 'rusty-tankard', 'rusty-tankard'),"
        "  ('npc-green-woman', 'The Green Woman', 'spirit', 'forest', 'rusty-tankard', 'rusty-tankard')"
    )
    # Seed a minimal test character (required for hub_rumors FK constraint)
    conn.execute(
        "INSERT OR REPLACE INTO characters ("
        "  id, player_id, name, race, class, level, "
        "  hp_current, hp_max, ac_value, ability_scores_json, location_id"
        ") VALUES (?, ?, ?, ?, ?, 1, 10, 10, 16, '{}', 'thornhold')",
        ("test-char-001", "test-player", "TestHero", "Human", "Fighter")
    )
    conn.commit()
    conn.close()
    yield
    # Teardown: delete temp DB file
    try:
        os.unlink(TEST_DB.name)
    except Exception:
        pass


def _character_id():
    return "test-char-001"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_record_and_get_hub_rumors():
    char_id = _character_id()
    loc = "thornhold"

    is_new = hub_rumors.record_rumor(char_id, loc, "marta_hollow_eye_grudge", -1, "npc-marta")
    assert is_new is True

    rumors = hub_rumors.get_hub_rumors(char_id, loc)
    assert len(rumors) == 1
    assert rumors[0]["rumor_key"] == "marta_hollow_eye_grudge"
    assert rumors[0]["sentiment"] == -1
    assert rumors[0]["spread_count"] == 1

    # Repeat → update
    is_new2 = hub_rumors.record_rumor(char_id, loc, "marta_hollow_eye_grudge", -1, "npc-marta")
    assert is_new2 is False
    r2 = hub_rumors.get_hub_rumors(char_id, loc)
    assert r2[0]["spread_count"] == 2


def test_get_hub_social_state_summary():
    char_id = _character_id()
    loc = "thornhold"
    empty = hub_rumors.get_hub_social_state(char_id, loc)
    assert empty["rumors"] == []
    assert empty["summary_text"] == ""

    hub_rumors.record_rumor(char_id, loc, "aldric_confessed", 1, "npc-aldric")
    hub_rumors.record_rumor(char_id, loc, "marta_hollow_eye_grudge", -1, "npc-marta")
    state = hub_rumors.get_hub_social_state(char_id, loc)
    assert len(state["rumors"]) == 2
    assert len(state["summary_text"]) < 200


def test_get_reaction_modifiers_ser_maren_after_marta_grudge():
    char_id = _character_id()
    loc = "thornhold"
    base = hub_rumors.get_reaction_modifiers(char_id, loc, "npc-ser-maren")
    assert base["affinity_bonus"] == 0

    hub_rumors.record_rumor(char_id, loc, "marta_hollow_eye_grudge", -1, "npc-marta")

    reacted = hub_rumors.get_reaction_modifiers(char_id, loc, "npc-ser-maren")
    assert reacted["affinity_bonus"] == 5
    assert reacted["dialogue_hint"] == "marta_grudge_known"
    assert reacted["tone_modifier"] == "respectful"
