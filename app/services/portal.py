"""D20 Agent RPG — Portal Service.

Share token CRUD operations for the Player Portal.
Tokens allow unauthenticated viewing of character state.
"""

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Optional

from app.services.database import get_db
from app.services.npc_movement import get_npcs_at_location


def create_share_token(character_id: str, label: str = None, expires_hours: int = None) -> dict:
    """Create a new share token for a character.
    
    Args:
        character_id: The character to create a share token for.
        label: Optional human label (e.g., "Playtest #1").
        expires_hours: Optional expiry in hours. None = never expires.
    
    Returns:
        Dict with token details.
    """
    db = get_db()
    try:
        # Verify character exists
        char = db.execute("SELECT id, name FROM characters WHERE id = ?", (character_id,)).fetchone()
        if not char:
            return {"error": "character_not_found", "character_id": character_id}

        token_id = str(uuid.uuid4())
        token = secrets.token_urlsafe(32)
        expires_at = None
        if expires_hours:
            expires_at = (datetime.utcnow() + timedelta(hours=expires_hours)).isoformat()

        db.execute(
            """INSERT INTO share_tokens (id, character_id, token, label, expires_at)
               VALUES (?, ?, ?, ?, ?)""",
            (token_id, character_id, token, label, expires_at)
        )
        db.commit()

        return {
            "id": token_id,
            "character_id": character_id,
            "character_name": char["name"],
            "token": token,
            "label": label,
            "expires_at": expires_at,
            "created_at": datetime.utcnow().isoformat(),
        }
    finally:
        db.close()


def validate_share_token(token: str) -> dict:
    """Validate a share token and return basic info.
    
    Increments view_count on successful validation.
    
    Returns:
        Dict with token info or error.
    """
    db = get_db()
    try:
        row = db.execute(
            """SELECT st.id, st.character_id, st.token, st.label, st.expires_at, 
                      st.revoked, st.view_count, c.name as character_name
               FROM share_tokens st
               JOIN characters c ON st.character_id = c.id
               WHERE st.token = ?""",
            (token,)
        ).fetchone()

        if not row:
            return {"valid": False, "error": "token_not_found"}

        if row["revoked"]:
            return {"valid": False, "error": "token_revoked"}

        if row["expires_at"]:
            exp = datetime.fromisoformat(row["expires_at"])
            if datetime.utcnow() > exp:
                return {"valid": False, "error": "token_expired"}

        # Increment view count
        db.execute(
            """UPDATE share_tokens 
               SET view_count = view_count + 1, last_viewed_at = ?
               WHERE token = ?""",
            (datetime.utcnow().isoformat(), token)
        )
        db.commit()

        return {
            "valid": True,
            "id": row["id"],
            "character_id": row["character_id"],
            "character_name": row["character_name"],
            "label": row["label"],
            "view_count": row["view_count"] + 1,
        }
    finally:
        db.close()


def revoke_share_token(token: str) -> dict:
    """Revoke a share token.
    
    Returns:
        Dict with result.
    """
    db = get_db()
    try:
        result = db.execute(
            "UPDATE share_tokens SET revoked = 1 WHERE token = ? AND revoked = 0",
            (token,)
        )
        db.commit()
        if result.rowcount == 0:
            return {"ok": False, "error": "token_not_found_or_already_revoked"}
        return {"ok": True, "token": token}
    finally:
        db.close()


def list_character_tokens(character_id: str) -> list:
    """List all share tokens for a character.
    
    Returns:
        List of token dicts.
    """
    db = get_db()
    try:
        rows = db.execute(
            """SELECT id, token, label, created_at, expires_at, revoked, 
                      view_count, last_viewed_at
               FROM share_tokens 
               WHERE character_id = ?
               ORDER BY created_at DESC""",
            (character_id,)
        ).fetchall()

        tokens = []
        for r in rows:
            is_expired = False
            if r["expires_at"]:
                is_expired = datetime.utcnow() > datetime.fromisoformat(r["expires_at"])

            tokens.append({
                "id": r["id"],
                "token_prefix": r["token"][:8] + "...",
                "label": r["label"],
                "created_at": r["created_at"],
                "expires_at": r["expires_at"],
                "revoked": bool(r["revoked"]),
                "expired": is_expired,
                "active": not r["revoked"] and not is_expired,
                "view_count": r["view_count"],
                "last_viewed_at": r["last_viewed_at"],
            })
        return tokens
    finally:
        db.close()


