"""D20 Agent RPG — Scene Context Service.

Aggregates all narrative state for a character into a single bounded payload
intended for DM runtime decision-making. Provides a unified view of what the
player can see and do in the current scene.
"""

from __future__ import annotations

import json
import datetime
from typing import Optional, Dict, Any, List
from app.services.database import get_db
from app.services.npc_movement import get_available_npcs_at_location, get_npcs_at_location
from app.services.key_items import get_key_items
from app.services.hub_rumors import get_hub_rumors


def _get_character_row(conn, character_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT id, name, level, hp_current, hp_max, location_id, campaign_id, game_hour "
        "FROM characters WHERE id = ?",
        (character_id,),
    ).fetchone()
    return dict(row) if row else None


def _get_location_row(conn, location_id: str, campaign_id: str | None = None) -> Optional[Dict[str, Any]]:
    if campaign_id:
        rows = conn.execute(
            "SELECT id, name, biome, description, hostility_level, encounter_threshold, "
            "recommended_level, connected_to, image_url "
            "FROM locations WHERE id = ? AND campaign_id = ?",
            (location_id, campaign_id),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, biome, description, hostility_level, encounter_threshold, "
            "recommended_level, connected_to, image_url "
            "FROM locations WHERE id = ?",
            (location_id,),
        ).fetchall()
    return dict(rows[0]) if rows else None


def _get_connected_locations(conn, location_ids: List[str], campaign_id: str | None = None) -> List[Dict[str, Any]]:
    if not location_ids:
        return []
    placeholders = ",".join("?" * len(location_ids))
    if campaign_id:
        rows = conn.execute(
            f"SELECT id, name, biome, hostility_level FROM locations "
            f"WHERE id IN ({placeholders}) AND campaign_id = ?",
            location_ids + [campaign_id],
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT id, name, biome, hostility_level FROM locations "
            f"WHERE id IN ({placeholders})",
            location_ids,
        ).fetchall()
    return [dict(r) for r in rows]


def _get_combat_state(conn, character_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT id, encounter_name, round, turn_index, status, started_at "
        "FROM combats WHERE character_id = ? AND status = 'active'",
        (character_id,),
    ).fetchone()
    if not row:
        return None
    d = dict(row)
    participants = conn.execute(
        "SELECT participant_type, COUNT(*) as count FROM combat_participants "
        "WHERE combat_id = ? GROUP BY participant_type",
        (d["id"],),
    ).fetchall()
    d["participants"] = {r["participant_type"]: r["count"] for r in participants}
    return d


def _get_mark_stage(conn, character_id: str) -> int:
    row = conn.execute(
        "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?",
        (character_id,),
    ).fetchone()
    return row["mark_of_dreamer_stage"] if row else 0


def _get_narrative_flag_keys(conn, character_id: str) -> Dict[str, str]:
    rows = conn.execute(
        "SELECT flag_key, flag_value FROM narrative_flags WHERE character_id = ?",
        (character_id,),
    ).fetchall()
    return {r["flag_key"]: r["flag_value"] for r in rows}


