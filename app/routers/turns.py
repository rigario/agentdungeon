"""D20 Agent RPG — Adventure Turn Engine (Transparent).

Every roll is logged. Every decision is explained. The agent sees everything
the server did — no hidden mechanics, no opaque decisions.

The turn result gives the agent:
1. dice_log — every single roll with context
2. decision_log — why the server made each choice
3. combat_log — round-by-round combat detail
4. events — chronological narrative events
5. narrative — suggested narration payload for the agent
6. asks — any decisions the agent/human needs to make
"""

import json
import uuid
import hashlib
import random
import datetime
import re
import sqlite3
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional
from app.services.database import get_db
from app.services.srd_reference import ability_modifier

router = APIRouter(prefix="/characters/{character_id}/turn", tags=["turns"])


# ---------------------------------------------------------------------------
# Transparent Dice Logger
# ---------------------------------------------------------------------------

class DiceLogger:
    """Wraps RNG and records every roll with full context.

    If d20_pool is provided by the agent, uses those values sequentially.
    Falls back to server-generated rolls when pool is exhausted.
    """

    def __init__(self, seed_parts: list, d20_pool: list[int] = None):
        seed_str = ":".join(str(p) for p in seed_parts)
        self.seed = int(hashlib.sha256(seed_str.encode()).hexdigest()[:8], 16)
        self.rng = random.Random(self.seed)
        self.log: list[dict] = []
        self._d20_pool = list(d20_pool) if d20_pool else []
        self._pool_index = 0

    def _consume_d20(self) -> tuple[int, bool]:
        """Get next d20 value. Returns (value, from_pool)."""
        if self._pool_index < len(self._d20_pool):
            val = self._d20_pool[self._pool_index]
            self._pool_index += 1
            if 1 <= val <= 20:
                return val, True
            # Invalid pool value — skip and generate
        return self.rng.randint(1, 20), False

    def roll_d20(self, context: str, modifier: int = 0) -> int:
        raw, from_pool = self._consume_d20()
        total = raw + modifier
        entry = {
            "type": "d20",
            "raw": raw,
            "modifier": modifier,
            "total": total,
            "crit": raw == 20,
            "fumble": raw == 1,
            "context": context,
            "from_pool": from_pool,
        }
        self.log.append(entry)
        return total

    def roll_dice(self, context: str, expr: str) -> int:
        m = re.match(r'(\d+)d(\d+)(?:\+(\d+))?(?:-(\d+))?', expr)
        if not m:
            self.log.append({"type": "dice", "expr": expr, "result": 1, "context": context})
            return 1
        count, sides = int(m.group(1)), int(m.group(2))
        plus = int(m.group(3) or 0)
        minus = int(m.group(4) or 0)
        rolls = [self.rng.randint(1, sides) for _ in range(count)]
        total = sum(rolls) + plus - minus
        entry = {
            "type": "dice",
            "expr": expr,
            "count": count,
            "sides": sides,
            "rolls": rolls,
            "modifier": plus - minus,
            "total": max(0, total),
            "context": context,
        }
        self.log.append(entry)
        return max(0, total)

    def choose(self, context: str, options: list) -> any:
        """Random choice with logging."""
        idx = self.rng.randint(0, len(options) - 1)
        chosen = options[idx]
        self.log.append({
            "type": "choice",
            "options_count": len(options),
            "chosen_index": idx,
            "chosen": str(chosen)[:100] if not isinstance(chosen, dict) else chosen.get("name", str(chosen)[:100]),
            "context": context,
        })
        return chosen

    def get_log(self) -> list[dict]:
        return list(self.log)

    def get_seed_hex(self) -> str:
        return hex(self.seed)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class TurnIntent(BaseModel):
    goal: str = Field(..., description="explore, travel, rest, farm, flee_to_safety")
    target: Optional[str] = Field(None, description="target location ID")
    stop_hp_pct: int = Field(50, description="stop if HP drops below this %")
    stop_on: list[str] = Field(
        default=["combat_end", "new_location", "named_npc", "quest", "level_up"],
        description="triggers: combat_end, new_location, named_npc, quest, level_up, item_found, danger"
    )
    auto_loot: bool = Field(True)
    auto_rest: bool = Field(False)
    max_encounters: int = Field(5)
    max_steps: int = Field(10)
    aggression: int = Field(50, description="0=cautious, 50=balanced, 100=aggressive")
    d20_pool: Optional[list[int]] = Field(
        None,
        description="Agent's pre-rolled d20 values. Server uses these sequentially for all d20 rolls (player attacks, enemy attacks, initiative, encounter checks, flee). Unused rolls returned. If pool runs out, server generates remaining rolls."
    )


