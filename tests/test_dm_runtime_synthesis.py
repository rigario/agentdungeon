"""Regression tests for DM runtime synthesis and mechanics normalization."""

import sys
import os

# Add project roots to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dm-runtime"))

from app.services.synthesis import _extract_mechanics, _extract_choices


def test_extract_mechanics_stringifies_dice_log_entries():
    server_result = {
        "dice_log": [
            {"type": "choice", "context": "Choose direction from thornhold", "chosen": "forest-edge"},
            {"type": "d20", "context": "Attack roll", "raw": 17, "modifier": 3, "total": 20},
        ],
        "events": [
            {"type": "travel", "desc": "Traveled to Forest Edge."},
            {"type": "new_location", "desc": "First visit to Forest Edge!"},
        ],
        "xp_end": 25,
        "xp_start": 0,
    }
    world_context = {
        "character": {"hp_current": 9, "hp_max": 12},
        "location": {"id": "forest-edge"},
    }

    mechanics = _extract_mechanics(server_result, world_context)

    assert mechanics["hp"] == {"current": 9, "max": 12}
    assert mechanics["location"] == "forest-edge"
    assert mechanics["xp"] == {"current": 25, "gained": 25}
    assert all(isinstance(x, str) for x in mechanics["what_happened"])
    assert "Traveled to Forest Edge." in mechanics["what_happened"]
    assert any("Attack roll" in x for x in mechanics["what_happened"])


def test_extract_choices_from_asks_and_connections():
    server_result = {
        "asks": [
            {
                "type": "explore_new",
                "description": "You've reached Deep Whisperwood.",
                "options": ["explore", "move_on"],
            }
        ]
    }
    world_context = {
        "connections": [
            {"id": "forest-edge", "name": "Whisperwood Edge"},
            {"id": "cave-entrance", "name": "Whisperwood Cave"},
        ]
    }

    choices = _extract_choices(server_result, world_context)

    labels = [c["label"] for c in choices]
    ids = [c["id"] for c in choices]
    assert "Go to Whisperwood Edge" in labels
    assert "Go to Whisperwood Cave" in labels
    assert "explore" in ids
    assert "move_on" in ids
