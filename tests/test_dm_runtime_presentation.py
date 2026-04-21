"""Regression tests for DM runtime presentation fallbacks."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dm-runtime"))

from app.services.synthesis import _build_passthrough


def test_passthrough_uses_dialogue_template_and_character_state_fallbacks():
    server_result = {
        "narration": "You search the pass but find nothing.",
        "character_state": {"hp_current": 7, "hp_max": 12, "location_id": "mountain-pass"},
    }
    world_context = {
        "npcs": [
            {
                "name": "Torren the Hunter",
                "dialogue": [{"template": "Keep your voice down in these mountains."}],
            }
        ],
        "location": {},
        "connections": [],
    }

    result = _build_passthrough(server_result, {}, world_context)

    assert result["narration"]["npc_lines"][0]["speaker"] == "Torren the Hunter"
    assert result["narration"]["npc_lines"][0]["text"] == "Keep your voice down in these mountains."
    assert result["mechanics"]["hp"] == {"current": 7, "max": 12}
    assert result["mechanics"]["location"] == "mountain-pass"
