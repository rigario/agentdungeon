"""D20 Agent RPG — NPC movement service.

Handles NPC relocation between locations based on:
- Narrative flags (Green Woman retreats, Kol moves to seal chamber)
- Quest completion (Drenna returns to Thornhold)
- Scheduled patrol/travel (Ser Maren patrols, Kira travels)
- Time-based movement (future: day/night cycles)

All movement is server-side — agents observe where NPCs are, they don't move them.
"""

import json
import logging
from app.services.database import get_db

logger = logging.getLogger(__name__)


def get_npcs_at_location(location_id: str) -> list[dict]:
    """Get all NPCs currently at a given location."""
    conn = get_db()
    rows = conn.execute("""
        SELECT id, name, archetype, current_location_id, movement_rules_json
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


def move_npc(npc_id: str, target_location_id: str, reason: str = "manual") -> dict:
    """Move an NPC to a new location.

    Args:
        npc_id: The NPC to move.
        target_location_id: Where to move them (None = remove from world).
        reason: Human-readable reason for the move.

    Returns:
        Dict with old_location, new_location, and event data.
    """
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
        "reason": reason
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


def evaluate_movement_triggers(narrative_flags: dict, active_quests: list[str] = None) -> list[dict]:
    """Check all NPC movement triggers against current game state.

    Args:
        narrative_flags: Dict of flag_key -> flag_value from the narrative system.
        active_quests: List of completed quest IDs.

    Returns:
        List of movement events that should fire.
    """
    conn = get_db()
    rows = conn.execute(
        "SELECT id, name, current_location_id, movement_rules_json FROM npcs"
    ).fetchall()
    conn.close()

    movements = []
    active_quests = active_quests or []

    for row in rows:
        npc_id = row[0]
        npc_name = row[1]
        current_loc = row[2]
        rules_json = row[3]

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

            # Check flag-based triggers
            if 'flag' in trigger:
                flag_key = trigger['flag']
                if flag_key in narrative_flags:
                    flag_val = narrative_flags[flag_key]
                    # Flag exists and is truthy
                    if flag_val and flag_val != 'false' and flag_val != '0':
                        should_move = True

            # Check quest-completion triggers
            if 'quest_complete' in trigger:
                quest_id = trigger['quest_complete']
                if quest_id in active_quests:
                    should_move = True

            if should_move:
                target = trigger.get('target')
                if target != current_loc:
                    movements.append({
                        'npc_id': npc_id,
                        'npc_name': npc_name,
                        'from': current_loc,
                        'to': target,
                        'reason': reason
                    })
                # Only fire the first matching trigger per NPC
                break

    return movements


def process_movement_triggers(narrative_flags: dict, active_quests: list[str] = None) -> list[dict]:
    """Evaluate and execute all pending NPC movements.

    Returns list of movements that were executed.
    """
    movements = evaluate_movement_triggers(narrative_flags, active_quests)
    executed = []

    for move in movements:
        result = move_npc(move['npc_id'], move['to'], reason=move['reason'])
        if result.get('moved'):
            executed.append(result)

    return executed


def get_npcs_visible_to_character(character_id: str) -> list[dict]:
    """Get NPCs at the character's current location."""
    conn = get_db()
    char_row = conn.execute(
        "SELECT current_location_id FROM characters WHERE id = ?",
        (character_id,)
    ).fetchone()

    if not char_row:
        conn.close()
        return []

    location_id = char_row[0]

    rows = conn.execute("""
        SELECT id, name, archetype, personality, is_quest_giver, is_spirit, is_enemy
        FROM npcs
        WHERE current_location_id = ?
        ORDER BY name
    """, (location_id,)).fetchall()
    conn.close()

    return [dict(r) for r in rows]
