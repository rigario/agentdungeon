"""Integration-ish unit tests for IntentRouter using DM fallback resolver."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.contract import AffordancePlannerResult, PlannerDecision
from app.services import intent_router
from app.services.intent_router import IntentRouter, classify_intent


WORLD_CONTEXT = {
    "current_location": {"id": "thornhold", "name": "Thornhold"},
    "location": {"id": "thornhold", "name": "Thornhold"},
    "exits": [{"id": "rusty-tankard", "name": "The Rusty Tankard"}],
    "locations": [
        {"id": "thornhold", "name": "Thornhold"},
        {"id": "rusty-tankard", "name": "The Rusty Tankard"},
    ],
    "npcs_here": [{"id": "npc-aldric", "name": "Aldric the Innkeeper", "available": True}],
    "npcs": [{"id": "npc-aldric", "name": "Aldric the Innkeeper", "available": True}],
}


class FakeRulesClient:
    def __init__(self):
        self.submitted_actions = []

    async def get_latest_turn(self, character_id):
        raise RuntimeError("fresh character has no latest turn")

    async def get_scene_context(self, character_id):
        return dict(WORLD_CONTEXT)

    async def check_approval(self, character_id, payload):
        return {"needs_approval": False}

    async def get_combat(self, character_id):
        raise RuntimeError("no combat")

    async def submit_action(self, character_id, payload):
        self.submitted_actions.append(payload)
        return {
            "success": True,
            "narration": "You travel to the Rusty Tankard.",
            "events": [],
            "character_state": {"location_id": payload.get("target")},
            "world_context": WORLD_CONTEXT,
        }


@pytest.mark.parametrize("message", ["take out the rocket launcher", "use my smartphone"])
def test_classify_intent_marks_offworld_as_invalid(message):
    classified = classify_intent(message)
    assert classified.details.get("_offworld") is True
    assert classified.details.get("_absurd") is True


@pytest.mark.asyncio
async def test_router_uses_dm_fallback_execute_for_flexible_move(monkeypatch):
    async def fake_resolve(message, world_context, session_id=None):
        return AffordancePlannerResult(
            decision=PlannerDecision.EXECUTE,
            action_type="move",
            target="rusty-tankard",
            confidence=0.91,
            reason="DM resolved tavern phrasing to Rusty Tankard.",
        )

    monkeypatch.setattr(intent_router, "resolve_fallback_intent", fake_resolve)
    client = FakeRulesClient()
    router = IntentRouter(client)

    result = await router.route("char-1", "wander over to the tavern")

    assert result.success is True
    assert result.endpoint_called == "actions"
    assert result.intent.details.get("_dm_fallback") is True
    assert result.intent.action_type == "move"
    assert result.intent.target == "rusty-tankard"
    assert client.submitted_actions[-1]["target"] == "rusty-tankard"


@pytest.mark.asyncio
async def test_router_refuses_offworld_before_rules_mutation():
    client = FakeRulesClient()
    router = IntentRouter(client)

    result = await router.route("char-1", "take out the rocket launcher")

    assert result.success is False
    assert result.error_status == 400
    assert "world" in (result.error or "").lower() or "fantasy" in (result.error or "").lower()
    assert client.submitted_actions == []
