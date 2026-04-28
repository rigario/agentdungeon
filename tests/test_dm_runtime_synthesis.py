"""Regression tests for DM runtime synthesis and mechanics normalization."""

import sys
import os

# Add project roots to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dm-runtime"))

import pytest

from app.services.synthesis import _extract_mechanics, _extract_choices, _is_combat_response, synthesize_narration
import app.services.synthesis as synthesis_module


def test_is_combat_response_detects_nested_combat_key():
    """Attack actions wrap combat under 'combat' key — must be detected."""
    server_result = {
        "success": True,
        "narration": "You hit the goblin!",
        "events": [{"type": "attack", "description": "You hit the goblin for 5 damage."}],
        "character_state": {"hp": {"current": 10, "max": 12}},
        "combat": {
            "hp_remaining": 10,
            "victory": False,
            "rounds": 1,
            "events": [{"type": "combat_start", "description": "Combat begins!"}],
        },
    }
    assert _is_combat_response(server_result) is True


def test_is_combat_response_detects_top_level_enemies():
    """Combat/start and combat/act return enemies at top level."""
    server_result = {
        "enemies": [{"name": "Goblin", "hp": 7}],
        "round": 1,
        "combat_over": False,
    }
    assert _is_combat_response(server_result) is True


def test_extract_choices_returns_combat_actions_when_combat_detected():
    """Combat responses must include attack/flee/cast/use_item/defend choices."""
    server_result = {
        "combat": {"enemies": [{"name": "Goblin"}]},
        "events": [],
    }
    world_context = {}  # empty during combat
    choices = _extract_choices(server_result, world_context)
    labels = [c["label"] for c in choices]
    assert "Attack" in labels
    assert "Flee" in labels
    assert "Cast Spell" in labels
    assert "Use Item" in labels
    assert "Defend" in labels


def test_extract_choices_ignores_connections_during_combat():
    """Movement connections should not leak into combat choices."""
    server_result = {
        "combat": {"enemies": [{"name": "Goblin"}]},
        "events": [],
    }
    world_context = {
        "connections": [
            {"id": "forest", "name": "Forest", "description": "Go to Forest"},
        ]
    }
    choices = _extract_choices(server_result, world_context)
    labels = [c["label"] for c in choices]
    # Only combat actions — no movement
    assert "Go to Forest" not in labels
    assert len([l for l in labels if "Go to" in l]) == 0


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


@pytest.mark.asyncio
async def test_synthesize_semantic_guard_returns_noop_without_story_progression():
    intent = {
        "type": "general",
        "details": {
            "_semantic_guard": True,
            "_semantic_guard_reason": "negated_or_refusal_action",
            "_original_msg": "I don't want to go to the woods",
        },
    }
    result = await synthesize_narration({}, intent, {})
    assert "No travel" in result["narration"]["scene"]
    assert result["narration"]["npc_lines"] == []
    assert "Action held" in result["mechanics"]["what_happened"][0]
    assert result["server_trace"]["refusal_reason"] == "semantic_guard_negated_or_refusal_action"
    assert "session_id" not in result


@pytest.mark.asyncio
async def test_synthesize_passthrough_preserves_hermes_session_when_scope_rejected(monkeypatch):
    async def fake_llm_narrate(server_result, intent, world_context, session_id=None):
        return {"_hermes_session_id": "session-proof", "_scope_rejected": True}

    monkeypatch.setattr(synthesis_module, "llm_narrate", fake_llm_narrate)
    result = await synthesize_narration(
        {"narration": "Server-safe narration."},
        {"type": "explore", "details": {}},
        {"location": {"id": "thornhold", "name": "Thornhold"}},
    )

    assert result["narration"]["scene"] == "Server-safe narration."
    assert result["session_id"] == "session-proof"
