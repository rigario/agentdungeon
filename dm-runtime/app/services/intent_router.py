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
from app.services.narrative_planner import NarrativePlanner
from app.services.intent_fallback import resolve_intent as resolve_fallback_intent, is_offworld_action
from app.contract import AffordancePlannerResult, PlannerDecision


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
    # Normalized intent (after _normalize_target) — use this instead of re-classifying
    intent: Optional["Intent"] = None
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
        # Include normalized intent for traceability
        if self.intent is not None:
            d["_normalized_intent"] = {
                "type": self.intent.type.value,
                "target": self.intent.target,
                "action_type": self.intent.action_type,
                "details": self.intent.details,
                "confidence": self.intent.confidence,
            }
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
    # EXPLORE keywords — MUST come before LOOK and INTERACT
    (IntentType.EXPLORE, "explore", ["explore", "look around", "looking around", "look closer", "what do i see", "examine the area", "current location", "this room", "here", "without leaving", "stay here", "search", "investigate", "scout", "check around"]),
    # TALK before INTERACT (clean separation)
    (IntentType.TALK, "interact", ["talk to", "speak to", "speak with", "ask ", "tell ", "say to", "chat with", "conversation with", "greet"]),
    # PUZZLE before INTERACT (avoid OVERLAP "use item"/"use the" vs "pick up")
    (IntentType.PUZZLE, "puzzle", ["solve", "puzzle", "place the", "put the", "use item", "use the"]),
    # QUEST BEFORE INTERACT — "take quest" must not be shadowed by INTERACT's generic "take "
    (IntentType.QUEST, "quest", ["accept quest", "take quest", "complete quest", "finish quest", "turn in quest", "turn in the quest", "quest log", "view quest", "check quest"]),
    # INTERACT before LOOK to catch "look at X" and "examine X"
    (IntentType.INTERACT, "interact", ["interact with", "examine", "inspect", "look at", "pick up", "grab", "take ", "open ", "touch", "feel", "study", "read", "press", "trace", "search for", "look for", "listen to", "listen for", "sniff", "push", "pull", "run my hand over"]),
    # Generic LOOK LAST among look-adjacent verbs — only catches truly generic look words
    (IntentType.LOOK, "look", ["glance", "scan", "observe", "survey"]),
    (IntentType.MOVE, "move", ["go to", "travel to", "walk to", "head to", "move to", "visit", "enter ", "return to", "go back"]),
]


# Broad intent patterns → turn/start (async simulation)
_BROAD_PATTERNS = [
    r"^\s*(explore|adventure|wander|roam|survive|continue|keep going|what now|next)\s*[.!]?\s*$",
    r"^\s*(find .*|go .*|do .*)until\s+",
]


def _extract_error_status(e: Exception) -> int:
    """Extract HTTP status code from an exception, defaulting to 502."""
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

# Player-agent semantic guard: negated/refusal statements must not be treated as
# permission to execute the embedded verb. Example: "I don't want to go to the
# woods" contains "go to", but it means "do not go". These patterns block rules
# server mutation before approval/routing. Speech acts directed at NPCs are
# exempt so "tell Aldric I don't want to go" remains valid dialogue.
_NEGATED_ACTION_PATTERNS = [
    r"(?:^|\b(?:i|we|you|please)\s+)(?:do\s+not|don't|dont|never)\s+(?:go|move|travel|head|enter|visit|return|walk|rest|sleep|camp)\b",
    r"(?:^|\b(?:i|we|you|please)\s+)(?:do\s+not|don't|dont|never)\s+(?:attack|fight|hit|strike|shoot|cast|use|open|take|grab|touch|press|pull|push)\b",
    r"\b(?:i|we)\s+(?:do\s+not|don't|dont)\s+want\s+to\s+(?:go|move|travel|head|enter|visit|return|walk|rest|sleep|camp|attack|fight|cast|use|open|take|grab|touch|press|pull|push)\b",
    r"\b(?:i|we)\s+(?:refuse|decline)\s+to\s+(?:go|move|travel|head|enter|visit|return|walk|rest|sleep|camp|attack|fight|cast|use|open|take|grab|touch|press|pull|push)\b",
    r"\b(?:i|we)\s+will\s+not\s+(?:go|move|travel|head|enter|visit|return|walk|rest|sleep|camp|attack|fight|cast|use|open|take|grab|touch|press|pull|push)\b",
    r"^\s*(?:avoid|stay\s+away\s+from)\b",
    r"^\s*not\s+(?:going|entering|attacking|resting|opening)\b",
    r"^\s*(?:let(?:'| u)?s|let\s+us|we)\s+not\s+(?:go|move|travel|head|enter|visit|return|walk|rest|sleep|camp|attack|fight|cast|use|open|take|grab|touch|press|pull|push)\b",
]

