"""Unit tests for DM runtime contract and intent classification.

These tests require NO running servers — they validate pure logic.
Run: pytest tests/test_unit_contract.py -v
"""

import pytest
from app.contract import (
    IntentType, ServerEndpoint, RoutingPolicy,
    DMActionRequest, NarrationPayload, MechanicsPayload,
    ChoiceOption, ServerTrace, DMResponse, AuthorityBoundary,
)


# =============================================================================
# Contract Version
# =============================================================================

class TestContractVersion:
    def test_contract_version_exists(self):
        from app.contract import CONTRACT_VERSION
        assert CONTRACT_VERSION == "1.0.0"

    def test_contract_doc_reference(self):
        from app.contract import CONTRACT_DOC
        assert CONTRACT_DOC == "DM-RUNTIME-ARCHITECTURE.md"


# =============================================================================
# Authority Boundaries
# =============================================================================

class TestAuthorityBoundaries:
    def test_dm_owned_has_narration(self):
        assert "descriptive_prose" in AuthorityBoundary.DM_OWNED
        assert "npc_voice" in AuthorityBoundary.DM_OWNED
        assert "choice_framing" in AuthorityBoundary.DM_OWNED

    def test_server_owned_has_rules(self):
        assert "encounter_rolls" in AuthorityBoundary.SERVER_OWNED
        assert "damage_calculation" in AuthorityBoundary.SERVER_OWNED
        assert "xp_loot_application" in AuthorityBoundary.SERVER_OWNED

    def test_forbidden_has_db_writes(self):
        assert "direct_db_writes" in AuthorityBoundary.FORBIDDEN
        assert "invent_outcomes" in AuthorityBoundary.FORBIDDEN
        assert "replace_server_truth" in AuthorityBoundary.FORBIDDEN

    def test_no_overlap_dm_server(self):
        overlap = AuthorityBoundary.DM_OWNED & AuthorityBoundary.SERVER_OWNED
        assert not overlap, f"DM and Server authority overlap: {overlap}"

    def test_no_overlap_dm_forbidden(self):
        overlap = AuthorityBoundary.DM_OWNED & AuthorityBoundary.FORBIDDEN
        assert not overlap, f"DM owns forbidden items: {overlap}"


# =============================================================================
# Routing Policy
# =============================================================================

class TestRoutingPolicy:
    @pytest.mark.parametrize("intent,expected", [
        (IntentType.MOVE, ServerEndpoint.ACTIONS),
        (IntentType.TALK, ServerEndpoint.ACTIONS),
        (IntentType.EXPLORE, ServerEndpoint.ACTIONS),
        (IntentType.COMBAT, ServerEndpoint.COMBAT),
        (IntentType.GENERAL, ServerEndpoint.TURN),
        (IntentType.REST, ServerEndpoint.ACTIONS),
        (IntentType.INTERACT, ServerEndpoint.ACTIONS),
        (IntentType.PUZZLE, ServerEndpoint.ACTIONS),
        (IntentType.CAST, ServerEndpoint.ACTIONS),
    ])
    def test_sync_routing(self, intent, expected):
        assert RoutingPolicy.get_endpoint(intent) == expected

    @pytest.mark.parametrize("intent,expected", [
        (IntentType.GENERAL, ServerEndpoint.TURN),
        (IntentType.MOVE, ServerEndpoint.TURN),
        (IntentType.REST, ServerEndpoint.TURN),
    ])
    def test_async_routing(self, intent, expected):
        assert RoutingPolicy.get_endpoint(intent, async_mode=True) == expected


# =============================================================================
# Pydantic Contract Models
# =============================================================================

class TestContractModels:
    def test_dm_action_request_valid(self):
        req = DMActionRequest(action_type="move", target="crossroads")
        assert req.action_type == "move"
        assert req.target == "crossroads"

    def test_dm_action_request_invalid_type(self):
        with pytest.raises(ValueError, match="action_type must be one of"):
            DMActionRequest(action_type="dance")

    def test_dm_action_request_all_valid_types(self):
        valid = {"move", "attack", "rest", "explore", "interact", "puzzle", "cast"}
        for action_type in valid:
            req = DMActionRequest(action_type=action_type)
            assert req.action_type == action_type

    def test_narration_payload_required_scene(self):
        with pytest.raises(Exception):  # Pydantic validation error
            NarrationPayload()

    def test_narration_payload_full(self):
        n = NarrationPayload(
            scene="You enter the cave.",
            npc_lines=[{"speaker": "Kol", "text": "Welcome."}],
            tone="mysterious",
        )
        assert n.scene == "You enter the cave."
        assert n.tone == "mysterious"

    def test_dm_response_construction(self):
        resp = DMResponse(
            narration=NarrationPayload(scene="Test scene"),
            mechanics=MechanicsPayload(hp={"current": 10, "max": 10}),
            choices=[ChoiceOption(id="1", label="Continue")],
            server_trace=ServerTrace(server_endpoint_called="actions"),
        )
        assert resp.narration.scene == "Test scene"
        assert resp.mechanics.hp == {"current": 10, "max": 10}
        assert len(resp.choices) == 1
        assert resp.choices[0].label == "Continue"

    def test_dm_response_serialization(self):
        resp = DMResponse(
            narration=NarrationPayload(scene="Test"),
            session_id="test-session",
        )
        data = resp.model_dump()
        assert data["narration"]["scene"] == "Test"
        assert data["session_id"] == "test-session"


# =============================================================================
# Intent Classification (requires no server)
# =============================================================================

