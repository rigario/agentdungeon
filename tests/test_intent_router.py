"""Tests for DM Intent Router — intent classification + routing logic.

Tests the classify_intent function against all supported player message patterns
and validates that the routing maps match the rules server contract (ActionRequest, TurnIntent).
"""

import pytest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "dm-runtime"))

from app.services.intent_router import classify_intent, Intent, _extract_target, _keyword_in_message
from app.contract import IntentType, ServerEndpoint, RoutingPolicy


# =============================================================================
# classify_intent — keyword matching
# =============================================================================

class TestClassifyIntent:
    """Test intent classification for various player messages."""

    # --- MOVE intent ---

    def test_go_to(self):
        intent = classify_intent("go to the tavern")
        assert intent.type == IntentType.MOVE
        assert intent.action_type == "move"
        assert "tavern" in (intent.target or "").lower()

    def test_travel_to(self):
        intent = classify_intent("travel to Thornhold")
        assert intent.type == IntentType.MOVE
        assert intent.target is not None

    def test_walk_to(self):
        intent = classify_intent("walk to the market square")
        assert intent.type == IntentType.MOVE

    def test_head_to(self):
        intent = classify_intent("head to the forest")
        assert intent.type == IntentType.MOVE

    def test_move_to(self):
        intent = classify_intent("move to the cave entrance")
        assert intent.type == IntentType.MOVE

    def test_visit(self):
        intent = classify_intent("visit the blacksmith")
        assert intent.type == IntentType.MOVE

    def test_enter(self):
        intent = classify_intent("enter the dungeon")
        assert intent.type == IntentType.MOVE

    def test_return_to(self):
        intent = classify_intent("return to town")
        assert intent.type == IntentType.MOVE

    # --- REST intent ---

    def test_rest(self):
        intent = classify_intent("rest")
        assert intent.type == IntentType.REST
        assert intent.action_type == "rest"

    def test_long_rest(self):
        intent = classify_intent("take a long rest")
        assert intent.type == IntentType.REST
        assert intent.details.get("details", {}).get("rest_type") == "long"

    def test_short_rest(self):
        intent = classify_intent("short rest")
        assert intent.type == IntentType.REST
        assert intent.details.get("details", {}).get("rest_type") == "short"

    def test_sleep(self):
        intent = classify_intent("sleep for the night")
        assert intent.type == IntentType.REST

    def test_camp(self):
        intent = classify_intent("set up camp here")
        assert intent.type == IntentType.REST

    # --- COMBAT intent ---

    def test_attack(self):
        intent = classify_intent("attack the goblin")
        assert intent.type == IntentType.COMBAT
        assert intent.action_type == "attack"

    def test_fight(self):
        intent = classify_intent("fight the dragon")
        assert intent.type == IntentType.COMBAT

    def test_hit(self):
        intent = classify_intent("hit the skeleton")
        assert intent.type == IntentType.COMBAT

    def test_strike(self):
        intent = classify_intent("strike at the enemy")
        assert intent.type == IntentType.COMBAT

    def test_shoot(self):
        intent = classify_intent("shoot the orc")
        assert intent.type == IntentType.COMBAT

    def test_swing_at(self):
        intent = classify_intent("swing at the troll")
        assert intent.type == IntentType.COMBAT

    # --- CAST intent ---

    def test_cast_spell(self):
        intent = classify_intent("cast fireball")
        assert intent.type == IntentType.CAST
        assert intent.action_type == "cast"

    def test_use_spell(self):
        intent = classify_intent("use spell magic missile")
        assert intent.type == IntentType.CAST

    # --- TALK intent ---

    def test_talk_to(self):
        intent = classify_intent("talk to the innkeeper")
        assert intent.type == IntentType.TALK
        assert intent.action_type == "interact"

    def test_speak_to(self):
        intent = classify_intent("speak to Sister Drenna")
        assert intent.type == IntentType.TALK

    def test_ask(self):
        intent = classify_intent("ask the guard about the cave")
        assert intent.type == IntentType.TALK

    def test_tell(self):
        intent = classify_intent("tell the merchant about the quest")
        assert intent.type == IntentType.TALK

    def test_greet(self):
        intent = classify_intent("greet the stranger")
        assert intent.type == IntentType.TALK

    # --- EXPLORE intent ---

    def test_explore(self):
        intent = classify_intent("explore the area")
        assert intent.type == IntentType.EXPLORE
        assert intent.action_type == "explore"

    def test_look_around(self):
        intent = classify_intent("look around")
        assert intent.type == IntentType.EXPLORE

    def test_search(self):
        intent = classify_intent("search the room")
        assert intent.type == IntentType.EXPLORE

    def test_investigate(self):
        intent = classify_intent("investigate the strange markings")
        assert intent.type == IntentType.EXPLORE

    def test_scout(self):
        intent = classify_intent("scout ahead")
        assert intent.type == IntentType.EXPLORE

    # --- INTERACT intent ---

    def test_examine(self):
        intent = classify_intent("examine the statue")
        assert intent.type == IntentType.INTERACT
        assert intent.action_type == "interact"

    def test_inspect(self):
        intent = classify_intent("inspect the door")
        assert intent.type == IntentType.INTERACT

    def test_pick_up(self):
        intent = classify_intent("pick up the sword")
        assert intent.type == IntentType.INTERACT

    def test_open(self):
        intent = classify_intent("open the chest")
        assert intent.type == IntentType.INTERACT

    # --- PUZZLE intent ---

    def test_solve(self):
        intent = classify_intent("solve the puzzle")
        assert intent.type == IntentType.PUZZLE
        assert intent.action_type == "puzzle"

    def test_place_item(self):
        intent = classify_intent("place the gem in the slot")
        assert intent.type == IntentType.PUZZLE

    def test_use_item(self):
        intent = classify_intent("use the key on the door")
        assert intent.type == IntentType.PUZZLE

    # --- GENERAL (default) intent ---

    def test_general_wander(self):
        intent = classify_intent("wander around")
        assert intent.type == IntentType.GENERAL

    def test_general_continue(self):
        intent = classify_intent("continue")
        assert intent.type == IntentType.GENERAL

    def test_general_what_now(self):
        intent = classify_intent("what now")
        assert intent.type == IntentType.GENERAL

    def test_general_keep_going(self):
        intent = classify_intent("keep going")
        assert intent.type == IntentType.GENERAL

    def test_unknown_message(self):
        intent = classify_intent("I wonder what's for dinner")
        assert intent.type == IntentType.GENERAL
        assert intent.confidence == 0.3

    # --- Leading phrase stripping ---

    def test_leading_i_want_to(self):
        intent = classify_intent("I want to go to the tavern")
        assert intent.type == IntentType.MOVE

    def test_leading_lets(self):
        intent = classify_intent("let's explore the cave")
        assert intent.type == IntentType.EXPLORE

    def test_leading_im_going_to(self):
        intent = classify_intent("I'm going to attack the goblin")
        assert intent.type == IntentType.COMBAT


