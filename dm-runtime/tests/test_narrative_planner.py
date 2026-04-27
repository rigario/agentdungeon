"""Unit tests for DM Narrative Planner — affordance extraction and ambiguity detection.

These tests validate the planner's ability to interpret player messages against
scene affordances without requiring server process. Tests the decision matrix,
keyword extraction, negation guard, absurdity detection, and ambiguity resolution.

Run: pytest dm-runtime/tests/test_narrative_planner.py -v
"""

import pytest
from unittest.mock import Mock, AsyncMock
from app.services.narrative_planner import (
    NarrativePlanner,
    SceneAffordances,
    PlannerDecision,
    AffordancePlannerResult,
)
from app.contract import IntentType


# =============================================================================
# Affordance Extraction Helpers
# =============================================================================

class TestSceneAffordances:
    """_extract_affordances builds correct SceneAffordances from world_context."""

    def test_extracts_available_npcs(self):
        wc = {
            "npcs": [
                {"name": "Aldric", "id": "npc1", "is_available": True, "asleep": False},
                {"name": "Marta", "id": "npc2", "is_available": True, "asleep": False},
                {"name": "Sleepy Guard", "id": "npc3", "is_available": False, "asleep": True},
            ]
        }
        aff = NarrativePlanner._extract_affordances(NarrativePlanner(Mock()), wc)
        assert len(aff.available_npcs) == 2
        names = [n["name"] for n in aff.available_npcs]
        assert "Aldric" in names and "Marta" in names

    def test_extracts_location_connections(self):
        wc = {
            "location": {"id": "rusty-tankard", "connections": '[{"to": "whisperwood-edge"}, {"to": "thornhold"}]'}
        }
        aff = NarrativePlanner._extract_affordances(NarrativePlanner(Mock()), wc)
        assert set(aff.available_locations) == {"whisperwood-edge", "thornhold"}

    def test_combat_flag_detected(self):
        wc = {
            "encounters": [{"combat": {"combat_id": "abc123"}}],
            "in_combat": False,
        }
        aff = NarrativePlanner._extract_affordances(NarrativePlanner(Mock()), wc)
        assert aff.active_combat is True

    def test_key_items_as_interactables(self):
        wc = {"key_items": [{"id": "seal_stone", "name": "Seal Stone Fragment"}]}
        aff = NarrativePlanner._extract_affordances(NarrativePlanner(Mock()), wc)
        assert len(aff.interactable_objects) >= 1


# =============================================================================
# Negation / Absurd Guard
# =============================================================================

class TestSemanticGuard:
    """Negated statements should not trigger action execution."""

    @pytest.mark.parametrize("msg", [
        "I don't want to go to the woods",
        "we shouldn't attack the goblin",
        "let's not rest here",
        "I refuse to enter",
        "we will not open that door",
    ])
    def test_detects_negation(self, msg):
        planner = NarrativePlanner(Mock())
        assert planner._is_negated_or_refusal(msg) is True

    @pytest.mark.parametrize("msg", [
        "I want to go to the woods",
        "attack the goblin",
        "let's rest",
    ])
    def test_allows_affirmative(self, msg):
        planner = NarrativePlanner(Mock())
        assert planner._is_negated_or_refusal(msg) is False

    @pytest.mark.parametrize("msg", [
        "attack the DM",
        "cast a spell at the dungeon master",
        "punch the rules server",
    ])
    def test_detects_absurd(self, msg):
        planner = NarrativePlanner(Mock())
        assert planner._is_absurd_action(msg) is True


# =============================================================================
# Intent Extraction
# =============================================================================