class TestIntentClassification:
    """Test classify_intent function with various player messages."""

    def _classify(self, msg):
        from app.services.intent_router import classify_intent
        return classify_intent(msg)

    @pytest.mark.parametrize("msg,expected_type", [
        ("attack the goblin", IntentType.COMBAT),
        ("fight!", IntentType.COMBAT),
        ("hit the skeleton", IntentType.COMBAT),
        ("swing at the orc", IntentType.COMBAT),
    ])
    def test_combat_intents(self, msg, expected_type):
        intent = self._classify(msg)
        assert intent.type == expected_type

    @pytest.mark.parametrize("msg,expected_type", [
        ("go to crossroads", IntentType.MOVE),
        ("travel to thornhold", IntentType.MOVE),
        ("head to the cave", IntentType.MOVE),
        ("visit the inn", IntentType.MOVE),
        ("return to the village", IntentType.MOVE),
    ])
    def test_move_intents(self, msg, expected_type):
        intent = self._classify(msg)
        assert intent.type == expected_type

    @pytest.mark.parametrize("msg,expected_type", [
        ("rest for the night", IntentType.REST),
        ("take a long rest", IntentType.REST),
        ("sleep", IntentType.REST),
        ("camp here", IntentType.REST),
    ])
    def test_rest_intents(self, msg, expected_type):
        intent = self._classify(msg)
        assert intent.type == expected_type

    @pytest.mark.parametrize("msg,expected_type", [
        ("look around", IntentType.EXPLORE),
        ("search the area", IntentType.EXPLORE),
        ("investigate the room", IntentType.EXPLORE),
        ("scout ahead", IntentType.EXPLORE),
    ])
    def test_explore_intents(self, msg, expected_type):
        intent = self._classify(msg)
        assert intent.type == expected_type

    @pytest.mark.parametrize("msg,expected_type", [
        ("talk to the innkeeper", IntentType.TALK),
        ("speak with Kol", IntentType.TALK),
        ("ask Sister Drenna about the quest", IntentType.TALK),
    ])
    def test_talk_intents(self, msg, expected_type):
        intent = self._classify(msg)
        assert intent.type == expected_type

    @pytest.mark.parametrize("msg,expected_type", [
        ("examine the statue", IntentType.INTERACT),
        ("inspect the chest", IntentType.INTERACT),
        ("look at the painting", IntentType.INTERACT),
        ("pick up the sword", IntentType.INTERACT),
    ])
    def test_interact_intents(self, msg, expected_type):
        intent = self._classify(msg)
        assert intent.type == expected_type

    @pytest.mark.parametrize("msg,expected_type", [
        ("cast fireball", IntentType.CAST),
        ("use spell", IntentType.CAST),
    ])
    def test_cast_intents(self, msg, expected_type):
        intent = self._classify(msg)
        assert intent.type == expected_type

    @pytest.mark.parametrize("msg", [
        "explore",
        "what now",
        "continue",
        "keep going",
    ])

    def test_broad_intents_default_to_general(self, msg):
        intent = self._classify(msg)
        assert intent.type == IntentType.GENERAL

    @pytest.mark.parametrize("msg,expected_type", [
        ("accept quest", IntentType.QUEST),
        ("take quest", IntentType.QUEST),
        ("complete quest", IntentType.QUEST),
        ("finish quest", IntentType.QUEST),
        ("turn in the quest", IntentType.QUEST),
        ("quest log", IntentType.QUEST),
        ("view quest", IntentType.QUEST),
        ("check quest", IntentType.QUEST),
    ])
    def test_quest_intents(self, msg, expected_type):
        intent = self._classify(msg)
        assert intent.type == expected_type, f"'{msg}' -> got {intent.type.value}, expected {expected_type.value}"

    def test_target_extraction(self):
        intent = self._classify("go to the crossroads")
        assert intent.target is not None
        assert "crossroads" in intent.target.lower()

    def test_prefix_stripping(self):
        """Leading filler phrases should be stripped before classification."""
        intent = self._classify("I want to go to the crossroads")
        assert intent.type == IntentType.MOVE

    def test_confidence_precise(self):
        intent = self._classify("attack the goblin")
        assert intent.confidence >= 0.7

    def test_confidence_broad(self):
        intent = self._classify("explore")
        assert intent.confidence <= 0.7

    def test_absurd_attack_on_celestial(self):
        """Physical absurdity: attacking celestial bodies should be rejected."""
        intent = self._classify("attack the sun")
        assert intent.type == IntentType.GENERAL
        assert intent.confidence == 0.3
        assert intent.details.get("_absurd") is True

    def test_absurd_fly_to_moon(self):
        """Physical absurdity: flying to the moon."""
        intent = self._classify("fly to the moon")
        assert intent.type == IntentType.GENERAL
        assert intent.confidence == 0.3
        assert intent.details.get("_absurd") is True

    def test_absurd_devour_statue(self):
        """Physical absurdity: eating large statues."""
        intent = self._classify("I want to eat the statue")
        assert intent.type == IntentType.GENERAL
        assert intent.confidence == 0.3
        assert intent.details.get("_absurd") is True

    def test_absurd_checked_before_precise_verbs(self):
        """CRITICAL: absurd patterns MUST override precise verb matching.
        
        Bug: "attack the sun" previously matched COMBAT because verb check ran first.
        Regression would return IntentType.COMBAT here.
        """
        intent = self._classify("punch the sun")
        assert intent.type == IntentType.GENERAL, "Absurd check must run before verb matching"
        assert intent.confidence == 0.3

