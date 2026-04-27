"""Regression tests for the unified D20 scene context service."""

import json
import sqlite3
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import scene_context


class FakeDB:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, *args, **kwargs):
        return self.conn.execute(*args, **kwargs)

    def close(self):
        pass


def _setup_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE characters (
            id TEXT PRIMARY KEY,
            name TEXT,
            level INTEGER,
            hp_current INTEGER,
            hp_max INTEGER,
            location_id TEXT,
            campaign_id TEXT DEFAULT 'default',
            game_hour INTEGER DEFAULT 8,
            mark_of_dreamer_stage INTEGER DEFAULT 0
        );
        CREATE TABLE locations (
            id TEXT PRIMARY KEY,
            name TEXT,
            biome TEXT,
            description TEXT,
            hostility_level INTEGER DEFAULT 0,
            encounter_threshold INTEGER DEFAULT 10,
            recommended_level INTEGER DEFAULT 1,
            connected_to TEXT DEFAULT '[]',
            image_url TEXT,
            campaign_id TEXT DEFAULT 'default'
        );
        CREATE TABLE narrative_flags (
            character_id TEXT,
            flag_key TEXT,
            flag_value TEXT
        );
        CREATE TABLE character_quests (
            character_id TEXT,
            quest_id TEXT,
            quest_title TEXT,
            status TEXT,
            accepted_at TEXT
        );
        CREATE TABLE combats (
            id TEXT PRIMARY KEY,
            character_id TEXT,
            encounter_name TEXT,
            round INTEGER,
            turn_index INTEGER,
            status TEXT,
            started_at TEXT
        );
        CREATE TABLE combat_participants (
            combat_id TEXT,
            participant_type TEXT
        );
        CREATE TABLE fronts (
            id TEXT PRIMARY KEY,
            name TEXT,
            danger_type TEXT
        );
        CREATE TABLE character_fronts (
            character_id TEXT,
            front_id TEXT,
            current_portent_index INTEGER,
            is_active INTEGER,
            advanced_at TEXT
        );
        CREATE TABLE doom_clock (
            character_id TEXT PRIMARY KEY,
            total_ticks INTEGER,
            portents_triggered INTEGER,
            is_active INTEGER,
            last_tick_at TEXT
        );
        """
    )
    conn.execute(
        "INSERT INTO characters (id, name, level, hp_current, hp_max, location_id, campaign_id, game_hour, mark_of_dreamer_stage) "
        "VALUES ('char-1', 'Freeze Hero', 1, 12, 12, 'rusty-tankard', 'default', 8, 1)"
    )
    conn.execute(
        "INSERT INTO locations (id, name, biome, description, hostility_level, connected_to, campaign_id) VALUES "
        "('rusty-tankard', 'The Rusty Tankard', 'town', 'A warm tavern', 0, '[\"south-road\"]', 'default'),"
        "('south-road', 'South Road', 'road', 'A muddy road', 2, '[]', 'default')"
    )
    conn.execute(
        "INSERT INTO narrative_flags VALUES ('char-1', 'aldric_met', 'true')"
    )
    conn.execute(
        "INSERT INTO character_quests VALUES ('char-1', 'quest-1', 'Ask About the Hollow Eye', 'accepted', '2026-04-27')"
    )
    conn.execute(
        "INSERT INTO fronts VALUES ('dreaming_hunger', 'The Dreaming Hunger', 'doom')"
    )
    conn.execute(
        "INSERT INTO character_fronts VALUES ('char-1', 'dreaming_hunger', 1, 1, '2026-04-27')"
    )
    conn.execute(
        "INSERT INTO doom_clock VALUES ('char-1', 3, 1, 1, '2026-04-27')"
    )
    conn.commit()
    return conn


def test_scene_context_returns_bounded_affordance_payload(monkeypatch):
    conn = _setup_conn()
    monkeypatch.setattr(scene_context, "get_db", lambda: FakeDB(conn))
    monkeypatch.setattr(
        scene_context,
        "get_npcs_at_location",
        lambda location_id: [
            {
                "id": "npc-aldric",
                "name": "Aldric the Innkeeper",
                "archetype": "innkeeper",
                "is_quest_giver": 1,
                "is_spirit": 0,
                "is_enemy": 0,
                "personality": "Warm but wary",
                "image_url": "/static/aldric.png",
            }
        ],
    )
    monkeypatch.setattr(
        scene_context,
        "get_available_npcs_at_location",
        lambda location_id, character_context: {
            "all_npcs": [],
            "available": [{"id": "npc-aldric", "availability_reason": "All conditions met"}],
            "unavailable": [],
        },
    )
    monkeypatch.setattr(scene_context, "get_key_items", lambda character_id, conn: [{"id": "kols_journal", "name": "Kol's Journal"}])
    monkeypatch.setattr(scene_context, "get_hub_rumors", lambda character_id, location_id: [{"key": "aldric_warning", "sentiment": 1}])

    ctx = scene_context.get_scene_context("char-1")

    assert ctx["character_id"] == "char-1"
    assert ctx["current_location"]["id"] == "rusty-tankard"
    assert ctx["exits"][0]["id"] == "south-road"
    assert ctx["npcs_here"][0]["id"] == "npc-aldric"
    assert ctx["npcs_here"][0]["available"] is True
    assert ctx["narrative_flags"] == {"aldric_met": "true"}
    assert ctx["key_items"][0]["id"] == "kols_journal"
    assert ctx["active_quests"][0]["quest_id"] == "quest-1"
    assert ctx["fronts"][0]["id"] == "dreaming_hunger"
    assert ctx["doom_clock"]["portents_triggered"] == 1
    assert any(a["action_type"] == "interact" and a["target"] == "npc-aldric" for a in ctx["allowed_actions"])
    assert any(a["action_type"] == "move" and a["target"] == "south-road" for a in ctx["allowed_actions"])

    conn.close()