class DiceLogEntry(BaseModel):
    type: str  # d20, dice, choice
    context: str
    raw: Optional[int] = None
    modifier: Optional[int] = None
    total: Optional[int] = None
    crit: Optional[bool] = None
    fumble: Optional[bool] = None
    expr: Optional[str] = None
    rolls: Optional[list[int]] = None


class DecisionLogEntry(BaseModel):
    step: int
    decision: str
    reasoning: str
    context: dict = {}


class CombatRoundLog(BaseModel):
    round: int
    turns: list[dict]  # each turn: {actor, action, roll, hit, damage, hp_after}


class TurnAsk(BaseModel):
    """Something the server is asking the agent/human to decide."""
    type: str  # level_up, allocate_stats, choose_spell, moral_choice, proceed_confirm
    description: str
    options: list[str] = []
    context: dict = {}


class TurnResult(BaseModel):
    """Full transparent result of an adventure turn."""
    turn_id: str
    status: str  # completed, waiting_for_input

    # Transparency — everything the server did
    dice_log: list[dict]          # every single roll
    decision_log: list[dict]      # why the server made each choice
    combat_log: list[dict]        # round-by-round combat detail
    rng_seed: str                 # hex seed for reproducibility

    # Chronological events
    events: list[dict]

    # State changes
    hp_start: int
    hp_end: int
    hp_max: int
    gold_start: int
    gold_end: int
    xp_start: int
    xp_end: int
    locations_visited: list[str]
    current_location: str
    encounters_fought: int
    in_game_time_passed: str

    # For the agent
    narrative: str                # suggested narration the agent can use/adapt
    asks: list[dict] = []         # decisions needed from agent/human
    decision_point: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_char(cid: str) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM characters WHERE id = ?", (cid,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Character not found: {cid}")
    return dict(row)


