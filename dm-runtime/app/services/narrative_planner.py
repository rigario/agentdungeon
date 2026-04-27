"""DM Narrative Planner — Affordance interpreter for player messages.

Lifecycle position:
  Player message → NarrativePlanner.plan() → structured decision → IntentRouter
  (BEFORE rules-server mutation — pre-approval affordance validation)

Design goals:
  1. Interpret free-form message against available scene affordances (NPCs, locations, objects).
  2. Resolve pronoun/reference ambiguity ("talk to him" → which NPC?).
  3. Detect unclear/impossible actions and trigger clarification or refusal.
  4. Return a strict, structured decision that downstream routing can trust.
"""

from __future__ import annotations
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from app.contract import AffordancePlannerResult, PlannerDecision
from app.services.rules_client import get_latest_turn


@dataclass
class SceneAffordances:
    available_npcs: List[Dict[str, Any]] = field(default_factory=list)
    available_locations: List[str] = field(default_factory=list)
    interactable_objects: List[str] = field(default_factory=list)
    active_quests: List[Dict[str, Any]] = field(default_factory=list)
    active_combat: bool = False
    can_rest: bool = True
    can_explore: bool = True


class NarrativePlanner:
    def __init__(self, rules_client):
        self._rules_client = rules_client

    def _extract_affordances(self, world_context: Dict[str, Any]) -> SceneAffordances:
        """
        Normalize world_context affordances across legacy turn-world_context and
        fresh scene-context schemas.

        Legacy (from get_latest_turn): contains 'npcs' (with is_available/asleep),
        'location.connections', 'encounters', 'in_combat', etc.
        Scene-context (from /characters/{id}/scene-context): contains 'npcs_here'
        (availability merged), 'current_location' + 'exits', 'combat_state', etc.
        """
        # ---- NPCs: available (not asleep, available flag) ----
        # Legacy path: npcs list with is_available/asleep
        npcs_legacy = world_context.get("npcs", [])
        if npcs_legacy:
            available_npcs = [
                n for n in npcs_legacy
                if n.get("is_available", True) and not n.get("asleep", False)
            ]
        else:
            # Scene-context: npcs_here list with 'available' boolean already computed
            npcs_here = world_context.get("npcs_here", [])
            available_npcs = [
                n for n in npcs_here
                if n.get("available", True) and not n.get("asleep", False)
            ]

        # ---- Movement destinations (exits / connections) ----
        connections = []
        # Try legacy location.connections first
        location = world_context.get("location", {})
        if location:
            conns = location.get("connections", [])
            if isinstance(conns, str):
                try:
                    import json as _json
                    conns = _json.loads(conns or "[]")
                except Exception:
                    conns = []
            connections = conns if conns else []
        # Scene-context fallback: direct 'exits' array (list of location dicts)
        if not connections:
            exits = world_context.get("exits", [])
            if exits:
                connections = exits

        # ---- Combat detection ----
        # Legacy: encounters list + in_combat flag
        encounters = world_context.get("encounters", [])
        active_combat = any(
            e.get("combat", {}).get("combat_id") for e in encounters
        ) or world_context.get("in_combat", False)
        # Scene-context fallback: combat_state dict
        if not active_combat:
            combat_state = world_context.get("combat_state", {})
            if combat_state and combat_state.get("combat_id"):
                active_combat = True

        # ---- Interactable objects ----
        # Legacy: 'key_items' + 'interactables' separate
        # Scene-context: key_items supplies interactables; no separate 'interactables'
        key_items = world_context.get("key_items", [])
        interactables = world_context.get("interactables", [])
        if not interactables and key_items:
            interactables = key_items

        return SceneAffordances(
            available_npcs=[{"name": n.get("name"), "id": n.get("id")} for n in available_npcs],
            available_locations=[
                c.get("to") or c.get("location_id") or c.get("id")
                for c in connections if c
            ],
            interactable_objects=interactables,
            active_quests=world_context.get("active_quests", []),
            active_combat=active_combat,
            can_rest=world_context.get("can_rest", True),
            can_explore=world_context.get("can_explore", True),
        )

    async def plan(
        self,
        character_id: str,
        player_message: str,
        world_context: Optional[Dict[str, Any]] = None,
    ) -> AffordancePlannerResult:
        msg = player_message.lower().strip()
        if world_context is None:
            try:
                turn = await self._rules_client.get_latest_turn(character_id)
                world_context = turn.get("world_context", {}) or {}
            except Exception:
                world_context = {}
        affordances = self._extract_affordances(world_context)

        if self._is_negated_or_refusal(msg):
            return AffordancePlannerResult(
                decision=PlannerDecision.NARRATE_NOOP,
                action_type=None,
                target=None,
                confidence=0.95,
                reason="Semantic guard: statement is a refusal or negation, not permission to act.",
                clarifying_question=None,
                narration_hint="The player is hesitating or declining. No action taken.",
            )

        if self._is_absurd_action(msg):
            return AffordancePlannerResult(
                decision=PlannerDecision.REFUSE,
                action_type=None,
                target=None,
                confidence=0.9,
                reason="Action is physically impossible or off-scope (absurd).",
                clarifying_question="That action isn't possible in this world.",
                narration_hint="Politely explain why that cannot be done.",
            )

        action_type, target, confidence = self._extract_intent_keywords(msg, affordances)
        ambiguity = self._detect_ambiguity(msg, action_type, target, affordances)
        if ambiguity:
            return AffordancePlannerResult(
                decision=PlannerDecision.CLARIFY,
                action_type=action_type,
                target=None,
                confidence=0.3,
                reason=f"Ambiguous target: {ambiguity}",
                clarifying_question=ambiguity,
                narration_hint=None,
            )

        if action_type == "talk" and target:
            npc_names_lower = [n.get("name", "").lower() for n in affordances.available_npcs]
            if target.lower() not in npc_names_lower:
                available = [n.get("name") for n in affordances.available_npcs]
                m = f'"{target}" isn\'t here. Available: '
                m += ', '.join(available) if available else 'no one'
                m += '.'
                return AffordancePlannerResult(
                    decision=PlannerDecision.CLARIFY,
                    action_type=action_type,
                    target=None,
                    confidence=0.4,
                    reason=f"NPC '{target}' not available at this location",
                    clarifying_question=m,
                    narration_hint=None,
                )

        if action_type == "move" and not target:
            if len(affordances.available_locations) > 1:
                m = "Where would you like to go? Options: "
                m += ', '.join(affordances.available_locations)
                m += '.'
                return AffordancePlannerResult(
                    decision=PlannerDecision.CLARIFY,
                    action_type="move",
                    target=None,
                    confidence=0.3,
                    reason="Move intent without specific destination",
                    clarifying_question=m,
                    narration_hint=None,
                )
            elif len(affordances.available_locations) == 1:
                target = affordances.available_locations[0]

        return AffordancePlannerResult(
            decision=PlannerDecision.EXECUTE,
            action_type=action_type,
            target=target,
            confidence=confidence,
            reason=f"Action '{action_type}' {f'on {target}' if target else ''} is well-formed and available.",
            clarifying_question=None,
            narration_hint=None,
        )

    def _is_negated_or_refusal(self, msg: str) -> bool:
        msg = msg.lower().strip()
        patterns = [
            r"^(?:i|we)\s+(?:do\s+not|don't|dont|never)\s+(?:go|move|travel|head|enter|attack|fight|cast|use|open|take|grab|touch|press|pull|push)",
            r"^(?:i|we)\s+(?:do\s+not|don't|dont|never)\s+want\s+to",
            r"^(?:i|we)\s+(?:refuse|decline)\s+to",
            r"^\s*(?:let'?s\s+not|we\s+shouldn't|avoid|stay\s+away)\b",
            r"\bnot\s+(?:going|entering|attacking|resting|opening)\b",
            # will not / won't patterns — must allow word boundary before subject for mid-sentence
            r"(?:^|\b)(?:i|we|you)\s+(?:will\s+not|won't)\s+(?:go|move|travel|head|enter|attack|fight|cast|use|open|take|grab|touch|press|pull|push)",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _is_absurd_action(self, msg: str) -> bool:
        msg = msg.lower().strip()
        patterns = [
            r"\b(attack|fight|hit|strike|punch|kick)\b.*\b(dm|dungeon\s+master|the\s+dm|rules\s+server|smoke\s+test)\b",
            r"\b(cast|use)\b.*\bat\b.*\b(dm|dungeon\s+master|test\s+suite)\b",
            r"\b(swallow|eat|devour)\b.*\b(statue|moon|sun|building|mountain|ocean)\b",
            r"\b(fly|teleport|walk\s+through\s+walls|breathe\s+underwater)\b",
        ]
        return any(re.search(p, msg) for p in patterns)

    def _extract_intent_keywords(
        self, msg: str, affordances: SceneAffordances
    ) -> tuple[Optional[str], Optional[str], float]:
        keyword_map = [
            ("rest", "rest", 0.9), ("sleep", "rest", 0.9), ("camp", "rest", 0.85),
            ("attack", "attack", 0.9), ("fight", "attack", 0.9), ("hit ", "attack", 0.7),
            ("explore", "explore", 0.9), ("look around", "explore", 0.9),
            ("search", "explore", 0.8), ("investigate", "explore", 0.8),
            ("go to ", "move", 0.9), ("travel to ", "move", 0.9),
            ("walk to ", "move", 0.9), ("head to ", "move", 0.9), ("move to ", "move", 0.9),
            ("talk to ", "talk", 0.9), ("speak to ", "talk", 0.9), ("chat with ", "talk", 0.9),
            ("ask ", "talk", 0.8), ("tell ", "talk", 0.8),
            ("examine", "interact", 0.9), ("inspect", "interact", 0.9),
            ("look at ", "interact", 0.8), ("pick up ", "interact", 0.9),
            ("grab ", "interact", 0.9), ("open ", "interact", 0.8),
            ("accept quest", "quest", 0.95), ("complete quest", "quest", 0.95),
        ]
        best_action = best_target = None
        best_score = 0.0
        for keyword, action_type, score in keyword_map:
            idx = msg.find(keyword)
            if idx >= 0:
                after = msg[idx + len(keyword):].strip()
                target = after.split()[0] if after else None
                if target:
                    target = re.sub(r"[.,;!?].*$", "", target)
                if score > best_score:
                    best_score, best_action, best_target = score, action_type, target
        if best_action == "explore" and best_target is None:
            best_score = 0.6
        return best_action, best_target, best_score

    def _detect_ambiguity(
        self,
        msg: str,
        action_type: Optional[str],
        target: Optional[str],
        affordances: SceneAffordances,
    ) -> Optional[str]:
        if action_type == "talk" and not target:
            names = [n.get("name") for n in affordances.available_npcs]
            if len(names) == 0:
                return "There's nobody here to talk to."
            elif len(names) == 1:
                return None
            else:
                return f"Who would you like to talk to? Available: {', '.join(names)}."

        if action_type == "talk" and target:
            npc_lower = [n.get("name", "").lower() for n in affordances.available_npcs]
            if target.lower() not in npc_lower:
                # Single-NPC pronoun resolution: "her"/"him"/"them" with exactly 1 NPC → auto-resolve
                PRONOUNS = {"her", "him", "them", "it", "that person", "the npc", "the person", "the guard", "the woman", "the man"}
                if len(affordances.available_npcs) == 1 and target.lower() in PRONOUNS:
                    return None  # unambiguous — pronoun refers to the only NPC
                available = [n.get("name") for n in affordances.available_npcs]
                m = f'"{target}" isn\'t here. Available: '
                m += ', '.join(available) if available else 'no one'
                m += '.'
                return m

        if action_type == "move" and not target:
            if len(affordances.available_locations) > 1:
                m = "Where would you like to go? Options: "
                m += ', '.join(affordances.available_locations)
                m += '.'
                return m
            elif len(affordances.available_locations) == 1:
                return None
            else:
                return "There's nowhere to go from here."
        return None
