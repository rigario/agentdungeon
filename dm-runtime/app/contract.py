"""D20 DM Runtime — Formal Contract Definition.

This module defines the payload schemas, authority boundaries, and routing
policy for the DM runtime. It is the single source of truth for what the
DM runtime can send to and receive from the rules server, and what it may
synthesize into player-facing output.

Three-entity contract:
    Player Agent → DM Runtime → Rules Server → DM synthesis → Player

Authority invariants (enforced by schema, not just docs):
    - Rules server owns: rolls, state transitions, combat, XP, loot, quest state
    - DM runtime owns: narration, NPC voice, pacing, choice framing
    - DM runtime MUST NOT: write to DB, invent world objects, replace server truth
"""

from __future__ import annotations
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field, model_validator


# =============================================================================
# Intent Classification
# =============================================================================

class IntentType(str, Enum):
    """Player intent categories recognized by the DM runtime."""
    MOVE = "move"
    TALK = "talk"
    COMBAT = "combat"
    REST = "rest"
    LOOK = "look"
    EXPLORE = "explore"
    INTERACT = "interact"
    PUZZLE = "puzzle"
    CAST = "cast"
    QUEST = "quest"
    GENERAL = "general"


class ServerEndpoint(str, Enum):
    """Which rules server endpoint to call for a given intent."""
    ACTIONS = "actions"      # POST /characters/{id}/actions
    TURN = "turn"            # POST /characters/{id}/turn/start
    COMBAT = "combat"        # /characters/{id}/combat/*


class IntentClassification(BaseModel):
    """Result of classifying a player message into a server-callable intent."""
    type: IntentType
    target: Optional[str] = None
    details: dict = Field(default_factory=dict)
    server_endpoint: ServerEndpoint

    model_config = {"frozen": True}


# =============================================================================
# DM → Rules Server (Outbound) Contracts
# =============================================================================

class DMActionRequest(BaseModel):
    """What the DM runtime sends to POST /characters/{id}/actions.

    The DM runtime translates player intent into a structured action request.
    It does NOT resolve rules — the server does that.
    """
    action_type: str = Field(..., description="move, attack, rest, explore, interact, puzzle, cast")
    target: Optional[str] = Field(None, description="Target location ID, NPC name, or entity")
    details: Optional[dict] = Field(None, description="Extra parameters (rest_type, spell, etc.)")

    @model_validator(mode="after")
    def action_type_valid(self) -> "DMActionRequest":
        valid = {"move", "attack", "rest", "explore", "interact", "puzzle", "cast", "quest"}
        if self.action_type not in valid:
            raise ValueError(f"action_type must be one of {valid}, got '{self.action_type}'")
        return self


class DMTurnRequest(BaseModel):
    """What the DM runtime sends to POST /characters/{id}/turn/start."""
    intent: str = Field(..., description="Freeform player intent description")
    aggression_slider: Optional[int] = Field(None, ge=0, le=100)


class DMCombatAction(BaseModel):
    """What the DM runtime sends to POST /characters/{id}/combat/act."""
    action_type: str = Field(default="attack")
    target: Optional[str] = None
    details: Optional[dict] = None


# =============================================================================
# Rules Server → DM Runtime (Inbound) Contracts
# =============================================================================

class ServerNarration(BaseModel):
    """Server-provided narrative fragment (if any)."""
    text: str = ""
    source: str = "server"


class ServerDecisionPoint(BaseModel):
    """A decision point that requires player/human input."""
    type: str = Field(..., description="danger, npc, quest, moral, location, combat_end")
    description: str = ""
    options: list = Field(default_factory=list)


class ServerWorldContext(BaseModel):
    """Bounded context the rules server provides — the DM's scope.

    The DM runtime MUST treat this as a hard boundary: never invent
    NPCs, locations, items, or outcomes not present in this object.
    """
    location: dict = Field(default_factory=dict)
    character: dict = Field(default_factory=dict)
    npcs: list = Field(default_factory=list)
    connections: list = Field(default_factory=list)
    encounters: list = Field(default_factory=list)
    atmosphere: dict = Field(default_factory=dict)
    front_progression: dict = Field(default_factory=dict)
    active_quests: list = Field(default_factory=list)
    key_items: list = Field(default_factory=list)


class ServerActionResult(BaseModel):
    """Full response from POST /characters/{id}/actions."""
    success: bool = True
    narration: str = ""
    events: list = Field(default_factory=list)
    character_state: dict = Field(default_factory=dict)
    world_context: Optional[dict] = None
    dice_log: list = Field(default_factory=list)
    decision_log: list = Field(default_factory=list)
    approval_triggered: bool = False
    approval_reason: Optional[str] = None


class ServerTurnResult(BaseModel):
    """Full response from POST /characters/{id}/turn/start."""
    turn_id: Optional[str] = None
    narrative: str = ""
    asks: list = Field(default_factory=list)
    world_context: Optional[dict] = None
    decision_point: Optional[dict] = None
    dice_log: list = Field(default_factory=list)
    decision_log: list = Field(default_factory=list)
    combat_log: list = Field(default_factory=list)
    turn_results: Optional[list] = None
    available_actions: list = Field(default_factory=list)


class ServerCombatResult(BaseModel):
    """Full response from combat endpoints."""
    status: str = ""
    round: int = 0
    narration: str = ""
    events: list = Field(default_factory=list)
    character_state: dict = Field(default_factory=dict)
    enemy_state: list = Field(default_factory=list)
    combat_log: list = Field(default_factory=list)
    loot: Optional[dict] = None
    xp_gained: Optional[int] = None


# =============================================================================
# DM Runtime → Player (Player-Facing) Contracts
# =============================================================================

class NPCLine(BaseModel):
    """A single NPC dialogue line."""
    speaker: str
    text: str
    tone: Optional[str] = None