# =============================================================================
# _keyword_in_message — boundary matching
# =============================================================================

class TestKeywordMatching:
    """Test word-boundary keyword matching."""

    def test_exact_match(self):
        assert _keyword_in_message("attack the goblin", "attack") is True

    def test_substring_no_match(self):
        # "attack" should not match inside "counterattack"
        assert _keyword_in_message("counterattack the goblin", "attack") is False

    def test_multiword_match(self):
        assert _keyword_in_message("go to the tavern", "go to") is True

    def test_multiword_no_partial(self):
        # "go to" should not match "going to"
        assert _keyword_in_message("going to the tavern", "go to") is False


# =============================================================================
# _extract_target — target extraction
# =============================================================================

class TestExtractTarget:
    """Test target extraction from player messages."""

    def test_simple_target(self):
        target = _extract_target("go to the tavern", "go to")
        assert target is not None
        assert "tavern" in target.lower()

    def test_target_with_filler(self):
        target = _extract_target("attack the goblin", "attack")
        assert target is not None
        assert "goblin" in target.lower()

    def test_no_target(self):
        target = _extract_target("rest", "rest")
        # "rest" with nothing after it should return None
        assert target is None

    def test_strips_trailing_conjunction(self):
        target = _extract_target("go to the tavern and rest", "go to")
        assert target is not None
        assert "and" not in target.lower()


# =============================================================================
# RoutingPolicy — endpoint mapping
# =============================================================================

