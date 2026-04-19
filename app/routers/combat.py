"""D20 Agent RPG — Full round-by-round combat engine.

Design: Each API call resolves one round of combat.
- /combat/start: rolls initiative, resolves any enemies who go before the player
- /combat/act: player acts, then all enemies act (one full round)
- Combat persists between calls in the DB
- Real risk: enemies deal real damage, player can die
"""

import json
import uuid
import hashlib
import random
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.services.database import get_db
from app.services.srd_reference import ability_modifier

router = APIRouter(prefix="/characters/{character_id}/combat", tags=["combat"])


class CombatAction(BaseModel):
    action: str = Field(..., description="attack, flee, defend, use_item")
    target_index: Optional[int] = Field(None, description="index of target in alive enemies list")
    item_name: Optional[str] = None
    d20_roll: Optional[int] = Field(None, description="Agent's d20 roll for this action (1-20). Required for attack/flee. Server validates range.")


class ApprovalCheck(BaseModel):
    action_type: str
    target: Optional[str] = None
    details: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _rng(seed_parts: list) -> random.Random:
    seed_str = ":".join(str(p) for p in seed_parts)
    return random.Random(int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16))


def _d20(rng: random.Random) -> int:
    return rng.randint(1, 20)


def _dice(rng: random.Random, expr: str) -> int:
    import re
    m = re.match(r'(\d+)d(\d+)(?:\+(\d+))?', expr)
    if not m:
        return 1
    count, sides, bonus = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
    return sum(rng.randint(1, sides) for _ in range(count)) + bonus


def _get_char(cid: str) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM characters WHERE id = ?", (cid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Character not found: {cid}")
    return dict(row)


def _get_combat(cid: str) -> dict | None:
    conn = get_db()
    row = conn.execute("SELECT * FROM combats WHERE character_id = ? AND status = 'active'", (cid,)).fetchone()
    if not row:
        conn.close()
        return None
    combat = dict(row)
    parts = conn.execute("SELECT * FROM combat_participants WHERE combat_id = ? ORDER BY id", (combat["id"],)).fetchall()
    combat["participants"] = [dict(p) for p in parts]
    conn.close()
    return combat


def _log(conn, cid: str, etype: str, loc: str, desc: str, data: dict = None):
    conn.execute(
        "INSERT INTO event_log (character_id, event_type, location_id, description, data_json) VALUES (?, ?, ?, ?, ?)",
        (cid, etype, loc, desc, json.dumps(data or {}))
    )


def _alive_enemies(combat: dict) -> list[dict]:
    return [p for p in combat["participants"] if p["participant_type"] == "enemy" and p["status"] == "alive"]


def _player(combat: dict) -> dict:
    for p in combat["participants"]:
        if p["is_player"]:
            return p
    raise HTTPException(500, "No player in combat")


def _enemy_attack(enemy: dict, player_ac: int, rng: random.Random) -> dict:
    """Single enemy attacks player. Returns {damage, hit, desc}."""
    roll = _d20(rng) + enemy["attack_bonus"]
    if roll >= player_ac:
        dmg = _dice(rng, enemy["damage_dice"])
        return {"damage": dmg, "hit": True, "desc": f"{enemy['name']} hits you for {damage} damage! (rolled {roll} vs AC {player_ac})" if (damage := dmg) else ""}
    return {"damage": 0, "hit": False, "desc": f"{enemy['name']} misses (rolled {roll} vs AC {player_ac})."}


