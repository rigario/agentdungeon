"""Tests for approval gate logic (task 24d4ed65).

Covers unit tests for evaluate_approval_gate gate categories.
Integration tests via gate_action wrapper are covered by smoke tests.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.approval_gate import evaluate_approval_gate


class TestEvaluateApprovalGate:
    def test_no_gate_healthy_character(self):
        char = {
            "id": "c1",
            "hp_current": 30,
            "hp_max": 30,
            "level": 3,
            "approval_config": {},
        }
        result = evaluate_approval_gate(char, "move", location=None)
        assert result["needs_approval"] is False
        assert result["reasons"] == []
        assert "context" in result

    def test_low_hp_gate_triggers(self):
        char = {
            "id": "c1",
            "hp_current": 10,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"hp_threshold_pct": 25},
        }
        result = evaluate_approval_gate(char, "explore", location=None)
        assert result["needs_approval"] is True
        assert any("HP" in r for r in result["reasons"])

    def test_low_hp_respects_threshold(self):
        char = {
            "id": "c1",
            "hp_current": 20,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"hp_threshold_pct": 25},
        }
        # At 40%, should NOT gate
        result = evaluate_approval_gate(char, "move", location=None)
        assert result["needs_approval"] is False

    def test_high_level_spell_gate(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 5,
            "approval_config": {"spell_level_min": 3},
        }
        result = evaluate_approval_gate(char, "cast", details={"spell_level": 4})
        assert result["needs_approval"] is True
        assert any("4 >= 3" in r for r in result["reasons"])

    def test_low_level_spell_no_gate(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"spell_level_min": 3},
        }
        result = evaluate_approval_gate(char, "cast", details={"spell_level": 2})
        assert result["needs_approval"] is False

    def test_dangerous_area_gate(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"dangerous_area_entry": True},
        }
        loc = {"name": "Dragon's Lair", "recommended_level": 6}
        result = evaluate_approval_gate(char, "move", location=loc)
        assert result["needs_approval"] is True
        assert any("Dangerous area" in r for r in result["reasons"])

    def test_safe_area_no_gate(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 5,
            "approval_config": {"dangerous_area_entry": True},
        }
        loc = {"name": "Rusty Tankard", "recommended_level": 1}
        result = evaluate_approval_gate(char, "move", location=loc)
        assert result["needs_approval"] is False

    def test_named_npc_interaction_gate(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"named_npc_interaction": True},
        }
        result = evaluate_approval_gate(char, "interact", details={"is_named": True})
        assert result["needs_approval"] is True
        assert "Named/story NPC" in result["reasons"]

    def test_regular_npc_no_gate(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"named_npc_interaction": False},
        }
        result = evaluate_approval_gate(char, "interact", details={"is_named": False})
        assert result["needs_approval"] is False

    def test_quest_accept_gate(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"quest_acceptance": True},
        }
        result = evaluate_approval_gate(char, "quest_accept")
        assert result["needs_approval"] is True
        assert "Quest acceptance" in result["reasons"]

    def test_moral_choice_gate(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"moral_choice": True},
        }
        result = evaluate_approval_gate(char, "moral_choice")
        assert result["needs_approval"] is True

    def test_flee_combat_gate_when_enabled(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"flee_combat": True},
        }
        result = evaluate_approval_gate(char, "flee")
        assert result["needs_approval"] is True
        assert "Fleeing combat" in result["reasons"]

    def test_flee_combat_no_gate_when_disabled(self):
        char = {
            "id": "c1",
            "hp_current": 50,
            "hp_max": 50,
            "level": 3,
            "approval_config": {"flee_combat": False},
        }
        result = evaluate_approval_gate(char, "flee")
        assert result["needs_approval"] is False

# Run via: pytest tests/test_approval_gate.py -v
