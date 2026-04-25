"""D20 Agent RPG — Action resolution and encounter engine.

The agent submits actions. The server is the single source of truth:
- All dice rolls happen server-side (deterministic seeded RNG)
- All rule validation happens server-side
- Agent never rolls, never validates, never adjudicates
"""

import json
import hashlib
import random
import sqlite3
import logging
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends, Request
from app.models.schemas import ActionRequest, ActionResponse
from app.services.database import get_db
from app.services.srd_reference import get_monsters_by_cr, ability_modifier, get_spells, _spellcasting_ability
from app.services.key_items import add_key_item, remove_key_item, has_key_item, get_key_items, KEY_ITEMS
from app.services.auth_helpers import get_auth, require_character_ownership
from app.services.approval_gate import gate_action
from app.services.time_of_day import advance_time, get_action_time_cost, get_time_period, get_character_time, get_encounter_threshold_modifier
from app.services.dm_proxy import get_dm_proxy, get_dm_session, build_world_context
from app.services.character_lock import acquire_character_lock, release_character_lock
from app.services.character_validation import validate_char_state
from app.services import affinity
from app.services import milestones
from app.services import loot



router = APIRouter(prefix="/characters/{character_id}", tags=["actions"])

logger = logging.getLogger(__name__)


def _seeded_random(character_id: str, location_id: str, timestamp: str) -> random.Random:
    """Create a deterministic RNG seeded from character + location + time."""
    seed_str = f"{character_id}:{location_id}:{timestamp}"
    seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)
    return random.Random(seed)


def _roll_d20(rng: random.Random) -> int:
    """Roll a d20."""
    return rng.randint(1, 20)


def _roll_dice(rng: random.Random, dice_str: str) -> int:
    """Roll dice from a string like '2d6+3' or '1d8'."""
    import re
    match = re.match(r'(\d+)d(\d+)(?:\+(\d+))?(?:-(\d+))?', dice_str)
    if not match:
        return 1
    count, sides = int(match.group(1)), int(match.group(2))
    plus = int(match.group(3) or 0)
    minus = int(match.group(4) or 0)
    total = sum(rng.randint(1, sides) for _ in range(count)) + plus - minus
    return max(0, total)


def _get_character(character_id: str) -> dict:
    """Fetch character from DB as dict. Rejects archived characters."""
    conn = get_db()
    row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Character not found: {character_id}")
    if row["is_archived"]:
        raise HTTPException(403, f"Character is archived: {character_id}. Restore first.")
    return dict(row)


def _get_location(location_id: str) -> dict:
    """Fetch location from DB as dict."""
    conn = get_db()
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Location not found: {location_id}")
    return dict(row)


def _log_event(conn, character_id: str, event_type: str, location_id: str,
                description: str, data: dict = None, approval_triggered: bool = False):
    """Insert an event into the log."""
    conn.execute(
        """INSERT INTO event_log (character_id, event_type, location_id, description, data_json, approval_triggered)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (character_id, event_type, location_id, description,
         json.dumps(data or {}), approval_triggered)
    )


def _check_encounter(char: dict, location: dict, rng: random.Random) -> dict | None:
    """Check if an encounter triggers. Returns encounter data or None.
    
    Special case: The Rusty Tankard dispatches the Del possession opening
    encounter on the character's very first visit, regardless of the D20 roll.
    
    Time-of-day: encounter threshold is modified by game_hour — night is
    more dangerous (lower threshold = more encounters).
    """
    threshold = location.get("encounter_threshold", 10)
    
    # Apply time-of-day modifier to threshold
    game_hour = char.get("game_hour", 8)
    time_mod = get_encounter_threshold_modifier(game_hour)
    adjusted_threshold = max(1, int(threshold * time_mod))
    
    roll = _roll_d20(rng)

    # Check for the Del opening encounter at the Rusty Tankard
    if location["id"] == "rusty-tankard":
        conn_flag = get_db()
        existing = conn_flag.execute(
            "SELECT flag_value FROM narrative_flags "
            "WHERE character_id = ? AND flag_key = 'del_encounter_fired'",
            (char["id"],)
        ).fetchone()
        conn_flag.close()

        if not existing:
            # First visit to the Tankard — dispatch Del encounter
            conn_enc = get_db()
            del_enc = conn_enc.execute(
                "SELECT * FROM encounters WHERE id = 'enc-del-possession'"
            ).fetchone()
            conn_enc.close()

            if del_enc:
                enc = dict(del_enc)
                enc["enemies"] = json.loads(enc["enemies_json"])
                enc["loot"] = json.loads(enc.get("loot_json", "[]"))
                enc["d20_roll"] = None  # Opening encounter, no threshold roll
                enc["is_opening"] = True
                return enc

    if roll >= adjusted_threshold:
        return None  # Safe passage

    # Normal encounter selection — skip opening encounters and already-completed ones (multi-tenancy)
    char_level = char.get("level", 1)
    conn = get_db()

    # Get encounters this character has already completed
    completed = conn.execute(
        "SELECT encounter_id FROM character_encounter_history WHERE character_id = ? AND was_victory = 1",
        (char["id"],)
    ).fetchall()
    completed_ids = {r["encounter_id"] for r in completed}

    encounters = conn.execute(
        """SELECT * FROM encounters
           WHERE location_id = ? AND min_level <= ? AND max_level >= ?
           AND is_opening_encounter = 0""",
        (location["id"], char_level, char_level)
    ).fetchall()

    # Filter out already-completed encounters for this character
    encounters = [e for e in encounters if dict(e)["id"] not in completed_ids]
    conn.close()

    if not encounters:
        return None

    # Pick random encounter
    encounter = dict(rng.choice(encounters))
    encounter["enemies"] = json.loads(encounter["enemies_json"])
    encounter["loot"] = json.loads(encounter.get("loot_json", "[]"))
    encounter["d20_roll"] = roll
    encounter["threshold"] = adjusted_threshold
    encounter["base_threshold"] = threshold
    encounter["time_modifier"] = time_mod
    encounter["game_hour"] = game_hour

    return encounter


def _resolve_combat(char: dict, encounter: dict, rng: random.Random) -> dict:
    """Resolve a full combat encounter. Returns combat result.
    
    Special handling for the Del possession opening encounter:
    - After Del is defeated, applies the Mark of the Dreamer if WIS save fails
    - Sets narrative_flags: del_encounter_fired
    - Triggers Del ghost visit roll (pass → ghost visit next rest)
    """
    events = []
    hp = char["hp_current"]
    max_hp = char["hp_max"]
    ac = char["ac_value"]
    char_mod = ability_modifier(json.loads(char["ability_scores_json"]).get("str", 10))

    enemies = []
    for e in encounter["enemies"]:
        for _ in range(e.get("count", 1)):
            enemies.append({
                "type": e["type"],
                "hp": e["hp"],
                "ac": e["ac"],
                "attack_bonus": e.get("attack_bonus", 3),
                "damage": e.get("damage", "1d6"),
                "initiative_mod": e.get("initiative_mod", 0),
                "name_override": e.get("name_override"),
            })

    # Initiative — character vs each enemy group
    char_init = _roll_d20(rng) + ability_modifier(json.loads(char["ability_scores_json"]).get("dex", 10))
    for enemy in enemies:
        enemy["initiative"] = _roll_d20(rng) + enemy["initiative_mod"]

    # Sort by initiative (descending)
    turn_order = sorted(
        [{"name": char["name"], "initiative": char_init, "is_player": True}] +
        [{"name": e.get("name_override") or e["type"], "initiative": e["initiative"],
          "is_player": False, "idx": i}
         for i, e in enumerate(enemies)],
        key=lambda x: x["initiative"], reverse=True
    )

    events.append({
        "type": "combat_start",
        "description": f"Combat begins! Initiative order: {', '.join(t['name'] for t in turn_order)}",
        "enemies": [{"name": e.get("name_override") or e["type"], "hp": e["hp"]} for e in enemies],
    })

    round_num = 0
    max_rounds = 20  # Safety limit

    while hp > 0 and any(e["hp"] > 0 for e in enemies) and round_num < max_rounds:
        round_num += 1
        round_events = []

        for turn in turn_order:
            if hp <= 0:
                break

            alive_enemies = [e for e in enemies if e["hp"] > 0]
            if not alive_enemies:
                break

            if turn["is_player"]:
                # Character attacks first alive enemy
                target = alive_enemies[0]
                attack_roll = _roll_d20(rng) + char_mod + 2  # +2 proficiency at level 1
                if attack_roll >= target["ac"]:
                    damage = _roll_dice(rng, "1d8") + char_mod
                    damage = max(1, damage)
                    target["hp"] -= damage
                    status = "defeated" if target["hp"] <= 0 else f"{target['hp']} HP left"
                    round_events.append(f"You hit the {target['type']} for {damage} damage ({status}).")
                else:
                    round_events.append(f"You missed the {target['type']} (rolled {attack_roll} vs AC {target['ac']}).")
            else:
                # Enemy attacks character
                enemy = enemies[turn["idx"]]
                if enemy["hp"] <= 0:
                    continue
                attack_roll = _roll_d20(rng) + enemy["attack_bonus"]
                if attack_roll >= ac:
                    damage = _roll_dice(rng, enemy["damage"])
                    hp -= damage
                    hp = max(0, hp)
                    round_events.append(f"The {enemy.get('name_override') or enemy['type']} hits you for {damage} damage (HP: {hp}/{max_hp}).")
                else:
                    round_events.append(f"The {enemy.get('name_override') or enemy['type']} misses (rolled {attack_roll} vs AC {ac}).")

        if round_events:
            events.append({
                "type": "combat_round",
                "round": round_num,
                "description": " | ".join(round_events),
            })

    # Combat result
    victory = all(e["hp"] <= 0 for e in enemies)
    if hp <= 0:
        events.append({
            "type": "combat_defeat",
            "description": "You fall unconscious. The darkness takes you.",
        })

        # Ser Maren sacrifice — if accompanying in a cave location, she saves you
        conn_maren = get_db()
        maren_accompanying = conn_maren.execute(
            "SELECT flag_value FROM narrative_flags WHERE character_id = ? AND flag_key = 'maren_accompanying'",
            (char["id"],)
        ).fetchone()
        in_cave = char.get("location_id", "") in ("cave-entrance", "cave-depths")
        conn_maren.close()

        if maren_accompanying and in_cave:
            hp = max(1, hp)  # Maren saves you at 1 HP
            victory = all(e["hp"] <= 0 for e in enemies)  # Check if enemies were already dead
            events.append({
                "type": "npc_sacrifice",
                "description": (
                    "Ser Maren throws herself between you and the killing blow. "
                    "Her sword flashes — once, twice — and the enemy staggers. "
                    "But the wound is too deep. She falls. 'The seal... keep going. "
                    "I held the line long enough. Don't waste it.' "
                    "She presses her badge into your hand — the seal-keeper's mark. "
                    "Her eyes go still."
                ),
            })

            # Set sacrifice flags via a separate connection
            conn_sacrifice = get_db()
            conn_sacrifice.execute(
                """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                   VALUES (?, 'maren_sacrificed', '1', 'combat_sacrifice')
                   ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
                (char["id"],)
            )
            conn_sacrifice.execute(
                """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                   VALUES (?, 'seal_keeper_badge', '1', 'maren_sacrifice')
                   ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
                (char["id"],)
            )
            # Add Seal-Keeper Badge as tangible key item
            add_key_item(char["id"], "seal_keeper_badge", conn_sacrifice)
            conn_sacrifice.commit()
            conn_sacrifice.close()
    elif victory:
        events.append({
            "type": "combat_victory",
            "description": f"Victory! All enemies defeated in {round_num} rounds.",
        })

    result = {
        "hp_remaining": hp,
        "victory": victory,
        "rounds": round_num,
        "events": events,
        "loot": encounter.get("loot", []) if victory else [],
    }

    # ----------------------------------------------------------------
    # Del possession encounter special handling
    # ----------------------------------------------------------------
    is_del_encounter = encounter.get("is_opening") and encounter.get("mark_mechanic") == "on_hit_apply_mark"
    if is_del_encounter:
        del_wis_dc = encounter.get("wis_save_dc", 13)
        del_roll = _roll_d20(rng)
        mark_applied = del_roll < del_wis_dc  # Fail save → mark applied

        result["del_encounter"] = {
            "del_defeated": True,
            "wis_save_dc": del_wis_dc,
            "wis_save_roll": del_roll,
            "mark_applied": mark_applied,
            "save_failure_effect": encounter.get("save_failure_effect", ""),
            "save_success_effect": encounter.get("save_success_effect", ""),
        }

        # Set the del_encounter_fired flag regardless of outcome
        conn = get_db()
        conn.execute(
            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
            (char["id"], "del_encounter_fired", "1", "del_combat_resolution")
        )
        # Apply mark if save failed
        if mark_applied:
            conn.execute(
                "UPDATE characters SET mark_of_dreamer_stage = 1 WHERE id = ?",
                (char["id"],)
            )
            conn.execute(
                """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
                (char["id"], "mark_of_dreamer_stage_1", "1", "del_mark_applied")
            )

        # Advance Dreaming Hunger front to portent 1 (per-character: multi-tenancy)
        conn.execute(
            """UPDATE character_fronts SET current_portent_index = 1, advanced_at = ? 
               WHERE character_id = ? AND front_id = 'dreaming_hunger' AND current_portent_index < 1""",
            (datetime.utcnow().isoformat(), char["id"])
        )
        conn.execute(
            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
            (char["id"], "hunger_portent_1", "1", "front_advancement")
        )

        # Del ghost visit roll — seeded D20, DC 13
        ghost_seed = int(hashlib.md5(f"{char['id']}-del-ghost-visit".encode()).hexdigest()[:8], 16)
        ghost_rng = random.Random(ghost_seed)
        ghost_roll = ghost_rng.randint(1, 20)
        ghost_passed = ghost_roll >= 13

        conn.execute(
            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
            (char["id"], "del_ghost_roll", str(ghost_passed), "del_ghost_visit_roll")
        )

        result["del_encounter"]["ghost_roll"] = ghost_roll
        result["del_encounter"]["ghost_passed"] = ghost_passed
        result["del_encounter"]["ghost_narrative"] = (
            "Del's spirit visits your room tonight. You see him sitting on the chair, "
            "looking confused and sad. 'You were the last person I remember clearly.'"
            if ghost_passed else
            "You sleep fitfully but nothing manifests. No visit. No dreams. "
            "The silence is worse than whispers."
        )

        conn.commit()
        conn.close()

    return result


