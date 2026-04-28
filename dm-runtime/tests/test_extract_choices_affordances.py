"""Tests for synthesis._extract_choices — scene affordances → player choices.

Validates that allowed_actions from world_context are properly converted into
player-facing choices: talk to NPCs, quest actions, rest, look, explore, etc.
"""

import pytest
from app.services.synthesis import _extract_choices


class TestExtractChoicesFromAllowedActions:
    """Test _extract_choices builds choices from world_context.allowed_actions."""

    def test_tavern_multi_npc_talk_choices(self):
        """Rusty Tankard with multiple available NPCs should offer Talk choices per NPC."""
        world_context = {
            "npcs_here": [
                {"id": "npc_bartender", "name": "Gren the Bartender"},
                {"id": "npc_adventurer", "name": "Lyra the Adventurer"},
                {"id": "npc_stranger", "name": "Mysterious Stranger"},
            ],
            "allowed_actions": [
                {"action_type": "interact", "target": "npc_bartender", "confidence": 0.9, "reason": "NPC available: Gren the Bartender"},
                {"action_type": "interact", "target": "npc_adventurer", "confidence": 0.9, "reason": "NPC available: Lyra the Adventurer"},
                {"action_type": "interact", "target": "npc_stranger", "confidence": 0.8, "reason": "NPC available: Mysterious Stranger"},
                {"action_type": "look", "target": None, "confidence": 1.0, "reason": "Can observe surroundings"},
            ],
            "connections": [{"id": "exit_street", "name": "Whisperwood Edge", "description": "The forest path"}],
        }
        server_result = {}  # No explicit choices from server

        choices = _extract_choices(server_result, world_context)

        # Should have: 3 talk choices + look + move = 6 choices
        talk_choices = [c for c in choices if c["id"].startswith("interact_")]
        assert len(talk_choices) == 3, f"Expected 3 talk choices, got {len(talk_choices)}: {talk_choices}"

        labels = {c["label"] for c in talk_choices}
        assert "Talk to Gren the Bartender" in labels
        assert "Talk to Lyra the Adventurer" in labels
        assert "Talk to Mysterious Stranger" in labels

        # Verify stable IDs
        ids = {c["id"] for c in talk_choices}
        assert ids == {"interact_npc_bartender", "interact_npc_adventurer", "interact_npc_stranger"}

        # Verify look choice exists
        look = [c for c in choices if c["id"] == "look"]
        assert len(look) == 1
        assert look[0]["label"] == "Look around"

        # Verify movement choice still present from connections
        move = [c for c in choices if c["id"] == "exit_street"]
        assert len(move) == 1

    def test_quest_choices_from_active_quests(self):
        """Active quests should generate quest advancement choices."""
        world_context = {
            "active_quests": [
                {"quest_id": "quest_drenna", "title": "Sister Drenna's Missing Daughter", "status": "active"},
                {"quest_id": "quest_moonpetal", "title": "Warden of Moonpetal", "status": "active"},
            ],
            "allowed_actions": [
                {"action_type": "quest", "target": "quest_drenna", "confidence": 0.7, "reason": "1 active quest(s) can be advanced"},
                {"action_type": "quest", "target": "quest_moonpetal", "confidence": 0.7, "reason": "1 active quest(s) can be advanced"},
                {"action_type": "look", "target": None, "confidence": 1.0, "reason": "Can observe surroundings"},
            ],
            "connections": [],
        }
        choices = _extract_choices({}, world_context)

        quest_choices = [c for c in choices if c["id"].startswith("quest_")]
        assert len(quest_choices) == 2

        labels = {c["label"] for c in quest_choices}
        assert "Sister Drenna's Missing Daughter" in labels
        assert "Warden of Moonpetal" in labels

        ids = {c["id"] for c in quest_choices}
        assert "quest_quest_drenna" in ids
        assert "quest_quest_moonpetal" in ids

    def test_rest_choice_when_allowed(self):
        """Rest should appear as a choice when allowed by biome/safety."""
        world_context = {
            "allowed_actions": [
                {"action_type": "rest", "target": None, "confidence": 0.9, "reason": "Safe location (town) permits rest"},
                {"action_type": "look", "target": None, "confidence": 1.0, "reason": "Can observe surroundings"},
            ],
            "connections": [],
        }
        choices = _extract_choices({}, world_context)

        rest = [c for c in choices if c["id"] == "rest"]
        assert len(rest) == 1
        assert rest[0]["label"] == "Rest here"
        assert "Safe location" in rest[0]["description"]

    def test_look_and_explore_choices(self):
        """Look and explore should appear as explicit choices."""
        world_context = {
            "allowed_actions": [
                {"action_type": "look", "target": None, "confidence": 1.0, "reason": "Can observe surroundings"},
                {"action_type": "explore", "target": None, "confidence": 0.8, "reason": "Can search location"},
            ],
            "connections": [],
        }
        choices = _extract_choices({}, world_context)

        look = [c for c in choices if c["id"] == "look"]
        assert len(look) == 1 and look[0]["label"] == "Look around"

        explore = [c for c in choices if c["id"] == "explore"]
        assert len(explore) == 1 and explore[0]["label"] == "Explore area"

    def test_object_inspect_from_key_items(self):
        """Key items should produce 'Inspect' choices via allowed_actions."""
        # Note: inspectable objects come from key_items; allowed_actions would include
        # action_type='interact' with target = item_id for inspectable objects.
        # Should NOT use "Talk to" for items; should use "Inspect <item name>".
        world_context = {
            "key_items": [
                {"id": "item_kols_journal", "name": "Kol's Journal", "description": "A weathered ledger"},
            ],
            "allowed_actions": [
                {"action_type": "interact", "target": "item_kols_journal", "confidence": 0.8, "reason": "Key item in inventory"},
            ],
            "npcs_here": [],
            "connections": [],
        }
        choices = _extract_choices({}, world_context)

        # Should produce an inspect choice with id 'inspect_item_kols_journal'
        inspect = [c for c in choices if c["id"] == "inspect_item_kols_journal"]
        assert len(inspect) == 1, f"Expected inspect choice, got: {choices}"
        assert "Journal" in inspect[0]["label"]
        assert inspect[0]["label"].startswith("Inspect")

    def test_npc_unavailable_not_in_choices(self):
        """NPCs marked unavailable should NOT appear as interact choices."""
        # This depends on world_context.npcs_here filtering unavailable NPCs,
        # AND allowed_actions not including interact for them.
        world_context = {
            "npcs_here": [
                {"id": "npc_asleep", "name": "Sleeping Guard", "available": False},
                {"id": "npc_awake", "name": "Daywatch Knight", "available": True},
            ],
            "allowed_actions": [
                # Only the available NPC appears in allowed_actions
                {"action_type": "interact", "target": "npc_awake", "confidence": 0.9, "reason": "NPC available"},
            ],
            "connections": [],
        }
        choices = _extract_choices({}, world_context)

        interact_ids = [c["id"] for c in choices if c["id"].startswith("interact_")]
        assert "interact_npc_awake" in interact_ids
        assert "interact_npc_asleep" not in interact_ids

    def test_combat_choices_override_affordances(self):
        """In combat, choices should be the fixed combat set, NOT allowed_actions."""
        world_context = {
            "allowed_actions": [
                {"action_type": "interact", "target": "npc_bartender", "confidence": 0.9, "reason": "NPC available"},
            ],
            "connections": [],
        }
        # Simulate a combat server_result
        server_result = {
            "combat": {"combat_id": "abc", "round": 1},
            "enemies": [{"name": "Goblin", "hp": 5}],
        }

        choices = _extract_choices(server_result, world_context)

        # Should be the fixed combat choices
        ids = {c["id"] for c in choices}
        assert ids == {"attack", "flee", "cast", "use_item", "defend"}

    def test_deduplication_move_vs_allowed_actions(self):
        """Move from allowed_actions should be skipped; movement from connections only."""
        world_context = {
            "connections": [
                {"id": "exit_a", "name": "Location A"},
                {"id": "exit_b", "name": "Location B"},
            ],
            "allowed_actions": [
                {"action_type": "move", "target": "exit_a", "confidence": 0.95, "reason": "Exit: Location A"},
            ],
        }
        choices = _extract_choices({}, world_context)

        move_ids = [c["id"] for c in choices if c["id"] in ("exit_a", "exit_b")]
        assert len(move_ids) == 2  # Only from connections; duplicate move skipped

    def test_unknown_action_type_handled(self):
        """Unknown action_type should still produce a generic choice."""
        world_context = {
            "allowed_actions": [
                {"action_type": "custom_action", "target": None, "confidence": 0.5, "reason": "Custom thing"},
            ],
        }
        choices = _extract_choices({}, world_context)

        custom = [c for c in choices if c["id"] == "custom_action"]
        assert len(custom) == 1
        assert custom[0]["label"] == "Custom Action"

    def test_server_provided_choices_take_precedence(self):
        """If server_result has choices, return them directly without augmentation."""
        server_result = {
            "choices": [
                {"id": "accept_quest", "label": "Accept Quest", "description": "Say yes"},
            ]
        }
        world_context = {"allowed_actions": []}
        choices = _extract_choices(server_result, world_context)

        # Should return ONLY the server-provided choices, not add allowed_actions augmentations
        assert len(choices) == 1
        assert choices[0]["id"] == "accept_quest"


