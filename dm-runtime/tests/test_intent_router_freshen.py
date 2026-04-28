"""Unit tests for intent_router world_context freshening (c572fb73).

Tests that _freshen_world_context():
- Returns authoritative post-action world_context from get_latest_turn()
- Falls back to provided current_wc on failure
- Handles None/missing values gracefully

Run: pytest tests/test_intent_router_freshen.py -v
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from app.services.intent_router import IntentRouter


class TestFreshenWorldContext:
    @pytest.fixture
    def mock_client(self):
        """Create a mock rules client."""
        client = AsyncMock()
        return client

    @pytest.fixture
    def router(self, mock_client):
        """Create IntentRouter with mock client."""
        return IntentRouter(mock_client)

    @pytest.mark.asyncio
    async def test_freshen_returns_latest_world_context_when_available(self, router, mock_client):
        """Freshen returns world_context from get_latest_turn when successful."""
        mock_client.get_latest_turn = AsyncMock(return_value={
            "world_context": {
                "location": {"id": "new-forest", "npcs": ["mysterious-stranger"]},
                "character": {"flags": {"statue_observed": True}},
            }
        })
        current = {"old": "stale"}
        result = await router._freshen_world_context("char-123", current)
        assert result == {"location": {"id": "new-forest", "npcs": ["mysterious-stranger"]},
                          "character": {"flags": {"statue_observed": True}}}
        mock_client.get_latest_turn.assert_awaited_once_with("char-123")

    @pytest.mark.asyncio
    async def test_freshen_falls_back_to_current_wc_on_get_error(self, router, mock_client):
        """Freshen returns current_wc when get_latest_turn fails."""
        mock_client.get_latest_turn = AsyncMock(side_effect=Exception("DB locked"))
        current = {"fallback": "context"}
        result = await router._freshen_world_context("char-456", current)
        assert result == current
        mock_client.get_latest_turn.assert_awaited_once_with("char-456")

    @pytest.mark.asyncio
    async def test_freshen_falls_back_when_latest_has_no_world_context(self, router, mock_client):
        """Freshen returns current_wc when latest turn lacks world_context key."""
        mock_client.get_latest_turn = AsyncMock(return_value={
            "turn_id": "t-789",
            "narration": "You moved."
            # no world_context
        })
        current = {"location": {"id": "old-hall"}}
        result = await router._freshen_world_context("char-789", current)
        assert result == current
        mock_client.get_latest_turn.assert_awaited_once_with("char-789")

    @pytest.mark.asyncio
    async def test_freshen_handles_none_current_wc(self, router, mock_client):
        """Freshen returns fresh wc when current_wc is None."""
        mock_client.get_latest_turn = AsyncMock(return_value={
            "world_context": {"fresh": True}
        })
        result = await router._freshen_world_context("char-999", None)
        assert result == {"fresh": True}

    @pytest.mark.asyncio
    async def test_freshen_returns_empty_dict_when_all_fails(self, router, mock_client):
        """Freshen returns {} when current_wc is falsy and latest fetch fails."""
        mock_client.get_latest_turn = AsyncMock(side_effect=RuntimeError("unavailable"))
        result = await router._freshen_world_context("char-000", None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_freshen_handles_non_dict_latest_response(self, router, mock_client):
        """Freshen falls back if latest response isn't dict."""
        mock_client.get_latest_turn = AsyncMock(return_value=["not", "a", "dict"])
        current = {"still": "here"}
        result = await router._freshen_world_context("char-111", current)
        assert result == current


# =============================================================================
# Scene-context fallback in route() (0c056bba)
# =============================================================================

class TestSceneContextFallback:
    """Tests that route() falls back to get_scene_context when get_latest_turn fails."""

    @pytest.fixture
    def mock_client(self):
        client = AsyncMock()
        return client

    @pytest.fixture
    def router(self, mock_client):
        return IntentRouter(mock_client)

    @pytest.mark.asyncio
    async def test_route_uses_scene_context_when_latest_turn_fails(self, router, mock_client):
        """Planner receives scene-context as world_context when get_latest_turn returns nothing."""
        from app.contract import AffordancePlannerResult, PlannerDecision

        # Arrange: get_latest_turn fails (e.g., fresh character, 404)
        mock_client.get_latest_turn = AsyncMock(side_effect=Exception("No turns yet"))
        scene_wc = {
            "npcs": [{"id": "npc1", "name": "Aldric"}],
            "location": {"id": "rusty-tankard", "connections": []},
            "allowed_actions": [
                {"type": "interact", "target_id": "npc1", "target_name": "Aldric"}
            ],
            "can_rest": True,
            "can_explore": True,
        }
        mock_client.get_scene_context = AsyncMock(return_value=scene_wc)
        # Mock get_map_data to avoid hitting the real API (not needed for this test path)
        mock_client.get_map_data = AsyncMock(return_value={"locations": [], "current_location": None})

        # Mock planner to return CLARIFY — short-circuits before routing
        mock_planner = AsyncMock()
        mock_planner.plan = AsyncMock(return_value=AffordancePlannerResult(
            decision=PlannerDecision.CLARIFY,
            action_type=None,
            target=None,
            confidence=0.9,
            reason="Ambiguous NPC reference",
            clarifying_question="Which NPC do you want to talk to? Available: Aldric.",
            narration_hint="Ask for clarification",
        ))
        router._planner = mock_planner

        # Act: call the public route method
        result = await router.route("char-xyz", "talk to him")

        # Assert: get_latest_turn was attempted
        mock_client.get_latest_turn.assert_awaited_once_with("char-xyz")
        # Fallback: get_scene_context was called because get_latest_turn failed
        mock_client.get_scene_context.assert_awaited_once_with("char-xyz")
        # Planner called with the scene context
        mock_planner.plan.assert_awaited_once_with("char-xyz", "talk to him", scene_wc)
        # Result indicates planner clarify short-circuit
        assert result.endpoint_called == "planner-clarify"
        assert result.narration == "Which NPC do you want to talk to? Available: Aldric."
