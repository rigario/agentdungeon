"""
from pathlib import Path
Regression tests for deterministic NPC selection logic (task 8084708d).

Unit tests: exercise extracted routing logic (mock-only, fast).
Integration tests: hit real FastAPI endpoints with an in-memory DB.
"""

import json
import sqlite3
import sys
import os
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# Mock NPC data and pure-Python routing simulation (unit tests)
# =============================================================================

NPC_ALDRIC = {
    "id": "npc-aldric",
    "name": "Aldric the Innkeeper",
    "archetype": "innkeeper",
}
NPC_MARTA = {
    "id": "npc-marta",
    "name": "Marta the Merchant",
    "archetype": "merchant",
}
NPC_SER_MAREN = {
    "id": "npc-ser-maren",
    "name": "Ser Maren",
    "archetype": "guard",
}


def simulate_npc_routing(npcs):
    npc = None
    if npc is None:
        if len(npcs) > 1:
            npc_choices = [
                {
                    "id": n["id"],
                    "label": n["name"],
                    "description": f"Talk to {n['name']} ({n['archetype']}).",
                }
                for n in npcs
            ]
            return {
                "success": True,
                "narration": "Several people are here. Who would you like to speak with?",
                "choices": npc_choices,
                "events": [
                    {
                        "type": "npc_selection_required",
                        "available_npcs": [n["id"] for n in npcs],
                    }
                ],
            }
        else:
            npc = npcs[0]
            return {
                "success": True,
                "narration": f"You approach {npc['name']}.",
                "npc": npc,
            }


def test_single_npc_hub_is_deterministic():
    result = simulate_npc_routing([NPC_ALDRIC])
    assert "npc" in result
    assert result["npc"]["id"] == "npc-aldric"
    assert "Aldric" in result["narration"]
    assert "choices" not in result


def test_multi_npc_hub_returns_explicit_choices():
    npcs = [NPC_MARTA, NPC_SER_MAREN]
    result = simulate_npc_routing(npcs)
    assert "choices" in result
    assert isinstance(result["choices"], list)
    assert len(result["choices"]) == 2
    labels = {c["label"] for c in result["choices"]}
    assert "Marta the Merchant" in labels
    assert "Ser Maren" in labels
    for c in result["choices"]:
        assert "id" in c and c["id"] in ("npc-marta", "npc-ser-maren")
        assert "description" in c
        assert "Talk to" in c["description"]
    assert result.get("success") is True
    ev_types = [e["type"] for e in result.get("events", [])]
    assert "npc_selection_required" in ev_types


def test_multi_npc_hub_choice_ids_match_npcs():
    npcs = [NPC_MARTA, NPC_SER_MAREN, NPC_ALDRIC]
    result = simulate_npc_routing(npcs)
    choice_ids = {c["id"] for c in result["choices"]}
    npc_ids = {n["id"] for n in npcs}
    assert choice_ids == npc_ids


# =============================================================================
# Integration tests — real FastAPI endpoint + in-memory DB
# =============================================================================

@pytest.fixture(scope="function")
def in_memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    schema_path = str(Path(__file__).resolve().parents[1] / "app/services/database_schema.sql")
    with open(schema_path, "r") as f:
        conn.executescript(f.read())
    conn.execute("INSERT INTO campaigns (id, name) VALUES ('default', 'Default Campaign')")
    conn.execute(
        "INSERT INTO locations (id, name, biome, hostility_level, connected_to) "
        "VALUES ('rusty-tankard', 'Rusty Tankard', 'town', 1, '[]')"
    )
    npcs_data = [
        {
            "id": "npc-aldric",
            "name": "Aldric the Innkeeper",
            "archetype": "innkeeper",
            "biome": "town",
            "current_location_id": "rusty-tankard",
            "default_location_id": "rusty-tankard",
            "movement_rules_json": json.dumps({"can_visit": ["rusty-tankard"], "schedule": "static"}),
        },
        {
            "id": "npc-marta",
            "name": "Marta the Merchant",
            "archetype": "merchant",
            "biome": "town",
            "current_location_id": "rusty-tankard",
            "default_location_id": "rusty-tankard",
            "movement_rules_json": json.dumps({"can_visit": ["rusty-tankard"], "schedule": "static"}),
        },
    ]
    for n in npcs_data:
        conn.execute(
            """INSERT INTO npcs (
                id, name, archetype, biome, current_location_id, default_location_id,
                movement_rules_json, campaign_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'default')""",
            (n["id"], n["name"], n["archetype"], n["biome"],
             n["current_location_id"], n["default_location_id"], n["movement_rules_json"]),
        )
    conn.commit()
    yield conn
    conn.close()


def _mock_get_db(conn):
    def _inner():
        yield conn
    return _inner


@pytest.fixture(scope="function")
def client_with_db(in_memory_db, monkeypatch):
    try:
        import app.services.database as db_module
        import app.routers.actions as actions_module
        import app.routers.characters as chars_module
        import app.routers.map as map_module
        from app.main import app as rules_app
    except ImportError as e:
        pytest.skip(f"Skipping integration tests: missing dependency ({e})")

    mock_gen = _mock_get_db(in_memory_db)
    monkeypatch.setattr(db_module, "get_db", mock_gen)
    monkeypatch.setattr(actions_module, "get_db", mock_gen)
    monkeypatch.setattr(chars_module, "get_db", mock_gen)
    monkeypatch.setattr(map_module, "get_db", mock_gen)

    with TestClient(rules_app) as client:
        yield client


