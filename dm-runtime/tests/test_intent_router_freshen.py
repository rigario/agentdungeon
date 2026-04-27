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
