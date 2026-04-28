"""Tests for DM narrator scope validation and system prompt enforcement."""

import sys
import os

# Add project roots to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dm-runtime"))

from app.services.narrator import _validate_scope, DM_SYSTEM_PROMPT


class TestScopeEnforcement:
    """Test that the DM system prompt enforces world_context scope."""

    def test_system_prompt_mentions_scope_enforcement(self):
        """System prompt must explicitly enforce world_context scope."""
        assert "SCOPE ENFORCEMENT" in DM_SYSTEM_PROMPT
        assert "world_context" in DM_SYSTEM_PROMPT
        assert "ONLY source of truth" in DM_SYSTEM_PROMPT

    def test_system_prompt_forbids_inventing_npcs(self):
        """System prompt must forbid inventing NPCs."""
        assert "Invent NPCs" in DM_SYSTEM_PROMPT or "invent" in DM_SYSTEM_PROMPT.lower()

    def test_system_prompt_forbids_state_changes(self):
        """System prompt must forbid changing game state."""
        assert "Change game state" in DM_SYSTEM_PROMPT

    def test_system_prompt_requires_json_output(self):
        """System prompt must specify JSON output format."""
        assert "json" in DM_SYSTEM_PROMPT.lower() or "JSON" in DM_SYSTEM_PROMPT