def get_portal_state(character_id: str) -> dict:
    """Aggregate character state for portal view.
    
    Returns character sheet, current location, active quests,
    recent events, doom clock status, inventory, and map state.
    
    Returns:
        Dict with full portal state or error.
    """
    db = get_db()
    try:
        # Character
        char = db.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
        if not char:
            return {"error": "character_not_found"}

        import json
        sheet = json.loads(char["sheet_json"]) if char["sheet_json"] else {}

        # Current location + nearby NPCs (with availability filtering)
        location = None
        location_id = char["location_id"] if "location_id" in char.keys() else None
        npcs_at_location = []
        npcs_available = []
        npcs_unavailable = []
        if location_id:
            loc = db.execute(
                "SELECT id, name, description, biome, hostility_level FROM locations WHERE id = ?",
                (location_id,),
            ).fetchone()
            if loc:
                location = dict(loc)
                # Build character context for availability filtering
                game_hour = char["game_hour"] if "game_hour" in char.keys() and char["game_hour"] is not None else 8
                flag_rows = db.execute(
                    "SELECT flag_key, flag_value FROM narrative_flags WHERE character_id = ?",
                    (character_id,),
                ).fetchall()
                narrative_flags = {r[0]: r[1] for r in flag_rows}
                char_ctx = {
                    "game_hour": game_hour,
                    "narrative_flags": narrative_flags,
                    "character_id": character_id,
                }
                # Use availability-filtered query
                from app.services.npc_movement import get_available_npcs_at_location
                avail_data = get_available_npcs_at_location(location_id, char_ctx)
                npcs_at_location = avail_data["all_npcs"]
                npcs_available = avail_data["available"]
                npcs_unavailable = avail_data["unavailable"]

        # Active quests
        quests = db.execute(
            """SELECT quest_id, quest_title, quest_description, giver_npc_name, 
                      status, reward_xp, reward_gold, accepted_at
               FROM character_quests 
               WHERE character_id = ? AND status = 'accepted'
               ORDER BY accepted_at DESC""",
            (character_id,),
        ).fetchall()

        # Recent events (last 10)
        events = db.execute(
            """SELECT event_type, description, data_json, timestamp
               FROM event_log 
               WHERE character_id = ?
               ORDER BY timestamp DESC
               LIMIT 10""",
            (character_id,),
        ).fetchall()

        # Doom clock
        doom = db.execute(
            "SELECT * FROM doom_clock WHERE character_id = ?",
            (character_id,),
        ).fetchone()

        # Inventory
        inventory = db.execute(
            """SELECT ci.item_id, ci.quantity, ci.is_equipped, ci.acquired_at,
                      i.name, i.item_type, i.rarity, i.description, i.image_url
               FROM character_items ci
               LEFT JOIN items i ON ci.item_id = i.id
               WHERE ci.character_id = ?
               ORDER BY ci.acquired_at DESC""",
            (character_id,),
        ).fetchall()

        # === MAP STATE: derive fog-of-war from event_log ===
        # 1. Get all world locations for the base map
        all_locations_rows = db.execute(
            "SELECT id, name, biome, hostility_level, connected_to FROM locations ORDER BY hostility_level, name"
        ).fetchall()
        all_locations = [dict(r) for r in all_locations_rows]
        for loc in all_locations:
            try:
                loc["connected_to"] = json.loads(loc["connected_to"]) if loc["connected_to"] else []
            except (json.JSONDecodeError, TypeError):
                loc["connected_to"] = []

        # 2. Get character's visited_locations from move/explore/arrive events
        visit_rows = db.execute(
            """SELECT location_id, event_type, timestamp
               FROM event_log 
               WHERE character_id = ? 
                 AND event_type IN ('move', 'explore', 'arrive')
                 AND location_id IS NOT NULL
               ORDER BY timestamp ASC""",
            (character_id,),
        ).fetchall()
        visited_locations = list({r["location_id"] for r in visit_rows if r["location_id"]})

        # 3. Get traveled_edges from consecutive move events (from → to pairs)
        move_rows = db.execute(
            """SELECT location_id, timestamp, data_json
               FROM event_log 
               WHERE character_id = ? AND event_type = 'move'
               ORDER BY timestamp ASC""",
            (character_id,),
        ).fetchall()
        traveled_edges = []
        prev_loc = None
        for row in move_rows:
            curr_loc = row["location_id"]
            if prev_loc is not None and prev_loc != curr_loc:
                traveled_edges.append([prev_loc, curr_loc])
            prev_loc = curr_loc

        # 4. Character's map-relevant state
        mark_stage = char["mark_of_dreamer_stage"] if "mark_of_dreamer_stage" in char.keys() else 0
        portents_triggered = doom["portents_triggered"] if doom else 0

        return {
            "character": {
                "id": char["id"],
                "name": char["name"],
                "level": char["level"],
                "xp": char["xp"],
                "hp_current": char["hp_current"],
                "hp_max": char["hp_max"],
                "sheet": sheet,
            },
            "location": location,
            "npcs_at_location": npcs_at_location,
            "npcs_available": npcs_available,
            "npcs_unavailable": npcs_unavailable,
            "quests": [dict(q) for q in quests],
            "recent_events": [
                {
                    "type": e["event_type"],
                    "description": e["description"],
                    "data": json.loads(e["data_json"]) if e["data_json"] else {},
                    "timestamp": e["timestamp"],
                }
                for e in events
            ],
            "doom_clock": dict(doom) if doom else None,
            "inventory": [dict(i) for i in inventory],
            # === NEW: map state derived from event_log ===
            "map": {
                "locations": all_locations,
                "visited_locations": visited_locations,
                "traveled_edges": traveled_edges,
                "current_location_id": location_id,
                "mark_of_dreamer_stage": mark_stage,
                "doom_portents_triggered": portents_triggered,
            },
        }
    finally:
        db.close()