@pytest.fixture(scope="function")
def seeded_character(in_memory_db):
    char_id = "test-interact-char"
    char_data = {
        "id": char_id,
        "player_id": "test-player",
        "name": "Test Character",
        "race": "Human",
        "class": "Fighter",
        "level": 1,
        "hp_current": 10,
        "hp_max": 10,
        "hp_temporary": 0,
        "ac_value": 14,
        "ac_description": "Leather armor",
        "ability_scores_json": json.dumps({"str": 16, "dex": 14, "con": 14, "int": 10, "wis": 12, "cha": 8}),
        "speed_json": json.dumps({"Walk": 30}),
        "skills_json": json.dumps({}),
        "saving_throws_json": json.dumps({}),
        "languages_json": json.dumps(["Common"]),
        "weapon_proficiencies_json": json.dumps([]),
        "armor_proficiencies_json": json.dumps([]),
        "equipment_json": json.dumps([]),
        "treasure_json": json.dumps({"gp": 10, "sp": 0, "cp": 0, "pp": 0, "ep": 0}),
        "spell_slots_json": json.dumps({}),
        "spells_json": json.dumps([]),
        "feats_json": json.dumps([]),
        "conditions_json": json.dumps({}),
        "mark_of_dreamer_stage": 0,
        "xp": 0,
        "location_id": "rusty-tankard",
        "campaign_id": "default",
        "sheet_json": json.dumps({"name": "Test Character", "race": "Human", "classes": [{"name": "Fighter"}]}),
        "sheet_signature": "sha256:test",
        "approval_config": json.dumps({}),
        "aggression_slider": 50,
        "user_id": None,
        "agent_id": None,
        "agent_permission_level": "none",
        "is_archived": 0,
        "archived_at": None,
    }
    columns = ", ".join(char_data.keys())
    placeholders = ", ".join(["?"] * len(char_data))
    sql = f"INSERT INTO characters ({columns}) VALUES ({placeholders})"
    in_memory_db.execute(sql, tuple(char_data.values()))
    in_memory_db.commit()
    return char_id


class TestInteractDeterminismWithRealEndpoint:
    """Integration tests: interact endpoint responses through TestClient."""

    def test_single_npc_hub_returns_deterministic_npc(self, client_with_db, seeded_character):
        resp = client_with_db.post(
            f"/characters/{seeded_character}/actions",
            json={"action_type": "interact"}
        )
        assert resp.status_code == 200, f"Response error: {resp.text}"
        data = resp.json()
        assert data["success"] is True
        assert "npc" in data, "Expected single NPC in response"
        assert "choices" not in data, "Single-NPC should not return choices list"
        assert data["npc"]["id"] == "npc-aldric"
        assert "Aldric" in data["narration"]

    def test_multi_npc_hub_returns_choices_not_random(self, client_with_db, seeded_character):
        resp = client_with_db.post(
            f"/characters/{seeded_character}/actions",
            json={"action_type": "interact"}
        )
        assert resp.status_code == 200, f"Response error: {resp.text}"
        data = resp.json()
        assert data["success"] is True
        assert "choices" in data, "Multi-NPC hub must return explicit choices"
        assert isinstance(data["choices"], list)
        labels = {c["label"] for c in data["choices"]}
        assert "Aldric the Innkeeper" in labels
        assert "Marta the Merchant" in labels
        assert "npc" not in data
        event_types = [e["type"] for e in data.get("events", [])]
        assert "npc_selection_required" in event_types

    def test_named_target_selects_exact_npc(self, client_with_db, seeded_character):
        resp = client_with_db.post(
            f"/characters/{seeded_character}/actions",
            json={"action_type": "interact", "target": "Marta"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "npc" in data
        assert data["npc"]["id"] == "npc-marta"
        assert "choices" not in data

    def test_unknown_target_in_multi_npc_returns_choices(self, client_with_db, seeded_character):
        resp = client_with_db.post(
            f"/characters/{seeded_character}/actions",
            json={"action_type": "interact", "target": "someone"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "choices" in data or data.get("success") is False

    def test_interactive_object_takes_precedence_over_npcs(self, client_with_db, seeded_character, in_memory_db):
        in_memory_db.execute("UPDATE characters SET location_id = 'cave-depths' WHERE id = ?", (seeded_character,))
        in_memory_db.execute(
            "INSERT OR REPLACE INTO locations (id, name, biome, hostility_level, connected_to) "
            "VALUES ('cave-depths', 'Cave Depths', 'underground', 3, '[]')"
        )
        in_memory_db.execute(
            """INSERT INTO npcs (id, name, archetype, biome, current_location_id, default_location_id,
                movement_rules_json, campaign_id)
            VALUES ('npc-miner', 'Stubborn Miner', 'miner', 'underground', 'cave-depths', 'cave-depths',
                    '{}', 'default')"""
        )
        in_memory_db.commit()
        resp = client_with_db.post(
            f"/characters/{seeded_character}/actions",
            json={"action_type": "interact", "target": "journal"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "journal" in data["narration"].lower() or data.get("events", [{}])[0].get("object") == "journal"
