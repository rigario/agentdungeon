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

        def safe_json(col):
            try:
                val = char[col] if col in char.keys() else None
                return json.loads(val) if val else {}
            except (json.JSONDecodeError, TypeError, ValueError):
                return {}

        sheet = safe_json("sheet_json")

        # Current location + nearby NPCs (with availability filtering)
        location = None
        location_id = char["location_id"] if "location_id" in char.keys() else None
        npcs_at_location = []
        npcs_available = []
        npcs_unavailable = []
        if location_id:
            loc = db.execute(
                "SELECT id, name, description, biome, hostility_level, image_url FROM locations WHERE id = ?",
                (location_id,),
            ).fetchone()
            if loc:
                location = dict(loc)
                # Frontend compatibility aliases: portal.html historically reads
                # `hostility` while the DB/API contract stores `hostility_level`.
                location["hostility"] = location.get("hostility_level")
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
            "SELECT id, name, biome, description, hostility_level, connected_to, image_url FROM locations ORDER BY hostility_level, name"
        ).fetchall()
        all_locations = [dict(r) for r in all_locations_rows]
        for loc in all_locations:
            try:
                loc["connected_to"] = json.loads(loc["connected_to"]) if loc["connected_to"] else []
            except (json.JSONDecodeError, TypeError):
                loc["connected_to"] = []

        # 1b. Enrich locations with per-location NPCs (for map.html loc.npcs compatibility)
        npc_rows = db.execute(
            "SELECT id, name, current_location_id, archetype, image_url, personality, is_quest_giver "
            "FROM npcs WHERE current_location_id IS NOT NULL"
        ).fetchall()
        npcs_by_location = {}
        for nr in npc_rows:
            npc = dict(nr)
            loc_id = npc["current_location_id"]
            if loc_id not in npcs_by_location:
                npcs_by_location[loc_id] = []
            npcs_by_location[loc_id].append({
                "id": npc["id"],
                "name": npc["name"],
                "archetype": npc.get("archetype"),
                "image_url": npc.get("image_url"),
                "personality": npc.get("personality"),
                "is_quest_giver": bool(npc.get("is_quest_giver", 0)),
            })
        for loc in all_locations:
            loc["npcs"] = npcs_by_location.get(loc["id"], [])

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

        # === NEW: map state derived from event_log ===
        mark_stage = char["mark_of_dreamer_stage"] if "mark_of_dreamer_stage" in char.keys() else 0
        portents_triggered = doom["portents_triggered"] if doom else 0

        # Build enriched character sheet object for the visual panel
        character_sheet = {
            "race": (char["race"] if "race" in char.keys() else None) or sheet.get("race") or "",
            "class": (char["class"] if "class" in char.keys() else None) or sheet.get("class") or sheet.get("class_name") or "",
            "ac_value": (char["ac_value"] if "ac_value" in char.keys() else None) or sheet.get("ac", {}).get("value") or sheet.get("armor_class", {}).get("value") or 10,
            "ac_description": (char["ac_description"] if "ac_description" in char.keys() else None) or sheet.get("ac", {}).get("description") or sheet.get("armor_class", {}).get("description") or "",
            "ability_scores": safe_json("ability_scores_json") or sheet.get("ability_scores") or {},
            "speed": safe_json("speed_json") or sheet.get("speed") or {},
            "skills": safe_json("skills_json") or sheet.get("skills") or {},
            "saving_throws": safe_json("saving_throws_json") or sheet.get("saving_throws") or {},
            "languages": safe_json("languages_json") or sheet.get("languages") or [],
            "weapon_proficiencies": safe_json("weapon_proficiencies_json") or sheet.get("weapon_proficiencies") or [],
            "armor_proficiencies": safe_json("armor_proficiencies_json") or sheet.get("armor_proficiencies") or [],
            "equipment": safe_json("equipment_json") or sheet.get("equipment") or [],
            "treasure": safe_json("treasure_json") or sheet.get("treasure") or {},
            "spell_slots": safe_json("spell_slots_json") or sheet.get("spell_slots") or {},
            "spells": safe_json("spells_json") or sheet.get("spells") or [],
            "feats": safe_json("feats_json") or sheet.get("feats") or [],
            "conditions": safe_json("conditions_json") or sheet.get("conditions") or {},
            "mark_of_dreamer_stage": mark_stage,
        }

        # Latest live-tick queued turns for trust/progress display.
        queued_turns = []
        try:
            turn_rows = db.execute(
                """SELECT turn_id, status, tick_id, next_tick_at, cutoff_at,
                          estimated_processing_window_seconds, created_at, updated_at,
                          processing_started_at, completed_at, error_json
                   FROM queued_turns
                   WHERE character_id = ?
                   ORDER BY created_at DESC
                   LIMIT 5""",
                (character_id,),
            ).fetchall()
            for tr in turn_rows:
                error = None
                if tr["error_json"]:
                    try:
                        error = json.loads(tr["error_json"])
                    except (json.JSONDecodeError, TypeError):
                        error = {"raw": tr["error_json"]}
                queued_turns.append({
                    "turn_id": tr["turn_id"],
                    "status": tr["status"],
                    "tick_id": tr["tick_id"],
                    "next_tick_at": tr["next_tick_at"],
                    "cutoff_at": tr["cutoff_at"],
                    "estimated_processing_window_seconds": tr["estimated_processing_window_seconds"],
                    "created_at": tr["created_at"],
                    "updated_at": tr["updated_at"],
                    "processing_started_at": tr["processing_started_at"],
                    "completed_at": tr["completed_at"],
                    "error": error,
                })
        except Exception:
            queued_turns = []

        return {
            "character": {
                "id": char["id"],
                "name": char["name"],
                "level": char["level"],
                "xp": char["xp"],
                "hp_current": char["hp_current"],
                "hp_max": char["hp_max"],
                "sheet": sheet,
                "character_sheet": character_sheet,
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
            "queued_turns": queued_turns,
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
