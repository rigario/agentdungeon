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

from app.contract import IntentType, ServerEndpoint, RoutingPolicy


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


# Keyword groups with priority ordering (first match wins)
_INTENT_PATTERNS: list[tuple[IntentType, str, list[str]]] = [
    # (intent_type, action_type, keywords)
    (IntentType.COMBAT, "attack", ["attack", "fight", "hit ", "strike", "swing at", "shoot"]),
    (IntentType.CAST, "cast", ["cast ", "use spell", "cast spell"]),
    (IntentType.REST, "rest", ["rest", "sleep", "camp", "long rest", "short rest", "take a rest"]),
    (IntentType.MOVE, "move", ["go to", "travel to", "walk to", "head to", "move to", "visit", "enter ", "return to", "go back"]),
    (IntentType.TALK, "interact", ["talk to", "speak to", "speak with", "ask ", "tell ", "say to", "chat with", "conversation with", "greet"]),
    (IntentType.PUZZLE, "puzzle", ["solve", "puzzle", "place the", "put the", "use item", "use the"]),
    (IntentType.EXPLORE, "explore", ["explore", "look around", "search", "investigate", "scout", "check around"]),
    (IntentType.INTERACT, "interact", ["interact with", "examine", "inspect", "look at", "pick up", "grab", "take ", "open "]),
]

# Broad intent patterns → turn/start (async simulation)
_BROAD_PATTERNS = [
    r"^\s*(explore|adventure|wander|roam|survive|continue|keep going|what now|next)\s*[.!]?\s*$",
    r"^\s*(find .*|go .*|do .*)until\s+",
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
                details={"intent": player_message},
                confidence=0.6,
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
        details={"intent": player_message},
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
        """Check if a character has active combat. Returns combat state or None."""
        try:
            combat = await self._client.get_combat(character_id)
            if combat and combat.get("status") == "active":
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
                error_status=502,
                raw_response={"error": str(e)},
            )

    async def _route_action(self, character_id: str, intent: Intent) -> RouterResult:
        """Route to POST /characters/{id}/actions."""
        try:
            result = await self._client.submit_action(character_id, intent.details)
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
                raw_response=result,
            )
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="actions",
                error=str(e),
                error_status=getattr(e, "status_code", 502) if hasattr(e, "status_code") else 502,
                raw_response={"error": str(e)},
            )

    async def _route_turn(self, character_id: str, player_message: str) -> RouterResult:
        """Route to POST /characters/{id}/turn/start."""
        try:
            result = await self._client.start_turn(character_id, {"intent": player_message})
            return RouterResult(
                success=True,
                endpoint_called="turn/start",
                narration=result.get("narration", result.get("narrative", "")),
                events=result.get("events", []),
                dice_log=result.get("dice_log", []),
                character_state=result.get("character_state", {}),
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
                error_status=getattr(e, "status_code", 502) if hasattr(e, "status_code") else 502,
                raw_response={"error": str(e)},
            )

    async def _route_combat_start(self, character_id: str, intent: Intent) -> RouterResult:
        """Route to POST /characters/{id}/combat/start."""
        try:
            target = intent.target or "Unknown"
            result = await self._client.start_combat(character_id, target, "[]")
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
                error_status=getattr(e, "status_code", 502) if hasattr(e, "status_code") else 502,
                raw_response={"error": str(e)},
            )

    async def _route_combat_act(self, character_id: str, intent: Intent, combat_state: dict) -> RouterResult:
        """Route to POST /characters/{id}/combat/act — active combat detected."""
        # Map intent to combat action
        action = "attack"  # default
        if intent.type == IntentType.REST:
            action = "defend"
        elif intent.type == IntentType.MOVE:
            action = "flee"

        try:
            payload = {"action": action}
            if intent.target:
                payload["target_index"] = 0  # default first target

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
                is_your_turn=result.get("is_your_turn", False),
                raw_response=result,
            )
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="combat/act",
                error=str(e),
                error_status=getattr(e, "status_code", 502) if hasattr(e, "status_code") else 502,
                raw_response={"error": str(e)},
            )
