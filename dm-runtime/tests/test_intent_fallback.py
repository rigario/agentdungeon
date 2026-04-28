"""Tests for the DM-agent fallback intent resolver."""

import os
import sys
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.contract import PlannerDecision
from app.services import intent_fallback


WORLD_CONTEXT = {
    "current_location": {"id": "thornhold", "name": "Thornhold"},
    "location": {"id": "thornhold", "name": "Thornhold"},
    "exits": [
        {"id": "rusty-tankard", "name": "The Rusty Tankard"},
        {"id": "south-road", "name": "South Road"},
    ],
    "locations": [
        {"id": "thornhold", "name": "Thornhold"},
        {"id": "rusty-tankard", "name": "The Rusty Tankard"},
    ],
    "npcs_here": [{"id": "npc-aldric", "name": "Aldric the Innkeeper", "available": True}],
    "npcs": [{"id": "npc-aldric", "name": "Aldric the Innkeeper", "available": True}],
    "key_items": [{"id": "weathered-statue", "name": "Weathered Statue"}],
}


@pytest.mark.parametrize(
    "message",
    [
        "take out the rocket launcher",
        "fire my machine gun",
        "call someone on my smartphone",
        "google the map",
    ],
)
def test_offworld_actions_are_detected_without_llm(message):
    assert intent_fallback.is_offworld_action(message) is True


@pytest.mark.parametrize(
    "message",
    ["draw my longsword", "cast fireball", "shoot my bow", "light a torch"],
)
def test_period_appropriate_actions_are_not_offworld(message):
    assert intent_fallback.is_offworld_action(message) is False


@pytest.mark.asyncio
async def test_resolve_intent_refuses_rocket_launcher_without_calling_llm(monkeypatch):
    narrate = AsyncMock(return_value={"decision": "execute", "action_type": "attack", "target": "npc-aldric"})
    monkeypatch.setattr(intent_fallback.dm_profile, "narrate", narrate)

    result = await intent_fallback.resolve_intent("take out the rocket launcher", WORLD_CONTEXT)

    assert result.decision == PlannerDecision.REFUSE
    assert "fantasy" in (result.reason or "").lower()
    narrate.assert_not_called()


@pytest.mark.asyncio
async def test_resolve_intent_executes_valid_flexible_move(monkeypatch):
    narrate = AsyncMock(return_value={
        "decision": "execute",
        "action_type": "move",
        "target": "rusty-tankard",
        "confidence": 0.86,
        "reason": "Player means to go to the tavern.",
    })
    monkeypatch.setattr(intent_fallback.dm_profile, "narrate", narrate)

    result = await intent_fallback.resolve_intent("wander over to the tavern", WORLD_CONTEXT)

    assert result.decision == PlannerDecision.EXECUTE
    assert result.action_type == "move"
    assert result.target == "rusty-tankard"
    assert result.confidence == pytest.approx(0.86)


@pytest.mark.asyncio
async def test_resolve_intent_rejects_hallucinated_target(monkeypatch):
    narrate = AsyncMock(return_value={
        "decision": "execute",
        "action_type": "move",
        "target": "moon-base",
        "confidence": 0.9,
        "reason": "Bad hallucinated target.",
    })
    monkeypatch.setattr(intent_fallback.dm_profile, "narrate", narrate)

    result = await intent_fallback.resolve_intent("go to the moon base", WORLD_CONTEXT)

    assert result.decision == PlannerDecision.CLARIFY
    assert "out-of-scope" in (result.reason or "") or "invalid" in (result.reason or "")