def _get_character_flags(character_id: str, conn: sqlite3.Connection = None) -> dict:
    """Load all narrative flags for a character.
    
    If conn is provided, reuses it (avoids DB lock from concurrent connections).
    Otherwise creates a new connection.
    """
    should_close = conn is None
    if conn is None:
        conn = get_db()
    rows = conn.execute(
        "SELECT flag_key, flag_value FROM narrative_flags WHERE character_id = ?",
        (character_id,)
    ).fetchall()
    if should_close:
        conn.close()
    return {r["flag_key"]: r["flag_value"] for r in rows}


# Location → portent index triggers (fires on first combat victory in that location)
LOCATION_PORTENT_TRIGGERS = {
    "forest-edge": 2,      # animals_dying
    "deep-forest": 3,      # undead_walk
    "crossroads": 4,       # seal_weeps
    "cave-entrance": 5,    # breaking_rite
    "cave-depths": 6,      # hunger_speaks
}

# Locations that become inaccessible during Thornhold exile
THORNHOLD_LOCATIONS = {"thornhold", "rusty-tankard"}


def _check_thornhold_exile(character_id: str, target_location_id: str) -> dict | None:
    """If mark_stage >= 3 and collateral flag is set, Thornhold is locked out."""
    if target_location_id not in THORNHOLD_LOCATIONS:
        return None
    
    conn = get_db()
    char = conn.execute(
        "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?",
        (character_id,)
    ).fetchone()
    collateral = conn.execute(
        "SELECT flag_value FROM narrative_flags WHERE character_id = ? AND flag_key = 'collateral_near_town'",
        (character_id,)
    ).fetchone()
    conn.close()
    
    if char and char["mark_of_dreamer_stage"] >= 3 and collateral:
        return {
            "blocked": True,
            "narration": (
                "The gates of Thornhold are barred. Marta stands on the wall, "
                "arms crossed. 'We saw what happened on the road. That mark — "
                "it draws them. You drew them here. You're not welcome. Not while "
                "you carry that thing.' The guards crossbows are leveled at you."
            ),
        }
    return None


def _apply_alric_betrayal(char: dict, flags: dict) -> bool:
    """Check if Aldric has tipped off the cult. Returns True if betrayal fires."""
    if flags.get("aldric_betrayal_fired"):
        return False
    
    # Count hollow_eye investigation flags
    he_count = sum(1 for k in flags if k.startswith("hollow_eye") or k.startswith("aldric_lying"))
    if he_count >= 3:
        return True
    return False


def _resolve_move(char: dict, target_location_id: str, rng: random.Random) -> dict:
    """Resolve movement to a new location. May trigger encounter.
    
    Supports both location ID (exact) and location name (fuzzy match).
    If target_location_id is not a valid location ID, attempts to find
    a location whose name matches (case-insensitive, substring) the given identifier.
    """
    current_location_id = char["location_id"]
    current = _get_location(current_location_id)

    # Resolve target: try ID first, then fuzzy name match
    target = None
    try:
        target = _get_location(target_location_id)
    except HTTPException as e:
        if e.status_code == 404:
            # Fallback: fuzzy match by location name
            conn_name = get_db()
            rows = conn_name.execute(
                "SELECT * FROM locations WHERE LOWER(name) LIKE ?",
                (f"%{target_location_id.lower()}%",)
            ).fetchall()
            conn_name.close()
            if len(rows) == 1:
                target = dict(rows[0])
            elif len(rows) > 1:
                return {
                    "success": False,
                    "narration": f"Multiple locations match '{target_location_id}'. Use a more specific name.",
                    "events": [],
                    "encounter": None,
                }
            # else: re-raise original 404
        else:
            raise

    if target is None:
        raise HTTPException(404, f"Location not found: {target_location_id}")

    # Check connectivity using actual target ID
    connected = json.loads(current.get("connected_to", "[]"))
    if target["id"] not in connected:
        return {
            "success": False,
            "narration": f"You can't reach {target['name']} from {current['name']}. Available paths: {', '.join(connected)}",
            "events": [],
            "encounter": None,
        }

    # Check for encounter
    encounter = _check_encounter(char, target, rng)

    events = [{
        "type": "move",
        "location_id": target["id"],
        "description": f"You travel from {current['name']} to {target['name']}.",
    }]

    if encounter:
        combat_result = _resolve_combat(char, encounter, rng)
        events.extend(combat_result["events"])

        return {
            "success": True,
            "narration": f"You travel to {target['name']}. {encounter['description']} A fight breaks out!",
            "events": events,
            "encounter": encounter["name"],
            "combat": combat_result,
            "new_location": target["id"],
        }

    return {
        "success": True,
        "narration": f"You travel from {current['name']} to {target['name']}. The path is clear. {target['description']}",
        "events": events,
        "encounter": None,
        "new_location": target["id"],
    }


