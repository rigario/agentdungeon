"""Approval Gate Service — shared gate evaluation logic.

Centralizes the approvalgating rules so they can be used by:
- app/routers/combat.py (the /approval-check endpoint)
- app/routers/actions.py (submit_action gate)
- dm-runtime (dm_turn gate, via local import for eval or httpx call to rules-server)

Gate categories:
- Low HP (< threshold)
- Cast high-level spells
- Interact with named/story NPCs
- Quest acceptance / moral choices
- Enter dangerous area (level > char+1)
- Flee combat (when configured)
"""

from __future__ import annotations
from typing import Optional, Dict, Any, List
import sqlite3


def evaluate_approval_gate(
    character: Dict[str, Any],
    action_type: str,
    target: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    location: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Evaluate whether an action requires human approval.

    Args:
        character: Character row dict (must include hp_current, hp_max, level, approval_config)
        action_type: One of: move, attack, cast, rest, explore, interact, quest_accept, moral_choice, flee
        target: Optional target name/location_id
        details: Optional action details dict (spell info, etc.)
        location: Optional pre-fetched location row dict (to avoid re-query)

    Returns:
        {"needs_approval": bool, "reasons": List[str], "context": {...}}
    """
    reasons: List[str] = []
    config = character.get("approval_config") or {}
    if isinstance(config, str):
        import json
        config = json.loads(config) or {}

    hp_current = int(character.get("hp_current", 0))
    hp_max = int(character.get("hp_max", 1))
    hp_pct = (hp_current / hp_max * 100) if hp_max > 0 else 100

    character_level = character.get("level", 1)

    # Rule 1: Low HP threshold
    if hp_pct < config.get("hp_threshold_pct", 25):
        reasons.append(f"HP at {hp_pct:.0f}% (threshold: {config.get('hp_threshold_pct', 25)}%)")

    # Rule 2: High-level spell casting
    if action_type == "cast" and details:
        spell_level = details.get("spell_level", 0)
        if spell_level >= config.get("spell_level_min", 3):
            reasons.append(f"Spell level {spell_level} >= {config.get('spell_level_min', 3)}")

    # Rule 3: Named/story NPC interaction
    if action_type == "interact" and details:
        if details.get("is_named") and config.get("named_npc_interaction", True):
            reasons.append("Named/story NPC")

    # Rule 4: Quest acceptance
    if action_type == "quest_accept" and config.get("quest_acceptance", True):
        reasons.append("Quest acceptance")

    # Rule 5: Moral choice
    if action_type == "moral_choice" and config.get("moral_choice", True):
        reasons.append("Moral choice")

    # Rule 6: Dangerous area entry
    if action_type == "move" and location:
        recommended = location.get("recommended_level", 1)
        if recommended > character_level + 1 and config.get("dangerous_area_entry", True):
            loc_name = location.get("name") or location.get("id") or target or "unknown"
            reasons.append(f"Dangerous area: {loc_name} (level {recommended})")

    # Rule 7: Fleeing combat
    if action_type == "flee" and config.get("flee_combat", False):
        reasons.append("Fleeing combat")

    return {
        "needs_approval": len(reasons) > 0,
        "reasons": reasons,
        "context": {
            "hp": {"current": hp_current, "max": hp_max, "pct": round(hp_pct, 1)},
            "character_level": character_level,
            "action_type": action_type,
        },
    }


def gate_action(
    character_id: str,
    action_type: str,
    target: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    *,
    raise_on_approval: bool = True,
) -> Optional[Dict[str, Any]]:
    """Evaluate an action against approval gates. If gated, either raise or return gate info.

    Args:
        character_id: Character to check
        action_type: Action type
        target: Optional target
        details: Optional action details
        raise_on_approval: If True, raise HTTPException when approval needed. If False, return gate result.

    Returns:
        None if action proceeds (no gate), else gate result dict.

    Raises:
        HTTPException(202) if raise_on_approval=True and gate fires.
    """
    from fastapi import HTTPException
    from app.services.database import get_db

    conn = get_db()
    char_row = conn.execute(
        "SELECT * FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    conn.close()

    if not char_row:
        raise HTTPException(status_code=404, detail=f"Character not found: {character_id}")

    char = dict(char_row)

    # Fetch location if action is move/dange, row
    location = None
    if action_type == "move":
        loc_id = char.get("location_id")
        if loc_id:
            conn = get_db()
            loc_row = conn.execute(
                "SELECT * FROM locations WHERE id = ?", (loc_id,)
            ).fetchone()
            conn.close()
            if loc_row:
                location = dict(loc_row)

    result = evaluate_approval_gate(
        character=char,
        action_type=action_type,
        target=target,
        details=details,
        location=location,
    )

    if result["needs_approval"]:
        if raise_on_approval:
            raise HTTPException(
                status_code=202,  # Accepted — processing halted, awaiting approval
                detail={
                    "error": "approval_required",
                    "reasons": result["reasons"],
                    "context": result["context"],
                    "action_type": action_type,
                    "character_id": character_id,
                },
            )
        return result

    return None
