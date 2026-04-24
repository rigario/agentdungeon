"""DM Intent Router — Classifies player intent and routes to the correct rules server endpoint.

Design:
- Broad/ambiguous intent → POST /characters/{id}/turn/start (async adventure simulation)
- Precise verb actions → POST /characters/{id}/actions (single-action resolution)
- Active combat detected → /characters/{id}/combat/* (round-by-round)

The router never validates rules — it only classifies and dispatches.
All failure handling stays here so the turn router stays clean.
"""

from __future__ import annotations
import re
from typing import Optional
from dataclasses import dataclass, field

from fastapi import HTTPException
from app.contract import IntentType, ServerEndpoint, RoutingPolicy


# =============================================================================
# Monster Stat Reference — used to resolve encounters when world_context
# only provides {type, count} without full stat blocks.
# Sourced from encounters in the D20 database.
# =============================================================================
MONSTER_STATS: dict[str, dict] = {
    "cultist":      {"type": "Cultist",        "hp": 9,  "ac": 12, "attack_bonus": 3, "damage": "1d6+1", "initiative_mod": 1},
    "bandit":       {"type": "Bandit",         "hp": 11, "ac": 12, "attack_bonus": 3, "damage": "1d6+1", "initiative_mod": 1},
    "wolf":         {"type": "Wolf",           "hp": 11, "ac": 13, "attack_bonus": 4, "damage": "2d4+2", "initiative_mod": 2},
    "goblin":       {"type": "Goblin",         "hp": 7,  "ac": 15, "attack_bonus": 4, "damage": "1d6+2", "initiative_mod": 2},
    "skeleton":     {"type": "Skeleton",       "hp": 13, "ac": 13, "attack_bonus": 4, "damage": "1d6+2", "initiative_mod": 2},
    "bugbear":      {"type": "Bugbear",        "hp": 27, "ac": 16, "attack_bonus": 4, "damage": "2d8+2", "initiative_mod": 2},
    "orc":          {"type": "Orc",            "hp": 15, "ac": 13, "attack_bonus": 5, "damage": "1d12+3", "initiative_mod": 1},
    "zombie":       {"type": "Zombie",         "hp": 45, "ac": 13, "attack_bonus": 5, "damage": "1d6+3", "initiative_mod": -1},
    "giant spider": {"type": "Giant Spider",   "hp": 52, "ac": 16, "attack_bonus": 7, "damage": "2d8+4", "initiative_mod": 3},
    "cult fanatic": {"type": "Cult Fanatic",   "hp": 60, "ac": 15, "attack_bonus": 7, "damage": "2d8+4", "initiative_mod": 1},
    "bandit captain": {"type": "Bandit Captain", "hp": 65, "ac": 15, "attack_bonus": 6, "damage": "2d6+3", "initiative_mod": 2},
    "dryad":        {"type": "Dryad",          "hp": 55, "ac": 13, "attack_bonus": 5, "damage": "2d6+3", "initiative_mod": 2},
    "specter":      {"type": "Specter",        "hp": 45, "ac": 12, "attack_bonus": 5, "damage": "3d6",   "initiative_mod": 3},
    "treant":       {"type": "Treant",         "hp": 95, "ac": 16, "attack_bonus": 8, "damage": "3d6+4", "initiative_mod": -1},
    "hill giant":   {"type": "Hill Giant",     "hp": 105,"ac": 13, "attack_bonus": 8, "damage": "3d8+5", "initiative_mod": -1},
    "gibbering mouther": {"type": "Gibbering Mouther", "hp": 67, "ac": 9, "attack_bonus": 4, "damage": "5d6", "initiative_mod": -1},
    "wood woad":    {"type": "Wood Woad",      "hp": 45, "ac": 18, "attack_bonus": 6, "damage": "2d6+4", "initiative_mod": 0},
}


# =============================================================================
# Normalized Result Models
# =============================================================================