class NarrationPayload(BaseModel):
    """Rich DM prose for the player."""
    scene: str = Field(..., description="DM prose describing what happened")
    npc_lines: list[NPCLine] = Field(default_factory=list)
    tone: str = Field(default="neutral", description="ominous, hopeful, tense, neutral, etc.")


class MechanicsPayload(BaseModel):
    """Visible mechanical summary for player trust."""
    what_happened: list[str] = Field(default_factory=list)
    hp: dict = Field(default_factory=dict)
    xp: Optional[dict] = None
    location: str = ""
    loot: Optional[dict] = None


class ChoiceOption(BaseModel):
    """A single player-facing choice."""
    id: str
    label: str
    description: Optional[str] = None


class ServerTrace(BaseModel):
    """Debugging/audit trace — never shown to players."""
    turn_id: Optional[str] = None
    decision_point: Optional[dict] = None
    available_actions: list = Field(default_factory=list)
    combat_log: list = Field(default_factory=list)
    intent_used: Optional[dict] = None
    server_endpoint_called: str = ""
    raw_server_response_keys: list = Field(default_factory=list)


class DMResponse(BaseModel):
    """The final player-facing payload from the DM runtime.

    This is what the player (or player agent) sees after one turn.
    """
    narration: NarrationPayload
    mechanics: MechanicsPayload = Field(default_factory=MechanicsPayload)
    choices: list[ChoiceOption] = Field(default_factory=list)
    server_trace: ServerTrace = Field(default_factory=ServerTrace)
    session_id: Optional[str] = None
    portal_url: Optional[str] = None


# =============================================================================
# Session Memory
# =============================================================================

class DMSessionState(BaseModel):
    """Lightweight session memory owned by the DM runtime.

    This is NOT authoritative game state — it only preserves narrative
    continuity between turns. The rules server owns all truth.
    """
    session_id: str
    character_id: str
    latest_turn_id: Optional[str] = None
    current_scene_summary: str = ""
    last_location: Optional[str] = None
    last_speaking_npc: Optional[str] = None
    open_choices: list[str] = Field(default_factory=list)
    unresolved_tensions: list[str] = Field(default_factory=list)
    narration_tone: str = "neutral"
    turn_count: int = 0


# =============================================================================
# Authority Boundary Enforcement
# =============================================================================

class AuthorityBoundary:
    """Constants defining what the DM runtime may and may not do.

    These are enforced by convention + code review, not runtime checks
    (the server rejects invalid writes anyway). Documented here as the
    contract's authoritative reference.
    """

    # The DM runtime OWNS these (may synthesize freely):
    DM_OWNED = {
        "descriptive_prose",
        "npc_voice",
        "pacing_and_emphasis",
        "scene_transitions",
        "mechanical_detail_exposure",  # how much dice/HP detail to show
        "choice_framing",
        "tone_setting",
    }

    # The rules server OWNS these (DM must pass through verbatim):
    SERVER_OWNED = {
        "encounter_rolls",
        "initiative_order",
        "enemy_attacks",
        "damage_calculation",
        "xp_loot_application",
        "quest_state_transitions",
        "front_state_transitions",
        "death_defeat_conditions",
        "hidden_dm_checks",
        "approval_triggers",
    }

    # The DM runtime MUST NEVER do these:
    FORBIDDEN = {
        "direct_db_writes",
        "freeform_world_mutation",
        "invent_off_contract_npcs",
        "invent_off_contract_locations",
        "invent_off_contract_items",
        "invent_outcomes",
        "replace_server_truth",
        "override_approval_gates",
        "self_modify_character_state",
    }


# =============================================================================
# Sync/Async Routing Policy
# =============================================================================

class RoutingPolicy:
    """Defines which server endpoint to use for each intent pattern.

    Sync loop (active play):
        - Player sends message → DM classifies → server call → narration → player
        - Used for: travel, exploration, NPC interaction, puzzles, combat rounds

    Async loop (persistent play):
        - Cron/agent submits broad intent → server simulates → stores result
        - DM later converts result into recap
        - Used for: idle adventuring, background travel, while-you-were-away
    """

    SYNC_ENDPOINTS = {
        IntentType.MOVE: ServerEndpoint.ACTIONS,
        IntentType.TALK: ServerEndpoint.ACTIONS,
        IntentType.EXPLORE: ServerEndpoint.ACTIONS,
        IntentType.INTERACT: ServerEndpoint.ACTIONS,
        IntentType.REST: ServerEndpoint.ACTIONS,
        IntentType.LOOK: ServerEndpoint.ACTIONS,
        IntentType.PUZZLE: ServerEndpoint.ACTIONS,
        IntentType.CAST: ServerEndpoint.ACTIONS,
        IntentType.QUEST: ServerEndpoint.ACTIONS,
        IntentType.COMBAT: ServerEndpoint.COMBAT,
        IntentType.GENERAL: ServerEndpoint.TURN,
    }

    ASYNC_ENDPOINTS = {
        IntentType.GENERAL: ServerEndpoint.TURN,
        IntentType.MOVE: ServerEndpoint.TURN,
        IntentType.REST: ServerEndpoint.TURN,
    }

    @classmethod
    def get_endpoint(cls, intent_type: IntentType, async_mode: bool = False) -> ServerEndpoint:
        """Route an intent to the correct server endpoint."""
        table = cls.ASYNC_ENDPOINTS if async_mode else cls.SYNC_ENDPOINTS
        return table.get(intent_type, ServerEndpoint.TURN)


# =============================================================================
# Contract Version
# =============================================================================

CONTRACT_VERSION = "1.0.0"
CONTRACT_DOC = "DM-RUNTIME-ARCHITECTURE.md"
