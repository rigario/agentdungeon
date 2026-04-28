"""Tests for intent router target normalization (P0 freeze blocker 88880a54).

Validates that natural language targets like "Thornhold town square" or
"Aldric the Innkeeper" are mapped to canonical game IDs before being
sent to the rules server.
"""

import pytest
from unittest.mock import MagicMock
from app.services.intent_router import IntentRouter, Intent
from app.contract import IntentType


def make_intent(action_type: str, target: str):
    """Create a minimal Intent dataclass instance for testing."""
    return Intent(
        type=IntentType.MOVE if action_type == "move" else IntentType.INTERACT
        if action_type == "interact"
        else IntentType.TALK,
        action_type=action_type,
        target=target,
        details={"action_type": action_type, "_original_msg": f"go to {target}"},
        confidence=0.8,
    )


def make_world_context(locations=None, npcs=None, current_location=None):
    """Build a minimal world_context dict."""
    return {
        "locations": locations or [],
        "npcs": npcs or [],
        "current_location": current_location or {},
    }


class TestTargetNormalization:
    """Test _normalize_target method normalizes aliases to canonical IDs."""

    def test_move_exact_location_id_match(self):
        """Exact ID match returns canonical ID."""
        intent = make_intent("move", "thornhold")
        wc = make_world_context(
            locations=[{"id": "thornhold", "name": "Thornhold"}]
        )
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "thornhold"

    def test_move_location_name_substring_in_target(self):
        """'thornhold town square' → 'thornhold' (ID is substring of target)."""
        intent = make_intent("move", "Thornhold town square")
        wc = make_world_context(
            locations=[{"id": "thornhold", "name": "Thornhold"}]
        )
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "thornhold"

    def test_move_target_substring_of_location_name(self):
        """'town square' → 'thornhold' if location name contains target."""
        intent = make_intent("move", "town square")
        wc = make_world_context(
            locations=[{"id": "thornhold", "name": "Thornhold Town Square"}]
        )
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        # "town square" is part of "Thornhold Town Square" but we should
        # still prefer the canonical ID since the location name contains target
        assert result == "thornhold"

    def test_move_connection_location_normalization(self):
        """Move to connected location via display name works."""
        intent = make_intent("move", "south road")
        current_loc = {
            "id": "rusty-tankard",
            "name": "The Rusty Tankard",
            "connections": [
                {"id": "south-road", "name": "South Road"}
            ],
        }
        wc = make_world_context(
            locations=[
                {"id": "rusty-tankard", "name": "The Rusty Tankard"},
                {"id": "south-road", "name": "South Road"},
            ],
            current_location=current_loc,
        )
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "south-road"

    def test_interact_npc_exact_name_match(self):
        """'Marta the Merchant' → 'marta' (canonical NPC id)."""
        intent = make_intent("interact", "Marta the Merchant")
        wc = make_world_context(
            npcs=[
                {"id": "marta", "name": "Marta the Merchant", "archetype": "merchant"},
                {"id": "drenna", "name": "Sister Drenna", "archetype": "cult_doubter"},
            ],
            current_location={"id": "thornhold", "npcs_present": ["marta"]},
        )
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "marta"

    def test_interact_npc_partial_name_match(self):
        """'aldric' → 'aldric' (fragment matches 'Aldric the Innkeeper')."""
        intent = make_intent("interact", "aldric")
        wc = make_world_context(
            npcs=[
                {"id": "aldric", "name": "Aldric the Innkeeper", "archetype": "innkeeper"},
            ],
            current_location={"id": "rusty-tankard", "npcs_present": ["aldric"]},
        )
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "aldric"

    def test_interact_npc_no_match_returns_original(self):
        """Unknown NPC target passes through unchanged."""
        intent = make_intent("interact", "Unknown Person")
        wc = make_world_context(
            npcs=[
                {"id": "marta", "name": "Marta the Merchant"},
            ],
            current_location={"id": "thornhold", "npcs_present": ["marta"]},
        )
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "Unknown Person"

    def test_talk_intent_normalizes_npc(self):
        """TALK action type also normalizes."""
        intent = Intent(
            type=IntentType.TALK,
            action_type="interact",
            target="Sister Drenna",
            details={"action_type": "interact"},
            confidence=0.8,
        )
        wc = make_world_context(
            npcs=[
                {"id": "drenna", "name": "Sister Drenna"},
            ],
            current_location={"id": "thornhold"},
        )
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "drenna"

    def test_move_without_world_context_returns_original(self):
        """No world_context → target unchanged."""
        intent = make_intent("move", "Thornhold")
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, {})
        assert result == "Thornhold"

    def test_normalization_case_insensitive(self):
        """Match should be case-insensitive."""
        intent = make_intent("move", "THORNHOLD TOWN SQUARE")
        wc = make_world_context(
            locations=[{"id": "thornhold", "name": "Thornhold"}]
        )
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "thornhold"

    def test_move_uses_top_level_connections_when_current_location_missing(self):
        """Move target matches against top-level world_context.connections (from turn/latest).

        This covers case where world_context from turn/latest has connections at top-level
        but not nested under current_location.connections. E.g., south-road turn world_context.
        """
        intent = make_intent("move", "Thornhold town square")
        wc = {
            "locations": [],  # empty
            "current_location": {},  # no connections nested
            "connections": ["thornhold", "crossroads"],  # top-level string IDs
        }
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "thornhold"

    def test_move_uses_top_level_connections_dicts(self):
        """Top-level connections can also be dicts with id/name."""
        intent = make_intent("move", "Crossroads")
        wc = {
            "locations": [],
            "connections": [
                {"id": "thornhold", "name": "Thornhold"},
                {"id": "crossroads", "name": "The Crossroads"},
            ],
        }
        router = IntentRouter(rules_client=MagicMock())
        result = router._normalize_target(intent, wc)
        assert result == "crossroads"