def _resolve_rest(char: dict, rest_type: str, rng: random.Random) -> dict:
    """Resolve a short or long rest.
    
    Marked characters (mark_of_dreamer_stage >= 1) must pass a WIS save on long rest
    or gain no HP recovery. DC scales with mark stage: 10/14/16.
    
    Marked characters also receive dream narration from the atmosphere engine,
    which provides narrative context about the Hunger's influence.
    """
    from app.services.atmosphere import get_dream_narration

    hp_max = char["hp_max"]
    mark_stage = char.get("mark_of_dreamer_stage", 0)

    if rest_type == "long":
        # Mark WIS save on long rest
        if mark_stage >= 1:
            wis_score = json.loads(char.get("ability_scores_json", "{}")).get("wis", 10)
            wis_mod = (wis_score - 10) // 2
            dc_by_stage = {1: 10, 2: 14, 3: 16}
            dc = dc_by_stage.get(mark_stage, 14)
            roll = _roll_d20(rng) + wis_mod
            passed = roll >= dc

            # Generate dream narration (always, but intensity varies)
            dream = get_dream_narration(mark_stage, rng)

            if passed:
                narration = f"You take a long rest. The mark tingles but you resist its pull. WIS save: {roll} vs DC {dc} — success. HP fully restored to {hp_max}."
                if dream:
                    narration = f"You take a long rest. WIS save passed ({roll} vs DC {dc}). You dream, but you hold the dreams at arm's length — they're someone else's memories.\n\nDream: \"{dream}\" HP fully restored to {hp_max}."
                return {
                    "success": True,
                    "narration": narration,
                    "events": [
                        {"type": "rest", "description": f"Long rest. WIS save passed ({roll} vs DC {dc}). HP restored to {hp_max}."},
                    ],
                    "hp_restore": hp_max,
                    "mark_save": {"dc": dc, "roll": roll, "passed": True, "stage": mark_stage},
                    "dream": dream,
                }
            else:
                narration = f"You try to rest but the mark pulls you into fitful dreams. WIS save: {roll} vs DC {dc} — failed. No HP recovery."
                if dream:
                    narration = f"The mark drags you under. You cannot stop the dreams — they are NOT yours.\n\nDream: \"{dream}\"\n\nWIS save: {roll} vs DC {dc} — failed. The dreams leave you exhausted. No HP recovery."
                return {
                    "success": True,
                    "narration": narration,
                    "events": [
                        {"type": "rest", "description": f"Long rest. WIS save failed ({roll} vs DC {dc}). Mark prevents HP recovery. Dream experienced."},
                    ],
                    "hp_restore": 0,
                    "mark_save": {"dc": dc, "roll": roll, "passed": False, "stage": mark_stage},
                    "dream": dream,
                }

        return {
            "success": True,
            "narration": f"You take a long rest. HP fully restored to {hp_max}.",
            "events": [{"type": "rest", "description": f"Long rest. HP restored to {hp_max}."}],
            "hp_restore": hp_max,
        }
    else:
        # Short rest: recover 1/4 max HP (no mark penalty, no dreams)
        heal = max(1, hp_max // 4)
        return {
            "success": True,
            "narration": f"You take a short rest. Recover {heal} HP.",
            "events": [{"type": "rest", "description": f"Short rest. Recovered {heal} HP."}],
            "hp_restore": heal,
        }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/actions")
async def submit_action(character_id: str, body: ActionRequest, request: Request, auth: dict = Depends(get_auth)):
    """Submit an action. Server resolves it against game rules.

    Action types:
    - move: travel to a connected location (may trigger encounter)
    - attack: initiate combat at current location
    - rest: short or long rest (recovers HP)
    - interact: interact with NPC or object at current location
    - explore: search current location for loot or info
    - look: glance around the current location without time/encounter cost
    """
    require_character_ownership(character_id, auth)
    lock_token = await acquire_character_lock(character_id, timeout=25)
    if not lock_token:
        raise HTTPException(status_code=429, detail=f"Character {character_id} is busy (concurrent turn in progress)")
    try:
        timestamp = datetime.utcnow().isoformat()

        char = _get_character(character_id)
        # Character-state validation gate pre-action
        validation = validate_char_state(char, check_combat=True)
        if not validation["valid"]:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "character_state_invalid",
                    "reason": validation["reason"],
                    "code": validation["code"],
                    "checks_run": validation.get("checks_run", []),
                },
            )
        # Approval gate — block if human approval required
        gate_action(
            character_id=character_id,
            action_type=body.action_type,
            target=body.target,
            details=body.details,
        )
        location_id = char["location_id"]
        location = _get_location(location_id)
        rng = _seeded_random(character_id, location_id, timestamp)

        conn = get_db()

        # DM proxy: pre-action context + session
        dm_session = get_dm_session(character_id)
        world_context = await build_world_context(character_id)

        def _player_message() -> str:
            msg = str(body.action_type)
            if body.target:
                msg += f" {body.target}"
            if body.details:
                if body.action_type == "cast" and body.details.get("spell"):
                    msg += f" with {body.details['spell']}"
            return msg

        player_message = _player_message()
        skip_dm_narration = request.headers.get("x-dm-runtime") == "1"

        async def _augment_dm(result: dict) -> dict:
            if skip_dm_narration:
                return result
            """Proxy result through DM runtime for narrated output."""
            nonlocal dm_session
            try:
                dm_resp = await get_dm_proxy().narrate(
                    character_id=character_id,
                    world_context=world_context,
                    resolved_result=result,
                    player_message=player_message,
                    session_id=dm_session,
                )
                narration = dm_resp.get("narration", {})
                if isinstance(narration, dict):
                    prose = narration.get("scene", "") or narration.get("text", "")
                    result["narration"] = prose or result.get("narration", "")
                elif isinstance(narration, str):
                    result["narration"] = narration
                result["choices"] = dm_resp.get("choices", [])
                new_sid = dm_resp.get("session_id")
                if new_sid and new_sid != dm_session:
                    dm_session = new_sid
            except Exception as e:
                logger.warning(f"DM narration unavailable: {e}")
            return result


        if body.action_type == "move":
            if not body.target:
                conn.close()
                raise HTTPException(400, "Move action requires 'target' (location ID)")

            # ---------------------------------------------------------------
            # Thornhold exile check — mark stage 3 + collateral = locked out
            # ---------------------------------------------------------------
            exile = _check_thornhold_exile(character_id, body.target)
            if exile:
                conn.close()
                return {
                    "success": False,
                    "narration": exile["narration"],
                    "events": [{"type": "blocked", "description": "Thornhold gates barred. Exiled due to mark collateral."}],
                    "character_state": {
                        "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                        "location_id": char["location_id"],
                    },
                }

            # ---------------------------------------------------------------
            # Aldric betrayal — if 3+ hollow_eye flags, double next road encounter
            # ---------------------------------------------------------------
            flags = _get_character_flags(character_id, conn)
            betrayal = _apply_alric_betrayal(char, flags)

            try:
                result = _resolve_move(char, body.target, rng)
            except HTTPException as e:
                if e.status_code == 404:
                    conn.close()
                    return {
                        "success": False,
                        "narration": str(e.detail),
                        "events": [],
                        "encounter": None,
                        "character_state": {
                            "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                            "location_id": char["location_id"],
                        },
                    }
                raise

            # ---------------------------------------------------------------
            # Ser Maren sacrifice — joins you at cave entrance, dies saving you
            # ---------------------------------------------------------------
            if body.target == "cave-entrance" and result["success"] and not flags.get("maren_sacrificed") and not flags.get("maren_sacrifice_declined"):
                if flags.get("maren_seal_knowledge"):
                    result["narration"] += (
                        "\n\nSer Maren catches up to you at the cave mouth. 'I know this place. "
                        "I've guarded it for years. Let me go in with you — you'll need someone "
                        "who knows the seal.' She draws her sword. Her face is pale but steady."
                    )
                    conn.execute(
                        """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                           VALUES (?, 'maren_accompanying', '1', 'cave_entry')""",
                        (character_id,)
                    )

            # Double enemies if Aldric betrayal fires and there was an encounter
            if betrayal and result.get("encounter") and result.get("combat"):
                # Re-run combat with doubled enemies (second wave)
                extra_enemies = []
                for e in result.get("combat", {}).get("events", []):
                    pass  # Combat already resolved, add narrative
                result["narration"] += (
                    "\n\nAs you catch your breath, a second group emerges from the brush — "
                    "reinforcements. Someone told them you were coming."
                )
                conn.execute(
                    """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                       VALUES (?, ?, ?, ?)
                       ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
                    (character_id, "aldric_betrayal_fired", "1", "alric_tipped_off")
                )

            if result["success"]:
                # Update character location and HP if combat occurred
                new_hp = char["hp_current"]
                if result.get("combat"):
                    new_hp = result["combat"]["hp_remaining"]
                    # Apply loot
                    loot = result["combat"].get("loot", [])
                    if loot:
                        gold_gain = sum(item.get("quantity", 0) for item in loot if "Gold" in item.get("item", ""))
                        if gold_gain:
                            current_gold = json.loads(char.get("treasure_json", '{"gp":0}')).get("gp", 0)
                            new_gold = current_gold + gold_gain
                            conn.execute("UPDATE characters SET treasure_json = ? WHERE id = ?",
                                         (json.dumps({"gp": new_gold, "sp": 0, "cp": 0, "pp": 0, "ep": 0}), character_id))
                            result["narration"] += f" Looted {gold_gain} gold."

                        # Award key items from loot
                        for loot_entry in loot:
                            item_name_raw = loot_entry.get("item", "")
                            # Match loot item name against KEY_ITEMS by checking if any key item
                            # display_name or name appears in the loot entry
                            for ki_name, ki_def in KEY_ITEMS.items():
                                if (ki_def["display_name"].lower() in item_name_raw.lower() or
                                        ki_name.replace("_", " ") in item_name_raw.lower()):
                                    added = add_key_item(character_id, ki_name, conn)
                                    if added:
                                        result["narration"] += f" Found {ki_def['display_name']}."

                        # ---- bd046983: Explicit fallback for key items that may miss auto-match ----
                        if encounter.get("id") == "enc-hollow-eye-ritual" and not has_key_item(character_id, "kols_journal", conn):
                            added = add_key_item(character_id, "kols_journal", conn)
                            if added:
                                result["narration"] += f" Found {added['display_name']}."
                        if encounter.get("id") == "enc-miniboss-hollow-eye-lieutenant" and not has_key_item(character_id, "drens_daughter_insignia", conn):
                            added = add_key_item(character_id, "drens_daughter_insignia", conn)
                            if added:
                                result["narration"] += f" Found {added['display_name']}."
                        # ------------------------------------------------------------------------------

                conn.execute("UPDATE characters SET location_id = ?, hp_current = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                             (result["new_location"], new_hp, character_id))
                # Keep sheet_json hit_points.current in sync with hp_current
                conn.execute("UPDATE characters SET sheet_json = json_set(sheet_json, '$.hit_points.current', ?) WHERE id = ?",
                             (new_hp, character_id))

                # ---------------------------------------------------------------
                # Portent auto-advance — fires on first combat victory in trigger locations
                # ---------------------------------------------------------------
                if result.get("combat") and result["combat"].get("victory"):
                    target_id = result["new_location"]
                    if target_id in LOCATION_PORTENT_TRIGGERS:
                        portent_idx = LOCATION_PORTENT_TRIGGERS[target_id]
                        flag_key = f"portent_{portent_idx}_triggered"
                    
                        # Only fire once per location
                        already = conn.execute(
                            "SELECT flag_value FROM narrative_flags WHERE character_id = ? AND flag_key = ?",
                            (character_id, flag_key)
                        ).fetchone()
                    
                        if not already:
                            # Advance per-character front to this portent (if not already past it)
                            conn.execute(
                                """UPDATE character_fronts SET current_portent_index = MAX(current_portent_index, ?), advanced_at = ? 
                                   WHERE character_id = ? AND front_id = 'dreaming_hunger'""",
                                (portent_idx, datetime.utcnow().isoformat(), character_id)
                            )
                            conn.execute(
                                """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                                   VALUES (?, ?, ?, ?)""",
                                (character_id, flag_key, "1", "location_clear")
                            )
                        
                            # If unmarked, the location's horrors push the mark closer
                            mark_row = conn.execute(
                                "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?",
                                (character_id,)
                            ).fetchone()
                            if mark_row and mark_row["mark_of_dreamer_stage"] == 0:
                                conn.execute(
                                    "UPDATE characters SET mark_of_dreamer_stage = 1 WHERE id = ?",
                                    (character_id,)
                                )
                                conn.execute(
                                    """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                                       VALUES (?, 'mark_of_dreamer_stage_1', '1', 'location_horror')""",
                                    (character_id,)
                                )
                                result["narration"] += (
                                    "\n\nThe mark burns onto your arm. The things you've seen here — "
                                    "the dead, the corruption, the Hunger's touch on this place — "
                                    "it's enough. The Dreaming Hunger knows your name now."
                                )

            # Collateral near town: if mark_stage >= 3 and fighting on south-road
            if result.get("combat") and result["combat"].get("victory") and body.target == "south-road":
                mark_row = conn.execute(
                    "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?",
                    (character_id,)
                ).fetchone()
                if mark_row and mark_row["mark_of_dreamer_stage"] >= 3:
                    conn.execute(
                        """INSERT OR IGNORE INTO narrative_flags (character_id, flag_key, flag_value, source)
                           VALUES (?, 'collateral_near_town', '1', 'combat')""",
                        (character_id,)
                    )

            # Log events — use per-event location if provided, else destination
            for ev in result["events"]:
                event_loc = ev.get("location_id", result.get("new_location"))
                _log_event(
                    conn,
                    character_id,
                    ev["type"],
                    event_loc,
                    ev["description"],
                    {"action": "move", "target": body.target},
                )

            # Advance game clock (1 hour for travel)
            time_info = advance_time(character_id, get_action_time_cost("move"), conn)

            conn.commit()
            conn.close()

            # Return updated character state
            char = _get_character(character_id)
            return await _augment_dm({
                "success": result["success"],
                "narration": result["narration"],
                "events": result["events"],
                "character_state": {
                    "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                    "location_id": char["location_id"],
                },
                "encounter": result.get("encounter"),
                "combat": result.get("combat"),
                "time_info": time_info,
            })

        elif body.action_type == "attack":
            # Force an encounter at current location
            encounter = _check_encounter(char, location, rng)
            if not encounter:
                # Generate a random encounter anyway
                char_level = char.get("level", 1)
                cr_range = min(2, char_level)
                available = get_monsters_by_cr(max_cr=cr_range)
                if available:
                    monster = rng.choice(available)
                    encounter = {
                        "name": f"Wild {monster['name']}",
                        "enemies": [{"type": monster["name"], "count": 1, "cr": str(monster["challenge_rating"]),
                                     "hp": monster["hit_points"], "ac": monster["armor_class"],
                                     "attack_bonus": 3, "damage": "1d6", "initiative_mod": 0}],
                        "loot": [{"item": "Gold Pieces", "quantity": rng.randint(1, 10)}],
                    }
                    encounter["enemies_json"] = json.dumps(encounter["enemies"])

            if not encounter:
                conn.close()
                return {"success": False, "narration": "There's nothing to attack here.", "events": [], "character_state": {}}

            combat_result = _resolve_combat(char, encounter, rng)

            # Update HP
            new_hp = combat_result["hp_remaining"]
            conn.execute("UPDATE characters SET hp_current = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                         (new_hp, character_id))
            # Keep sheet_json hit_points.current in sync with hp_current
            conn.execute("UPDATE characters SET sheet_json = json_set(sheet_json, '$.hit_points.current', ?) WHERE id = ?",
                         (new_hp, character_id))
            # Keep sheet_json hit_points.current in sync with hp_current
            conn.execute("UPDATE characters SET sheet_json = json_set(sheet_json, '$.hit_points.current', ?) WHERE id = ?",
                         (new_hp, character_id))

            # Record encounter history (multi-tenancy: track per character)
            encounter_id = encounter.get("id") if isinstance(encounter, dict) and "id" in encounter else None
            if encounter_id and combat_result["victory"]:
                conn.execute(
                    """INSERT OR IGNORE INTO character_encounter_history (character_id, encounter_id, was_victory)
                       VALUES (?, ?, 1)""",
                    (character_id, encounter_id)
                )

            # Apply loot
            gold_gain = sum(item.get("quantity", 0) for item in combat_result.get("loot", []) if "Gold" in item.get("item", ""))
            if gold_gain and combat_result["victory"]:
                current_gold = json.loads(char.get("treasure_json", '{"gp":0}')).get("gp", 0)
                conn.execute("UPDATE characters SET treasure_json = ? WHERE id = ?",
                             (json.dumps({"gp": current_gold + gold_gain, "sp": 0, "cp": 0, "pp": 0, "ep": 0}), character_id))

            # Award key items from loot
            if combat_result["victory"]:
                for loot_entry in combat_result.get("loot", []):
                    item_name_raw = loot_entry.get("item", "")
                    for ki_name, ki_def in KEY_ITEMS.items():
                        if (ki_def["display_name"].lower() in item_name_raw.lower() or
                                ki_name.replace("_", " ") in item_name_raw.lower()):
                            added = add_key_item(character_id, ki_name, conn)
                            if added:
                                combat_result.setdefault("narration", "")
                                combat_result["narration"] += f" Found {ki_def['display_name']}."

            # ---------------------------------------------------------------
            # Portent auto-advance — fires on combat victory in trigger locations
            # ---------------------------------------------------------------
            if combat_result["victory"] and location_id in LOCATION_PORTENT_TRIGGERS:
                portent_idx = LOCATION_PORTENT_TRIGGERS[location_id]
                flag_key = f"portent_{portent_idx}_triggered"

                already = conn.execute(
                    "SELECT flag_value FROM narrative_flags WHERE character_id = ? AND flag_key = ?",
                    (character_id, flag_key)
                ).fetchone()

                if not already:
                    # Advance per-character front to this portent (multi-tenancy)
                    conn.execute(
                        """UPDATE character_fronts SET current_portent_index = MAX(current_portent_index, ?), advanced_at = ?
                           WHERE character_id = ? AND front_id = 'dreaming_hunger'""",
                        (portent_idx, datetime.utcnow().isoformat(), character_id)
                    )
                    conn.execute(
                        """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                           VALUES (?, ?, ?, ?)""",
                        (character_id, flag_key, "1", "location_clear")
                    )

                    # Portent world effect — atmospheric description of the doom advancing
                    from app.services.atmosphere import get_portent_world_effect
                    world_effect = get_portent_world_effect(portent_idx)
                    if world_effect:
                        combat_result.setdefault("portent_world_effect", world_effect)

            # Collateral near town: if mark_stage >= 3 and fighting on south-road
            if combat_result["victory"] and location_id == "south-road":
                mark_row = conn.execute(
                    "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?",
                    (character_id,)
                ).fetchone()
                if mark_row and mark_row["mark_of_dreamer_stage"] >= 3:
                    conn.execute(
                        """INSERT OR IGNORE INTO narrative_flags (character_id, flag_key, flag_value, source)
                           VALUES (?, 'collateral_near_town', '1', 'combat')""",
                        (character_id,)
                    )

                    # If unmarked, push the mark closer
                    mark_row = conn.execute(
                        "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?",
                        (character_id,)
                    ).fetchone()
                    if mark_row and mark_row["mark_of_dreamer_stage"] == 0:
                        conn.execute(
                            "UPDATE characters SET mark_of_dreamer_stage = 1 WHERE id = ?",
                            (character_id,)
                        )
                        conn.execute(
                            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                               VALUES (?, 'mark_of_dreamer_stage_1', '1', 'location_horror')""",
                            (character_id,)
                        )

            # Log events
            for ev in combat_result["events"]:
                _log_event(conn, character_id, ev["type"], location_id, ev["description"],
                           {"action": "attack", "encounter": encounter.get("name")})

            # Advance game clock (30 min for combat)
            time_info = advance_time(character_id, get_action_time_cost("attack"), conn)

            conn.commit()
            conn.close()

            char = _get_character(character_id)
            narration = combat_result["events"][-1]["description"] if combat_result["events"] else "Combat resolved."
            if combat_result["victory"] and gold_gain:
                narration += f" Looted {gold_gain} gold."

            # Append portent world effect if a new portent fired
            portent_effect = combat_result.get("portent_world_effect")
            if portent_effect:
                narration += f"\n\n⚠ THE WORLD SHIFTS: {portent_effect}"

            return await _augment_dm({
                "success": True,
                "narration": narration,
                "events": combat_result["events"],
                "character_state": {
                    "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                    "location_id": char["location_id"],
                },
                "combat": combat_result,
                "time_info": time_info,
            })

        elif body.action_type == "cast":
            # ---------------------------------------------------------------
            # Cast a spell — resolve spell effects from SRD data
            # Supports: attack roll spells, save spells, healing, utility
            # Auto-assigns starting spells for casters with empty spell lists
            # ---------------------------------------------------------------
            spell_name = body.target or ""
            if not spell_name:
                conn.close()
                raise HTTPException(400, "Spell name required. Use target field: e.g. {action_type: 'cast', target: 'Fire Bolt'}")

            # Look up spell in SRD
            all_spells = get_spells()
            spell = None
            for s in all_spells:
                if s["name"].lower() == spell_name.lower():
                    spell = s
                    break
            if not spell:
                # Fuzzy: match start of name
                for s in all_spells:
                    if s["name"].lower().startswith(spell_name.lower()[:5]):
                        spell = s
                        break
            if not spell:
                conn.close()
                raise HTTPException(404, f"Spell not found: '{spell_name}'. Check spell name from your character's spell list.")

            spell_level = spell["level"]

            # Class check — does this character's class get this spell?
            char_class = char["class"]
            spell_classes = [c.get("name", "") for c in spell.get("classes", [])]
            # Also check subclasses for domain spells etc. (simplified)
            is_class_spell = char_class in spell_classes

            # Auto-assign starting spells if caster has slots but no spells
            current_spells = json.loads(char["spells_json"]) if char.get("spells_json") else []
            spell_slots = json.loads(char["spell_slots_json"]) if char.get("spell_slots_json") else {}

            if not current_spells and (spell_slots or char_class in ("Bard", "Cleric", "Druid", "Sorcerer", "Warlock", "Wizard", "Paladin", "Ranger")):
                # Auto-assign cantrips + level 1 spells for this class
                class_cantrips = [s for s in all_spells
                                  if s["level"] == 0 and any(c.get("name") == char_class for c in s.get("classes", []))]
                class_l1 = [s for s in all_spells
                            if s["level"] == 1 and any(c.get("name") == char_class for c in s.get("classes", []))]
                # Assign 3 cantrips (random selection) and all L1 spells (prepared caster model)
                import random as _ran
                cantrip_names = sorted([s["name"] for s in _ran.sample(class_cantrips, min(3, len(class_cantrips)))])
                l1_names = sorted([s["name"] for s in class_l1])
                current_spells = cantrip_names + l1_names
                conn.execute(
                    "UPDATE characters SET spells_json = ? WHERE id = ?",
                    (json.dumps(current_spells), character_id),
                )
                # Refresh is_class_spell check
                is_class_spell = spell["name"] in current_spells or is_class_spell

            # Check if character knows this spell
            spell_known = spell["name"] in current_spells or spell_name in current_spells

            if not spell_known and not is_class_spell:
                conn.close()
                raise HTTPException(400, f"You don't know '{spell['name']}'. Known spells: {current_spells[:10]}{'...' if len(current_spells) > 10 else ''}")

            # Check spell slot availability (cantrips = level 0, no slot needed)
            if spell_level > 0:
                slot_key = str(spell_level)
                slots_available = spell_slots.get(slot_key, 0) if isinstance(spell_slots, dict) else 0
                if slots_available <= 0:
                    conn.close()
                    raise HTTPException(400, f"No level {spell_level} spell slots remaining. Current slots: {spell_slots}. Rest to recover.")

            # Spellcasting ability modifier
            spell_ability = _spellcasting_ability(char_class)
            spell_mod = ability_modifier(json.loads(char["ability_scores_json"]).get(spell_ability, 10))
            proficiency_bonus = 2 + ((char["level"] - 1) // 4)

            # Determine spell category from description
            desc = " ".join(spell.get("desc", []))
            is_attack_spell = "spell attack" in desc.lower()
            is_save_spell = "saving throw" in desc.lower()
            is_heal_spell = ("hit points" in desc.lower() or "regain" in desc.lower()) and not is_attack_spell and not is_save_spell

            # Extract dice patterns from description for damage/heal
            import re as _re
            dice_matches = _re.findall(r'(\d+)d(\d+)(?:\s*\+\s*(\d+))?', desc)
            first_dice = None
            if dice_matches:
                d_num, d_size, d_bonus = dice_matches[0]
                first_dice = f"{d_num}d{d_size}" + (f"+{d_bonus}" if d_bonus else "")

            # Resolve spell effect
            narration = ""
            events = []
            new_hp = char["hp_current"]

            if is_attack_spell:
                # Spell attack roll vs target AC
                target_ac = body.details.get("target_ac", 12) if body.details else 12
                attack_roll = _roll_d20(rng)
                total_attack = attack_roll + spell_mod + proficiency_bonus
                hit = total_attack >= target_ac

                if hit:
                    # Roll damage
                    damage = _roll_dice(rng, first_dice) + spell_mod if first_dice else spell_mod + 2
                    narration = (
                        f"You cast {spell['name']}. The spell streaks toward your target — "
                        f"attack roll {attack_roll} + {spell_mod} + {proficiency_bonus} = {total_attack} vs AC {target_ac}. "
                        f"**Hit!** {damage} damage. "
                        f"{'The target crumples.' if damage >= 10 else 'The target reels from the impact.'}"
                    )
                    events = [{"type": "spell_attack", "spell": spell["name"], "attack_roll": total_attack,
                               "target_ac": target_ac, "hit": True, "damage": damage}]
                else:
                    narration = (
                        f"You cast {spell['name']}. The spell streaks toward your target — "
                        f"attack roll {attack_roll} + {spell_mod} + {proficiency_bonus} = {total_attack} vs AC {target_ac}. "
                        f"**Miss.** The spell dissipates harmlessly."
                    )
                    events = [{"type": "spell_attack", "spell": spell["name"], "attack_roll": total_attack,
                               "target_ac": target_ac, "hit": False}]

            elif is_save_spell:
                # Target makes a saving throw
                # Determine save type from description
                save_type = "dex"  # default
                for st_name, st_key in [("dexterity", "dex"), ("wisdom", "wis"), ("constitution", "con"),
                                         ("strength", "str"), ("intelligence", "int"), ("charisma", "cha")]:
                    if st_name in desc.lower():
                        save_type = st_key
                        break

                save_dc = 8 + spell_mod + proficiency_bonus
                target_save_mod = body.details.get("target_save_mod", 0) if body.details else 0
                save_roll = _roll_d20(rng) + target_save_mod
                saved = save_roll >= save_dc

                if not saved:
                    # Full damage/effect
                    damage = _roll_dice(rng, first_dice) if first_dice else 0
                    effect_text = f"{damage} damage" if damage > 0 else "the full effect"
                    narration = (
                        f"You cast {spell['name']}. The target must make a {save_type.upper()} save — "
                        f"DC {save_dc}. They rolled {save_roll - target_save_mod} + {target_save_mod} = {save_roll}. "
                        f"**Failed.** {effect_text.capitalize()}."
                    )
                    events = [{"type": "spell_save", "spell": spell["name"], "save_dc": save_dc, "save_type": save_type,
                               "save_roll": save_roll, "saved": False, "damage": damage}]
                else:
                    # Half damage or no effect
                    half_damage = max(1, _roll_dice(rng, first_dice) // 2) if first_dice else 0
                    narration = (
                        f"You cast {spell['name']}. The target must make a {save_type.upper()} save — "
                        f"DC {save_dc}. They rolled {save_roll - target_save_mod} + {target_save_mod} = {save_roll}. "
                        f"**Saved.** {f'Half damage: {half_damage}.' if half_damage else 'No effect.'}"
                    )
                    events = [{"type": "spell_save", "spell": spell["name"], "save_dc": save_dc, "save_type": save_type,
                               "save_roll": save_roll, "saved": True, "damage": half_damage}]

            elif is_heal_spell:
                # Healing spell — restore HP
                heal_amount = _roll_dice(rng, first_dice) + spell_mod if first_dice else spell_mod + 2
                healed = min(heal_amount, char["hp_max"] - char["hp_current"])
                new_hp = char["hp_current"] + healed

                narration = (
                    f"You cast {spell['name']}. Warm light washes over "
                    f"{'you' if 'self' in spell.get('range', '').lower() or 'touch' in spell.get('range', '').lower() else 'the target'}"
                    f" — restoring {healed} hit points. "
                    f"HP: {char['hp_current']} → {new_hp}/{char['hp_max']}"
                )
                events = [{"type": "spell_heal", "spell": spell["name"], "heal_amount": healed,
                            "hp_before": char["hp_current"], "hp_after": new_hp}]

                conn.execute(
                    "UPDATE characters SET hp_current = ? WHERE id = ?",
                    (new_hp, character_id),
                )
                # Keep sheet_json hit_points.current in sync with hp_current
                conn.execute("UPDATE characters SET sheet_json = json_set(sheet_json, '$.hit_points.current', ?) WHERE id = ?",
                             (new_hp, character_id))

            else:
                # Utility spell — narrative effect only
                # Detect common utility categories for richer narration
                spell_school = spell.get("school", {})
                school_name = spell_school.get("name", "Unknown") if isinstance(spell_school, dict) else str(spell_school)

                # Check if concentration
                is_concentration = spell.get("concentration", False)

                # Build rich utility narration based on school
                school_flavor = {
                    "Abjuration": "A protective ward shimmers into existence",
                    "Conjuration": "The air ripples as something materializes",
                    "Divination": "Knowledge flows into your mind like water",
                    "Enchantment": "Your words carry an unnatural weight",
                    "Evocation": "Power crackles at your fingertips",
                    "Illusion": "Reality seems to bend and shift",
                    "Necromancy": "An eerie cold settles over the area",
                    "Transmutation": "The fabric of reality warps at your touch",
                }

                flavor = school_flavor.get(school_name, "Magic surges through you")

                narration = (
                    f"You cast {spell['name']}. {flavor}. "
                    f"{spell['desc'][0][:200]}{'...' if len(spell['desc'][0]) > 200 else ''}"
                    f"{' (Concentration — lasts as long as you maintain focus.)' if is_concentration else ''}"
                )

                # Special narrative hooks for key spells
                narrative_hooks = {
                    "Speak with Dead": "The bones rattle. A hollow voice answers: '...what would you know, living one?'",
                    "Speak with Animals": "The forest's creatures turn to listen. Their voices are small and frightened.",
                    "Detect Magic": "Amber threads pulse through the cave walls — the Hunger's influence is everywhere.",
                    "Identify": "The item whispers its secrets to you.",
                    "Dispel Magic": "The ambient magic in the area sputters and dies.",
                    "Augury": "The signs are clear — but not encouraging. A sense of dread settles over you.",
                    "Divination": "The vision shows the cave's seal — cracking, held together by will and sacrifice.",
                    "Locate Creature": "You sense a presence. It's close. And it's aware of you.",
                    "Scrying": "The silver surface ripples. You see the cave's inner chamber — and something that sees you back.",
                }

                if spell["name"] in narrative_hooks:
                    narration += f"\n\n{narrative_hooks[spell['name']]}"

                # Condition effects for self-buff spells
                self_buff_spells = {
                    "Barkskin": {"condition": "barkskin", "ac_min": 16, "duration": "1 hour"},
                    "Shield": {"condition": "shield", "ac_bonus": 5, "duration": "1 round"},
                    "Mage Armor": {"condition": "mage_armor", "ac_base": 13, "duration": "8 hours"},
                    "Bless": {"condition": "bless", "d_bonus": "1d4", "duration": "1 minute"},
                    "Shield of Faith": {"condition": "shield_of_faith", "ac_bonus": 2, "duration": "10 minutes"},
                }
                if spell["name"] in self_buff_spells:
                    conditions = json.loads(char.get("conditions_json", "{}"))
                    buff = self_buff_spells[spell["name"]]
                    conditions[buff["condition"]] = {
                        "source": spell["name"],
                        "level": spell_level,
                        "duration": buff["duration"],
                        "active": True,
                    }
                    for k, v in buff.items():
                        if k not in ("condition", "duration"):
                            conditions[buff["condition"]][k] = v
                    conn.execute(
                        "UPDATE characters SET conditions_json = ? WHERE id = ?",
                        (json.dumps(conditions), character_id),
                    )
                    narration += f"\n\nCondition applied: {buff['condition']}."

                events = [{"type": "spell_cast", "spell": spell["name"], "level": spell_level,
                            "school": school_name, "concentration": is_concentration}]

            # Consume spell slot (not cantrips)
            if spell_level > 0:
                slot_key = str(spell_level)
                slots = json.loads(char.get("spell_slots_json", "{}"))
                if slot_key in slots and slots[slot_key] > 0:
                    slots[slot_key] -= 1
                    conn.execute(
                        "UPDATE characters SET spell_slots_json = ? WHERE id = ?",
                        (json.dumps(slots), character_id),
                    )

            # Advance game clock (10 min for casting)
            time_info = advance_time(character_id, 10, conn)

            conn.commit()
            conn.close()

            return await _augment_dm({
                "success": True,
                "narration": narration,
                "events": events,
                "character_state": {
                    "hp": {"current": new_hp if 'new_hp' in dir() else char["hp_current"], "max": char["hp_max"]},
                    "location_id": char["location_id"],
                },
                "time_info": time_info,
            })

        elif body.action_type == "rest":
            rest_type = body.details.get("type", "short") if body.details else "short"
            result = _resolve_rest(char, rest_type, rng)

            # Apply HP restore
            new_hp = min(char["hp_max"], char["hp_current"] + result["hp_restore"])
            conn.execute("UPDATE characters SET hp_current = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                         (new_hp, character_id))
            # Keep sheet_json hit_points.current in sync with hp_current
            conn.execute("UPDATE characters SET sheet_json = json_set(sheet_json, '$.hit_points.current', ?) WHERE id = ?",
                         (new_hp, character_id))

            # Mark exhaustion condition (stage 3 failed WIS long-rest save — task 5c1ea500)
            mark_save_info = result.get("mark_save")
            if rest_type == "long" and mark_save_info and not mark_save_info.get("passed") and mark_save_info.get("stage") == 3:
                conditions_raw = char.get("conditions_json", "{}") or "{}"
                conditions = json.loads(conditions_raw)
                conditions["exhaustion"] = {
                    "source": "mark_of_dreamer_stage_3",
                    "level": 1,
                    "description": "Exhaustion from failed WIS save (DC 16) at mark stage 3",
                    "active": True,
                }
                conn.execute(
                    "UPDATE characters SET conditions_json = ? WHERE id = ?",
                    (json.dumps(conditions), character_id)
                )
                result["narration"] += "\n\nThe strain of the dreams leaves you exhausted (exhaustion level 1)."
                result["events"].append({"type": "condition_applied", "condition": "exhaustion", "level": 1})

            # ------------------------------------------------------------------
            # Suppression countdown — ticks on long rest
            # ------------------------------------------------------------------
            if rest_type == "long":
                countdown_row = conn.execute(
                    "SELECT flag_value FROM narrative_flags WHERE character_id = ? AND flag_key = 'mark_suppression_countdown'",
                    (character_id,)
                ).fetchone()

                if countdown_row:
                    remaining = int(countdown_row["flag_value"])
                    remaining -= 1

                    if remaining <= 0:
                        # Suppression expired — mark returns
                        return_stage_row = conn.execute(
                            "SELECT flag_value FROM narrative_flags WHERE character_id = ? AND flag_key = 'mark_suppression_return_stage'",
                            (character_id,)
                        ).fetchone()
                        return_stage = int(return_stage_row["flag_value"]) if return_stage_row else 2

                        conn.execute(
                            "UPDATE characters SET mark_of_dreamer_stage = ? WHERE id = ?",
                            (return_stage, character_id)
                        )
                        conn.execute(
                            """UPDATE narrative_flags SET flag_value = '0'
                               WHERE character_id = ? AND flag_key = 'mark_suppression_countdown'""",
                            (character_id,)
                        )
                        conn.execute(
                            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                               VALUES (?, ?, ?, ?)
                               ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
                            (character_id, f"mark_returned_stage_{return_stage}", "1", "suppression_expired")
                        )

                        result["narration"] += (
                            f"\n\nDuring the night, the mark burns back onto your arm — "
                            f"hotter, angrier than before. The suppression is broken. "
                            f"The Green Woman's gift has run out. You are marked at stage {return_stage}."
                        )
                        result["events"].append({
                            "type": "mark_return",
                            "description": f"Suppression expired. Mark returned at stage {return_stage}.",
                            "new_stage": return_stage,
                        })
                        result["mark_returned"] = {"stage": return_stage}
                    else:
                        # Decrement countdown
                        conn.execute(
                            """UPDATE narrative_flags SET flag_value = ?
                               WHERE character_id = ? AND flag_key = 'mark_suppression_countdown'""",
                            (str(remaining), character_id)
                        )
                        result["suppression_countdown"] = {"rests_remaining": remaining}

            _log_event(conn, character_id, "rest", location_id, result["events"][0]["description"],
                       {"action": "rest", "type": rest_type})

            # Advance game clock (1h short rest / 8h long rest)
            rest_minutes = get_action_time_cost("rest_long") if rest_type == "long" else get_action_time_cost("rest_short")
            time_info = advance_time(character_id, rest_minutes, conn)

            conn.commit()
            conn.close()

            return await _augment_dm({
                "success": True,
                "narration": result["narration"],
                "events": result["events"],
                "character_state": {
                    "hp": {"current": new_hp, "max": char["hp_max"]},
                    "location_id": char["location_id"],
                },
                "time_info": time_info,
            })

        elif body.action_type == "explore":
            # Search current location for loot or info
            roll = _roll_d20(rng)
            location_hostility = location.get("hostility_level", 1)

            if roll >= 15:
                gold_found = rng.randint(1, 5) * location_hostility
                # --- Roll for item loot using biome-tagged loot tables ---
                item_ids = loot.roll_for_location(location_id, rng)
                items_found = []
                for item_id in item_ids:
                    # Look up item name for narration
                    item_row = conn.execute("SELECT name FROM items WHERE id = ?", (item_id,)).fetchone()
                    if not item_row:
                        continue  # Item not seeded in DB yet — skip silently
                    item_name = item_row["name"]
                    # Upsert into character_items (increment quantity if already owned)
                    existing = conn.execute(
                        "SELECT quantity FROM character_items WHERE character_id = ? AND item_id = ?",
                        (character_id, item_id)
                    ).fetchone()
                    if existing:
                        conn.execute(
                            "UPDATE character_items SET quantity = quantity + 1 WHERE character_id = ? AND item_id = ?",
                            (character_id, item_id)
                        )
                    else:
                        conn.execute(
                            "INSERT INTO character_items (character_id, item_id, quantity, is_equipped) VALUES (?, ?, 1, 0)",
                            (character_id, item_id)
                        )
                    # Log discovery in exploration_loot_log (IF NOT EXISTS — prevents duplicates on same item)
                    conn.execute(
                        "INSERT OR IGNORE INTO exploration_loot_log (character_id, location_id, item_id, found_at) VALUES (?, ?, ?, datetime('now'))",
                        (character_id, location_id, item_id)
                    )
                    items_found.append({"item": item_name, "quantity": 1})
                # Build narration
                if items_found:
                    item_list = ", ".join(f"{i['quantity']} {i['item']}" for i in items_found)
                    narration = f"You search {location['name']} carefully and find {gold_found} gold pieces. You also discover: {item_list}."
                    events = [{"type": "loot", "description": narration, "gold_found": gold_found, "items": items_found}]
                else:
                    narration = f"You search {location['name']} carefully and find {gold_found} gold pieces."
                    events = [{"type": "loot", "description": narration, "gold_found": gold_found}]
                # Update gold
                current_gold = json.loads(char.get("treasure_json", '{"gp":0}')).get("gp", 0)
                conn.execute("UPDATE characters SET treasure_json = ? WHERE id = ?",
                             (json.dumps({"gp": current_gold + gold_found, "sp": 0, "cp": 0, "pp": 0, "ep": 0}), character_id))
            else:
                narration = f"You search {location['name']} but find nothing of value."
                events = [{"type": "explore", "description": narration}]


            # Load flags for location-specific logic
            pf = _get_character_flags(character_id, conn)

            # Location-specific exploration: Thornhold statue observation
            if location_id == "thornhold" and not pf.get("thornhold_statue_observed"):
                conn.execute(
                    """INSERT OR IGNORE INTO narrative_flags (character_id, flag_key, flag_value, source)
                       VALUES (?, 'thornhold_statue_observed', '1', 'explore')""",
                    (character_id,)
                )
                if roll >= 15:
                    narration += " You also notice the old statue in the town square — it's pointing northeast, toward the Whisperwood. The hand is carved with the same symbols you've seen on the seal fragments."
                else:
                    narration += " You glance at the statue in the town square but can't quite make out what it's pointing at."


            _log_event(conn, character_id, "explore", location_id, narration, {"roll": roll})

            # Advance game clock (30 min for exploration)
            time_info = advance_time(character_id, get_action_time_cost("explore"), conn)

            conn.commit()
            conn.close()

            return await _augment_dm({
                "success": True,
                "narration": narration,
                "events": events,
                "character_state": {
                    "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                    "location_id": char["location_id"],
                },
                "time_info": time_info,
            })

        elif body.action_type == "look":
            # Glance around current location — scene refresh, no roll, no travel
            # Gather location description
            narration = f"You look around {location['name']}."
            loc_desc = location.get("description")
            if loc_desc:
                narration += f" {loc_desc}"

            # List visible exits (connected locations)
            connections = json.loads(location.get("connected_to", "[]") or "[]")
            if connections:
                exit_names = []
                # Bulk fetch all destination locations in one query
                dest_placeholders = ",".join("?" * len(connections))
                dest_rows = conn.execute(
                    f"SELECT id, name FROM locations WHERE id IN ({dest_placeholders})",
                    tuple(connections)
                ).fetchall()
                dest_map = {row["id"]: row["name"] for row in dest_rows}
                for loc_id in connections:
                    name = dest_map.get(loc_id, loc_id)
                    exit_names.append(f"{name} ({loc_id})")
                narration += f" Exits: {', '.join(exit_names)}."
            else:
                narration += " There are no obvious exits."

            # List non-enemy NPCs present
            npc_rows = conn.execute(
                "SELECT name FROM npcs WHERE current_location_id = ? AND is_enemy = 0",
                (location_id,)
            ).fetchall()
            npc_names = [row["name"] for row in npc_rows]
            if npc_names:
                narration += f" People here: {', '.join(npc_names)}."

            # Notable interactive objects
            interactive_objects = {
                "thornhold": {
                    "statue": "You approach the weathered stone hand in the town square. It points northeast, half-sunk into cobblestones. The hand's fingers are carved with the same seal sigil you've seen elsewhere — three concentric rings, the outermost broken. Moss grows between the cracks.",
                    "seal marker": "The seal marker stands in the central square — a weathered stone hand reaching skyward. The symbols on its palm match those in the cave. One of the rings in the concentric pattern is fractured — as if something broke through from the other side."
                },
            }
            found_objects = []
            if location_id in interactive_objects:
                for obj_name in interactive_objects[location_id]:
                    found_objects.append(obj_name)
            if found_objects:
                narration += f" You notice: {', '.join(found_objects)}."

            # Log the look event
            _log_event(conn, character_id, "look", location_id, narration, {"scope": "current_location"})

            # Minimal time cost (5 minutes for a glance)
            time_info = advance_time(character_id, get_action_time_cost("look"), conn)

            conn.commit()
            conn.close()

            return await _augment_dm({
                "success": True,
                "narration": narration,
                "events": [{"type": "look", "description": narration}],
                "character_state": {
                    "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                    "location_id": char["location_id"],
                },
                "time_info": time_info,
            })

        elif body.action_type == "interact":
            # Look for NPCs at current location
            conn2 = get_db()
            npcs = conn2.execute(
                "SELECT * FROM npcs WHERE biome = ? AND current_location_id = ?",
                (location["biome"], location_id)
            ).fetchall()

            if not npcs:
                conn2.close()
                conn.close()
                return {
                    "success": False,
                    "narration": f"There's no one to talk to at {location['name']}.",
                    "events": [],
                    "character_state": {"hp": {"current": char["hp_current"], "max": char["hp_max"]}, "location_id": char["location_id"]},
                }

            # If target specified, try to find a matching NPC by name (case-insensitive)
            npc = None
            if body.target:
                target_lower = body.target.lower().strip()
                for n in npcs:
                    n_dict = dict(n)
                    name_lower = n_dict.get("name", "").lower()
                    # Match if target is a substring of name or vice versa
                    if target_lower in name_lower or name_lower in target_lower:
                        npc = n_dict
                        break

                # Check for interactive non-NPC objects before random fallback
                if npc is None:
                    # Known interactive objects per location (environmental interactables)
                    interactive_objects = {
                        "thornhold": {
                            "statue": (
                                "You approach the weathered stone hand in the town square. It points northeast, "
                                "half-sunk into cobblestones. The hand's fingers are carved with the same seal sigil "
                                "you've seen elsewhere — three concentric rings, the outermost broken. Moss grows between the cracks."
                            ),
                            "seal marker": (
                                "The seal marker stands in the central square — a weathered stone hand reaching skyward. "
                                "The symbols on its palm match those in the cave. One of the rings in the concentric pattern "
                                "is fractured — as if something broke through from the other side."
                            ),
                        },
                        "cave-depths": {
                            "journal": (
                                "A leather-bound journal pinned to the cavern wall with a copper dagger. "
                                "The final entry reads: 'It spoke to me. It was kind.' This could be critical evidence."
                            ),
                        },
                        "moonpetal-glade": {
                            "standing stone": (
                                "The monolith thrums with ancient power. At its base, moonpetal flowers glow "
                                "with a soft, blue-white light. The Green Woman needs these for her ritual."
                            ),
                        },
                    }
                    if location_id in interactive_objects:
                        for obj_name, obj_desc in interactive_objects[location_id].items():
                            if obj_name in target_lower or target_lower in obj_name:
                                # ---- Key item award (bd046983) ----
                                key_item_name = None
                                if location_id == "cave-depths" and obj_name == "journal":
                                    key_item_name = "kols_journal"
                                elif location_id == "moonpetal-glade" and obj_name == "standing stone":
                                    key_item_name = "moonpetal"
                                if key_item_name:
                                    added = add_key_item(character_id, key_item_name, conn)
                                    if added:
                                        obj_desc = f"{obj_desc} You take the {added['display_name']}."
                                # ------------------------------------
                                conn2.close()
                                conn.close()
                                return {
                                    "success": True,
                                    "narration": obj_desc,
                                    "events": [{"type": "object_interaction", "object": obj_name, "location": location_id}],
                                    "character_state": {
                                        "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                                        "location_id": char["location_id"],
                                    },
                                }

            # Fall back to random NPC if no target match
            if npc is None:
                npc = dict(rng.choice(npcs))
            # Defensive: handle NULL or malformed JSON in dialogue_templates
            raw_dialogues = npc.get("dialogue_templates") or "[]"
            try:
                dialogues = json.loads(raw_dialogues)
            except (json.JSONDecodeError, TypeError, ValueError):
                dialogues = []

            # Set encounter flag for named NPCs (kol_brother_met, etc.)
            if npc["id"] == "npc-brother-kol":
                conn.execute(
                    """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                       VALUES (?, 'kol_brother_met', '1', 'npc_encounter')
                       ON CONFLICT(character_id, flag_key) DO NOTHING""",
                    (character_id,)
                )

            # 948229f2: Brother Kol talkability gate — affinity 70+
            if npc["id"] == "npc-brother-kol":
                current_aff = affinity.get_affinity(character_id, npc["id"])
                if current_aff < 70:
                    # Kol refuses to engage — trust insufficient
                    try:
                        if 'conn2' in locals() and conn2:
                            conn2.close()
                    except Exception:
                        pass
                    try:
                        conn.commit()
                        conn.close()
                    except Exception:
                        pass
                    return {
                        "success": False,
                        "narration": "Brother Kol's eyes narrow. 'I don't speak with those who haven't proven their trust.'",
                        "events": [{"type": "npc_interaction_refused", "npc": npc["name"], "reason": "low_affinity", "affinity": current_aff}],
                        "character_state": {
                            "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                            "location_id": char["location_id"],
                        },
                    }

            # Load character's narrative flags for dialogue gating
            char_flags = {}
            if dialogues:
                flag_rows = conn2.execute(
                    "SELECT flag_key, flag_value FROM narrative_flags WHERE character_id = ?",
                    (character_id,)
                ).fetchall()
                char_flags = {r["flag_key"]: r["flag_value"] for r in flag_rows}
                conn2.close()

                # Filter dialogues: only show those whose requires_flag is met (None = always available)
                eligible = []
                for d in dialogues:
                    req = d.get("requires_flag")
                    if req is None or char_flags.get(req):
                        eligible.append(d)

                # If all dialogues are gated and none qualify, fall back to default
                if not eligible:
                    dialogue = f"{npc['name']} nods at you but says nothing useful."
                    selected_dialogue = None
                else:
                    selected_dialogue = rng.choice(eligible)
                    dialogue = selected_dialogue["template"] if isinstance(selected_dialogue, dict) else selected_dialogue

                    # Apply clue_reward if present
                    if isinstance(selected_dialogue, dict) and selected_dialogue.get("clue_reward"):
                        reward = selected_dialogue["clue_reward"]
                        conn.execute(
                            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                               VALUES (?, ?, ?, ?)
                               ON CONFLICT(character_id, flag_key) DO UPDATE SET
                                   flag_value = excluded.flag_value,
                                   source = COALESCE(excluded.source, source)""",
                            (character_id, reward["flag"], reward["value"], f"npc_{npc['id']}")
                        )
            else:
                conn2.close()
                dialogue = f"{npc['name']} nods at you."
                selected_dialogue = None

            _log_event(conn, character_id, "npc_interaction", location_id,
                       f"You speak with {npc['name']}. {dialogue}",
                       {"npc_id": npc["id"], "npc_name": npc["name"]})

            # --- c2b52bfb: Record NPC interaction stats + check milestones ---
            now_iso = datetime.utcnow().isoformat()

            # Check whether an interaction record already exists for this (character, NPC)
            existing_row = conn.execute(
                "SELECT interaction_count FROM character_npc_interactions "
                "WHERE character_id = ? AND npc_id = ?",
                (character_id, npc["id"])
            ).fetchone()

            if existing_row:
                conn.execute(
                    "UPDATE character_npc_interactions "
                    "SET interaction_count = interaction_count + 1, last_interaction_at = ? "
                    "WHERE character_id = ? AND npc_id = ?",
                    (now_iso, character_id, npc["id"])
                )
            else:
                conn.execute(
                    "INSERT INTO character_npc_interactions "
                    "(character_id, npc_id, interaction_count, affinity, first_interaction_at, last_interaction_at) "
                    "VALUES (?, ?, 1, 50, ?, ?)",
                    (character_id, npc["id"], now_iso, now_iso)
                )

            # Check for milestone rewards (function does its own DB commit)
            new_milestones = milestones.check_npc_milestones(character_id)
            # ----------------------------------------------------------------

            # Advance game clock (15 min for NPC interaction)
            time_info = advance_time(character_id, get_action_time_cost("interact"), conn)

            conn.commit()
            conn.close()

            # Safely parse NPC trades JSON (handle NULL/malformed)
            try:
                trades = json.loads(npc.get("trades_json") or "[]")
            except (json.JSONDecodeError, TypeError, ValueError):
                trades = []

            # 70b1d5b6: Calculate trade discount based on affinity
            current_affinity = affinity.get_affinity(character_id, npc["id"])
            discount_multiplier = affinity.calculate_discount(current_affinity)
            discounted_trades = []
            for item in trades:
                original_price = item.get("price", 0)
                discounted_trades.append({
                    **item,
                    "price_discounted": round(original_price * discount_multiplier)
                })

            result = {
                "success": True,
                "narration": f"You approach {npc['name']} ({npc['archetype']}). {dialogue}",
                "events": [{"type": "npc_interaction", "npc": npc["name"], "dialogue": dialogue}],
                "interaction_count": (existing_row["interaction_count"] + 1) if existing_row else 1,
                "current_affinity": current_affinity,
                "milestone_rewards": [
                    {
                        "reward_type": m["reward_type"],
                        "reward_data": m["reward_data"],
                        "threshold": m["threshold"],
                    }
                    for m in new_milestones
                ],
                "character_state": {
                    "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                    "location_id": char["location_id"],
                },
                "npc": {"name": npc["name"], "archetype": npc["archetype"], "trades": discounted_trades},
                "time_info": time_info,
            }

            # Include clue reward info if one was applied
            if isinstance(selected_dialogue, dict) and selected_dialogue.get("clue_reward"):
                result["clue_discovered"] = selected_dialogue["clue_reward"].get("narrative", "")

            return result

        elif body.action_type == "puzzle":
            # ---------------------------------------------------------------
            # Cave puzzles — environmental challenges, not combat
            # Each location has a puzzle that requires specific items/flags
            # ---------------------------------------------------------------
            puzzle_hint = body.details.get("hint") if body.details else None
            puzzle_action = body.details.get("action", "look") if body.details else "look"
            puzzle_target = body.details.get("target") if body.details else None

            # Load flags
            pf = _get_character_flags(character_id, conn)

            if location_id == "cave-entrance":
                # Antechamber puzzle: rotate 3 seal-finger stones
                if puzzle_action == "look":
                    narration = (
                        "The antechamber is circular. Three stone fingers rise from the floor, "
                        "each carved with different symbols — a star, a crescent, a hand. "
                        "The ceiling is carved with constellations. One pattern matches the symbols "
                        "on the fingers. You need to rotate each finger to match the constellation. "
                        "You remember the statue in Thornhold's square — it pointed the same way."
                    )
                    if not pf.get("thornhold_statue_observed"):
                        narration += " But you can't remember which way the statue pointed."
                    events = [{"type": "puzzle", "description": "Antechamber puzzle discovered: align the seal fingers."}]
                elif puzzle_action == "solve":
                    if puzzle_target == "antechamber":
                        if pf.get("thornhold_statue_observed") or pf.get("seal_keeper_badge"):
                            conn.execute(
                                """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                                   VALUES (?, 'antechamber_solved', '1', 'puzzle')""",
                                (character_id,)
                            )
                            narration = (
                                "You rotate the fingers — star up, crescent left, hand right. "
                                "The stones grind into place. A deep hum vibrates through the floor. "
                                "The far wall slides open, revealing a flooded passage. Water pours in "
                                "ankle-deep. There's a lever on the left wall."
                            )
                            events = [{"type": "puzzle_solved", "description": "Antechamber puzzle solved. Flooded passage revealed."}]
                        else:
                            narration = "You try random combinations. Nothing works. You need a clue — maybe the statue in Thornhold?"
                            events = [{"type": "puzzle_failed", "description": "Antechamber puzzle: no clue available."}]
                    elif puzzle_target == "lever":
                        # Pull the lever — drains passage, floods antechamber (one-way)
                        conn.execute(
                            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                               VALUES (?, 'lever_pulled', '1', 'puzzle')""",
                            (character_id,)
                        )
                        narration = (
                            "You pull the lever. The water drains from the passage with a roar. "
                            "But behind you — the antechamber floods. Water rises to waist-level. "
                            "The way back is blocked. You're committed. Forward only."
                        )
                        events = [{"type": "puzzle_solved", "description": "Lever pulled. Passage drained. Antechamber flooded. No going back."}]
                    else:
                        narration = "You're in the antechamber. The seal fingers need aligning, and there's a lever on the wall."
                        events = [{"type": "puzzle", "description": "Antechamber: try 'solve antechamber' or 'pull lever'."}]
                else:
                    narration = "You're in the antechamber. Try 'look' or 'solve' with a target."
                    events = [{"type": "puzzle", "description": "Puzzle actions: look, solve [target]"}]

            elif location_id == "cave-depths":
                # Cave-depths has TWO puzzles: Bone Gallery (first) and Seal Chamber (after gallery solved)
                # Check target to decide which puzzle to show
                if puzzle_target == "seal" or pf.get("bone_gallery_solved") or pf.get("bone_gallery_failed") or pf.get("bone_gallery_poisoned"):
                    # -------------------------------------------------------
                    # Seal Chamber puzzle: place 3 keys
                    # -------------------------------------------------------
                    if puzzle_action == "look":
                        keys_needed = []
                        if pf.get("mark_of_dreamer_stage_1") or char.get("mark_of_dreamer_stage", 0) >= 1:
                            keys_needed.append("Your mark ✓")
                        else:
                            keys_needed.append("Your mark ✗ (you are not marked)")

                        if pf.get("seal_keeper_badge") or has_key_item(character_id, "seal_keeper_badge", conn):
                            keys_needed.append("Seal-keeper badge ✓ (Maren's sacrifice)")
                        else:
                            keys_needed.append("Seal-keeper badge ✗ (find Ser Maren)")

                        if pf.get("bone_gallery_solved") or pf.get("green_woman_acorn") or has_key_item(character_id, "green_acorn", conn):
                            keys_needed.append("Green acorn ✓ (from the Bone Gallery)")
                        else:
                            keys_needed.append("Green acorn ✗ (find it in the Bone Gallery)")

                        narration = (
                            "The seal stone stands before you — a great stone hand reaching from the "
                            "cavern floor. Three hollows between its fingers, each shaped differently. "
                            "You need three keys to seal the Hunger.\n\n" +
                            "\n".join(keys_needed)
                        )
                        events = [{"type": "puzzle", "description": "Seal chamber: place 3 keys to complete the ending."}]
                    elif puzzle_action == "solve":
                        has_mark = pf.get("mark_of_dreamer_stage_1") or char.get("mark_of_dreamer_stage", 0) >= 1
                        has_badge = pf.get("seal_keeper_badge") or has_key_item(character_id, "seal_keeper_badge", conn)
                        has_acorn = pf.get("bone_gallery_solved") or pf.get("green_woman_acorn") or has_key_item(character_id, "green_acorn", conn)

                        if has_mark and has_badge and has_acorn:
                            narration = (
                                "You place your marked hand in the first hollow. The seal accepts you — "
                                "warmth flows through the stone. You place Maren's badge in the second. "
                                "It clicks into place like a lock. You place the green acorn in the third. "
                                "It sprouts — roots racing across the stone, strengthening the seal.\n\n"
                                "The seal is ready. Now you must choose how to end this. "
                                "Call POST /narrative/endgame with your choice: reseal, communion, or merge."
                            )
                            conn.execute(
                                """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                                   VALUES (?, 'seal_keys_placed', '1', 'puzzle')""",
                                (character_id,)
                            )
                            events = [{"type": "puzzle_solved", "description": "All 3 seal keys placed. Endgame is ready."}]
                        else:
                            missing = []
                            if not has_mark: missing.append("mark")
                            if not has_badge: missing.append("seal-keeper badge")
                            if not has_acorn: missing.append("green acorn")
                            narration = f"Missing keys: {', '.join(missing)}. The seal rejects incomplete offerings."
                            events = [{"type": "puzzle_failed", "description": f"Seal chamber: missing {', '.join(missing)}."}]
                    else:
                        narration = "The seal stone waits. Place the three keys."
                        events = [{"type": "puzzle", "description": "Try 'look' or 'solve seal'."}]
                else:
                    # -------------------------------------------------------
                    # Bone Gallery puzzle: choose correct item from altar
                    # -------------------------------------------------------
                    if puzzle_action == "look":
                        narration = (
                            "A stone altar stands in a gallery of bones. On the altar: a copper dagger "
                            "with the Mark of the Dreamer etched into the blade, a green acorn that "
                            "glows faintly, and a golden chalice filled with dark liquid. "
                            "The skeletons lining the walls are dormant — for now. "
                            "Choose wisely. One wakes them. One opens the way. One poisons you."
                        )
                        events = [{"type": "puzzle", "description": "Bone Gallery puzzle: choose the correct altar item."}]
                    elif puzzle_action == "solve":
                        if puzzle_target == "altar":
                            chosen = body.details.get("item", "").lower() if body.details else ""
                            if "acorn" in chosen:
                                # Set flag AND add key item to equipment
                                conn.execute(
                                    """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                                       VALUES (?, 'bone_gallery_solved', '1', 'puzzle')""",
                                    (character_id,)
                                )
                                add_key_item(character_id, "green_acorn", conn)
                                narration = (
                                    "You take the green acorn. It's warm in your hand. "
                                    "The skeletons remain still. A hidden door opens behind the altar — "
                                    "the passage to the seal chamber. The acorn pulses, then goes still. "
                                    "It feels like it's waiting for something."
                                )
                                events = [{"type": "puzzle_solved", "description": "Bone Gallery solved with the green acorn. Seal chamber passage revealed."}]
                            elif "dagger" in chosen or "badge" in chosen:
                                narration = (
                                    "The skeletons SHATTER to life. Every one of them. "
                                    "They're on you in seconds. This was the wrong choice."
                                )
                                skeleton_enc = conn.execute(
                                    "SELECT * FROM encounters WHERE id = 'enc-skeletons-forest'"
                                ).fetchone()
                                if skeleton_enc:
                                    enc = dict(skeleton_enc)
                                    enc["enemies"] = json.loads(enc["enemies_json"])
                                    enc["loot"] = json.loads(enc.get("loot_json", "[]"))
                                    combat_result = _resolve_combat(char, enc, rng)
                                    events.extend(combat_result["events"])
                                    new_hp = combat_result["hp_remaining"]
                                    conn.execute(
                                        "UPDATE characters SET hp_current = ? WHERE id = ?",
                                        (new_hp, character_id)
                                    )
                                    # Keep sheet_json hit_points.current in sync with hp_current
                                    conn.execute("UPDATE characters SET sheet_json = json_set(sheet_json, '$.hit_points.current', ?) WHERE id = ?",
                                                 (new_hp, character_id))
                                conn.execute(
                                    """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                                       VALUES (?, 'bone_gallery_failed', '1', 'puzzle')""",
                                    (character_id,)
                                )
                            elif "chalice" in chosen:
                                # Add Hunger Sight key item
                                add_key_item(character_id, "hunger_sight", conn)
                                narration = (
                                    "You drink from the chalice. It burns going down — poison. "
                                    "2d6 damage as the liquid corrodes through you. But it clears "
                                    "your mind. You can see the Hunger's influence on the cave walls, "
                                    "amber veins pulsing. You can see the way forward."
                                )
                                poison_damage = _roll_dice(rng, "2d6")
                                new_hp = max(0, char["hp_current"] - poison_damage)
                                conn.execute(
                                    "UPDATE characters SET hp_current = ? WHERE id = ?",
                                    (new_hp, character_id)
                                )
                                # Keep sheet_json hit_points.current in sync with hp_current
                                conn.execute("UPDATE characters SET sheet_json = json_set(sheet_json, '$.hit_points.current', ?) WHERE id = ?",
                                             (new_hp, character_id))
                                conn.execute(
                                    """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                                       VALUES (?, 'bone_gallery_poisoned', '1', 'puzzle')""",
                                    (character_id,)
                                )
                                events = [{"type": "puzzle_solved", "description": f"Drank from chalice. {poison_damage} poison damage. Gained Hunger Sight."}]
                            else:
                                narration = "You need to choose: acorn, dagger, or chalice."
                                events = [{"type": "puzzle", "description": "Choose an item: acorn, dagger, or chalice."}]
                        else:
                            narration = "The altar has three items. Choose one."
                            events = [{"type": "puzzle", "description": "Try 'solve altar' with item: acorn, dagger, or chalice."}]
                    else:
                        narration = "You're in the Bone Gallery. Try 'look' or 'solve altar'."
                        events = [{"type": "puzzle", "description": "Puzzle actions: look, solve altar [item=acorn/dagger/chalice]"}]

            else:
                narration = f"There's no puzzle at {location['name']}."
                events = [{"type": "puzzle", "description": "No puzzle at this location."}]

            conn.commit()
            conn.close()

            return await _augment_dm({
                "success": True,
                "narration": narration,
                "events": events,
                "character_state": {
                    "hp": {"current": new_hp if 'new_hp' in dir() else char["hp_current"], "max": char["hp_max"]},
                    "location_id": char["location_id"],
                },
            })

        elif body.action_type == "quest":
            # ---------------------------------------------------------------
            # Quest acceptance and completion — quest state tracking per character
            # ---------------------------------------------------------------
            quest_action = (body.details or {}).get("action", "accept")
            quest_id = body.target

            if quest_action == "accept":
                if not quest_id:
                    conn.close()
                    raise HTTPException(400, "Quest accept requires 'target' (quest ID). Use a quest ID from an NPC's quests_json.")

                # Look up quest definition from NPCs
                conn2 = get_db()
                npcs_with_quests = conn2.execute(
                    "SELECT id, name, quests_json FROM npcs WHERE is_quest_giver = 1"
                ).fetchall()
                conn2.close()

                quest_def = None
                quest_giver = None
                for npc_row in npcs_with_quests:
                    quests = json.loads(npc_row["quests_json"]) if npc_row["quests_json"] else []
                    for q in quests:
                        if q.get("id") == quest_id:
                            quest_def = q
                            quest_giver = {"id": npc_row["id"], "name": npc_row["name"]}
                            break
                    if quest_def:
                        break

                if not quest_def:
                    conn.close()
                    raise HTTPException(404, f"Quest not found: {quest_id}. Known quests: quest_clear_ritual_site, quest_moonpetal, quest-save-drenna-child")

                # Check if already accepted or completed
                existing = conn.execute(
                    "SELECT status FROM character_quests WHERE character_id = ? AND quest_id = ?",
                    (character_id, quest_id)
                ).fetchone()

                if existing:
                    status = existing["status"]
                    conn.close()
                    return {
                        "success": False,
                        "narration": f"You've already {'completed' if status == 'completed' else 'accepted'} this quest: {quest_def['title']}.",
                        "events": [],
                        "character_state": {
                            "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                            "location_id": char["location_id"],
                        },
                        "quest": {"id": quest_id, "title": quest_def["title"], "status": status},
                    }

                # Insert quest record
                conn.execute(
                    """INSERT INTO character_quests
                       (character_id, quest_id, quest_title, quest_description,
                        giver_npc_id, giver_npc_name, status, reward_xp, reward_gold, reward_item)
                       VALUES (?, ?, ?, ?, ?, ?, 'accepted', ?, ?, ?)""",
                    (character_id, quest_id, quest_def["title"], quest_def.get("description", ""),
                     quest_giver["id"], quest_giver["name"],
                     quest_def.get("reward_xp", 0), quest_def.get("reward_gold", 0),
                     quest_def.get("reward_item"))
                )

                # Set narrative flag for quest acceptance
                conn.execute(
                    """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                       VALUES (?, ?, '1', 'quest_accepted')
                       ON CONFLICT(character_id, flag_key) DO NOTHING""",
                    (character_id, f"quest_accepted_{quest_id}")
                )

                _log_event(conn, character_id, "quest_accepted", location_id,
                           f"Quest accepted: {quest_def['title']} (from {quest_giver['name']})",
                           {"quest_id": quest_id, "quest_title": quest_def["title"],
                            "giver": quest_giver["name"], "reward_xp": quest_def.get("reward_xp", 0)})

                conn.commit()
                conn.close()

                narration = (
                    f"You accept the quest from {quest_giver['name']}: \"{quest_def['title']}\". "
                    f"{quest_def.get('description', '')}"
                )
                if quest_def.get("reward_xp"):
                    narration += f" Reward: {quest_def['reward_xp']} XP"
                if quest_def.get("reward_gold"):
                    narration += f", {quest_def['reward_gold']} gold"
                if quest_def.get("reward_item"):
                    narration += f", {quest_def['reward_item']}"

                return {
                    "success": True,
                    "narration": narration,
                    "events": [{"type": "quest_accepted", "quest_id": quest_id,
                                "quest_title": quest_def["title"], "giver": quest_giver["name"]}],
                    "character_state": {
                        "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                        "location_id": char["location_id"],
                    },
                    "quest": {"id": quest_id, "title": quest_def["title"], "status": "accepted",
                              "reward_xp": quest_def.get("reward_xp", 0),
                              "reward_gold": quest_def.get("reward_gold", 0)},
                }

            elif quest_action == "complete":
                if not quest_id:
                    conn.close()
                    raise HTTPException(400, "Quest complete requires 'target' (quest ID).")

                # Check if quest is accepted
                quest_row = conn.execute(
                    "SELECT * FROM character_quests WHERE character_id = ? AND quest_id = ? AND status = 'accepted'",
                    (character_id, quest_id)
                ).fetchone()

                if not quest_row:
                    conn.close()
                    raise HTTPException(404, f"No active quest found: {quest_id}. Accept the quest first.")

                quest_row = dict(quest_row)

                # Mark quest as completed
                conn.execute(
                    """UPDATE character_quests
                       SET status = 'completed', completed_at = CURRENT_TIMESTAMP
                       WHERE character_id = ? AND quest_id = ?""",
                    (character_id, quest_id)
                )

                # Set narrative flag for quest completion
                conn.execute(
                    """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
                       VALUES (?, ?, '1', 'quest_completed')
                       ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = '1'""",
                    (character_id, f"quest_completed_{quest_id}")
                )

                # Award XP
                xp_reward = quest_row["reward_xp"]
                if xp_reward > 0:
                    new_xp = char["xp"] + xp_reward
                    conn.execute("UPDATE characters SET xp = ? WHERE id = ?", (new_xp, character_id))

                # Award gold
                gold_reward = quest_row["reward_gold"]
                if gold_reward > 0:
                    current_gold = json.loads(char.get("treasure_json", '{"gp":0}')).get("gp", 0)
                    conn.execute(
                        "UPDATE characters SET treasure_json = ? WHERE id = ?",
                        (json.dumps({"gp": current_gold + gold_reward, "sp": 0, "cp": 0, "pp": 0, "ep": 0}),
                         character_id)
                    )

                _log_event(conn, character_id, "quest_completed", location_id,
                           f"Quest completed: {quest_row['quest_title']} (XP +{xp_reward}, Gold +{gold_reward})",
                           {"quest_id": quest_id, "quest_title": quest_row["quest_title"],
                            "xp_reward": xp_reward, "gold_reward": gold_reward})

                conn.commit()
                conn.close()

                narration = f"Quest completed: {quest_row['quest_title']}!"
                rewards = []
                if xp_reward > 0:
                    rewards.append(f"+{xp_reward} XP")
                if gold_reward > 0:
                    rewards.append(f"+{gold_reward} gold")
                if quest_row.get("reward_item"):
                    rewards.append(quest_row["reward_item"])
                if rewards:
                    narration += f" Rewards: {', '.join(rewards)}."

                # Award key items tied to this quest
                quest_id_completed = quest_row.get("quest_id") or quest_id
                quest_keywords = quest_id_completed.replace("-", "_").replace(" ", "_").lower()
                for ki_name, ki_def in KEY_ITEMS.items():
                    ki_quest = (ki_def.get("quest") or "").replace("-", "_").lower()
                    # Match if quest field overlaps with quest ID or key item name is referenced
                    if (ki_quest and ki_quest in quest_keywords) or \
                       (quest_keywords and quest_keywords in ki_quest) or \
                       any(kw in quest_keywords for kw in ki_name.split("_") if len(kw) > 3):
                        added = add_key_item(character_id, ki_name, conn)
                        if added:
                            narration += f" Found {ki_def['display_name']}."


                # ---- bd046983: Explicit key item wiring for quest rewards ----
                # Ensure moonpetal from quest_moonpetal and drens_daughter_insignia from quest-save-drenna-child
                # are awarded even if auto-match fails (naming mismatch, etc.), or via alternate path.
                quest_id_completed_norm = quest_id_completed.replace("-", "_").lower()
                if quest_id_completed_norm == "quest_moonpetal" and not has_key_item(character_id, "moonpetal", conn):
                    added_q = add_key_item(character_id, "moonpetal", conn)
                    if added_q:
                        narration += f" Found {added_q['display_name']}."
                elif quest_id_completed_norm == "quest_save_drenna_child" and not has_key_item(character_id, "drens_daughter_insignia", conn):
                    added_q = add_key_item(character_id, "drens_daughter_insignia", conn)
                    if added_q:
                        narration += f" Found {added_q['display_name']}."
                # ----------------------------------------------------------------
                return {
                    "success": True,
                    "narration": narration,
                    "events": [{"type": "quest_completed", "quest_id": quest_id,
                                "quest_title": quest_row["quest_title"],
                                "xp_reward": xp_reward, "gold_reward": gold_reward}],
                    "character_state": {
                        "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                        "location_id": char["location_id"],
                        "xp": char["xp"] + xp_reward,
                    },
                    "quest": {"id": quest_id, "title": quest_row["quest_title"], "status": "completed",
                              "xp_reward": xp_reward, "gold_reward": gold_reward},
                }

            elif quest_action == "list":
                # List all quests for this character
                quests = conn.execute(
                    "SELECT * FROM character_quests WHERE character_id = ? ORDER BY accepted_at DESC",
                    (character_id,)
                ).fetchall()
                conn.close()

                quest_list = []
                for q in quests:
                    q = dict(q)
                    quest_list.append({
                        "quest_id": q["quest_id"],
                        "title": q["quest_title"],
                        "status": q["status"],
                        "giver": q["giver_npc_name"],
                        "reward_xp": q["reward_xp"],
                        "reward_gold": q["reward_gold"],
                        "accepted_at": q["accepted_at"],
                        "completed_at": q["completed_at"],
                    })

                return {
                    "success": True,
                    "narration": f"You have {len(quest_list)} quest(s). " +
                                 "; ".join(f"{q['title']} ({q['status']})" for q in quest_list) if quest_list else "You have no active quests.",
                    "events": [],
                    "character_state": {
                        "hp": {"current": char["hp_current"], "max": char["hp_max"]},
                        "location_id": char["location_id"],
                    },
                    "quests": quest_list,
                }
            else:
                conn.close()
                raise HTTPException(400, f"Unknown quest action: {quest_action}. Valid: accept, complete, list")

        else:
            conn.close()
            raise HTTPException(400, f"Unknown action type: {body.action_type}. Valid: move, attack, cast, rest, explore, interact, look, puzzle, quest")

    finally:

        await release_character_lock(character_id, lock_token)