_SPEECH_ACT_PREFIX = re.compile(r"^\s*(?:ask|tell|say\s+to|speak\s+to|speak\s+with|talk\s+to|chat\s+with|greet)\b")


def _keyword_in_message(msg: str, keyword: str) -> bool:
    """Check if keyword appears as a word/phrase boundary match, not substring.

    For multi-word keywords, checks the full phrase has word boundaries.
    For single words, uses \b word boundary regex.
    """
    escaped = re.escape(keyword.strip())
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

    # Semantic guard: a negated/refusal utterance is not consent to perform the
    # embedded action. This must happen before verb matching so "don't go to X"
    # never becomes MOVE(target=X). Speech acts are allowed through as dialogue.
    if not _SPEECH_ACT_PREFIX.match(msg):
        for pattern in _NEGATED_ACTION_PATTERNS:
            if re.search(pattern, msg):
                return Intent(
                    type=IntentType.GENERAL,
                    action_type=None,
                    details={
                        "intent": player_message,
                        "_original_msg": player_message,
                        "_semantic_guard": True,
                        "_semantic_guard_reason": "negated_or_refusal_action",
                    },
                    confidence=0.95,
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

    # Off-world/anachronistic actions are invalid in Rigario. Keep this
    # deterministic so obvious bad requests do not depend on LLM availability.
    if is_offworld_action(player_message):
        return Intent(
            type=IntentType.GENERAL,
            action_type=None,
            details={
                "intent": player_message,
                "_original_msg": player_message,
                "_absurd": True,
                "_offworld": True,
                "_absurd_reason": "offworld_or_anachronistic_action",
            },
            confidence=0.98,
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
    escaped = re.escape(keyword.strip())
    pattern = r'\b' + escaped + r'\b'
    match = re.search(pattern, msg)
    if not match:
        return None

    after = msg[match.end():].strip()
    after = re.split(r"[.,;!?]", after)[0].strip()
    after = re.split(r"\s+(and|then|but|or|while|if|because)\s+", after)[0].strip()
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
        self._planner = NarrativePlanner(rules_client)

    async def _freshen_world_context(self, character_id: str, current_wc: Optional[dict]) -> dict:
        """Fetch the latest turn to ensure world_context reflects post-action state.

        After an action or turn resolves, the rules-server state (flags, location,
        inventory, NPCs, quests, fronts) may have changed. The immediate response
        world_context can be stale. This helper fetches get_latest_turn() to get
        the authoritative updated world_context for narration.

        Falls back to scene-context when no turn history exists (fresh characters),
        ensuring the DM planner always has NPC affordances. Non-blocking — returns
        current_wc if all fetches fail.
        """
        if not current_wc:
            current_wc = {}
        try:
            latest = await self._client.get_latest_turn(character_id)
            if latest and isinstance(latest, dict):
                wc = latest.get("world_context")
                if wc and isinstance(wc, dict):
                    return wc
        except Exception as e:
            print(f"[DEBUG] get_latest_turn failed: {e!r}"); pass  # Non-blocking — fall through to scene-context
        # Scene-context fallback: fresh characters have no turn history
        try:
            scene = await self._client.get_scene_context(character_id)
            exits = scene.get("exits", [])
            # Populate backward-compatible keys
            if "npcs" not in scene:
                aliased = []
                for npc in scene.get("npcs_here", []):
                    npc_copy = dict(npc)
                    npc_copy["is_available"] = npc.get("available", True)
                    npc_copy.setdefault("asleep", False)
                    aliased.append(npc_copy)
                scene["npcs"] = aliased
            if not scene.get("locations"):
                scene["locations"] = exits
            if not scene.get("connections"):
                scene["connections"] = exits
            if "current_location" not in scene or not isinstance(scene.get("current_location"), dict):
                scene["current_location"] = {}
            if "connections" not in scene["current_location"]:
                scene["current_location"]["connections"] = exits
            if "location" not in scene:
                scene["location"] = scene.get("current_location", {})
            return scene
        except Exception:
            pass  # Scene-context unavailable — fall back to provided current_wc
        return current_wc or {}

    def _normalize_target(self, intent, world_context: dict) -> str:
        """
        Map natural language target phrases to canonical game object IDs
        using the current world_context.

        - For MOVE: maps location display names/aliases to canonical location IDs.
        - For INTERACT/TALK: maps NPC name fragments to canonical NPC IDs.
        Returns the normalized target string, or the original if no match found.
        """
        if not intent or not intent.target:
            return intent.target if intent else None

        target = intent.target.lower().strip()
        wc = world_context or {}

        # --- Location normalization for MOVE intents ---
        if intent.action_type == "move":
            def _clean(value) -> str:
                return str(value or "").lower().strip()

            def _target_tokens() -> list[str]:
                # Multi-word player aliases often include canonical IDs plus flavor words,
                # e.g. "thornhold town square". Also split hyphenated IDs so
                # "rusty tankard inn" can match "rusty-tankard".
                raw = target.replace("-", " ")
                return [t.strip(".,;:!?()[]{}\"'") for t in raw.split() if t.strip(".,;:!?()[]{}\"'")]

            def _matches_location(candidate_id: str, candidate_name: str) -> bool:
                loc_id = _clean(candidate_id)
                loc_name = _clean(candidate_name)
                if not loc_id and not loc_name:
                    return False
                if target == loc_id or target == loc_name:
                    return True
                if loc_id and (loc_id in target or target in loc_id):
                    return True
                if loc_name and (target in loc_name or loc_name in target):
                    return True
                normalized_id = loc_id.replace("-", " ")
                if normalized_id and (normalized_id in target or target in normalized_id):
                    return True
                tokens = _target_tokens()
                return any(token and (token == loc_id or token == normalized_id or token == loc_name) for token in tokens)

            locations = wc.get("locations", [])
            for loc in locations:
                if not isinstance(loc, dict):
                    continue
                loc_id = _clean(loc.get("id", ""))
                loc_name = _clean(loc.get("name", ""))
                if _matches_location(loc_id, loc_name):
                    return loc_id

            # Check connections from current_location.
            current = wc.get("current_location", {})
            connections = current.get("connections", []) if isinstance(current, dict) else []
            for conn in connections:
                conn_id = _clean(conn.get("id", "") if isinstance(conn, dict) else conn)
                conn_name = _clean(conn.get("name", "") if isinstance(conn, dict) else "")
                if _matches_location(conn_id, conn_name):
                    return conn_id

            # Also check top-level connections (e.g., from turn/latest world_context).
            for conn in wc.get("connections", []):
                conn_id = _clean(conn.get("id", "") if isinstance(conn, dict) else conn)
                conn_name = _clean(conn.get("name", "") if isinstance(conn, dict) else "")
                if _matches_location(conn_id, conn_name):
                    return conn_id

            # Additive fix for ISSUE-019 (verifier feedback): explicitly treat current_location as valid move target.
            # Prevents "I go to Thornhold town square" failing when current_location=thornhold not in exits list.
            current = wc.get("current_location", {}) or wc.get("location", {})
            if isinstance(current, dict):
                curr_id = _clean(current.get("id", ""))
                curr_name = _clean(current.get("name", "") or current.get("display_name", ""))
                if _matches_location(curr_id, curr_name):
                    return curr_id

        # --- NPC normalization for INTERACT/TALK intents ---
        if intent.action_type == "interact" or intent.type == IntentType.TALK:
            npcs = wc.get("npcs", [])
            target_lower = target
            best_match = None
            for npc in npcs:
                npc_id = npc.get("id", "").lower()
                npc_name = npc.get("name", "").lower()
                # Prefer exact match on id first
                if target_lower == npc_id:
                    return npc_id
                # Exact match on name
                if target_lower == npc_name:
                    return npc_id
                # Substring match: "aldric" in "aldric the innkeeper"
                if npc_id and npc_id in target_lower:
                    best_match = npc_id
                elif npc_name and npc_name in target_lower:
                    best_match = npc_id
                elif target_lower in npc_name:
                    best_match = npc_id
            if best_match:
                return best_match

        # No normalization found — return original
        return intent.target

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
        # Step 1a: Affordance planning (pre-routing interpretation against scene affordances)
        world_context = {}
        try:
            world_context = {}
            try:
                # Prefer latest turn if it contains NPC data; otherwise fall back to scene-context
                latest_turn = await self._client.get_latest_turn(character_id)
                wc = latest_turn.get("world_context", {}) or {}
                if wc.get("npcs"):
                    world_context = wc
                    # FIX ISSUE-018: Alias is_available/asleep from character-aware availability
                    # for legacy planner. NPC rows have 'available' (per-character), but
                    # NarrativePlanner checks 'is_available' and 'asleep'.
                    for npc in world_context.get("npcs", []):
                        if "is_available" not in npc:
                            npc["is_available"] = npc.get("available", True)
                        npc.setdefault("asleep", False)
                else:
                    raise ValueError("latest turn world_context has no NPCs")
            except Exception:
                pass  # latest_turn failed or had no NPCs; try scene-context

            if not world_context:
                try:
                    scene = await self._client.get_scene_context(character_id)
                    exits = scene.get("exits", [])
                    # Add/normalize backward-compatible NPC keys. Some scene-context
                    # responses include an empty `npcs` key and a populated `npcs_here`,
                    # so do not gate alias construction on key presence alone.
                    aliased_npcs = []
                    source_npcs = scene.get("npcs") or scene.get("npcs_here") or []
                    for npc in source_npcs:
                        npc_copy = dict(npc)
                        npc_copy["is_available"] = npc.get("is_available", npc.get("available", True))
                        npc_copy.setdefault("available", npc_copy.get("is_available", True))
                        npc_copy.setdefault("asleep", False)
                        aliased_npcs.append(npc_copy)
                    scene["npcs"] = aliased_npcs
                    # FIX 0c056bba: synthesis._extract_choices reads world_context["npcs_here"]
                    # for NPC name lookup. Provide both keys for backward compatibility.
                    scene["npcs_here"] = aliased_npcs
                    # Always populate locations and connections from exits if the scene lacks them
                    # or they are empty (scene_context may return empty 'locations' list).
                    if not scene.get("locations"):
                        scene["locations"] = exits
                    if not scene.get("connections"):
                        scene["connections"] = exits
                    if "current_location" not in scene or not isinstance(scene["current_location"], dict):
                        scene["current_location"] = {}
                    if "connections" not in scene["current_location"]:
                        scene["current_location"]["connections"] = exits
                    if "location" not in scene:
                        scene["location"] = scene.get("current_location", {})
                    world_context = scene
                except Exception:
                    pass  # Scene-context unavailable — proceed without context

            if world_context:
                plan = await self._planner.plan(character_id, player_message, world_context)
                if plan.decision != PlannerDecision.EXECUTE:
                    if plan.decision == PlannerDecision.REFUSE:
                        return RouterResult(
                            success=False,
                            endpoint_called="planner-refuse",
                            narration=plan.clarifying_question or plan.reason or "That action isn't available here.",
                            events=[
                                {
                                    "type": "affordance_planner",
                                    "decision": plan.decision.value,
                                    "reason": plan.reason,
                                    "confidence": plan.confidence,
                                    "clarifying_question": plan.clarifying_question,
                                    "narration_hint": plan.narration_hint,
                                }
                            ],
                            error=plan.clarifying_question or plan.reason or "Invalid action.",
                            error_status=400,
                            raw_response=plan.model_dump(),
                            intent=classify_intent(player_message),
                        )
                    # CLARIFY/NARRATE_NOOP are valid no-mutation responses.
                    return RouterResult(
                        success=True,
                        endpoint_called=f"planner-{plan.decision.value}",
                        narration=plan.clarifying_question or plan.reason or "That action isn't available here.",
                        events=[
                            {
                                "type": "affordance_planner",
                                "decision": plan.decision.value,
                                "reason": plan.reason,
                                "confidence": plan.confidence,
                                "clarifying_question": plan.clarifying_question,
                                "narration_hint": plan.narration_hint,
                            }
                        ],
                        raw_response=plan.model_dump(),
                        intent=classify_intent(player_message),
                    )
        except Exception:
            # Planner errors should NOT block the main flow — fall through to standard classification
            pass
        intent = classify_intent(player_message)

        # Step 1b: DM-agent fallback resolver for low-confidence/general input.
        # Deterministic routing still wins for precise known actions, but when the
        # parser cannot confidently map freeform language, ask the DM profile to
        # decide a bounded action or refuse/clarify. Every result is validated by
        # intent_fallback.py against scene affordances before reaching here.
        if not force_endpoint and (intent.type == IntentType.GENERAL or intent.confidence < 0.5):
            try:
                fallback = await resolve_fallback_intent(player_message, world_context)
                if fallback:
                    if fallback.decision == PlannerDecision.EXECUTE:
                        action_type = (fallback.action_type or "").lower().strip()
                        if action_type == "talk":
                            action_type = "interact"
                            intent_type = IntentType.TALK
                        else:
                            intent_type = {
                                "move": IntentType.MOVE,
                                "interact": IntentType.INTERACT,
                                "explore": IntentType.EXPLORE,
                                "look": IntentType.EXPLORE,
                                "rest": IntentType.REST,
                                "attack": IntentType.COMBAT,
                                "cast": IntentType.CAST,
                                "quest": IntentType.QUEST,
                                "puzzle": IntentType.PUZZLE,
                            }.get(action_type, IntentType.GENERAL)
                            if action_type == "look":
                                action_type = "explore"
                        details = {
                            "action_type": action_type,
                            "_original_msg": player_message,
                            "_dm_fallback": True,
                            "_dm_fallback_reason": fallback.reason,
                            "_dm_fallback_confidence": fallback.confidence,
                        }
                        if fallback.target:
                            details["target"] = fallback.target
                        intent = Intent(
                            type=intent_type,
                            target=fallback.target,
                            action_type=action_type,
                            details=details,
                            confidence=max(fallback.confidence, intent.confidence),
                        )
                    elif fallback.decision == PlannerDecision.REFUSE:
                        return RouterResult(
                            success=False,
                            endpoint_called="dm-fallback-refuse",
                            narration=fallback.clarifying_question or fallback.reason or "That action is invalid.",
                            events=[{
                                "type": "dm_fallback",
                                "decision": fallback.decision.value,
                                "reason": fallback.reason,
                                "confidence": fallback.confidence,
                            }],
                            error=fallback.clarifying_question or fallback.reason or "Invalid action.",
                            error_status=400,
                            raw_response=fallback.model_dump(),
                            intent=intent,
                        )
                    elif fallback.decision in {PlannerDecision.CLARIFY, PlannerDecision.NARRATE_NOOP}:
                        return RouterResult(
                            success=True,
                            endpoint_called=f"dm-fallback-{fallback.decision.value}",
                            narration=fallback.clarifying_question or fallback.narration_hint or fallback.reason or "What exactly are you trying to do?",
                            events=[{
                                "type": "dm_fallback",
                                "decision": fallback.decision.value,
                                "reason": fallback.reason,
                                "confidence": fallback.confidence,
                            }],
                            raw_response=fallback.model_dump(),
                            intent=intent,
                        )
            except Exception:
                pass  # Fallback resolver is advisory; deterministic route remains available.

        # Canonicalize natural language targets to known IDs using scene context.
        if intent.target and world_context:
            try:
                normalized = self._normalize_target(intent, world_context)

                # FIX ISSUE-019: if scene/latest context is too narrow to resolve a MOVE
                # alias, enrich from the full map and retry. This avoids false raw targets
                # such as "thornhold town square" reaching /actions as a location ID.
                if normalized == intent.target and intent.action_type == "move":
                    try:
                        map_data = await self._client.get_map_data()
                        world_locations = map_data.get("locations", []) if isinstance(map_data, dict) else []
                        if world_locations:
                            existing_ids = {
                                str(loc.get("id", "")).lower()
                                for loc in world_context.get("locations", [])
                                if isinstance(loc, dict)
                            }
                            merged_locations = list(world_context.get("locations", []) or [])
                            for loc in world_locations:
                                if isinstance(loc, dict) and str(loc.get("id", "")).lower() not in existing_ids:
                                    merged_locations.append(loc)
                            world_context["locations"] = merged_locations
                            if isinstance(map_data, dict) and map_data.get("current_location") and not world_context.get("current_location"):
                                world_context["current_location"] = map_data["current_location"]
                            normalized = self._normalize_target(intent, world_context)
                    except Exception:
                        pass  # Non-blocking — proceed with whatever context we already had

                if normalized and normalized != intent.target:
                    intent = Intent(
                        type=intent.type,
                        target=normalized,
                        action_type=intent.action_type,
                        details=dict(intent.details),
                        confidence=intent.confidence,
                    )
            except Exception:
                pass  # Non-blocking — send original target on normalization failure

        # Semantic guard — do not greenlight an action when the player-agent's
        # own text negates/refuses the embedded verb (e.g. "I don't want to go
        # to the woods"). This is a no-mutation guard before approval/routing.
        if intent.details.get("_semantic_guard"):
            return RouterResult(
                success=True,
                endpoint_called="semantic-guard",
                narration="You hold. The instruction is a refusal or caution, not permission to act. No travel, combat, item use, or other state-changing action is taken.",
                events=[{
                    "type": "semantic_guard",
                    "description": "Action blocked before server mutation because the player message negated/refused the embedded action.",
                    "reason": intent.details.get("_semantic_guard_reason"),
                    "player_message": player_message,
                }],
                raw_response={"semantic_guard": True, "reason": intent.details.get("_semantic_guard_reason")},
                intent=intent,
            )

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
                return await self._route_turn(character_id, player_message, intent)
            else:
                return await self._route_turn(character_id, player_message, intent)
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="error",
                error=f"Rules server error: {str(e)}",
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
                intent=intent,
            )

    async def _route_action(self, character_id: str, intent: Intent) -> RouterResult:
        """Route to POST /characters/{id}/actions."""
        try:
            # Build the payload — intent.details has action_type and possibly target
            payload = dict(intent.details)
            if intent.target:
                # Intent details are created before target normalization and may still
                # contain the raw phrase (e.g. "thornhold town square"). The canonical
                # Intent.target must win before POST /actions.
                payload["target"] = intent.target

            # Quest actions need special payload shaping: details.action = accept|complete|list
            if intent.action_type == "quest":
                details = payload.get("details", {})
                if isinstance(details, dict):
                    action_val = details.get("action", "")
                else:
                    action_val = ""
                if not action_val:
                    orig = payload.get("_original_msg", "").lower()
                    if "complete" in orig or "finish" in orig or "turn in" in orig:
                        action_val = "complete"
                    elif "list" in orig or "log" in orig or "view" in orig or "check" in orig:
                        action_val = "list"
                    else:
                        action_val = "accept"
                payload["details"] = {"action": action_val}

            result = await self._client.submit_action(character_id, payload)
            combat_data = result.get("combat") or {}

            # --- FIX c572fb73: rebuild world_context AFTER action resolves ---
            # The rules server may return a stale world_context; proactively refresh
            # from the authoritative latest turn to ensure narration sees post-action
            # reality (flag changes, location, inventory, NPC movements, quest state).
            fresh_world_context = await self._freshen_world_context(
                character_id, result.get("world_context")
            )

            result_kwargs = {
                "success": True,
                "endpoint_called": "actions",
                "narration": result.get("narration", ""),
                "events": result.get("events", []),
                "dice_log": result.get("dice_log", []),
                "character_state": result.get("character_state", {}),
                "world_context": fresh_world_context,
                "approval_triggered": result.get("approval_triggered", False),
                "approval_reason": result.get("approval_reason"),
                "raw_response": result,
            }
            if combat_data:
                result_kwargs.update({
                    "enemies": combat_data.get("enemies", []),
                    "round": combat_data.get("rounds", 0),
                    "combat_over": combat_data.get("victory") is not None or combat_data.get("hp_remaining", 1) <= 0,
                    "combat_result": "victory" if combat_data.get("victory") else "defeat" if combat_data.get("victory") is not None else None,
                    "combat_log": result.get("events", []),
                })
            return RouterResult(**result_kwargs, intent=intent)
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="actions",
                error=str(e),
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
                intent=intent,
            )

    async def _route_turn(self, character_id: str, player_message: str, intent: Optional["Intent"] = None) -> RouterResult:
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

            # --- FIX c572fb73: rebuild world_context AFTER turn resolves ---
            # The adventure turn can move the character, change flags, advance fronts,
            # spawn/remove NPCs, unlock quests. Fetch fresh world_context to reflect
            # the post-turn state so narration is never stale.
            fresh_world_context = await self._freshen_world_context(
                character_id, result.get("world_context")
            )

            return RouterResult(
                success=True,
                endpoint_called="turn/start",
                narration=result.get("narration", result.get("narrative", "")),
                events=result.get("events", []),
                dice_log=result.get("dice_log", []),
                character_state=character_state,
                world_context=fresh_world_context,
                turn_id=result.get("turn_id"),
                asks=result.get("asks", []),
                decision_point=result.get("decision_point"),
                available_actions=result.get("available_actions", []),
                combat_log=result.get("combat_log", []),
                turn_results=result.get("turn_results"),
                raw_response=result,
                intent=intent,
            )
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="turn/start",
                error=str(e),
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
                intent=intent,
            )

    async def _route_combat_start(self, character_id: str, intent: Intent) -> RouterResult:
        """Route to POST /characters/{id}/combat/start.

        Resolves encounter data from the character's world context, builds
        full enemy stat blocks, rolls initiative, and starts combat.
        """
        import json
        import random

        try:
            world_context = {}
            try:
                latest = await self._client.get_latest_turn(character_id)
                world_context = latest.get("world_context", {}) or {}
            except Exception:
                pass

            encounters = world_context.get("encounters", [])

            if not encounters:
                try:
                    turn_result = await self._client.start_turn(character_id, {
                        "goal": "explore",
                        "max_steps": 1,
                        "max_encounters": 0,
                    })
                    world_context = turn_result.get("world_context", {})
                    encounters = world_context.get("encounters", [])
                except Exception:
                    pass

            chosen_encounter = None
            target_lower = (intent.target or "").lower()

            if encounters:
                for enc in encounters:
                    enc_name = enc.get("name", "").lower()
                    enemy_types = [e.get("type", "").lower() for e in enc.get("enemies", [])]
                    if target_lower and (target_lower in enc_name or any(target_lower in et for et in enemy_types)):
                        chosen_encounter = enc
                        break
                if not chosen_encounter:
                    chosen_encounter = random.choice(encounters)

            if not chosen_encounter:
                return RouterResult(
                    success=False,
                    endpoint_called="combat/start",
                    error="No encounters available at current location",
                    error_status=404,
                    raw_response={"error": "no encounters"},
                    intent=intent,
                )

            # Resolve enemy stats
            encounter_enemies = chosen_encounter.get("enemies", [])
            enemies_list = []
            for eg in encounter_enemies:
                if "hp" in eg and "ac" in eg:
                    count = eg.get("count", 1)
                    for i in range(count):
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
                    intent=intent,
                )

            initiative_roll = random.randint(1, 20)
            encounter_name = chosen_encounter.get("name", "Wild Encounter")
            enemies_json = json.dumps(enemies_list)
            result = await self._client.start_combat(
                character_id, encounter_name, enemies_json, initiative_roll
            )

            # --- FIX c572fb73: refresh world_context after combat start ---
            fresh_world_context = await self._freshen_world_context(
                character_id, result.get("world_context")
            )

            return RouterResult(
                success=True,
                endpoint_called="combat/start",
                narration=result.get("narration", ""),
                events=result.get("events", []),
                dice_log=result.get("dice_log", []),
                character_state=result.get("character_state", {}),
                world_context=fresh_world_context,
                combat_over=result.get("combat_over", False),
                combat_result=result.get("result"),
                combat_log=result.get("events", []),
                enemies=result.get("enemies", []),
                round=result.get("round", 0),
                is_your_turn=result.get("is_your_turn", False),
                raw_response=result,
                intent=intent,
            )
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="combat/start",
                error=str(e),
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
                intent=intent,
            )

    async def _route_combat_act(self, character_id: str, intent: Intent, combat_state: dict) -> RouterResult:
        """Route to POST /characters/{id}/combat/act — active combat detected."""
        import random

        action = "attack"
        if intent.type == IntentType.REST:
            action = "defend"
        elif intent.type == IntentType.MOVE:
            action = "flee"

        try:
            d20_roll = random.randint(1, 20)
            payload = {"action": action, "d20_roll": d20_roll}
            target_index = 0
            if intent.target:
                target_lower = intent.target.lower()
                enemies = combat_state.get("enemies", [])
                for i, e in enumerate(enemies):
                    if target_lower in e.get("name", "").lower():
                        target_index = i
                        break
            payload["target_index"] = target_index

            result = await self._client.combat_act(character_id, payload)

            # --- FIX c572fb73: refresh world_context after combat round ---
            fresh_world_context = await self._freshen_world_context(
                character_id, result.get("world_context")
            )

            return RouterResult(
                success=True,
                endpoint_called="combat/act",
                narration=result.get("narration", ""),
                events=result.get("events", []),
                dice_log=result.get("dice_log", []),
                character_state=result.get("character_state", {}),
                world_context=fresh_world_context,
                combat_over=result.get("combat_over", False),
                combat_result=result.get("result"),
                enemies=result.get("enemies", []),
                round=result.get("round", 0),
                combat_log=result.get("events", []),
                is_your_turn=result.get("is_your_turn", False),
                raw_response=result,
                intent=intent,
            )
        except Exception as e:
            return RouterResult(
                success=False,
                endpoint_called="combat/act",
                error=str(e),
                error_status=_extract_error_status(e),
                raw_response={"error": str(e)},
                intent=intent,
            )