class TestSceneAffordancesIntegration:
    """Integration-style tests combining multiple affordance sources."""

    def test_tavern_with_quest_and_rest(self):
        """Tavern scene: NPC talk + quest + rest + movement all present."""
        world_context = {
            "npcs_here": [
                {"id": "npc_quentin", "name": "Quentin the Questgiver"},
            ],
            "active_quests": [
                {"quest_id": "find_potion", "title": "Find the Healing Potion"},
            ],
            "connections": [{"id": "road_west", "name": "West Road"}],
            "allowed_actions": [
                {"action_type": "interact", "target": "npc_quentin", "confidence": 0.9, "reason": "NPC available"},
                {"action_type": "quest", "target": "find_potion", "confidence": 0.7, "reason": "Quest can be advanced"},
                {"action_type": "rest", "target": None, "confidence": 0.9, "reason": "Safe location permits rest"},
                {"action_type": "look", "target": None, "confidence": 1.0, "reason": "Can observe"},
            ],
        }
        choices = _extract_choices({}, world_context)

        ids = {c["id"] for c in choices}
        # Expected: interact_npc_quentin, quest_find_potion, rest, look, move road_west
        expected = {"interact_npc_quentin", "quest_find_potion", "rest", "look", "road_west"}
        assert ids == expected, f"Missing or extra IDs: got {ids}, expected {expected}"