@dataclass
class RouterResult:
    """Normalized result from any rules server call."""
    success: bool = True
    endpoint_called: str = ""
    narration: str = ""
    events: list = field(default_factory=list)
    dice_log: list = field(default_factory=list)
    character_state: dict = field(default_factory=dict)
    world_context: Optional[dict] = None
    # Turn-specific
    turn_id: Optional[str] = None
    asks: list = field(default_factory=list)
    decision_point: Optional[dict] = None
    available_actions: list = field(default_factory=list)
    combat_log: list = field(default_factory=list)
    turn_results: Optional[list] = None
    # Combat-specific
    combat_over: bool = False
    combat_result: Optional[str] = None  # victory, defeat, fled
    enemies: list = field(default_factory=list)
    round: int = 0
    is_your_turn: bool = False
    # Action-specific
    approval_triggered: bool = False
    approval_reason: Optional[str] = None
    # Error
    error: Optional[str] = None
    error_status: Optional[int] = None
    raw_response: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization (matches contract models)."""
        d = {
            "success": self.success,
            "narration": self.narration,
            "events": self.events,
            "dice_log": self.dice_log,
            "character_state": self.character_state,
        }
        if self.world_context:
            d["world_context"] = self.world_context
        if self.turn_id:
            d["turn_id"] = self.turn_id
        if self.asks:
            d["asks"] = self.asks
        if self.decision_point:
            d["decision_point"] = self.decision_point
        if self.available_actions:
            d["available_actions"] = self.available_actions
        if self.combat_log:
            d["combat_log"] = self.combat_log
        if self.turn_results is not None:
            d["turn_results"] = self.turn_results
        if self.combat_over:
            d["combat_over"] = self.combat_over
            d["result"] = self.combat_result
        if self.enemies:
            d["enemies"] = self.enemies
        if self.round:
            d["round"] = self.round
        if self.approval_triggered:
            d["approval_triggered"] = True
            d["approval_reason"] = self.approval_reason
        if self.error:
            d["error"] = self.error
        return d


# =============================================================================
# Intent Classification
# =============================================================================

@dataclass
class Intent:
    """Classified player intent."""
    type: IntentType
    target: Optional[str] = None
    action_type: Optional[str] = None  # move, rest, explore, interact, puzzle, attack
    details: dict = field(default_factory=dict)
    confidence: float = 0.0

    @property
    def server_endpoint(self) -> ServerEndpoint:
        return RoutingPolicy.get_endpoint(self.type)


MONSTER_STATS: dict[str, dict] = {
    "cultist":      {"type": "Cultist",        "hp": 9,  "ac": 12, "attack_bonus": 3, "damage": "1d6+1", "initiative_mod": 1},
}

# Keyword groups with priority ordering (first match wins)
_INTENT_PATTERNS: list[tuple[IntentType, str, list[str]]] = [
    # (intent_type, action_type, keywords)
    (IntentType.COMBAT, "attack", ["attack", "fight", "hit ", "strike", "swing at", "shoot"]),
    (IntentType.CAST, "cast", ["cast ", "use spell", "cast spell"]),
    (IntentType.REST, "rest", ["rest", "sleep", "camp", "long rest", "short rest", "take a rest"]),
    (IntentType.LOOK, "look", ["look", "look at", "glance", "scan", "observe", "survey"]),
    (IntentType.MOVE, "move", ["go to", "travel to", "walk to", "head to", "move to", "visit", "enter ", "return to", "go back"]),
    (IntentType.TALK, "interact", ["talk to", "speak to", "speak with", "ask ", "tell ", "say to", "chat with", "conversation with", "greet"]),
    (IntentType.PUZZLE, "puzzle", ["solve", "puzzle", "place the", "put the", "use item", "use the"]),
    (IntentType.QUEST, "quest", ["accept quest", "take quest", "complete quest", "finish quest", "turn in quest", "turn in the quest", "quest log", "view quest", "check quest"]),
    (IntentType.EXPLORE, "explore", ["explore", "look around", "look closer", "what do i see", "examine the area", "current location", "this room", "here", "without leaving", "stay here", "search", "investigate", "scout", "check around"]),
    (IntentType.INTERACT, "interact", ["interact with", "examine", "inspect", "look at", "pick up", "grab", "take ", "open ", "touch", "feel", "study", "read", "press", "trace"]),
]

# Broad intent patterns → turn/start (async simulation)
_BROAD_PATTERNS = [
    r"^\s*(explore|adventure|wander|roam|survive|continue|keep going|what now|next)\s*[.!]?\s*$",
    r"^\s*(find .*|go .*|do .*)until\s+",
]

def _extract_error_status(e: Exception) -> int:
    """Extract HTTP status code from an exception, defaulting to 502."""
    # httpx.HTTPStatusError stores status in e.response.status_code
    if hasattr(e, 'response') and hasattr(e.response, 'status_code'):
        return e.response.status_code
    if hasattr(e, 'status_code'):
        return e.status_code
    return 502

# Absurd / physically impossible action patterns → refusal
_ABSURD_PATTERNS = [
    r'\b(swallow|eat|devour|consume)\b.*\b(statue|moon|sun|cloud|tree|building|mountain)\b',
    r'\b(fly|teleport|time.?travel|breathe underwater|walk through walls)\b',
    r'\b(punch|kick|attack|fight)\b.*\b(sun|moon|cloud|sky|ground|earth|gravity)\b',
    r'\b(lift|carry|throw)\b.*\b(mountain|castle|building|ocean)\b',
    # Meta-actions targeting the DM should be refused gracefully
    r'\b(attack|fight|hit|strike|target)\b.*\b(dm\b|the dm\b|dungeon master\b)',
    r'\b(cast|use)\b.*\bat\b.*\b(dm\b|the dm\b|dungeon master\b)',
    r'\b(kill|defeat|damage)\b.*\b(dm\b|the dm\b)',
]


def _keyword_in_message(msg: str, keyword: str) -> bool:
    """Check if keyword appears as a word/phrase boundary match, not substring.

    For multi-word keywords, checks the full phrase has word boundaries.
    For single words, uses \\b word boundary regex.
    """
    # Escape keyword for regex
    escaped = re.escape(keyword.strip())
    # Match with word boundaries
    pattern = r'\b' + escaped + r'\b'
    return bool(re.search(pattern, msg))


def classify_intent(player_message: str) -> Intent:
    """Classify a freeform player message into a structured intent.

    Priority:
    1. Active combat continuation (check via patterns)
    2. Precise verb matching (→ actions endpoint)
    3. Broad intent patterns (→ turn/start endpoint)
    4. Default: general turn
    """
    msg = player_message.lower().strip()

    # Strip common leading phrases
    msg = re.sub(r"^(i want to|i'd like to|i'm going to|let me|let's|okay,?\s*i)\s+", "", msg)

    # Check broad intent patterns first (→ turn/start)
    for pattern in _BROAD_PATTERNS:
        if re.match(pattern, msg):
            return Intent(
                type=IntentType.GENERAL,
                action_type=None,
                details={"intent": player_message, "_original_msg": player_message},
                confidence=0.6,
            )

    # Check absurd / physically impossible actions BEFORE precise verb matching
    # Ensures impossible actions (e.g., "attack the sun") aren't misrouted as valid combat
    for pattern in _ABSURD_PATTERNS:
        if re.search(pattern, msg):
            return Intent(
                type=IntentType.GENERAL,
                action_type=None,
                details={"intent": player_message, "_original_msg": player_message, "_absurd": True},
                confidence=0.3,
            )

    # Check precise verb patterns (→ actions)
    for intent_type, action_type, keywords in _INTENT_PATTERNS:
        for kw in keywords:
            if _keyword_in_message(msg, kw):
                target = _extract_target(msg, kw)
                details = {"action_type": action_type}
                if target:
                    details["target"] = target
                # Add specific details based on action type
                if action_type == "rest":
                    details["details"] = {"rest_type": "long" if "long" in msg else "short"}
                elif action_type == "move" and target:
                    details["target"] = target
                details["_original_msg"] = player_message
                return Intent(
                    type=intent_type,
                    target=target,
                    action_type=action_type,
                    details=details,
                    confidence=0.8,
                )

    # Default: broad intent → turn/start
    return Intent(
        type=IntentType.GENERAL,
        action_type=None,
        details={"intent": player_message, "_original_msg": player_message},
        confidence=0.3,
    )


def _extract_target(msg: str, keyword: str) -> Optional[str]:
    """Extract the target from a message after a keyword."""
    # Find keyword position using word boundary matching
    escaped = re.escape(keyword.strip())
    pattern = r'\b' + escaped + r'\b'
    match = re.search(pattern, msg)
    if not match:
        return None

    after = msg[match.end():].strip()

    # Clean up trailing punctuation/phrases
    after = re.split(r"[.,;!?]", after)[0].strip()
    after = re.split(r"\s+(and|then|but|or|while|if|because)\s+", after)[0].strip()

    # Remove common filler words from start
    after = re.sub(r"^(the|a|an|my|that|this)\s+", "", after)

    return after if after else None


# =============================================================================
# Intent Router — the main dispatcher
# =============================================================================

class IntentRouter:
    """Routes player intent to the correct rules server endpoint and normalizes results.

    Uses the rules_client to call the rules server and normalizes all responses
    into a unified RouterResult.
    """

    def __init__(self, rules_client):
        self._client = rules_client

    async def check_active_combat(self, character_id: str) -> Optional[dict]:
        """Check if a character has active combat. Returns combat state or None.

        The rules server returns 200 with combat data when active, 404 when not.
        There is no 'status' field — presence of the response means combat exists.
        """
        try:
            combat = await self._client.get_combat(character_id)
            if combat and combat.get("combat_id"):
                return combat
        except Exception:
            pass
        return None

    async def route(
        self,
        character_id: str,
        player_message: str,
        force_endpoint: Optional[ServerEndpoint] = None,
    ) -> RouterResult:
        """Main dispatch: classify → check combat → route → normalize.

        Args:
            character_id: Character to act for
            player_message: Freeform player text
            force_endpoint: Override automatic routing (for testing/debug)

        Returns:
            RouterResult with normalized data from any endpoint
        """
        # Step 1: Classify intent
        intent = classify_intent(player_message)

        # Approval gate — check before routing to rules server
        try:
            approval_payload = {
                "action_type": intent.action_type,
                "target": intent.target,
                "details": intent.details,
            }
            approval = await self._client.check_approval(character_id, approval_payload)
            if approval.get("needs_approval"):
                raise HTTPException(
                    status_code=202,
                    detail={
                        "error": "approval_required",
                        "reasons": approval["reasons"],
                        "context": approval["context"],
                        "intent": {
                            "type": intent.type.value,
                            "action_type": intent.action_type,
                        },
                    },
                )
        except Exception:
            # If approval check fails (rules server down), allow to proceed
            # This prevents total outage — human-in-the-loop becomes advisory
            pass


        # Step 2: Check for active combat (overrides intent routing)
        active_combat = await self.check_active_combat(character_id)

        if active_combat and intent.type != IntentType.REST:
            # Active combat detected — route to combat/act unless explicitly resting
            return await self._route_combat_act(character_id, intent, active_combat)

        # Step 3: Determine endpoint
        endpoint = force_endpoint or intent.server_endpoint

        # Step 4: Route
        try:
            if endpoint == ServerEndpoint.COMBAT:
                return await self._route_combat_start(character_id, intent)
            elif endpoint == ServerEndpoint.ACTIONS:
                return await self._route_action(character_id, intent)
            elif endpoint == ServerEndpoint.TURN:
                return await self._route_turn(character_id, player_message)
            else:
                return await self._route_turn(character_id, player_message)
        except Exception as e:
            return RouterResult(
                success=False,
                error=f"Rules server error: {str(e)}",
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
            )

    async def _route_action(self, character_id: str, intent: Intent) -> RouterResult:
        """Route to POST /characters/{id}/actions."""
        try:
            # Build the payload — intent.details has action_type and possibly target
            payload = dict(intent.details)
            if intent.target and "target" not in payload:
                payload["target"] = intent.target

            # Quest actions need special payload shaping: details.action = accept|complete|list
            if intent.action_type == "quest":
                # Determine quest sub-action from the original message keywords
                details = payload.get("details", {})
                if isinstance(details, dict):
                    action_val = details.get("action", "")
                else:
                    action_val = ""
                if not action_val:
                    # Infer from keyword presence in the stored original message
                    orig = payload.get("_original_msg", "").lower()
                    if "complete" in orig or "finish" in orig or "turn in" in orig:
                        action_val = "complete"
                    elif "list" in orig or "log" in orig or "view" in orig or "check" in orig:
                        action_val = "list"
                    else:
                        action_val = "accept"
                payload["details"] = {"action": action_val}

            result = await self._client.submit_action(character_id, payload)
            # Attack actions wrap combat data under 'combat' key — extract to top-level
            # Handle null combat value: result.get("combat", {}) returns None when key exists with null
            combat_data = result.get("combat") or {}
            return RouterResult(
                success=True,
                endpoint_called="actions",
                narration=result.get("narration", ""),
                events=result.get("events", []),
                dice_log=result.get("dice_log", []),
                character_state=result.get("character_state", {}),
                world_context=result.get("world_context"),
                approval_triggered=result.get("approval_triggered", False),
                approval_reason=result.get("approval_reason"),
                # Combat fields extracted from nested combat_data
                enemies=combat_data.get("enemies", []),
                round=combat_data.get("rounds", 0),
                combat_over=combat_data.get("victory") is not None or combat_data.get("hp_remaining", 0) <= 0,
                combat_result="victory" if combat_data.get("victory") else "defeat" if combat_data.get("victory") is not None else None,
                combat_log=result.get("events", []),  # Combat events from top-level events
                raw_response=result,
            )
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="actions",
                error=str(e),
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
            )

    async def _route_turn(self, character_id: str, player_message: str) -> RouterResult:
        """Route to POST /characters/{id}/turn/start.

        The rules server requires TurnIntent with a `goal` field. Freeform DM
        messages are normalized here into a conservative turn goal.
        """
        try:
            msg = player_message.lower().strip()
            if any(word in msg for word in ["rest", "sleep", "camp"]):
                goal = "rest"
            elif any(word in msg for word in ["travel", "go ", "move ", "head ", "return "]):
                goal = "travel"
            else:
                goal = "explore"

            payload = {
                "goal": goal,
                "target": None,
                "max_steps": 3,
                "max_encounters": 1,
            }

            result = await self._client.start_turn(character_id, payload)

            # turn/start returns hp_start/hp_end/hp_max at top level (not character_state)
            # Populate character_state so synthesis can extract HP
            character_state = result.get("character_state", {})
            if not character_state and result.get("hp_max"):
                character_state = {
                    "hp": {
                        "current": result.get("hp_end", 0),
                        "max": result.get("hp_max", 0),
                    },
                    "location_id": result.get("current_location"),
                }

            return RouterResult(
                success=True,
                endpoint_called="turn/start",
                narration=result.get("narration", result.get("narrative", "")),
                events=result.get("events", []),
                dice_log=result.get("dice_log", []),
                character_state=character_state,
                world_context=result.get("world_context"),
                turn_id=result.get("turn_id"),
                asks=result.get("asks", []),
                decision_point=result.get("decision_point"),
                available_actions=result.get("available_actions", []),
                combat_log=result.get("combat_log", []),
                turn_results=result.get("turn_results"),
                raw_response=result,
            )
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="turn/start",
                error=str(e),
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
            )

    async def _route_combat_start(self, character_id: str, intent: Intent) -> RouterResult:
        """Route to POST /characters/{id}/combat/start.

        Resolves encounter data from the character's world context, builds
        full enemy stat blocks, rolls initiative, and starts combat.
        """
        import json
        import random

        try:
            # Step 1: Get world context to find available encounters
            world_context = {}
            try:
                latest = await self._client.get_latest_turn(character_id)
                world_context = latest.get("world_context", {})
            except Exception:
                pass

            encounters = world_context.get("encounters", [])

            # Step 1b: If no world context, start a short exploration turn to populate it
            if not encounters:
                try:
                    turn_result = await self._client.start_turn(character_id, {
                        "goal": "explore",
                        "max_steps": 1,
                        "max_encounters": 0,  # don't auto-resolve encounters
                    })
                    world_context = turn_result.get("world_context", {})
                    encounters = world_context.get("encounters", [])
                except Exception:
                    pass

            # Step 2: Pick an encounter matching the intent target, or random
            chosen_encounter = None
            target_lower = (intent.target or "").lower()

            if encounters:
                # Try to match target to encounter name or enemy type
                for enc in encounters:
                    enc_name = enc.get("name", "").lower()
                    enemy_types = [e.get("type", "").lower() for e in enc.get("enemies", [])]
                    if target_lower and (target_lower in enc_name or
                                         any(target_lower in et for et in enemy_types)):
                        chosen_encounter = enc
                        break
                # Fallback: random encounter
                if not chosen_encounter:
                    chosen_encounter = random.choice(encounters)

            if not chosen_encounter:
                return RouterResult(
                    success=False,
                    endpoint_called="combat/start",
                    error="No encounters available at current location",
                    error_status=404,
                    raw_response={"error": "no encounters"},
                )

            # Step 3: Build enemies with full stat blocks from encounter data
            # The encounter's enemies list has full stats from the DB
            encounter_enemies = chosen_encounter.get("enemies", [])
            enemies_list = []
            for eg in encounter_enemies:
                # If we have full stats (hp, ac), use them directly
                if "hp" in eg and "ac" in eg:
                    count = eg.get("count", 1)
                    for i in range(count):
                        suffix = f" {i+1}" if count > 1 else ""
                        name_override = eg.get("name_override")
                        enemies_list.append({
                            "type": eg["type"],
                            "hp": eg["hp"],
                            "ac": eg["ac"],
                            "attack_bonus": eg.get("attack_bonus", 3),
                            "damage": eg.get("damage", "1d6"),
                            "initiative_mod": eg.get("initiative_mod", 0),
                        })
                else:
                    # Minimal data — resolve from MONSTER_STATS
                    monster = MONSTER_STATS.get(eg.get("type", "").lower())
                    if monster:
                        count = eg.get("count", 1)
                        for i in range(count):
                            enemies_list.append({
                                "type": monster["type"],
                                "hp": monster["hp"],
                                "ac": monster["ac"],
                                "attack_bonus": monster["attack_bonus"],
                                "damage": monster["damage"],
                                "initiative_mod": monster["initiative_mod"],
                            })

            if not enemies_list:
                return RouterResult(
                    success=False,
                    endpoint_called="combat/start",
                    error=f"Could not resolve enemy stats for encounter: {chosen_encounter.get('name', 'unknown')}",
                    error_status=502,
                    raw_response={"error": "unresolved enemies"},
                )

            # Step 4: Roll initiative for the player (d20, 1-20)
            initiative_roll = random.randint(1, 20)

            # Step 5: Call combat/start with proper data
            encounter_name = chosen_encounter.get("name", "Wild Encounter")
            enemies_json = json.dumps(enemies_list)
            result = await self._client.start_combat(
                character_id, encounter_name, enemies_json, initiative_roll
            )

            return RouterResult(
                success=True,
                endpoint_called="combat/start",
                narration=result.get("narration", ""),
                events=result.get("events", []),
                dice_log=result.get("dice_log", []),
                character_state=result.get("character_state", {}),
                world_context=result.get("world_context"),
                combat_over=result.get("combat_over", False),
                combat_result=result.get("result"),
                combat_log=result.get("events", []),  # Combat log = round events
                enemies=result.get("enemies", []),
                round=result.get("round", 0),
                is_your_turn=result.get("is_your_turn", False),
                raw_response=result,
            )
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="combat/start",
                error=str(e),
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
            )

    async def _route_combat_act(self, character_id: str, intent: Intent, combat_state: dict) -> RouterResult:
        """Route to POST /characters/{id}/combat/act — active combat detected."""
        import random

        # Map intent to combat action
        action = "attack"  # default
        if intent.type == IntentType.REST:
            action = "defend"
        elif intent.type == IntentType.MOVE:
            action = "flee"

        try:
            # Roll d20 for the action (required by rules server for attack/flee)
            d20_roll = random.randint(1, 20)

            payload = {"action": action, "d20_roll": d20_roll}
            target_index = 0  # default to first enemy
            if intent.target:
                # Try to match target to enemy index
                target_lower = intent.target.lower()
                enemies = combat_state.get("enemies", [])
                for i, e in enumerate(enemies):
                    if target_lower in e.get("name", "").lower():
                        target_index = i
                        break
            payload["target_index"] = target_index

            result = await self._client.combat_act(character_id, payload)
            return RouterResult(
                success=True,
                endpoint_called="combat/act",
                narration=result.get("narration", ""),
                events=result.get("events", []),
                dice_log=result.get("dice_log", []),
                character_state=result.get("character_state", {}),
                world_context=result.get("world_context"),
                combat_over=result.get("combat_over", False),
                combat_result=result.get("result"),
                enemies=result.get("enemies", []),
                round=result.get("round", 0),
                combat_log=result.get("events", []),
                is_your_turn=result.get("is_your_turn", False),
                raw_response=result,
            )
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="combat/act",
                error=str(e),
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
            )
