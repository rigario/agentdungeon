"""LLM-backed fallback intent resolver for flexible D20 player input.

This module is intentionally advisory. It only runs when deterministic routing is
low-confidence/general, validates every model decision against scene affordances,
and returns a structured planner result that the IntentRouter can either execute,
clarify, or refuse before any rules-server mutation.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from app.contract import AffordancePlannerResult, PlannerDecision
from app.services import dm_profile
from app.services.narrative_planner import NarrativePlanner, SceneAffordances

logger = logging.getLogger(__name__)

# Genre/off-world guard. Keep this deterministic so clearly invalid modern/meta
# actions never depend on LLM availability.
_OFFWORLD_PATTERNS = [
    r"\b(rocket\s+launcher|machine\s+gun|assault\s+rifle|grenade|landmine|tank|helicopter|jet|drone)\b",
    r"\b(smartphone|cell\s*phone|computer|laptop|tablet|internet|wifi|bluetooth|gps|radio|television)\b",
    r"\b(laser|android|cyborg|robot|nuclear|atomic|pistol|revolver|shotgun)\b",
    r"\b(call|text|email|google|web\s+search)\b",
]

_ALLOWED_ACTION_TYPES = {"move", "interact", "explore", "rest", "attack", "cast", "quest", "puzzle", "look"}
_ACTION_TO_INTENT_TYPE = {
    "move": "move",
    "interact": "interact",
    "talk": "talk",
    "explore": "explore",
    "look": "explore",  # rules server has no stable `look` action; use local exploration.
    "rest": "rest",
    "attack": "combat",
    "cast": "cast",
    "quest": "quest",
    "puzzle": "puzzle",
}


def is_offworld_action(message: str) -> bool:
    """Return True for anachronistic/off-setting items or capabilities."""
    msg = (message or "").lower().strip()
    return any(re.search(pattern, msg) for pattern in _OFFWORLD_PATTERNS)


def _offworld_result(message: str) -> AffordancePlannerResult:
    return AffordancePlannerResult(
        decision=PlannerDecision.REFUSE,
        action_type=None,
        target=None,
        confidence=0.98,
        reason="Action references an item, technology, or capability that does not exist in this fantasy setting.",
        clarifying_question="That does not exist in this world. Choose an action using what your character actually has or can plausibly do here.",
        narration_hint="Refuse the anachronistic action without mutating state.",
    )


def _affordance_payload(affordances: SceneAffordances, world_context: dict[str, Any]) -> dict[str, Any]:
    current = world_context.get("current_location") or world_context.get("location") or {}
    current_location = {
        "id": current.get("id") if isinstance(current, dict) else None,
        "name": current.get("name") or current.get("display_name") if isinstance(current, dict) else None,
    }
    return {
        "current_location": current_location,
        "available_npcs": affordances.available_npcs,
        "available_locations": affordances.available_locations,
        "interactable_objects": affordances.interactable_objects,
        "active_quests": affordances.active_quests,
        "active_combat": affordances.active_combat,
        "can_rest": affordances.can_rest,
        "can_explore": affordances.can_explore,
    }


def _norm(value: Any) -> str:
    return str(value or "").lower().replace("-", " ").strip()


def _target_known(target: Optional[str], action_type: Optional[str], affordances: SceneAffordances, world_context: dict[str, Any]) -> bool:
    if not target:
        return action_type in {None, "explore", "rest", "look"}
    target_n = _norm(target)

    def values_match(*values: Any) -> bool:
        cleaned = [_norm(v) for v in values if v]
        return any(target_n == c or target_n in c or c in target_n for c in cleaned)

    if action_type == "move":
        current = world_context.get("current_location") or world_context.get("location") or {}
        if isinstance(current, dict) and values_match(current.get("id"), current.get("name"), current.get("display_name")):
            return True
        for loc in affordances.available_locations:
            if isinstance(loc, dict):
                if values_match(loc.get("id"), loc.get("name"), loc.get("to"), loc.get("location_id")):
                    return True
            elif values_match(loc):
                return True
        for loc in world_context.get("locations", []) or []:
            if isinstance(loc, dict) and values_match(loc.get("id"), loc.get("name"), loc.get("display_name")):
                return True
        return False

    if action_type in {"interact", "talk", "attack"}:
        for npc in affordances.available_npcs:
            if values_match(npc.get("id"), npc.get("name")):
                return True
        for obj in affordances.interactable_objects:
            if isinstance(obj, dict):
                if values_match(obj.get("id"), obj.get("name"), obj.get("display_name"), obj.get("item")):
                    return True
            elif values_match(obj):
                return True
        # Attack can target encounter/enemy types in current context.
        for enc in world_context.get("encounters", []) or []:
            if isinstance(enc, dict) and values_match(enc.get("name"), enc.get("type"), enc.get("enemy_type")):
                return True
        return False

    # Puzzle/cast/quest targets can be objects, active quest names, or omitted.
    if action_type in {"puzzle", "cast", "quest", "look", "explore"}:
        for obj in affordances.interactable_objects:
            if isinstance(obj, dict) and values_match(obj.get("id"), obj.get("name"), obj.get("display_name"), obj.get("item")):
                return True
            if not isinstance(obj, dict) and values_match(obj):
                return True
        for quest in affordances.active_quests:
            if isinstance(quest, dict) and values_match(quest.get("id"), quest.get("title"), quest.get("name")):
                return True
        return action_type in {"look", "explore", "cast"}

    return False


def _coerce_decision(raw: Any) -> Optional[PlannerDecision]:
    try:
        return PlannerDecision(str(raw or "").lower())
    except Exception:
        return None


def _validated_result(parsed: dict[str, Any], affordances: SceneAffordances, world_context: dict[str, Any]) -> AffordancePlannerResult:
    decision = _coerce_decision(parsed.get("decision"))
    if decision is None:
        raise ValueError("fallback resolver returned invalid decision")

    action_type = parsed.get("action_type")
    if action_type in ("", "null", "none"):
        action_type = None
    if action_type:
        action_type = str(action_type).lower().strip()
        if action_type == "talk":
            # Planner may say talk; rules server action is interact, but keep target semantics.
            action_type = "interact"
        if action_type not in _ALLOWED_ACTION_TYPES:
            raise ValueError(f"fallback resolver returned invalid action_type={action_type!r}")

    target = parsed.get("target")
    if target in ("", "null", "none"):
        target = None
    if target is not None:
        target = str(target).strip()

    if decision == PlannerDecision.EXECUTE and not action_type:
        raise ValueError("execute decision requires action_type")
    if decision == PlannerDecision.EXECUTE and not _target_known(target, action_type, affordances, world_context):
        raise ValueError(f"fallback target is outside scene affordances: {target!r}")

    confidence = parsed.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except Exception:
        confidence = 0.0

    return AffordancePlannerResult(
        decision=decision,
        action_type=action_type,
        target=target,
        confidence=confidence,
        reason=str(parsed.get("reason") or "DM fallback resolver decision."),
        clarifying_question=parsed.get("clarifying_question"),
        narration_hint=parsed.get("narration_hint"),
    )


def _system_prompt() -> str:
    return """You are Rigario's Dungeon Master intent resolver.