def _get_active_quests(conn, character_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        "SELECT quest_id, quest_title, status, accepted_at "
        "FROM character_quests "
        "WHERE character_id = ? AND status = 'accepted' "
        "ORDER BY accepted_at DESC",
        (character_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _get_fronts_status(conn, character_id: str) -> List[Dict[str, Any]]:
    rows = conn.execute(
        """SELECT f.id, f.name, f.danger_type, cf.current_portent_index, cf.is_active, cf.advanced_at
           FROM fronts f
           LEFT JOIN character_fronts cf ON cf.front_id = f.id AND cf.character_id = ?
           WHERE COALESCE(cf.is_active, 1) = 1
           ORDER BY f.id""",
        (character_id,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "danger_type": r["danger_type"],
            "current_portent_index": r["current_portent_index"] or 0,
            "is_active": bool(r["is_active"] if r["is_active"] is not None else 1),
            "advanced_at": r["advanced_at"],
        }
        for r in rows
    ]


def _get_doom_clock(conn, character_id: str) -> Optional[Dict[str, Any]]:
    row = conn.execute(
        "SELECT total_ticks, portents_triggered, is_active, last_tick_at "
        "FROM doom_clock WHERE character_id = ?",
        (character_id,),
    ).fetchone()
    return dict(row) if row else None


def _get_hub_rumors(conn, character_id: str, location_id: str) -> List[Dict[str, Any]]:
    from app.services.hub_rumors import get_hub_rumors
    return get_hub_rumors(character_id, location_id)


def _get_affinities(conn, character_id: str) -> Dict[str, int]:
    """Fetch per-NPC affinity scores (0-100 scale) for a character.

    Maps to narrator.py's expected world_context["social_context"]["affinities"]
    format: {npc_id: score}.
    """
    rows = conn.execute(
        "SELECT npc_id, affinity FROM character_npc_interactions "
        "WHERE character_id = ?",
        (character_id,),
    ).fetchall()
    return {r["npc_id"]: r["affinity"] for r in rows}


def _get_milestones(conn, character_id: str) -> List[Dict[str, Any]]:
    """Fetch claimed milestones for a character.

    Maps to narrator.py's expected world_context["social_context"]["milestones"]
    format: [{type, threshold, reward_type, claimed_at}, ...].
    """
    rows = conn.execute(
        "SELECT milestone_type, threshold, reward_type, claimed_at "
        "FROM character_milestones "
        "WHERE character_id = ? "
        "ORDER BY claimed_at DESC",
        (character_id,),
    ).fetchall()
    return [
        {
            "type": r["milestone_type"],
            "threshold": r["threshold"],
            "reward_type": r["reward_type"],
            "claimed_at": r["claimed_at"],
        }
        for r in rows
    ]


def _build_hub_social_summary(rumors: List[Dict[str, Any]]) -> str:
    """Build a 1-2 sentence hub atmosphere summary from rumors.

    Used by narrator.py's world_context["social_context"]["hub_social"]["summary_text"].
    """
    if not rumors:
        return ""
    parts = []
    positive = [r for r in rumors if r.get("sentiment", 0) > 0]
    negative = [r for r in rumors if r.get("sentiment", 0) < 0]
    if positive:
        keys = [r["rumor_key"].replace("_", " ") for r in positive[:2]]
        parts.append(f"Locals speak well of: {', '.join(keys)}.")
    if negative:
        keys = [r["rumor_key"].replace("_", " ") for r in negative[:2]]
        parts.append(f"Tensions noted: {', '.join(keys)}.")
    return " ".join(parts)


def _compute_allowed_actions(
    conn,
    character_id: str,
    location_id: str,
    npcs_here: List[Dict[str, Any]],
    exits: List[Dict[str, Any]],
    combat_state: Optional[Dict[str, Any]],
    active_quests: List[Dict[str, Any]],
    narrative_flags: Dict[str, str],
    key_items: List[Dict[str, Any]],
) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    allowed = []
    disallowed = []

    char_row = _get_character_row(conn, character_id)
    if not char_row:
        disallowed.append({"action_type": "all", "reason": "Character not found"})
        return [], disallowed

    hp_current = char_row["hp_current"]
    is_dead = hp_current <= 0

    if combat_state:
        if is_dead:
            disallowed.append({"action_type": "attack", "reason": "Cannot attack while dead"})
        else:
            allowed.append({"action_type": "attack", "target": None, "confidence": 0.9, "reason": "In combat — attack available"})
            allowed.append({"action_type": "flee", "target": None, "confidence": 0.8, "reason": "Can attempt to flee combat"})
            allowed.append({"action_type": "defend", "target": None, "confidence": 0.9, "reason": "Defensive action available"})
            allowed.append({"action_type": "use_item", "target": None, "confidence": 0.7, "reason": "Can use inventory items"})
        return allowed, disallowed

    # Non-combat
    if is_dead:
        disallowed.append({"action_type": "move", "reason": "Cannot move while dead"})
        disallowed.append({"action_type": "explore", "reason": "Cannot explore while dead"})
        disallowed.append({"action_type": "interact", "reason": "Cannot interact while dead"})
        disallowed.append({"action_type": "rest", "reason": "Cannot rest while dead"})
        allowed.append({"action_type": "look", "target": None, "confidence": 1.0, "reason": "Can always observe surroundings"})
        return allowed, disallowed

    # Always-available
    allowed.append({"action_type": "look", "target": None, "confidence": 1.0, "reason": "Can observe surroundings"})

    # Movement
    if exits:
        for exit_loc in exits:
            allowed.append({"action_type": "move", "target": exit_loc["id"], "confidence": 0.95, "reason": f"Exit: {exit_loc.get('name','?')}"})
    else:
        disallowed.append({"action_type": "move", "reason": "No visible exits from current location"})

    # Explore
    allowed.append({"action_type": "explore", "target": None, "confidence": 0.8, "reason": "Can search location for resources"})

    # Interact
    available_npcs = [n for n in npcs_here if n.get("available")]
    for npc in available_npcs:
        allowed.append({
            "action_type": "interact",
            "target": npc["id"],
            "confidence": 0.9,
            "reason": f"NPC available: {npc.get('name','?')}",
        })
    if not available_npcs:
        disallowed.append({"action_type": "interact", "reason": "No interactable NPCs currently available"})

    # Rest (only in safe biomes)
    location_row = _get_location_row(conn, location_id, char_row.get("campaign_id"))
    if location_row:
        biome = location_row.get("biome", "")
        hostility = location_row.get("hostility_level", 0)
        if biome in ("town", "shrine", "city") or hostility == 0:
            allowed.append({"action_type": "rest", "target": None, "confidence": 0.9, "reason": f"Safe location ({biome}) permits rest"})
        else:
            disallowed.append({"action_type": "rest", "reason": f"Resting not allowed in hostile area ({biome})"})

    # Quest action
    if active_quests:
        allowed.append({"action_type": "quest", "target": None, "confidence": 0.7, "reason": f"{len(active_quests)} active quest(s) can be advanced"})

    return allowed, disallowed


def get_scene_context(character_id: str) -> Dict[str, Any]:
    conn = get_db()
    try:
        char_row = _get_character_row(conn, character_id)
        if not char_row:
            raise ValueError(f"Character not found: {character_id}")

        campaign_id = char_row.get("campaign_id", "default")
        location_id = char_row.get("location_id")

        # Location
        location = None
        exits = []
        if location_id:
            location = _get_location_row(conn, location_id, campaign_id)
            if location:
                raw_conns = location.get("connected_to", "[]")
                try:
                    exits_raw = json.loads(raw_conns) if isinstance(raw_conns, str) else raw_conns
                except (json.JSONDecodeError, TypeError):
                    exits_raw = [c.strip() for c in str(raw_conns).split(",") if c.strip()]
                exits = _get_connected_locations(conn, exits_raw, campaign_id)

        # NPCs at location with availability split
        npcs_here_raw = get_npcs_at_location(location_id) if location_id else []
        char_context = {
            "character_id": character_id,
            "game_hour": char_row.get("game_hour", 8),
            "narrative_flags": _get_narrative_flag_keys(conn, character_id),
        }
        npcs_availability = get_available_npcs_at_location(location_id, char_context) if location_id else {
            "all_npcs": [], "available": [], "unavailable": []
        }

        # Merge availability into NPC summary
        npcs_summary = []
        for npc in npcs_here_raw:
            avail = next((a for a in npcs_availability["available"] if a["id"] == npc["id"]), None)
            unavail = next((u for u in npcs_availability["unavailable"] if u["id"] == npc["id"]), None)
            summary = {
                "id": npc["id"],
                "name": npc["name"],
                "archetype": npc.get("archetype"),
                "is_quest_giver": bool(npc.get("is_quest_giver", 0)),
                "is_spirit": bool(npc.get("is_spirit", 0)),
                "is_enemy": bool(npc.get("is_enemy", 0)),
                "personality": npc.get("personality", ""),
                "image_url": npc.get("image_url"),
            }
            if avail:
                summary["available"] = True
                summary["availability_reason"] = avail.get("availability_reason", "Available")
            if unavail:
                summary["available"] = False
                summary["unavailable_reason"] = unavail.get("unavailable_reason", "Not available")
            npcs_summary.append(summary)

        # Narrative state
        narrative_flags = _get_narrative_flag_keys(conn, character_id)
        mark_stage = _get_mark_stage(conn, character_id)

        # Key items
        key_items = get_key_items(character_id, conn)

        # Active quests
        active_quests = _get_active_quests(conn, character_id)

        # Combat
        combat_state = _get_combat_state(conn, character_id)

        # Fronts
        fronts = _get_fronts_status(conn, character_id)

        # Doom clock
        doom_clock = _get_doom_clock(conn, character_id)

        # Hub social state — aggregate for DM narrator
        hub_rumors = _get_hub_rumors(conn, character_id, location_id) if location_id else []
        hub_social = {
            "rumors": hub_rumors,
            "summary_text": _build_hub_social_summary(hub_rumors),
        }

        # NPC affinities — per-NPC relationship scores
        affinities = _get_affinities(conn, character_id)

        # Claimed milestones
        milestones = _get_milestones(conn, character_id)

        # Social context wrapper (matches narrator.py expected path)
        social_context = {
            "affinities": affinities,
            "milestones": milestones,
            "hub_social": hub_social,
        }

        # Affordances (allowed/disallowed actions)
        allowed_actions, disallowed_actions = _compute_allowed_actions(
            conn,
            character_id=character_id,
            location_id=location_id or "",
            npcs_here=npcs_summary,
            exits=exits,
            combat_state=combat_state,
            active_quests=active_quests,
            narrative_flags=narrative_flags,
            key_items=key_items,
        )

        return {
            "character_id": character_id,
            "character": {
                "name": char_row["name"],
                "level": char_row["level"],
                "hp_current": char_row["hp_current"],
                "hp_max": char_row["hp_max"],
                "location_id": location_id,
            },
            "current_location": location,
            "exits": exits,
            "npcs_here": npcs_summary,
            "narrative_flags": narrative_flags,
            "mark_of_dreamer_stage": mark_stage,
            "key_items": key_items,
            "active_quests": active_quests,
            "combat_state": combat_state,
            "fronts": fronts,
            "doom_clock": doom_clock,
            "hub_rumors": hub_rumors,  # DEPRECATED: use social_context.hub_social.rumors
            "social_context": social_context,
            "allowed_actions": allowed_actions,
            "disallowed_actions": disallowed_actions,
            "timestamp": datetime.datetime.utcnow().isoformat(),
        }

    finally:
        conn.close()