class TestRoutingPolicy:
    """Test that intent types map to the correct server endpoints."""

    def test_move_routes_to_actions(self):
        assert RoutingPolicy.get_endpoint(IntentType.MOVE) == ServerEndpoint.ACTIONS

    def test_talk_routes_to_actions(self):
        assert RoutingPolicy.get_endpoint(IntentType.TALK) == ServerEndpoint.ACTIONS

    def test_explore_routes_to_actions(self):
        assert RoutingPolicy.get_endpoint(IntentType.EXPLORE) == ServerEndpoint.ACTIONS

    def test_interact_routes_to_actions(self):
        assert RoutingPolicy.get_endpoint(IntentType.INTERACT) == ServerEndpoint.ACTIONS

    def test_rest_routes_to_actions(self):
        assert RoutingPolicy.get_endpoint(IntentType.REST) == ServerEndpoint.ACTIONS

    def test_puzzle_routes_to_actions(self):
        assert RoutingPolicy.get_endpoint(IntentType.PUZZLE) == ServerEndpoint.ACTIONS

    def test_cast_routes_to_actions(self):
        assert RoutingPolicy.get_endpoint(IntentType.CAST) == ServerEndpoint.ACTIONS

    def test_combat_routes_to_combat(self):
        assert RoutingPolicy.get_endpoint(IntentType.COMBAT) == ServerEndpoint.COMBAT

    def test_general_routes_to_turn(self):
        assert RoutingPolicy.get_endpoint(IntentType.GENERAL) == ServerEndpoint.TURN

    # Async mode routing

    def test_async_general_routes_to_turn(self):
        assert RoutingPolicy.get_endpoint(IntentType.GENERAL, async_mode=True) == ServerEndpoint.TURN

    def test_async_move_routes_to_turn(self):
        assert RoutingPolicy.get_endpoint(IntentType.MOVE, async_mode=True) == ServerEndpoint.TURN

    def test_async_rest_routes_to_turn(self):
        assert RoutingPolicy.get_endpoint(IntentType.REST, async_mode=True) == ServerEndpoint.TURN


# =============================================================================
# Contract validation — DMActionRequest matches rules server ActionRequest
# =============================================================================

class TestContractAlignment:
    """Validate that DM runtime payloads match the rules server contract."""

    def test_dm_action_request_valid_action_types(self):
        from app.contract import DMActionRequest
        valid_types = {"move", "attack", "rest", "explore", "interact", "puzzle", "cast"}
        for at in valid_types:
            req = DMActionRequest(action_type=at)
            assert req.action_type == at

    def test_dm_action_request_invalid_type(self):
        from app.contract import DMActionRequest
        with pytest.raises(ValueError, match="action_type must be one of"):
            DMActionRequest(action_type="fly")

    def test_dm_turn_request_requires_intent(self):
        from app.contract import DMTurnRequest
        req = DMTurnRequest(intent="explore the cave")
        assert req.intent == "explore the cave"

    def test_dm_turn_request_optional_fields(self):
        from app.contract import DMTurnRequest
        req = DMTurnRequest(intent="wander", aggression_slider=75)
        assert req.aggression_slider == 75

    def test_dm_combat_action_defaults(self):
        from app.contract import DMCombatAction
        action = DMCombatAction()
        assert action.action_type == "attack"
        assert action.target is None

    def test_rules_client_normalizes_intent_to_goal(self):
        """Verify that rules_client.start_turn normalizes {intent} to {goal}."""
        from app.services.rules_client import start_turn
        import inspect
        source = inspect.getsource(start_turn)
        assert "goal" in source
        assert "intent" in source


# =============================================================================
# RouterResult — normalized result model
# =============================================================================

class TestRouterResult:
    """Test RouterResult to_dict serialization."""

    def test_minimal_result(self):
        from app.services.intent_router import RouterResult
        result = RouterResult(success=True, narration="test")
        d = result.to_dict()
        assert d["success"] is True
        assert d["narration"] == "test"

    def test_error_result(self):
        from app.services.intent_router import RouterResult
        result = RouterResult(success=False, error="timeout", error_status=504)
        d = result.to_dict()
        assert d["error"] == "timeout"

    def test_combat_fields(self):
        from app.services.intent_router import RouterResult
        result = RouterResult(
            success=True,
            combat_over=True,
            combat_result="victory",
            round=3,
            enemies=[{"name": "goblin"}],
        )
        d = result.to_dict()
        assert d["combat_over"] is True
        assert d["result"] == "victory"
        assert d["round"] == 3

    def test_approval_fields(self):
        from app.services.intent_router import RouterResult
        result = RouterResult(
            success=True,
            approval_triggered=True,
            approval_reason="spell_level_3",
        )
        d = result.to_dict()
        assert d["approval_triggered"] is True
        assert d["approval_reason"] == "spell_level_3"

    def test_omit_empty_optional_fields(self):
        from app.services.intent_router import RouterResult
        result = RouterResult(success=True)
        d = result.to_dict()
        # These should NOT be in the dict when empty/default
        assert "world_context" not in d
        assert "turn_id" not in d
        assert "error" not in d
        assert "combat_over" not in d


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
