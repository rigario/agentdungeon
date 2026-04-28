"""Unit tests for DM narrator prompt context rendering.

Verifies that narrative_flags and key_items are included in the prompt
when present in world_context. Task 8de0b66a — render narrative state.
"""

import pytest
from app.services.narrator import _build_context_prompt


class TestNarratorContextRendering:
    """Test that narrator prompt includes all required narrative state."""

    def _minimal_world_context(self, narrative_flags=None, key_items=None):
        """Build a minimal world_context for testing."""
        wc = {
            "location": {"name": "Thornhold", "description": "A safe town"},
            "character": {"name": "Bryn", "hp_current": 10, "hp_max": 10},
            "npcs": [],
            "connections": [],
            "front_progression": {},
            "active_quests": [],
            "social_context": {},
        }
        if narrative_flags is not None:
            wc["narrative_flags"] = narrative_flags
        if key_items is not None:
            wc["key_items"] = key_items
        return wc

    def _minimal_server_result(self):
        """Minimal server_result dict."""
        return {"narration": "", "events": [], "dice_log": []}

    def test_narrative_flags_included_when_present(self):
        """Narrative flags appear in prompt when world_context provides them."""
        wc = self._minimal_world_context(
            narrative_flags={"mark_of_dreamer_stage": "2", "del_encounter_fired": "true"}
        )
        prompt = _build_context_prompt(self._minimal_server_result(), {}, wc)
        assert "NARRATIVE FLAGS:" in prompt
        assert "mark_of_dreamer_stage: 2" in prompt
        assert "del_encounter_fired: true" in prompt

    def test_narrative_flags_omitted_when_empty(self):
        """Narrative flags section absent when no flags."""
        wc = self._minimal_world_context(narrative_flags={})
        prompt = _build_context_prompt(self._minimal_server_result(), {}, wc)
        assert "NARRATIVE FLAGS:" not in prompt

    def test_key_items_included_when_present(self):
        """Key items appear in prompt when world_context provides them."""
        wc = self._minimal_world_context(
            key_items=[
                {"id": "moonpetal_seed", "name": "Moonpetal Seed", "description": "A glowing seed"},
                {"id": "seal_fragment", "name": "Seal Fragment", "description": "Part of the ancient seal"},
            ]
        )
        prompt = _build_context_prompt(self._minimal_server_result(), {}, wc)
        assert "KEY ITEMS:" in prompt
        assert "Moonpetal Seed" in prompt
        assert "Seal Fragment" in prompt

    def test_key_items_truncates_description(self):
        """Key item descriptions are truncated to avoid huge prompts."""
        long_desc = "x" * 200
        wc = self._minimal_world_context(
            key_items=[{"id": "test", "name": "Test Item", "description": long_desc}]
        )
        prompt = _build_context_prompt(self._minimal_server_result(), {}, wc)
        assert "Test Item:" in prompt
        # Should be truncated to under 100 chars per line
        item_line = [l for l in prompt.splitlines() if "Test Item:" in l][0]
        assert len(item_line) < 100

    def test_key_items_omitted_when_empty(self):
        """Key items section absent when no items."""
        wc = self._minimal_world_context(key_items=[])
        prompt = _build_context_prompt(self._minimal_server_result(), {}, wc)
        assert "KEY ITEMS:" not in prompt

    def test_comprehensive_context_in_prompt(self):
        """All specified sections (flags, key items, quests, fronts, hub) render together."""
        wc = self._minimal_world_context(
            narrative_flags={"drenna_child_saved": "true", "kol_ally": "false"},
            key_items=[
                {"id": "green_woman_charm", "name": "Charm of the Green Woman", "description": "A talisman"},
            ],
        )
        # Add other sections
        wc["active_quests"] = [{"name": "Save Elara", "status": "active"}]
        wc["front_progression"] = {"name": "Dreaming Hunger", "current_portent": 2, "grim_portents": []}
        wc["social_context"] = {
            "hub_social": {
                "rumors": [{"key": "aldric_confessed", "sentiment": 1, "spread": 2}],
                "summary_text": "Locals speak well of the heroes.",
            }
        }
        prompt = _build_context_prompt(self._minimal_server_result(), {}, wc)
        # Verify all required headers present
        assert "NARRATIVE FLAGS:" in prompt
        assert "KEY ITEMS:" in prompt
        assert "ACTIVE QUESTS:" in prompt
        assert "FRONT:" in prompt
        assert "HUB RUMORS" in prompt or "HUB ATMOSPHERE:" in prompt