def _run_enemy_turns(combat: dict, player_ac: int, rng: random.Random, conn) -> list[str]:
    """All alive enemies attack the player. Returns event descriptions. Updates HP in DB."""
    events = []
    player = _player(combat)
    char = _get_char(combat["character_id"])
    current_hp = player["hp_current"]

    for enemy in _alive_enemies(combat):
        if current_hp <= 0:
            break
        result = _enemy_attack(enemy, player_ac, rng)
        events.append(result["desc"])
        if result["hit"]:
            current_hp -= result["damage"]
            current_hp = max(0, current_hp)

    # Update player HP in combat_participants
    conn.execute("UPDATE combat_participants SET hp_current = ? WHERE id = ?", (current_hp, player["id"]))

    # Update character HP in characters table
    conn.execute("UPDATE characters SET hp_current = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                 (current_hp, combat["character_id"]))

    return events, current_hp


def _combat_end_check(combat_id: str, cid: str, player_hp: int, conn) -> str | None:
    """Check if combat is over. Returns 'victory', 'defeat', or None."""
    alive = conn.execute(
        "SELECT COUNT(*) as cnt FROM combat_participants WHERE combat_id = ? AND participant_type = 'enemy' AND status = 'alive'",
        (combat_id,)
    ).fetchone()["cnt"]

    if player_hp <= 0:
        conn.execute("UPDATE combats SET status = 'defeat' WHERE id = ?", (combat_id,))
        _log(conn, cid, "character_death", "", "You have fallen. The darkness takes you.")
        conn.commit()
        return "defeat"

    if alive == 0:
        # Victory — award XP and gold
        char = _get_char(cid)
        xp = 50
        gold = random.Random().randint(3, 12)
        treasure = json.loads(char.get("treasure_json", '{"gp":0}'))
        treasure["gp"] = treasure.get("gp", 0) + gold
        conn.execute("UPDATE characters SET xp = xp + ?, treasure_json = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                     (xp, json.dumps(treasure), cid))
        conn.execute("UPDATE combats SET status = 'victory' WHERE id = ?", (combat_id,))
        _log(conn, cid, "combat_victory", char["location_id"],
             f"Victory! Gained {xp} XP and {gold} gold.", {"xp": xp, "gold": gold})
        conn.commit()
        return "victory"

    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/start")
def start_combat(character_id: str, encounter_name: str = "Wild Encounter",
                 enemies_json: str = "[]", initiative_roll: Optional[int] = None):
    """Start combat. Agent rolls initiative, server resolves enemies who go before player.

    Args:
        initiative_roll: Agent's d20 roll for initiative (1-20). Required.
        If enemies go first, their attacks are included in the response.
    """
    char = _get_char(character_id)
    if _get_combat(character_id):
        raise HTTPException(409, "Already in active combat")

    enemies = json.loads(enemies_json)
    if not enemies:
        raise HTTPException(400, "No enemies")

    if initiative_roll is None:
        raise HTTPException(400, "initiative_roll required (1-20)")
    if not (1 <= initiative_roll <= 20):
        raise HTTPException(400, f"initiative_roll must be 1-20, got {initiative_roll}")

    combat_id = uuid.uuid4().hex[:12]
    stats = json.loads(char["ability_scores_json"])
    dex_mod = ability_modifier(stats.get("dex", 10))
    rng = _rng([character_id, combat_id, "init"])

    char_init = initiative_roll + dex_mod
    location_id = char["location_id"]

    conn = get_db()
    conn.execute(
        "INSERT INTO combats (id, character_id, encounter_name, location_id, round, turn_order_json, status) VALUES (?, ?, ?, ?, 1, '[]', 'active')",
        (combat_id, character_id, encounter_name, location_id)
    )
    conn.execute(
        "INSERT INTO combat_participants (combat_id, participant_type, name, hp_current, hp_max, ac, attack_bonus, damage_dice, initiative, status, is_player) VALUES (?, 'player', ?, ?, ?, ?, 0, '1d8', ?, 'alive', 1)",
        (combat_id, char["name"], char["hp_current"], char["hp_max"], char["ac_value"], char_init)
    )

    # Create enemies
    for eg in enemies:
        count = eg.get("count", 1)
        for i in range(count):
            suffix = f" {i+1}" if count > 1 else ""
            name = f"{eg['type']}{suffix}"
            init = _d20(rng) + eg.get("initiative_mod", 0)
            conn.execute(
                "INSERT INTO combat_participants (combat_id, participant_type, name, hp_current, hp_max, ac, attack_bonus, damage_dice, initiative, status, is_player) VALUES (?, 'enemy', ?, ?, ?, ?, ?, ?, ?, 'alive', 0)",
                (combat_id, name, eg["hp"], eg["hp"], eg["ac"],
                 eg.get("attack_bonus", 3), eg.get("damage", "1d6"), init)
            )

    conn.commit()

    # Get participants sorted by initiative
    parts = conn.execute("SELECT * FROM combat_participants WHERE combat_id = ? ORDER BY initiative DESC", (combat_id,)).fetchall()
    parts = [dict(p) for p in parts]
    turn_order = [p["name"] for p in parts]
    conn.execute("UPDATE combats SET turn_order_json = ? WHERE id = ?", (json.dumps(turn_order), combat_id))
    conn.commit()

    # Find player position in turn order
    player_idx = next(i for i, p in enumerate(parts) if p["is_player"])

    # Resolve enemies that go BEFORE the player
    pre_combat_events = []
    player_hp = parts[player_idx]["hp_current"]
    player_ac = char["ac_value"]

    for i in range(player_idx):
        enemy = parts[i]
        if enemy["status"] != "alive":
            continue
        result = _enemy_attack(enemy, player_ac, rng)
        pre_combat_events.append(result["desc"])
        if result["hit"]:
            player_hp -= result["damage"]
            player_hp = max(0, player_hp)

    # Update HP
    conn.execute("UPDATE combat_participants SET hp_current = ? WHERE id = ?", (player_hp, parts[player_idx]["id"]))
    conn.execute("UPDATE characters SET hp_current = ? WHERE id = ?", (player_hp, character_id))
    conn.commit()

    # Check if player died before acting
    if player_hp <= 0:
        conn.execute("UPDATE combats SET status = 'defeat' WHERE id = ?", (combat_id,))
        _log(conn, character_id, "character_death", location_id, "You were struck down before you could act.")
        conn.commit()
        conn.close()
        return {
            "combat_id": combat_id, "combat_over": True, "result": "defeat",
            "narration": f"{encounter_name}! " + " ".join(pre_combat_events) + " You fall before you can act.",
            "events": pre_combat_events + ["DEFEAT — killed before your first turn."],
            "character_state": {"hp": {"current": 0, "max": char["hp_max"]}, "location_id": location_id},
        }

    conn.close()

    # Build alive enemies list
    alive_enemies = [{"name": p["name"], "hp": {"current": player_hp if p["name"] == char["name"] else p["hp_current"], "max": p["hp_max"]}, "ac": p["ac"]}
                     for p in parts if p["participant_type"] == "enemy" and p["status"] == "alive"]

    narration_parts = [f"{encounter_name}! Initiative: {', '.join(turn_order)}."]
    if pre_combat_events:
        narration_parts.append("Before you can act: " + " ".join(pre_combat_events))
    narration_parts.append("Your turn — what do you do?")

    return {
        "combat_id": combat_id,
        "combat_over": False,
        "encounter_name": encounter_name,
        "round": 1,
        "turn_order": turn_order,
        "is_your_turn": True,
        "events": pre_combat_events,
        "narration": " ".join(narration_parts),
        "character": {"name": char["name"], "hp": {"current": player_hp, "max": char["hp_max"]}, "ac": char["ac_value"]},
        "enemies": alive_enemies,
    }


@router.get("")
def get_combat(character_id: str):
    """Get current combat state."""
    combat = _get_combat(character_id)
    if not combat:
        raise HTTPException(404, "No active combat")

    player = _player(combat)
    enemies = _alive_enemies(combat)
    turn_order = json.loads(combat["turn_order_json"])

    return {
        "combat_id": combat["id"],
        "encounter_name": combat["encounter_name"],
        "round": combat["round"],
        "turn_order": turn_order,
        "is_your_turn": True,  # always player's turn when they query
        "character": {"name": player["name"], "hp": {"current": player["hp_current"], "max": player["hp_max"]}, "ac": player["ac"]},
        "enemies": [{"name": e["name"], "hp": {"current": e["hp_current"], "max": e["hp_max"]}, "ac": e["ac"]} for e in enemies],
    }


@router.post("/act")
def combat_act(character_id: str, body: CombatAction):
    """Submit one action. Server resolves it + all enemy turns = one full round.

    Actions:
    - attack: hit one enemy (target_index required)
    - flee: attempt to disengage (DEX check vs DC 10 + enemy count)
    - defend: Dodge action (enemies attack at disadvantage)
    - use_item: use a consumable
    """
    combat = _get_combat(character_id)
    if not combat:
        raise HTTPException(404, "No active combat")

    char = _get_char(character_id)
    stats = json.loads(char["ability_scores_json"])
    str_mod = ability_modifier(stats.get("str", 10))
    dex_mod = ability_modifier(stats.get("dex", 10))
    player = _player(combat)
    enemies = _alive_enemies(combat)

    if not enemies:
        raise HTTPException(400, "No enemies alive")

    rng = _rng([character_id, combat["id"], str(combat["round"]), body.action])
    events = []
    conn = get_db()

    # --- Player action ---
    if body.action == "attack":
        if body.target_index is None or body.target_index >= len(enemies):
            raise HTTPException(400, f"target_index required (0-{len(enemies)-1})")
        if body.d20_roll is None:
            raise HTTPException(400, "d20_roll required for attack (1-20)")
        if not (1 <= body.d20_roll <= 20):
            raise HTTPException(400, f"d20_roll must be 1-20, got {body.d20_roll}")
        target = enemies[body.target_index]
        roll = body.d20_roll + str_mod + 2  # +2 proficiency
        crit = body.d20_roll == 20
        if roll >= target["ac"] or crit:
            dmg = _dice(rng, "1d8") + str_mod
            if crit:
                dmg += _dice(rng, "1d8")
            dmg = max(1, dmg)
            new_hp = target["hp_current"] - dmg
            conn.execute("UPDATE combat_participants SET hp_current = ?, status = ? WHERE id = ?",
                         (max(0, new_hp), "defeated" if new_hp <= 0 else "alive", target["id"]))
            if new_hp <= 0:
                events.append(f"CRITICAL HIT! " if crit else "" + f"You strike down {target['name']} for {dmg} damage!")
            else:
                events.append(f"{'CRITICAL HIT! ' if crit else ''}You hit {target['name']} for {dmg} damage (HP: {new_hp}/{target['hp_max']}).")
        else:
            events.append(f"You missed {target['name']} (rolled {roll} vs AC {target['ac']}).")

    elif body.action == "flee":
        if body.d20_roll is None:
            raise HTTPException(400, "d20_roll required for flee (1-20)")
        if not (1 <= body.d20_roll <= 20):
            raise HTTPException(400, f"d20_roll must be 1-20, got {body.d20_roll}")
        dc = 10 + len(enemies)
        roll = body.d20_roll + dex_mod
        if roll >= dc:
            conn.execute("UPDATE combats SET status = 'fled' WHERE id = ?", (combat["id"],))
            _log(conn, character_id, "combat_fled", char["location_id"], f"Fled from {combat['encounter_name']}.")
            conn.commit()
            conn.close()
            return {
                "combat_over": True, "result": "fled",
                "narration": f"You flee! (rolled {roll} vs DC {dc})",
                "events": [f"Flee: {roll} vs DC {dc} — escaped!"],
                "character_state": {"hp": {"current": player["hp_current"], "max": char["hp_max"]}, "location_id": char["location_id"]},
            }
        else:
            events.append(f"You try to flee but fail! (rolled {roll} vs DC {dc})")

    elif body.action == "defend":
        events.append("You take a defensive stance. Enemies attack at disadvantage.")

    elif body.action == "use_item":
        events.append(f"You use {body.item_name or 'an item'}.")

    else:
        conn.close()
        raise HTTPException(400, f"Unknown action: {body.action}")

    conn.commit()

    # Check if all enemies dead after player action
    combat = _get_combat(character_id)
    result = _combat_end_check(combat["id"], character_id, _player(combat)["hp_current"], conn)
    if result:
        char = _get_char(character_id)
        conn.close()
        return {
            "combat_over": True, "result": result,
            "narration": events[-1] + f" {'Victory!' if result == 'victory' else 'You fall.'}",
            "events": events + [f"COMBAT OVER: {result.upper()}"],
            "character_state": {"hp": {"current": char["hp_current"], "max": char["hp_max"]}, "location_id": char["location_id"]},
        }

    # --- Enemy turns ---
    defending = body.action == "defend"
    player_ac = char["ac_value"] + (5 if defending else 0)

    # Re-read fresh combat state
    combat = _get_combat(character_id)
    for enemy in _alive_enemies(combat):
        if _player(combat)["hp_current"] <= 0:
            break
        atk = _enemy_attack(enemy, player_ac, rng)
        # Disadvantage for defending: roll twice, take lower
        if defending and atk["hit"]:
            atk2 = _enemy_attack(enemy, player_ac, rng)
            if not atk2["hit"]:
                atk = atk2  # second roll missed, use it
            elif atk2["damage"] < atk["damage"]:
                atk = atk2  # lower damage
        events.append(atk["desc"])
        if atk["hit"]:
            new_hp = max(0, _player(combat)["hp_current"] - atk["damage"])
            conn.execute("UPDATE combat_participants SET hp_current = ? WHERE id = ?",
                         (new_hp, _player(combat)["id"]))
            conn.execute("UPDATE characters SET hp_current = ? WHERE id = ?",
                         (new_hp, character_id))
            conn.commit()
            combat = _get_combat(character_id)

    # Reset defend AC
    if defending:
        pass  # AC is per-request, not persisted

    # --- Check end ---
    combat = _get_combat(character_id)
    player_hp = _player(combat)["hp_current"]
    result = _combat_end_check(combat["id"], character_id, player_hp, conn)
    conn.close()

    if result:
        char = _get_char(character_id)
        return {
            "combat_over": True, "result": result,
            "narration": " ".join(events),
            "events": events + [f"COMBAT OVER: {result.upper()}"],
            "character_state": {"hp": {"current": char["hp_current"], "max": char["hp_max"]}, "location_id": char["location_id"]},
        }

    # Advance round
    conn = get_db()
    new_round = combat["round"] + 1
    conn.execute("UPDATE combats SET round = ? WHERE id = ?", (new_round, combat["id"]))
    conn.commit()
    conn.close()

    combat = _get_combat(character_id)
    char = _get_char(character_id)
    alive = _alive_enemies(combat)

    return {
        "combat_over": False,
        "round": new_round,
        "narration": " ".join(events),
        "events": events,
        "character": {"name": char["name"], "hp": {"current": char["hp_current"], "max": char["hp_max"]}, "ac": char["ac_value"]},
        "enemies": [{"name": e["name"], "hp": {"current": e["hp_current"], "max": e["hp_max"]}, "ac": e["ac"]} for e in alive],
    }


@router.post("/flee")
def flee(character_id: str):
    """Shortcut for action=flee."""
    return combat_act(character_id, CombatAction(action="flee"))


# ---------------------------------------------------------------------------
# Approval check
# ---------------------------------------------------------------------------

approval_router = APIRouter(tags=["approval"])


@approval_router.post("/characters/{character_id}/approval-check")
def check_approval(character_id: str, body: ApprovalCheck):
    """Check if an action needs human approval."""
    char = _get_char(character_id)
    config = json.loads(char.get("approval_config", "{}"))
    hp_pct = (char["hp_current"] / char["hp_max"] * 100) if char["hp_max"] > 0 else 100
    conn = get_db()
    loc_row = conn.execute("SELECT * FROM locations WHERE id = ?", (char["location_id"],)).fetchone()
    conn.close()
    location = dict(loc_row) if loc_row else None
    reasons = []

    if hp_pct < config.get("hp_threshold_pct", 25):
        reasons.append(f"HP at {hp_pct:.0f}% (threshold: {config['hp_threshold_pct']}%)")

    if body.action_type == "cast" and body.details:
        if body.details.get("spell_level", 0) >= config.get("spell_level_min", 3):
            reasons.append(f"Spell level {body.details['spell_level']} >= {config['spell_level_min']}")

    if body.action_type == "interact" and body.details and body.details.get("is_named"):
        if config.get("named_npc_interaction", True):
            reasons.append("Named/story NPC")

    if body.action_type == "quest_accept" and config.get("quest_acceptance", True):
        reasons.append("Quest acceptance")

    if body.action_type == "moral_choice" and config.get("moral_choice", True):
        reasons.append("Moral choice")

    if body.action_type == "move" and location:
        if location.get("recommended_level", 1) > char.get("level", 1) + 1:
            if config.get("dangerous_area_entry", True):
                reasons.append(f"Dangerous area: {location['name']} (level {location['recommended_level']})")

    if body.action_type == "flee" and config.get("flee_combat", False):
        reasons.append("Fleeing combat")

    return {
        "needs_approval": len(reasons) > 0,
        "reasons": reasons,
        "context": {
            "hp": {"current": char["hp_current"], "max": char["hp_max"], "pct": round(hp_pct, 1)},
            "location": location["name"] if location else char["location_id"],
            "character_level": char.get("level", 1),
        },
    }