class TestIntentExtraction:
    """_extract_intent_keywords returns (action_type, target, confidence)."""

    def test_rest_intent(self):
        planner = NarrativePlanner(Mock())
        aff = SceneAffordances(can_rest=True)
        action, target, conf = planner._extract_intent_keywords("I want to rest for the night", aff)
        assert action == "rest"
        assert conf >= 0.8

    def test_move_intent_with_target(self):
        planner = NarrativePlanner(Mock())
        aff = SceneAffordances(available_locations=["whisperwood-edge", "thornhold"])
        action, target, conf = planner._extract_intent_keywords("go to whisperwood-edge", aff)
        assert action == "move"
        assert target and "whisperwood" in target.lower()
        assert conf >= 0.8

    def test_talk_intent_with_target(self):
        planner = NarrativePlanner(Mock())
        aff = SceneAffordances(available_npcs=[{"name": "Aldric"}])
        action, target, conf = planner._extract_intent_keywords("talk to Aldric", aff)
        assert action == "talk"
        assert target and "aldric" in target.lower()
        assert conf >= 0.9

    def test_explore_without_target_lowers_confidence(self):
        planner = NarrativePlanner(Mock())
        aff = SceneAffordances()
        action, target, conf = planner._extract_intent_keywords("look around", aff)
        assert action == "explore"
        assert target is None
        assert conf < 0.8  # lower than targeted action


# =============================================================================
# Ambiguity Detection
# =============================================================================

class TestAmbiguityDetection:
    """_detect_ambiguity returns clarifying question or None."""

    def test_multiple_npcs_needs_clarification(self):
        planner = NarrativePlanner(Mock())
        aff = SceneAffordances(
            available_npcs=[
                {"name": "Aldric"},
                {"name": "Marta"},
            ]
        )
        q = planner._detect_ambiguity("talk to him", "talk", "him", aff)
        assert q is not None
        assert "Aldric" in q or "Marta" in q

    def test_single_npc_no_ambiguity(self):
        planner = NarrativePlanner(Mock())
        aff = SceneAffordances(available_npcs=[{"name": "The Green Woman"}])
        q = planner._detect_ambiguity("talk to her", "talk", "her", aff)
        assert q is None  # unambiguous

    def test_unavailable_npc_triggers_clarification(self):
        planner = NarrativePlanner(Mock())
        aff = SceneAffordances(available_npcs=[{"name": "Aldric"}])
        q = planner._detect_ambiguity("talk to Marta", "talk", "Marta", aff)
        assert q is not None
        assert "Marta" in q and "Aldric" in q

    def test_multiple_exits_needs_clarification(self):
        planner = NarrativePlanner(Mock())
        aff = SceneAffordances(available_locations=["whisperwood-edge", "thornhold", "deep-forest"])
        q = planner._detect_ambiguity("go", "move", None, aff)
        assert q is not None
        assert "Options" in q


# =============================================================================
# End-to-End Planner Integration
# =============================================================================

class TestPlannerIntegration:
    """Validates plan() returns structured decisions that integrate with DM flow."""

    @pytest.mark.asyncio
    async def test_plan_returns_clarify_for_ambiguous_talk(self):
        mock_client = Mock()
        mock_client.get_latest_turn = AsyncMock(return_value={
            "world_context": {
                "npcs": [{"name": "Aldric", "id": "a1", "is_available": True, "asleep": False}],
                "location": {"connections": []},
                "key_items": [],
            }
        })

        planner = NarrativePlanner(mock_client)
        result = await planner.plan("char123", "talk to him")

        assert result.decision == PlannerDecision.CLARIFY
        assert result.clarifying_question is not None
        assert "Aldric" in result.clarifying_question

    @pytest.mark.asyncio
    async def test_plan_executes_clear_action(self):
        mock_client = Mock()
        mock_client.get_latest_turn = AsyncMock(return_value={
            "world_context": {
                "npcs": [],
                "location": {"connections": [{"to": "whisperwood-edge"}]},
                "key_items": [],
                "can_rest": True,
                "can_explore": True,
            }
        })
        planner = NarrativePlanner(mock_client)
        result = await planner.plan("char123", "rest for the night")

        assert result.decision == PlannerDecision.EXECUTE
        assert result.action_type == "rest"
        assert result.confidence >= 0.8

    @pytest.mark.asyncio
    async def test_plan_refuses_impossible_action(self):
        planner = NarrativePlanner(Mock())
        result = await planner.plan("char123", "fly to the moon")
        assert result.decision == PlannerDecision.REFUSE
        assert result.clarifying_question is not None