def _get_location(loc_id: str) -> dict:
    conn = get_db()
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (loc_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Location not found: {loc_id}")
    return dict(row)


def _get_locations() -> list[dict]:
    conn = get_db()
    rows = conn.execute("SELECT * FROM locations").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _find_path(start_id: str, end_id: str) -> list[str]:
    if start_id == end_id:
        return [start_id]
    locations = {l["id"]: l for l in _get_locations()}
    visited = set()
    queue = [(start_id, [start_id])]
    while queue:
        current, path = queue.pop(0)
        if current == end_id:
            return path
        if current in visited:
            continue
        visited.add(current)
        for neighbor in json.loads(locations[current].get("connected_to", "[]")):
            if neighbor not in visited and neighbor in locations:
                queue.append((neighbor, path + [neighbor]))
    return []


def _log_event(conn, cid: str, etype: str, loc: str, desc: str, data: dict = None):
    conn.execute(
        "INSERT INTO event_log (character_id, event_type, location_id, description, data_json) VALUES (?, ?, ?, ?, ?)",
        (cid, etype, loc, desc, json.dumps(data or {}))
    )


# ---------------------------------------------------------------------------
# World Context — Hallucination Guardrail
# ---------------------------------------------------------------------------

def _get_char_flags(character_id: str) -> set[str]:
    """Get set of flag keys that are set for this character."""
    conn = get_db()
    rows = conn.execute(
        "SELECT flag_key FROM narrative_flags WHERE character_id = ?", (character_id,)
    ).fetchall()
    conn.close()
    return {r[0] for r in rows}


def _filter_dialogue(templates: list[dict], flags: set[str]) -> list[dict]:
    """Return only dialogue templates whose requirements are met."""
    accessible = []
    for tpl in templates:
        req = tpl.get("requires_flag")
        if req is None or req in flags:
            filtered = {
                "context": tpl.get("context"),
                "template": tpl.get("template"),
            }
            if tpl.get("clue_reward"):
                filtered["clue_reward"] = tpl["clue_reward"]
            if tpl.get("quest"):
                filtered["quest"] = tpl["quest"]
            if tpl.get("quest_prerequisite"):
                filtered["quest_prerequisite"] = tpl["quest_prerequisite"]
            if tpl.get("quest_offer"):
                filtered["quest_offer"] = tpl["quest_offer"]
            accessible.append(filtered)
    return accessible


def _build_world_context(
    location_id: str, character_id: str
) -> dict:
    """
    Build the world context the agent is ALLOWED to describe.

    The agent receives ONLY items in this list.
    The agent MUST NOT invent additional NPCs, locations, items, or events
    that are not present here.
    """
    conn = get_db()

    # 1. Current location
    loc = dict(conn.execute(
        "SELECT * FROM locations WHERE id = ?", (location_id,)
    ).fetchone())

    # 2. Connected locations
    connected_ids = json.loads(loc.get("connected_to", "[]"))
    connected = []
    for cid in connected_ids:
        row = conn.execute(
            "SELECT id, name, description, hostility_level, recommended_level FROM locations WHERE id = ?", (cid,)
        ).fetchone()
        if row:
            connected.append(dict(row))

    # 3. NPCs at this biome
    flags = _get_char_flags(character_id)
    rows = conn.execute(
        "SELECT * FROM npcs WHERE biome = ?", (loc["biome"],)
    ).fetchall()

    npcs_present = []
    for npc in rows:
        npc = dict(npc)
        try:
            dialogue_templates = json.loads(npc.get("dialogue_templates", "[]"))
        except:
            dialogue_templates = []
        accessible_dialogue = _filter_dialogue(dialogue_templates, flags)

        npc_entry = {
            "id": npc["id"],
            "name": npc["name"],
            "archetype": npc["archetype"],
            "personality": npc["personality"],
            "dialogue": accessible_dialogue,
            "is_quest_giver": bool(npc.get("is_quest_giver")),
            "is_spirit": bool(npc.get("is_spirit")),
            "is_enemy": bool(npc.get("is_enemy")),
        }
        if npc.get("trades_json"):
            try:
                npc_entry["trades"] = json.loads(npc["trades_json"])
            except:
                pass
        if npc.get("quests_json"):
            try:
                quests = json.loads(npc["quests_json"])
                if quests:
                    npc_entry["quests"] = quests
            except:
                pass
        npcs_present.append(npc_entry)

    # 4. Encounters at this location
    rows = conn.execute(
        "SELECT * FROM encounters WHERE location_id = ?", (location_id,)
    ).fetchall()
    encounters_here = []
    for enc in rows:
        enc = dict(enc)
        enemies = json.loads(enc.get("enemies_json", "[]"))
        encounter_entry = {
            "id": enc["id"],
            "name": enc["name"],
            "description": enc.get("description", ""),
            "level_range": [enc["min_level"], enc["max_level"]],
            "enemies": [{"type": e.get("type"), "count": e.get("count", 1)} for e in enemies],
        }
        encounters_here.append(encounter_entry)

    # 5. Character's flags
    flag_values = {}
    rows = conn.execute(
        "SELECT flag_key, flag_value, source FROM narrative_flags WHERE character_id = ?",
        (character_id,)
    ).fetchall()
    for r in rows:
        flag_values[r[0]] = {"value": r[1], "source": r[2]}

    # 6. Fronts active (per-character: multi-tenancy)
    fronts = []
    rows = conn.execute(
        """SELECT f.id, f.name, COALESCE(cf.current_portent_index, 0) as portent_index,
                  COALESCE(cf.is_active, 1) as is_active
           FROM fronts f
           LEFT JOIN character_fronts cf ON cf.front_id = f.id AND cf.character_id = ?
           WHERE COALESCE(cf.is_active, 1) = 1""",
        (character_id,)
    ).fetchall()
    for f in rows:
        fronts.append({
            "id": f["id"],
            "name": f["name"],
            "current_portent_index": f["portent_index"],
            "is_active": bool(f["is_active"]),
        })

    # 7. Atmospheric overlay (mark + portent aware)
    from app.services.atmosphere import get_atmospheric_description

    char_data = conn.execute("SELECT mark_of_dreamer_stage FROM characters WHERE id = ?", (character_id,)).fetchone()
    mark_stage = dict(char_data)["mark_of_dreamer_stage"] if char_data else 0
    # Use the portent index already fetched from character_fronts above
    portent_index = fronts[0]["current_portent_index"] if fronts else 0

    atmosphere = get_atmospheric_description(location_id, mark_stage, portent_index)

    conn.close()

    return {
        "location": {
            "id": location_id,
            "name": loc["name"],
            "biome": loc["biome"],
            "description": loc["description"],
            "atmosphere": atmosphere,  # None if no overlay applies
            "hostility_level": loc.get("hostility_level", 3),
            "recommended_level": loc.get("recommended_level", 1),
            "mark_influence": mark_stage,  # 0-4, lets agent calibrate tone
            "front_portent": portent_index,  # 0-7, how far the doom has advanced
        },
        "connections": connected,
        "npcs": npcs_present,
        "encounters": encounters_here,
        "flags": flag_values,
        "fronts": fronts,
        "scope_contract": (
            "SCOPE CONTRACT — The agent MAY describe ONLY the items in this world_context. "
            "The agent MUST NOT invent additional NPCs, locations, items, or plot hooks "
            "not present in this list. The agent's job is to flesh out what exists, "
            "not to create new content."
        ),
    }


# ---------------------------------------------------------------------------
# Transparent Combat Engine
# ---------------------------------------------------------------------------

def _auto_combat(char: dict, encounter: dict, aggression: int, logger: DiceLogger) -> dict:
    """Server fights on player's behalf. Every roll is logged."""
    stats = json.loads(char["ability_scores_json"])
    str_mod = ability_modifier(stats.get("str", 10))
    dex_mod = ability_modifier(stats.get("dex", 10))
    ac = char["ac_value"]
    hp = char["hp_current"]
    max_hp = char["hp_max"]
    flee_threshold = int((100 - aggression) * 0.5)
    proficiency = 2  # level 1

    # Create enemies
    enemies = []
    for eg in encounter["enemies"]:
        for i in range(eg.get("count", 1)):
            suffix = f" {i+1}" if eg.get("count", 1) > 1 else ""
            enemies.append({
                "name": f"{eg['type']}{suffix}",
                "hp": eg["hp"], "max_hp": eg["hp"],
                "ac": eg["ac"],
                "attack_bonus": eg.get("attack_bonus", 3),
                "damage": eg.get("damage", "1d6"),
                "initiative_mod": eg.get("initiative_mod", 0),
            })

    # Initiative (logged)
    char_init = logger.roll_d20(f"Initiative ({char['name']})", modifier=dex_mod)
    for e in enemies:
        e["initiative"] = logger.roll_d20(f"Initiative ({e['name']})", modifier=e["initiative_mod"])

    turn_order = sorted(
        [{"name": char["name"], "init": char_init, "is_player": True}] +
        [{"name": e["name"], "init": e["initiative"], "is_player": False, "idx": i}
         for i, e in enumerate(enemies)],
        key=lambda x: x["init"], reverse=True
    )

    combat_rounds = []
    rounds = 0
    fled = False

    while hp > 0 and any(e["hp"] > 0 for e in enemies) and rounds < 20 and not fled:
        rounds += 1
        round_turns = []

        for turn in turn_order:
            if hp <= 0 or not any(e["hp"] > 0 for e in enemies) or fled:
                break

            if turn["is_player"]:
                # Check flee
                hp_pct = (hp / max_hp) * 100
                if hp_pct < flee_threshold and aggression < 80:
                    flee_roll = logger.roll_d20(f"Flee attempt ({char['name']})", modifier=dex_mod)
                    dc = 10 + len([e for e in enemies if e["hp"] > 0])
                    if flee_roll >= dc:
                        round_turns.append({
                            "actor": char["name"], "action": "flee",
                            "roll": flee_roll, "dc": dc, "success": True,
                            "hp_after": hp,
                            "reasoning": f"HP at {hp_pct:.0f}% < flee threshold {flee_threshold}%. Aggression={aggression}."
                        })
                        fled = True
                        break
                    else:
                        round_turns.append({
                            "actor": char["name"], "action": "flee",
                            "roll": flee_roll, "dc": dc, "success": False,
                            "hp_after": hp,
                            "reasoning": f"Flee failed: {flee_roll} < DC {dc}."
                        })

                # Attack
                target = next(e for e in enemies if e["hp"] > 0)
                attack_roll = logger.roll_d20(
                    f"Attack ({char['name']} → {target['name']})",
                    modifier=str_mod + proficiency
                )
                raw_roll = attack_roll - str_mod - proficiency
                crit = raw_roll == 20

                if attack_roll >= target["ac"] or crit:
                    damage_expr = "1d8"
                    if crit:
                        dmg1 = logger.roll_dice(f"Damage ({char['name']} → {target['name']}, base)", damage_expr)
                        dmg2 = logger.roll_dice(f"Damage ({char['name']} → {target['name']}, crit)", damage_expr)
                        total_dmg = max(1, dmg1 + dmg2 + str_mod)
                    else:
                        total_dmg = max(1, logger.roll_dice(f"Damage ({char['name']} → {target['name']})", damage_expr) + str_mod)

                    target["hp"] -= total_dmg
                    round_turns.append({
                        "actor": char["name"], "action": "attack",
                        "target": target["name"],
                        "attack_roll": attack_roll, "vs_ac": target["ac"], "hit": True, "crit": crit,
                        "damage": total_dmg,
                        "target_hp_after": max(0, target["hp"]),
                        "reasoning": f"{'CRIT! ' if crit else ''}Auto-attack nearest enemy (aggression={aggression})."
                    })
                else:
                    round_turns.append({
                        "actor": char["name"], "action": "attack",
                        "target": target["name"],
                        "attack_roll": attack_roll, "vs_ac": target["ac"], "hit": False,
                        "reasoning": f"Missed: {attack_roll} < AC {target['ac']}."
                    })
            else:
                # Enemy attack
                enemy = enemies[turn["idx"]]
                if enemy["hp"] <= 0:
                    continue
                attack_roll = logger.roll_d20(
                    f"Attack ({enemy['name']} → {char['name']})",
                    modifier=enemy["attack_bonus"]
                )
                if attack_roll >= ac:
                    dmg = logger.roll_dice(f"Damage ({enemy['name']} → {char['name']})", enemy["damage"])
                    hp -= dmg
                    hp = max(0, hp)
                    round_turns.append({
                        "actor": enemy["name"], "action": "attack",
                        "target": char["name"],
                        "attack_roll": attack_roll, "vs_ac": ac, "hit": True,
                        "damage": dmg,
                        "target_hp_after": hp,
                    })
                else:
                    round_turns.append({
                        "actor": enemy["name"], "action": "attack",
                        "target": char["name"],
                        "attack_roll": attack_roll, "vs_ac": ac, "hit": False,
                    })

        if round_turns:
            combat_rounds.append({"round": rounds, "turns": round_turns})

    victory = all(e["hp"] <= 0 for e in enemies) and not fled

    return {
        "encounter_name": encounter.get("name", "Unknown"),
        "hp_remaining": hp,
        "victory": victory,
        "fled": fled,
        "rounds": rounds,
        "enemies_defeated": len([e for e in enemies if e["hp"] <= 0]),
        "enemies_total": len(enemies),
        "combat_rounds": combat_rounds,
        "flee_threshold": flee_threshold,
    }


# ---------------------------------------------------------------------------
# Adventure Turn Simulation
# ---------------------------------------------------------------------------

def _simulate_turn(character_id: str, intent: TurnIntent) -> dict:
    """Simulate an adventure turn with full transparency."""
    char = _get_char(character_id)
    logger = DiceLogger([character_id, str(datetime.datetime.utcnow().timestamp())], d20_pool=intent.d20_pool)

    hp_start = char["hp_current"]
    max_hp = char["hp_max"]
    gold_start = json.loads(char.get("treasure_json", '{"gp": 0}')).get("gp", 0)
    xp_start = char["xp"]
    char_level = char.get("level", 1)
    current_loc_id = char["location_id"]

    events = []
    decision_log = []
    combat_log = []
    locations_visited = [current_loc_id]
    encounters_fought = 0
    total_steps = 0
    in_game_minutes = 0
    decision_point = None
    stopped = False
    step = 0

    # Path for travel
    path = []
    if intent.goal == "travel" and intent.target:
        path = _find_path(current_loc_id, intent.target)
        if not path:
            events.append({"type": "error", "step": step, "desc": f"No path to {intent.target}."})
            stopped = True
        else:
            decision_log.append({
                "step": step, "decision": f"Plan travel route",
                "reasoning": f"Path: {' → '.join(path)} ({len(path)-1} steps)",
                "context": {"path": path}
            })
            path = path[1:]

    # Main loop
    while not stopped and total_steps < intent.max_steps:
        step += 1

        # --- Pick next location ---
        if intent.goal == "travel" and path:
            next_loc_id = path.pop(0)
            decision_log.append({
                "step": step, "decision": f"Follow planned path to {next_loc_id}",
                "reasoning": f"Remaining path: {' → '.join(path) if path else '(arrived)'}"
            })
        elif intent.goal == "flee_to_safety":
            safe = [l for l in _get_locations() if l.get("hostility_level", 5) <= 1]
            current_loc = _get_location(current_loc_id)
            if safe and current_loc_id not in [l["id"] for l in safe]:
                nearest = min(safe, key=lambda l: len(_find_path(current_loc_id, l["id"])))
                remaining = _find_path(current_loc_id, nearest["id"])
                next_loc_id = remaining[1] if len(remaining) > 1 else current_loc_id
                decision_log.append({
                    "step": step, "decision": f"Flee toward {nearest['name']}",
                    "reasoning": f"Nearest safe location: {nearest['name']} ({len(remaining)-1} steps). HP={char['hp_current']}/{max_hp}."
                })
            else:
                decision_log.append({"step": step, "decision": "Already at safe location", "reasoning": "Stopping."})
                stopped = True
                continue
        elif intent.goal == "rest":
            safe = [l for l in _get_locations() if l.get("hostility_level", 5) <= 1]
            current_loc = _get_location(current_loc_id)
            nearest = min(safe, key=lambda l: len(_find_path(current_loc_id, l["id"]))) if safe else current_loc
            remaining = _find_path(current_loc_id, nearest["id"])
            if len(remaining) > 1:
                next_loc_id = remaining[1]
                decision_log.append({
                    "step": step, "decision": f"Head toward {nearest['name']} to rest",
                    "reasoning": f"HP={char['hp_current']}/{max_hp}. Need safe location to rest."
                })
            else:
                # Rest now
                heal_roll = logger.roll_dice("Short rest heal", "1d4")
                heal = max(1, max_hp // 4) + heal_roll
                new_hp = min(max_hp, char["hp_current"] + heal)
                conn = get_db()
                conn.execute("UPDATE characters SET hp_current = ? WHERE id = ?", (new_hp, character_id))
                _log_event(conn, character_id, "rest", current_loc_id, f"Rested. Healed {heal} HP.")
                conn.commit()
                conn.close()
                char["hp_current"] = new_hp
                events.append({
                    "type": "rest", "step": step,
                    "desc": f"Rested at {current_loc['name']}. Rolled 1d4={heal_roll}+base={heal}. HP: {char['hp_current']}/{max_hp}."
                })
                decision_log.append({
                    "step": step, "decision": "Rest at current location",
                    "reasoning": f"At safe location. Healing: 1d4={heal_roll} + base={max_hp//4} = {heal} HP."
                })
                in_game_minutes += 60
                stopped = True
                continue
        elif intent.goal == "farm":
            connected = json.loads(_get_location(current_loc_id).get("connected_to", "[]"))
            if not connected:
                stopped = True
                continue
            next_loc_id = logger.choose(f"Choose exploration direction from {current_loc_id}", connected)
            decision_log.append({
                "step": step, "decision": f"Random exploration → {next_loc_id}",
                "reasoning": f"Goal=farm. Randomly chose from connected locations: {connected}"
            })
        else:  # explore
            connected = json.loads(_get_location(current_loc_id).get("connected_to", "[]"))
            if not connected:
                stopped = True
                continue
            next_loc_id = logger.choose(f"Choose exploration direction from {current_loc_id}", connected)
            decision_log.append({
                "step": step, "decision": f"Random exploration → {next_loc_id}",
                "reasoning": f"Goal=explore. Randomly chose from: {connected}"
            })

        next_loc = _get_location(next_loc_id)
        total_steps += 1
        in_game_minutes += 30

        # --- Danger check ---
        if "danger" in intent.stop_on and next_loc.get("recommended_level", 1) > char_level + 1:
            events.append({
                "type": "danger", "step": step,
                "desc": f"DANGER: {next_loc['name']} is recommended for level {next_loc['recommended_level']}+. You are level {char_level}."
            })
            decision_point = {
                "type": "danger",
                "description": f"{next_loc['name']} (level {next_loc['recommended_level']}) is too dangerous for level {char_level}. Enter anyway?",
                "location": next_loc_id,
                "recommended_level": next_loc.get("recommended_level"),
                "your_level": char_level,
            }
            stopped = True
            break

        # --- Move ---
        is_new = next_loc_id not in locations_visited
        locations_visited.append(next_loc_id)
        current_loc_id = next_loc_id
        events.append({"type": "travel", "step": step, "desc": f"Traveled to {next_loc['name']}.", "location": next_loc_id})

        # Update DB
        conn = get_db()
        conn.execute("UPDATE characters SET location_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                     (current_loc_id, character_id))
        conn.commit()
        conn.close()

        # --- New location stop ---
        if is_new and "new_location" in intent.stop_on:
            events.append({"type": "new_location", "step": step, "desc": f"First visit to {next_loc['name']}!"})
            decision_point = {
                "type": "new_location",
                "description": f"You've reached {next_loc['name']} for the first time. {next_loc['description']}",
                "location": next_loc_id,
                "hostility": next_loc.get("hostility_level"),
                "recommended_level": next_loc.get("recommended_level"),
            }
            stopped = True
            break

        # --- Encounter check ---
        threshold = next_loc.get("encounter_threshold", 10)
        encounter_roll = logger.roll_d20(f"Encounter check ({next_loc['name']}, threshold={threshold})")

        if encounter_roll < threshold:
            # Encounter!
            conn = get_db()
            available = conn.execute(
                "SELECT * FROM encounters WHERE location_id = ? AND min_level <= ? AND max_level >= ?",
                (next_loc_id, char_level, char_level)
            ).fetchall()
            conn.close()

            if available:
                encounter = dict(logger.choose(f"Select encounter at {next_loc_id}", [dict(e) for e in available]))
                encounter["enemies"] = json.loads(encounter["enemies_json"])
                encounters_fought += 1

                events.append({
                    "type": "encounter", "step": step,
                    "desc": f"ENCOUNTER: {encounter.get('name', 'Unknown')}! (rolled {encounter_roll} < threshold {threshold})",
                    "encounter": encounter.get("name"),
                    "roll": encounter_roll,
                    "threshold": threshold,
                })

                # Auto-combat
                combat_result = _auto_combat(char, encounter, intent.aggression, logger)
                combat_log.append(combat_result)

                # Update HP
                char["hp_current"] = combat_result["hp_remaining"]
                conn = get_db()
                conn.execute("UPDATE characters SET hp_current = ? WHERE id = ?",
                             (combat_result["hp_remaining"], character_id))
                conn.commit()
                conn.close()

                if combat_result["victory"]:
                    events.append({
                        "type": "combat_victory", "step": step,
                        "desc": f"VICTORY in {combat_result['rounds']} rounds! Defeated {combat_result['enemies_defeated']}/{combat_result['enemies_total']} enemies. HP: {combat_result['hp_remaining']}/{max_hp}."
                    })
                    # Loot
                    if intent.auto_loot:
                        gold_roll = logger.roll_dice("Loot gold", f"1d6")
                        gold = gold_roll * encounters_fought
                        treasure = json.loads(char.get("treasure_json", '{"gp":0}'))
                        treasure["gp"] = treasure.get("gp", 0) + gold
                        xp = combat_result["enemies_defeated"] * 25
                        conn = get_db()
                        conn.execute("UPDATE characters SET treasure_json = ?, xp = xp + ? WHERE id = ?",
                                     (json.dumps(treasure), xp, character_id))
                        conn.commit()
                        conn.close()
                        char["treasure_json"] = json.dumps(treasure)
                        events.append({
                            "type": "loot", "step": step,
                            "desc": f"Looted: 1d6={gold_roll} × {encounters_fought} encounters = {gold} gold. XP gained: {xp}."
                        })

                elif combat_result["fled"]:
                    events.append({
                        "type": "combat_fled", "step": step,
                        "desc": f"FLED after {combat_result['rounds']} rounds. HP: {combat_result['hp_remaining']}/{max_hp}."
                    })

                else:  # defeat
                    events.append({
                        "type": "combat_defeat", "step": step,
                        "desc": f"DEFEATED by {encounter.get('name', 'enemies')}. HP: 0/{max_hp}."
                    })
                    decision_point = {
                        "type": "defeat",
                        "description": f"You have fallen at {next_loc['name']}.",
                        "location": next_loc_id,
                    }
                    stopped = True
                    break

                # Combat end stop
                if "combat_end" in intent.stop_on:
                    decision_point = {
                        "type": "combat_end",
                        "description": f"Combat over. HP: {char['hp_current']}/{max_hp}. Continue?",
                        "combat_summary": {
                            "encounter": combat_result["encounter_name"],
                            "rounds": combat_result["rounds"],
                            "victory": combat_result["victory"],
                            "hp_remaining": combat_result["hp_remaining"],
                        },
                    }
                    stopped = True
                    break

                # Max encounters
                if encounters_fought >= intent.max_encounters:
                    events.append({"type": "max_encounters", "step": step, "desc": f"Max encounters ({intent.max_encounters}) reached."})
                    stopped = True
                    break
        else:
            events.append({
                "type": "safe_passage", "step": step,
                "desc": f"Safe passage through {next_loc['name']}. (rolled {encounter_roll} ≥ threshold {threshold})"
            })

        # --- HP threshold ---
        hp_pct = (char["hp_current"] / max_hp) * 100 if max_hp > 0 else 0
        if hp_pct < intent.stop_hp_pct:
            events.append({
                "type": "hp_low", "step": step,
                "desc": f"HP at {char['hp_current']}/{max_hp} ({hp_pct:.0f}%) — below {intent.stop_hp_pct}% threshold."
            })
            decision_point = {
                "type": "hp_threshold",
                "description": f"HP at {char['hp_current']}/{max_hp} ({hp_pct:.0f}%). Below your {intent.stop_hp_pct}% stop threshold.",
                "hp": {"current": char["hp_current"], "max": max_hp, "pct": round(hp_pct, 1)},
                "location": current_loc_id,
            }
            stopped = True
            break

        # --- Target reached ---
        if intent.goal == "travel" and intent.target and current_loc_id == intent.target:
            events.append({"type": "arrived", "step": step, "desc": f"Arrived at {next_loc['name']}!"})
            decision_point = {
                "type": "arrived",
                "description": f"Reached {next_loc['name']}. {next_loc['description']}",
                "location": current_loc_id,
            }
            stopped = True
            break

    # --- Build final result ---
    char_final = _get_char(character_id)
    hp_end = char_final["hp_current"]
    gold_end = json.loads(char_final.get("treasure_json", '{"gp": 0}')).get("gp", 0)
    xp_end = char_final["xp"]

    hours = in_game_minutes // 60
    mins = in_game_minutes % 60
    time_str = f"{hours}h {mins}m" if hours else f"{mins}m"

    # Build narrative payload
    narrative_parts = []
    for ev in events:
        narrative_parts.append(ev["desc"])
    narrative = " ".join(narrative_parts)

    # Build asks
    asks = []
    if decision_point:
        if decision_point["type"] == "hp_threshold":
            asks.append({
                "type": "proceed_choice",
                "description": f"HP at {hp_end}/{max_hp}. Continue, rest, or retreat?",
                "options": ["push_on", "rest_here", "retreat_to_safety"],
            })
        elif decision_point["type"] == "danger":
            asks.append({
                "type": "enter_danger",
                "description": decision_point["description"],
                "options": ["enter", "avoid"],
            })
        elif decision_point["type"] == "combat_end":
            asks.append({
                "type": "continue_exploring",
                "description": f"Combat over. HP: {hp_end}/{max_hp}. Continue?",
                "options": ["continue", "rest", "return_to_town"],
            })
        elif decision_point["type"] == "new_location":
            asks.append({
                "type": "explore_new",
                "description": decision_point["description"],
                "options": ["explore", "move_on"],
            })
        elif decision_point["type"] == "defeat":
            asks.append({
                "type": "death",
                "description": "You have fallen.",
                "options": [],
            })

    # Build world context (hallucination guardrail)
    world_context = _build_world_context(current_loc_id, character_id)

    # Build character spell and action context
    char_spells = json.loads(char.get("spells_json", "[]"))
    char_slots = json.loads(char.get("spell_slots_json", "{}"))
    char_class = char.get("class", "")

    # Auto-assign starting spells if needed (same logic as cast handler)
    if not char_spells and (char_slots or char_class in ("Bard", "Cleric", "Druid", "Sorcerer", "Warlock", "Wizard", "Paladin", "Ranger")):
        from app.services.srd_reference import get_spells as _get_spells_for_turn
        import random as _ran
        _all_sp = _get_spells_for_turn()
        _class_cantrips = [s for s in _all_sp if s["level"] == 0 and any(c.get("name") == char_class for c in s.get("classes", []))]
        _class_l1 = [s for s in _all_sp if s["level"] == 1 and any(c.get("name") == char_class for c in s.get("classes", []))]
        char_spells = sorted([s["name"] for s in _ran.sample(_class_cantrips, min(3, len(_class_cantrips)))]) + sorted([s["name"] for s in _class_l1])

    spell_context = {
        "known_spells": char_spells,
        "spell_slots": char_slots,
        "is_caster": bool(char_slots or char_class in ("Bard", "Cleric", "Druid", "Sorcerer", "Warlock", "Wizard")),
    }

    available_actions = ["move", "attack", "rest", "explore", "interact", "puzzle"]
    if char_spells or char_slots:
        available_actions.append("cast")

    # Remaining d20 pool
    remaining_pool = logger._d20_pool[logger._pool_index:] if logger._pool_index < len(logger._d20_pool) else []

    return {
        "turn_id": uuid.uuid4().hex[:12],
        "status": "waiting_for_input" if decision_point else "completed",
        "dice_log": logger.get_log(),
        "decision_log": decision_log,
        "combat_log": combat_log,
        "rng_seed": logger.get_seed_hex(),
        "events": events,
        "narrative": narrative,
        "asks": asks,
        "hp_start": hp_start,
        "hp_end": hp_end,
        "hp_max": max_hp,
        "gold_start": gold_start,
        "gold_end": gold_end,
        "xp_start": xp_start,
        "xp_end": xp_end,
        "locations_visited": list(set(locations_visited)),
        "current_location": current_loc_id,
        "encounters_fought": encounters_fought,
        "in_game_time_passed": time_str,
        "decision_point": decision_point,
        "world_context": world_context,
        "spell_context": spell_context,
        "available_actions": available_actions,
        "remaining_d20_pool": remaining_pool,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/start")
def start_turn(character_id: str, body: TurnIntent):
    """Submit a turn intent. Server simulates with full transparency."""
    conn = get_db()
    active_combat = conn.execute(
        "SELECT id FROM combats WHERE character_id = ? AND status = 'active'", (character_id,)
    ).fetchone()
    conn.close()
    if active_combat:
        raise HTTPException(409, "Character is in active combat. Finish or flee first.")

    result = _simulate_turn(character_id, body)

    conn = get_db()
    conn.execute(
        """INSERT OR REPLACE INTO turn_results (turn_id, character_id, intent_json, result_json, status, created_at)
           VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)""",
        (result["turn_id"], character_id, json.dumps(body.model_dump()), json.dumps(result), result["status"])
    )
    conn.commit()
    conn.close()

    return result


@router.get("/result/{turn_id}")
def get_turn_result(character_id: str, turn_id: str):
    """Pull a specific turn result."""
    conn = get_db()
    row = conn.execute("SELECT * FROM turn_results WHERE turn_id = ? AND character_id = ?", (turn_id, character_id)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Turn not found: {turn_id}")
    return json.loads(dict(row)["result_json"])


@router.get("/latest")
def get_latest_turn(character_id: str):
    """Pull most recent turn result."""
    conn = get_db()
    row = conn.execute("SELECT * FROM turn_results WHERE character_id = ? ORDER BY created_at DESC LIMIT 1", (character_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "No turns found")
    d = dict(row)
    return {"turn_id": d["turn_id"], "intent": json.loads(d["intent_json"]), **json.loads(d["result_json"])}
