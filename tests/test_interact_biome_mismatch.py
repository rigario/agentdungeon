"""
Regression test for interact query biome-filter bug.

The original bug (ISSUE-003) was that the interact handler queried:
    SELECT * FROM npcs WHERE biome = ? AND current_location_id = ?

This filtered out NPCs whose biome didn't match their assigned location's biome,
causing valid multi-NPC hubs to return "no one to talk to" even when NPCs were present.

The fix: use only location_id filter:
    SELECT * FROM npcs WHERE current_location_id = ?

This test seeds NPCs with biome MISMATCH versus location and verifies that:
- generic interact returns available NPCs
- named target selects the correct NPC even with biome mismatch
"""
import json
import sqlite3
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient


def _mock_get_db(conn):
    def _inner():
        yield conn
    return _inner


@pytest.fixture(scope="function")
def biome_mismatch_db():
    """DB where NPCs have biomes that DON'T match their location's biome.
    This catches regressions where biome filter is added back to the query."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Load schema
    schema_path = "/home/rigario/Projects/rigario-d20/app/services/database_schema.sql"
    with open(schema_path, "r") as f:
        conn.executescript(f.read())

    conn.execute("INSERT INTO campaigns (id, name) VALUES ('default', 'Default Campaign')")

    # LOCATION: biome = 'forest' (mismatched!)
    conn.execute(
        "INSERT INTO locations (id, name, biome, hostility_level, connected_to) "
        "VALUES ('rusty-tankard', 'Rusty Tankard', 'forest', 1, '[]')"
    )

    # NPCs: biome = 'town' (doesn't match location biome 'forest')
    # This reproduces the production deployment where seeded NPC biomes
    # came from SRD/lore while locations had different biome values.
    npcs_data = [
        {
            "id": "npc-aldric",
            "name": "Aldric the Innkeeper",
            "archetype": "innkeeper",
            "biome": "town",        # MISMATCH: location biome = forest
            "current_location_id": "rusty-tankard",
            "default_location_id": "rusty-tankard",
            "movement_rules_json": json.dumps({"can_visit": ["rusty-tankard"], "schedule": "static"}),
        },
        {
            "id": "npc-marta",
            "name": "Marta the Merchant",
            "archetype": "merchant",
            "biome": "town",        # MISMATCH
            "current_location_id": "rusty-tankard",
            "default_location_id": "rusty-tankard",
            "movement_rules_json": json.dumps({"can_visit": ["rusty-tankard"], "schedule": "static"}),
        },
    ]
    for n in npcs_data:
        conn.execute(
            "INSERT INTO npcs (id, name, archetype, biome, current_location_id, "
            "default_location_id, movement_rules_json, campaign_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'default')",
            (n["id"], n["name"], n["archetype"], n["biome"], n["current_location_id"],
             n["default_location_id"], n["movement_rules_json"]),
        )
    conn.commit()
    yield conn
    conn.close()


@pytest.fixture(scope="function")
def client_with_biome_mismatch(biome_mismatch_db, monkeypatch):
    try:
        import app.services.database as db_module
        import app.routers.actions as actions_module
        import app.routers.characters as chars_module
        import app.routers.map as map_module
        from app.main import app as rules_app
    except ImportError as e:
        pytest.skip(f"Skipping biome-mismatch tests: {e}")

    mock_gen = _mock_get_db(biome_mismatch_db)
    monkeypatch.setattr(db_module, "get_db", mock_gen)
    monkeypatch.setattr(actions_module, "get_db", mock_gen)
    monkeypatch.setattr(chars_module, "get_db", mock_gen)
    monkeypatch.setattr(map_module, "get_db", mock_gen)

    with TestClient(rules_app) as client:
        yield client


@pytest.fixture(scope="function")
def biome_mismatch_character(biome_mismatch_db):
    char_id = "test-biome-mismatch-char"
    char_data = {
        "id": char_id,
        "player_id": "test-player",
        "name": "BiomeMismatch",
        "race": "Human",
        "class": "Fighter",
        "level": 1,
        "hp_current": 10,
        "hp_max": 10,
        "hp_temporary": 0,
        "ac_value": 14,
        "ac_description": "Leather",
        "ability_scores_json": json.dumps({"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}),
        "speed_json": json.dumps({"Walk": 30}),
        "skills_json": json.dumps({}),
        "saving_throws_json": json.dumps({}),
        "languages_json": json.dumps(["Common"]),
        "weapon_proficiencies_json": json.dumps([]),
        "armor_proficiencies_json": json.dumps([]),
        "equipment_json": json.dumps([]),
        "treasure_json": json.dumps({"gp": 0, "sp": 0, "cp": 0, "pp": 0, "ep": 0}),
        "spell_slots_json": json.dumps({}),
        "spells_json": json.dumps([]),
        "feats_json": json.dumps([]),
        "conditions_json": json.dumps({}),
        "mark_of_dreamer_stage": 0,
        "xp": 0,
        "location_id": "rusty-tankard",
        "campaign_id": "default",
        "sheet_json": json.dumps({"name": "BiomeMismatch", "classes": [{"name": "Fighter"}]}),
        "sheet_signature": "sha256:test",
        "approval_config": json.dumps({}),
        "aggression_slider": 50,
        "user_id": None,
        "agent_id": None,
        "agent_permission_level": "none",
        "is_archived": 0,
        "archived_at": None,
    }
    cols = ", ".join(char_data.keys())
    phs = ", ".join(["?"] * len(char_data))
    sql = f"INSERT INTO characters ({cols}) VALUES ({phs})"
    biome_mismatch_db.execute(sql, tuple(char_data.values()))
    biome_mismatch_db.commit()
    return char_id


class TestInteractWithBiomeMismatch:
    """Integration test: biome filter regression — NPCs must be found by location only."""

    def test_generic_interact_returns_choices_with_biome_mismatch(self, client_with_biome_mismatch, biome_mismatch_character):
        """Generic 'interact' at multi-NPC hub must return choices even when NPC biome != location biome.
        This would fail with old query: WHERE biome = ? AND current_location_id = ?"""
        resp = client_with_biome_mismatch.post(
            f"/characters/{biome_mismatch_character}/actions",
            json={"action_type": "interact"}
        )
        assert resp.status_code == 200, f"HTTP {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["success"] is True
        # Multi-NPC hub should return choices list, NOT "no one to talk to"
        assert "choices" in data, "Expected choices list in multi-NPC hub; got 'npc' field (single-NPC) or error"
        assert len(data["choices"]) == 2
        labels = {c["label"] for c in data["choices"]}
        assert "Aldric the Innkeeper" in labels
        assert "Marta the Merchant" in labels
        # Must include npc_selection_required event
        event_types = [e["type"] for e in data.get("events", [])]
        assert "npc_selection_required" in event_types

    def test_named_target_works_with_biome_mismatch(self, client_with_biome_mismatch, biome_mismatch_character):
        """Named target (e.g., 'talk to Aldric') must find NPC even when biome mismatches location."""
        resp = client_with_biome_mismatch.post(
            f"/characters/{biome_mismatch_character}/actions",
            json={"action_type": "interact", "target": "Aldric"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        # Named target should return the specific NPC, not choices
        assert "npc" in data
        assert data["npc"]["id"] == "npc-aldric"
        assert "choices" not in data