Return ONLY valid JSON. Do not narrate.

Decide what the player is trying to do using only the supplied scene affordances.
Valid decisions: execute, clarify, refuse, narrate_noop.
Valid action_type values for execute: move, interact, explore, rest, attack, cast, quest, puzzle, look.

Rules:
- Execute only if the action is plausible in a fantasy D&D world and targets a supplied NPC/location/object/quest, or is targetless explore/rest/look.
- Refuse invalid, off-world, anachronistic, meta, or impossible requests. Example: rocket launchers, smartphones, attacking the DM.
- Clarify if the player likely intends a valid action but the target/action is ambiguous.
- Never invent NPCs, locations, objects, loot, weapons, enemies, or outcomes.

JSON schema:
{
  "decision": "execute|clarify|refuse|narrate_noop",
  "action_type": "move|interact|explore|rest|attack|cast|quest|puzzle|look|null",
  "target": "known target id/name or null",
  "confidence": 0.0,
  "reason": "brief reason",
  "clarifying_question": "question or null",
  "narration_hint": "optional hint or null"
}"""


def _user_prompt(player_message: str, affordances: SceneAffordances, world_context: dict[str, Any]) -> str:
    return json.dumps(
        {
            "player_message": player_message,
            "scene_affordances": _affordance_payload(affordances, world_context),
        },
        ensure_ascii=False,
    )


async def resolve_intent(
    player_message: str,
    world_context: Optional[dict[str, Any]] = None,
    session_id: str | None = None,
) -> Optional[AffordancePlannerResult]:
    """Resolve low-confidence freeform input through the DM agent.

    Returns None when the LLM is unavailable or invalid so the caller can use the
    deterministic router path. Deterministic off-world refusal always returns a
    REFUSE result without calling the LLM.
    """
    if is_offworld_action(player_message):
        return _offworld_result(player_message)

    world_context = world_context or {}
    affordances = NarrativePlanner(None)._extract_affordances(world_context)
    try:
        parsed = await dm_profile.narrate(
            _system_prompt(),
            _user_prompt(player_message, affordances, world_context),
            temperature=0.1,
            session_id=session_id,
        )
    except Exception as exc:
        logger.warning("intent fallback resolver failed: %s", exc, exc_info=True)
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return _validated_result(parsed, affordances, world_context)
    except Exception as exc:
        logger.warning("intent fallback resolver rejected output: %s parsed=%r", exc, parsed)
        return AffordancePlannerResult(
            decision=PlannerDecision.CLARIFY,
            action_type=None,
            target=None,
            confidence=0.2,
            reason="DM fallback returned an invalid or out-of-scope action.",
            clarifying_question="I can do that if it maps to something present here. What exactly are you trying to do?",
            narration_hint=None,
        )