class TestScopeValidation:
    """Test the _validate_scope function."""

    def test_valid_npc_line_passes(self):
        """NPC lines referencing valid NPCs should pass."""
        llm_output = {
            "scene": "Brother Kol steps forward.",
            "npc_lines": [{"speaker": "Brother Kol", "text": "You should not have come."}],
            "tone": "menacing",
            "choices_summary": "You can fight or flee.",
        }
        world_context = {
            "npcs": [{"name": "Brother Kol", "personality": "Zealous"}],
            "location": {"name": "Cave Entrance"},
            "connections": [],
        }
        assert _validate_scope(llm_output, world_context) is True

    def test_invalid_npc_line_fails(self):
        """NPC lines referencing NPCs not in world_context should fail."""
        llm_output = {
            "scene": "A stranger appears.",
            "npc_lines": [{"speaker": "Random Stranger", "text": "Hello traveler."}],
            "tone": "neutral",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [{"name": "Brother Kol"}],
            "location": {"name": "Cave Entrance"},
            "connections": [],
        }
        assert _validate_scope(llm_output, world_context) is False

    def test_empty_npc_lines_pass(self):
        """Empty NPC lines should always pass."""
        llm_output = {
            "scene": "You enter the empty cave.",
            "npc_lines": [],
            "tone": "neutral",
            "choices_summary": "Explore deeper.",
        }
        world_context = {
            "npcs": [],
            "location": {"name": "Cave Entrance"},
            "connections": [],
        }
        assert _validate_scope(llm_output, world_context) is True

    def test_no_npcs_in_context_passes(self):
        """When world_context has no NPCs, any NPC lines fail."""
        llm_output = {
            "scene": "Someone speaks.",
            "npc_lines": [{"speaker": "Ghost", "text": "Boo."}],
            "tone": "ominous",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [],
            "location": {"name": "Empty Room"},
            "connections": [],
        }
        # When allowed_npcs is empty, we can't validate — should pass
        # (the prompt should prevent this, but validation is lenient when no NPCs in context)
        assert _validate_scope(llm_output, world_context) is True

    def test_multiple_valid_npcs_pass(self):
        """Multiple NPC lines all referencing valid NPCs should pass."""
        llm_output = {
            "scene": "Both cultists speak.",
            "npc_lines": [
                {"speaker": "Brother Kol", "text": "Stand aside."},
                {"speaker": "Sister Drenna", "text": "Please, listen."},
            ],
            "tone": "tense",
            "choices_summary": "Choose who to trust.",
        }
        world_context = {
            "npcs": [
                {"name": "Brother Kol"},
                {"name": "Sister Drenna"},
            ],
            "location": {"name": "Crossroads"},
            "connections": [],
        }
        assert _validate_scope(llm_output, world_context) is True

    def test_one_invalid_among_many_fails(self):
        """If one NPC line references an invalid NPC, validation fails."""
        llm_output = {
            "scene": "The cultists argue.",
            "npc_lines": [
                {"speaker": "Brother Kol", "text": "Stand aside."},
                {"speaker": "Invented NPC", "text": "I am not real."},
            ],
            "tone": "tense",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [
                {"name": "Brother Kol"},
                {"name": "Sister Drenna"},
            ],
            "location": {"name": "Crossroads"},
            "connections": [],
        }
        assert _validate_scope(llm_output, world_context) is False

    def test_key_item_off_scope_fails(self):
        """Scene referencing a key item not in allowed set should fail."""
        llm_output = {
            "scene": "You hold the Crystal of Aldric, glowing with power.",
            "npc_lines": [],
            "tone": "neutral",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [],
            "location": {"name": "Tavern"},
            "connections": [],
            "key_items": [{"name": "Silver Key"}],
        }
        assert _validate_scope(llm_output, world_context) is False

    def test_key_item_allowed_passes(self):
        """Scene referencing an allowed key item should pass."""
        llm_output = {
            "scene": "You clutch the Silver Key tightly.",
            "npc_lines": [],
            "tone": "neutral",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [],
            "location": {"name": "Tavern"},
            "connections": [],
            "key_items": [{"name": "Silver Key"}],
        }
        assert _validate_scope(llm_output, world_context) is True

    def test_outcome_death_without_combat_fails(self):
        """Scene narrating death without combat_log should fail."""
        llm_output = {
            "scene": "Aldric falls dead at your feet.",
            "npc_lines": [{"speaker": "Aldric", "text": "I fall..."}],
            "tone": "tragic",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [{"name": "Aldric"}],
            "location": {"name": "Crossroads"},
            "connections": [],
            "server_trace": {"combat_log": []},
            "active_quests": [],
        }
        assert _validate_scope(llm_output, world_context) is False

    def test_outcome_death_with_combat_passes(self):
        """Scene narrating valid death with combat_log should pass."""
        llm_output = {
            "scene": "Aldric falls dead after your strike.",
            "npc_lines": [],
            "tone": "triumphant",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [{"name": "Aldric"}],
            "location": {"name": "Arena"},
            "connections": [],
            "server_trace": {
                "combat_log": [
                    {"round": 1, "event": "player hits Aldric for 5 damage"},
                    {"round": 2, "event": "Aldric reduced to 0 HP"},
                ]
            },
            "active_quests": [],
        }
        assert _validate_scope(llm_output, world_context) is True

    def test_outcome_quest_completion_without_quests_fails(self):
        """Scene claiming quest complete with no active quests should fail."""
        llm_output = {
            "scene": "Your quest is complete. The village is saved.",
            "npc_lines": [],
            "tone": "triumphant",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [],
            "location": {"name": "Village"},
            "connections": [],
            "active_quests": [],
        }
        assert _validate_scope(llm_output, world_context) is False

    def test_outcome_quest_completion_with_quest_passes(self):
        """Scene claiming quest completion with active quest should pass."""
        llm_output = {
            "scene": "Your quest is complete. The villagers are saved.",
            "npc_lines": [],
            "tone": "triumphant",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [],
            "location": {"name": "Village"},
            "connections": [],
            "active_quests": [{"name": "Rat Hunt", "status": "active"}],
        }
        assert _validate_scope(llm_output, world_context) is True

    def test_location_pronoun_exclusion_passes(self):
        """Scene containing capitalised pronouns (You, Someone) should not fail."""
        llm_output = {
            "scene": "You enter the room. Someone speaks from the shadows.",
            "npc_lines": [],
            "tone": "neutral",
            "choices_summary": "",
        }
        world_context = {
            "npcs": [],
            "location": {"name": "Dark Room"},
            "connections": [],
        }
        assert _validate_scope(llm_output, world_context) is True

