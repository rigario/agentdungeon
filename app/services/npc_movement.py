"""D20 Agent RPG — NPC movement and availability service.

Handles NPC relocation between locations based on:
- Narrative flags (Green Woman retreats, Kol moves to seal chamber)
- Quest completion (Drenna returns to Thornhold)
- Scheduled patrol/travel (Ser Maren patrols, Kira travels)
- Time-based movement (via time_of_day)
- Flag-based availability (required_flags, blocked_flags)

All movement is server-side — agents observe where NPCs are, they don't move them.
Availability filtering character-aware — hubs feel dynamic when player context is known.
"""

import json
import logging
from typing import Optional, Dict, Any, List
from app.services.database import get_db
from app.services.time_of_day import is_npc_available as time_based_available

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Location queries — raw DB access
# ---------------------------------------------------------------------------

def get_npcs_at_location(location_id: str) -> list[dict]:
    """Get all NPCs currently at a given location (full DB rows)."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, name, archetype, personality, dialogue_templates, is_quest_giver, is_spirit, is_enemy,
               image_url, movement_rules_json, current_location_id, default_location_id
        FROM npcs
        WHERE current_location_id = ?
        ORDER BY name
    """, (location_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_all_npc_locations() -> list[dict]:
    """Get current location of every NPC."""
    conn = get_db()
    rows = conn.execute("""
        SELECT n.id, n.name, n.current_location_id, n.default_location_id,
               l.name as location_name, l.biome as location_biome
        FROM npcs n
        LEFT JOIN locations l ON n.current_location_id = l.id
        ORDER BY n.name
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Physical movement — relocation
# ---------------------------------------------------------------------------

def move_npc(npc_id: str, target_location_id: str, reason: str = "manual") -> dict:
    """Move an NPC to a new location."""
    conn = get_db()
    conn.row_factory = None  # Use tuples for writes

    row = conn.execute(
        "SELECT id, name, current_location_id FROM npcs WHERE id = ?",
        (npc_id,)
    ).fetchone()

    if not row:
        conn.close()
        raise ValueError(f"NPC not found: {npc_id}")

    npc_name = row[1]
    old_location = row[2]

    if old_location == target_location_id:
        conn.close()
        return {"moved": False, "reason": "already at location"}

    conn.execute(
        "UPDATE npcs SET current_location_id = ? WHERE id = ?",
        (target_location_id, npc_id)
    )
    conn.commit()
    conn.close()

    logger.info(f"NPC moved: {npc_name} ({npc_id}) {old_location} -> {target_location_id} [{reason}]")

    return {
        "moved": True,
        "npc_id": npc_id,
        "npc_name": npc_name,
        "old_location": old_location,
        "new_location": target_location_id,
        "reason": reason,
    }


def reset_npc_to_default(npc_id: str) -> dict:
    """Reset an NPC to their default location."""
    conn = get_db()
    row = conn.execute(
        "SELECT default_location_id FROM npcs WHERE id = ?",
        (npc_id,)
    ).fetchone()
    conn.close()

    if not row:
        raise ValueError(f"NPC not found: {npc_id}")

    default_loc = row[0]
    return move_npc(npc_id, default_loc, reason="reset to default")


# ---------------------------------------------------------------------------
# Narrative-flag-based movement triggers
# ---------------------------------------------------------------------------

def evaluate_movement_triggers(narrative_flags: dict, active_quests: list[str] = None) -> list[dict]:
    """
    Check all NPC movement triggers against current game state.

    Returns list of movement events that should fire.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, current_location_id, movement_rules_json, default_location_id FROM npcs"
    ).fetchall()
    conn.close()

    movements = []
    active_quests = active_quests or []

    for row in rows:
        npc_id = row[0]
        npc_name = row[1]
        current_loc = row[2]
        rules_json = row[3]
        default_loc = row[4]

        if not rules_json:
            continue

        try:
            rules = json.loads(rules_json)
        except (json.JSONDecodeError, TypeError):
            continue

        triggers = rules.get('triggers', [])

        for trigger in triggers:
            should_move = False
            reason = trigger.get('description', 'narrative event')
            target = trigger.get('target')

            # Flag-based trigger
            if 'flag' in trigger:
                flag_key = trigger['flag']
                flag_val = narrative_flags.get(flag_key)
                if flag_val and flag_val not in ('false', '0', 0):
                    should_move = True

            # Quest-completion trigger
            if 'quest_complete' in trigger:
                quest_id = trigger['quest_complete']
                if quest_id in active_quests:
                    should_move = True

            if should_move:
                # target=None means leave the world (unmoved/unspawned)
                if target != current_loc:
                    movements.append({
                        'npc_id': npc_id,
                        'npc_name': npc_name,
                        'from': current_loc,
                        'to': target,
                        'reason': reason,
                    })
                # Only fire the first matching trigger per NPC
                break

    return movements


def process_movement_triggers(narrative_flags: dict, active_quests: list[str] = None) -> list[dict]:
    """Evaluate and execute all pending NPC movements. Returns list of movements executed."""
    movements = evaluate_movement_triggers(narrative_flags, active_quests)
    executed = []

    for move in movements:
        result = move_npc(move['npc_id'], move['to'], reason=move['reason'])
        if result.get('moved'):
            executed.append(result)

    return executed


# ---------------------------------------------------------------------------
# Availability evaluation — character-aware filtering
# ---------------------------------------------------------------------------

def get_npc_availability_status(npc_row: dict, character_context: Optional[Dict[str, Any]] = None) -> dict:
    """
    Compute availability status for a single NPC with full game context.

    Checks (cumulative — all must pass for NPC to be available):
      - `movement_rules_json.availability_hours` (time window override)
      - `movement_rules_json.required_flags` (must all be set)
      - `movement_rules_json.blocked_flags` (must all be absent)
      - Global NPC_HOURS (from time_of_day) if no per-NPC hour override
      - Presence in wilderness avoids time restrictions (spirits/hunters always avail)

    Args:
        npc_row: NPC database row dict (should include movement_rules_json)
        character_context: Optional dict with:
            - narrative_flags: {flag_key: value}
            - quests: list of quest IDs
            - game_hour: int (0–23)

    Returns:
        {
            "available": bool,
            "reasons": list[str],      # why available or not
            "requirements": {           # what this NPC requires
                "flags_required": list[str],
                "flags_blocked": list[str],
                "hours": [start,end] | None,
            }
        }
    """
    available = True
    reasons = []
    requirements = {"flags_required": [], "flags_blocked": [], "hours": None}

    # Parse movement_rules_json (already-available metadata source)
    rules = {}
    raw_rules = npc_row.get("movement_rules_json")
    if raw_rules:
        try:
            rules = json.loads(raw_rules)
        except (json.JSONDecodeError, TypeError):
            rules = {}

    # 1. Per-NPC availability_hours override (if defined)
    avail_hours = rules.get("availability_hours")
    requirements["hours"] = avail_hours

    if avail_hours and character_context:
        game_hour = character_context.get("game_hour")
        if game_hour is not None:
            start, end = avail_hours
            # Handle wrap-around (e.g. 22-6) but most hours are start <= end
            if start <= end:
                in_window = start <= game_hour <= end
            else:
                in_window = game_hour >= start or game_hour <= end
            if not in_window:
                available = False
                reasons.append(f"Outside available hours {start}:00–{end}:00")

    # 2. Required flags — ALL must be present and truthy
    req_flags = rules.get("required_flags", [])
    requirements["flags_required"] = req_flags
    if character_context and req_flags:
        flags = character_context.get("narrative_flags", {})
        for flag in req_flags:
            v = flags.get(flag)
            if not v or v in ('false', '0', 0):
                available = False
                reasons.append(f"Missing required flag: {flag}")

    # 3. Blocked flags — ANY present is enough to block
    blocked_flags = rules.get("blocked_flags", [])
    requirements["flags_blocked"] = blocked_flags
    if character_context and blocked_flags:
        flags = character_context.get("narrative_flags", {})
        for flag in blocked_flags:
            v = flags.get(flag)
            if v and v not in ('false', '0', 0):
                available = False
                reasons.append(f"Blocked by flag: {flag}")

    # 4. Fallback to global NPC_HOURS (legacy) — used when no per-NPC hours override
    # spirits/hunters (is_spirit=1) pass automatically via NPC_HOURS (always 0-23)
    if character_context and "game_hour" in character_context and not avail_hours:
        if not time_based_available(npc_row["id"], character_context["game_hour"]):
            available = False
            reasons.append("Not available at this hour (global schedule)")

    if available and not reasons:
        reasons.append("All conditions met")

    return {
        "available": available,
        "reasons": reasons,
        "requirements": requirements,
    }


def get_available_npcs_at_location(location_id: str, character_context: Optional[Dict[str, Any]] = None) -> dict:
    """
    Get NPCs at a location categorized by current availability.

    With character context (character_id or explicit flags/hour): returns split lists.
    Without character context: legacy mode returning all as 'all_npcs' with empty available/unavailable.

    Args:
        location_id: Location to query
        character_context: Dict with narrative_flags, quests, game_hour

    Returns:
        {
            "location_id": str,
            "all_npcs": list[dict],      # full NPC summary (id, name, archetype, ...)
            "available": list[dict],     # subset with availability_reason
            "unavailable": list[dict],   # subset with unavailable_reason
        }
    """
    all_rows = get_npcs_at_location(location_id)

    all_summary = []
    available = []
    unavailable = []

    for npc in all_rows:
        summary = {
            "id": npc["id"],
            "name": npc["name"],
            "archetype": npc.get("archetype", "unknown"),
            "is_quest_giver": bool(npc.get("is_quest_giver")),
            "personality": npc.get("personality", ""),
            "image_url": npc.get("image_url"),
        }
        all_summary.append(summary)

        status = get_npc_availability_status(npc, character_context)
        if status["available"]:
            available.append(summary | {"availability_reason": status["reasons"][0]})
        else:
            unavailable.append(summary | {"unavailable_reason": "; ".join(status["reasons"])})

    return {
        "location_id": location_id,
        "all_npcs": all_summary,
        "available": available,
        "unavailable": unavailable,
    }


# ---------------------------------------------------------------------------
# Character-scoped NPC visibility helper (used by portal & map)
# ---------------------------------------------------------------------------

def get_npcs_visible_to_character(character_id: str) -> list[dict]:
    """
    Get available NPCs at the character's current location with full availability context.
    Returns list of NPC dicts (available only).
    """
    conn = get_db()
    char_row =        conn.execute(
            "SELECT location_id AS current_location_id, game_hour FROM characters WHERE id = ?",
            (character_id,)
        ).fetchone()
    conn.close()

    if not char_row:
        return []

    location_id = char_row[0]
    game_hour = char_row[1] if char_row[1] is not None else 8

    # Build character narrative_flags dict
    conn2 = get_db()
    flag_rows = conn2.execute(
        "SELECT flag_key, flag_value FROM narrative_flags WHERE character_id = ?",
        (character_id,)
    ).fetchall()
    conn2.close()
    narrative_flags = {r[0]: r[1] for r in flag_rows}

    context = {
        "game_hour": game_hour,
        "narrative_flags": narrative_flags,
        "character_id": character_id,
    }

    avail_data = get_available_npcs_at_location(location_id, context)
    return avail_data["available"]
