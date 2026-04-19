"""D20 Agent RPG — Narrative engine: fronts, flags, and mark progression.

Provides endpoints for:
- GET  /narrative/fronts           — list active fronts
- GET  /narrative/fronts/{id}      — front detail with current portent
- POST /narrative/advance          — advance a front's portent (called by server cron)
- GET  /narrative/flags/{char_id}  — get all narrative flags for a character
- POST /narrative/flags            — set a narrative flag
- GET  /narrative/mark/{char_id}   — get mark of dreamer stage for a character
- POST /narrative/mark/{char_id}   — advance mark stage (auto-called by encounter resolution)
- GET  /narrative/del-roll/{char_id} — roll Del ghost visit (uses seeded D20)
"""

import hashlib
import random
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.database import get_db

router = APIRouter(prefix="/narrative", tags=["narrative"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class NarrativeFlagSet(BaseModel):
    character_id: str
    flag_key: str
    flag_value: str = "1"
    source: str | None = None


class MarkAdvance(BaseModel):
    character_id: str
    stage: int  # 0-4


class AdvanceFront(BaseModel):
    front_id: str
    character_id: str  # Multi-tenancy: front state is per-character


# ---------------------------------------------------------------------------
# Fronts
# ---------------------------------------------------------------------------

@router.get("/fronts")
def list_fronts(character_id: str = None):
    """List active fronts. If character_id provided, returns per-character state.
    Without character_id, returns global front templates (for admin/debug)."""
    conn = get_db()
    if character_id:
        # Per-character: join character_fronts with fronts template
        rows = conn.execute(
            """SELECT f.id, f.name, f.danger_type, cf.current_portent_index, cf.is_active, cf.advanced_at
               FROM fronts f
               LEFT JOIN character_fronts cf ON cf.front_id = f.id AND cf.character_id = ?
               WHERE COALESCE(cf.is_active, 1) = 1""",
            (character_id,)
        ).fetchall()
        conn.close()
        return [{"id": r["id"], "name": r["name"], "danger_type": r["danger_type"],
                 "current_portent_index": r["current_portent_index"] or 0,
                 "is_active": bool(r["is_active"] if r["is_active"] is not None else 1),
                 "advanced_at": r["advanced_at"]}
                for r in rows]
    else:
        # Global templates (backward compat / debug)
        rows = conn.execute(
            "SELECT id, name, danger_type, current_portent_index, is_active, advanced_at "
            "FROM fronts WHERE is_active = 1"
        ).fetchall()
        conn.close()
        return [{"id": r["id"], "name": r["name"], "danger_type": r["danger_type"],
                 "current_portent_index": r["current_portent_index"],
                 "is_active": bool(r["is_active"]), "advanced_at": r["advanced_at"]}
                for r in rows]


@router.get("/fronts/{front_id}")
def get_front(front_id: str, character_id: str = None):
    """Get full front detail including grim portents.
    If character_id provided, uses per-character front state (multi-tenancy)."""
    conn = get_db()
    row = conn.execute("SELECT * FROM fronts WHERE id = ?", (front_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Front not found: {front_id}")

    import json as _json
    portents = _json.loads(row["grim_portents_json"])
    stakes = _json.loads(row["stakes_json"])

    # Use per-character portent index if character_id provided
    if character_id:
        from app.services.database import get_character_front
        cf = get_character_front(character_id, front_id)
        current_idx = cf["current_portent_index"] if cf else 0
        is_active = bool(cf["is_active"]) if cf else True
        advanced_at = cf.get("advanced_at") if cf else row.get("advanced_at")
    else:
        current_idx = row["current_portent_index"]
        is_active = bool(row["is_active"])
        advanced_at = row["advanced_at"]

    # Mark the current and past portents
    for p in portents:
        if p["index"] < current_idx:
            p["status"] = "fired"
        elif p["index"] == current_idx:
            p["status"] = "current"
        else:
            p["status"] = "pending"

    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "danger_type": row["danger_type"],
        "current_portent_index": current_idx,
        "impending_doom": row["impending_doom"],
        "grim_portents": portents,
        "stakes": stakes,
        "is_active": is_active,
        "advanced_at": advanced_at,
    }


@router.post("/advance")
def advance_front(payload: AdvanceFront):
    """Advance a front to its next grim portent (per-character: multi-tenancy).
    
    Called by the server's cron job (typically every 2 in-game days).
    Returns the new current portent. When all portents fire, the front's
    impending doom is marked as triggered.
    """
    import json as _json
    from app.services.database import init_character_fronts

    conn = get_db()

    # Ensure per-character front state exists
    init_character_fronts(payload.character_id, conn)

    # Get the global front template
    front = conn.execute(
        "SELECT * FROM fronts WHERE id = ?", (payload.front_id,)
    ).fetchone()
    if not front:
        conn.close()
        raise HTTPException(404, f"Front not found: {payload.front_id}")

    # Get per-character front state
    cf = conn.execute(
        "SELECT * FROM character_fronts WHERE character_id = ? AND front_id = ?",
        (payload.character_id, payload.front_id)
    ).fetchone()

    if not cf or not cf["is_active"]:
        conn.close()
        raise HTTPException(400, f"Front {payload.front_id} is not active for character {payload.character_id}")

    portents = _json.loads(front["grim_portents_json"])
    next_idx = cf["current_portent_index"] + 1

    if next_idx >= len(portents):
        # All portents exhausted — doom is triggered (per-character)
        conn.execute(
            """UPDATE character_fronts SET current_portent_index = ?, is_active = 0, advanced_at = ?
               WHERE character_id = ? AND front_id = ?""",
            (next_idx, datetime.utcnow().isoformat(), payload.character_id, payload.front_id)
        )
        conn.commit()
        conn.close()
        return {
            "front_id": payload.front_id,
            "character_id": payload.character_id,
            "status": "doom_triggered",
            "impending_doom": front["impending_doom"],
        }

    # Advance to next portent (per-character)
    conn.execute(
        """UPDATE character_fronts SET current_portent_index = ?, advanced_at = ?
           WHERE character_id = ? AND front_id = ?""",
        (next_idx, datetime.utcnow().isoformat(), payload.character_id, payload.front_id)
    )
    conn.commit()
    conn.close()

    new_portent = portents[next_idx]
    return {
        "front_id": payload.front_id,
        "character_id": payload.character_id,
        "new_portent_index": next_idx,
        "new_portent_text": new_portent["text"],
        "mark_stage_advance": new_portent.get("mark_stage_advance", 0),
        "narrative_flag": new_portent.get("narrative_flag"),
    }


# ---------------------------------------------------------------------------
# Narrative Flags
# ---------------------------------------------------------------------------

@router.get("/flags/{character_id}")
def get_flags(character_id: str):
    """Get all narrative flags for a character."""
    conn = get_db()
    rows = conn.execute(
        "SELECT flag_key, flag_value, source, set_at FROM narrative_flags "
        "WHERE character_id = ? ORDER BY set_at",
        (character_id,)
    ).fetchall()
    conn.close()
    return {r["flag_key"]: r["flag_value"] for r in rows}


@router.post("/flags")
def set_flag(payload: NarrativeFlagSet):
    """Set a narrative flag for a character. Upserts."""
    conn = get_db()
    conn.execute(
        """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(character_id, flag_key) DO UPDATE SET
               flag_value = excluded.flag_value,
               source = COALESCE(excluded.source, source)""",
        (payload.character_id, payload.flag_key, payload.flag_value, payload.source)
    )
    conn.commit()
    conn.close()
    return {"character_id": payload.character_id, "flag_key": payload.flag_key,
            "flag_value": payload.flag_value}


# ---------------------------------------------------------------------------
# Mark of the Dreamer
# ---------------------------------------------------------------------------

@router.get("/mark/{character_id}")
def get_mark_stage(character_id: str):
    """Get the current mark stage for a character (0 = unmarked, 4 = cured)."""
    conn = get_db()
    row = conn.execute(
        "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?", (character_id,)
    ).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, f"Character not found: {character_id}")

    stage = row["mark_of_dreamer_stage"]
    stage_descriptions = {
        0: "Unmarked. The Hunger does not know your name.",
        1: "Minor mark. Vivid dreams, cold spots, the faint sense of another "
           "awareness at the edge of thought. DC 10 WIS save on long rest or no HP recovery. "
           "The dreams are not all unpleasant.",
        2: "Moderate mark. Animals avoid you. The Green Woman recognizes it. "
           "DC 12 WIS save. -1 to CHA checks with those who notice the mark. "
           "The whispers carry meaning — not always clear, not always wrong.",
        3: "Severe mark. The Hunger speaks directly. DC 14 WIS save. "
           "Approval gate fires if the agent acts on the whispers. "
           "It is hard to tell where your thoughts end and its begin.",
        4: "Cured. The mark is suppressed by the Green Woman's ritual. "
           "It will return in 14 days unless the seal is repaired or the Hunger is answered.",
    }
    return {
        "character_id": character_id,
        "stage": stage,
        "description": stage_descriptions.get(stage, "Unknown"),
    }


@router.post("/mark/{character_id}")
def advance_mark_stage(character_id: str, payload: MarkAdvance):
    """Advance a character's mark stage. Called by encounter resolution."""
    stage = max(0, min(4, payload.stage))  # Clamp 0-4
    conn = get_db()
    conn.execute(
        "UPDATE characters SET mark_of_dreamer_stage = ? WHERE id = ?",
        (stage, character_id)
    )
    conn.commit()
    conn.close()

    # Also set a narrative flag for tracking
    set_flag(NarrativeFlagSet(
        character_id=character_id,
        flag_key=f"mark_of_dreamer_stage_{stage}",
        flag_value="1",
        source="encounter_resolution",
    ))

    return {"character_id": character_id, "stage": stage}


# ---------------------------------------------------------------------------
# Del Ghost Visit Roll (Seeded)
# ---------------------------------------------------------------------------

@router.get("/del-roll/{character_id}")
def roll_del_ghost(character_id: str):
    """
    Roll the Del ghost visit for a character's first night.
    Uses a seeded D20 so the result is deterministic and stable.
    
    DC 13 WIS save. Pass → Del visits. Fail → no visit.
    """
    seed_str = f"{character_id}-del-ghost-visit"
    seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    roll = rng.randint(1, 20)
    passed = roll >= 13

    conn = get_db()
    conn.execute(
        """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
        (character_id, "del_ghost_roll", str(passed), "del_ghost_visit_roll")
    )
    conn.commit()
    conn.close()

    return {
        "character_id": character_id,
        "roll": roll,
        "dc": 13,
        "passed": passed,
        "narrative": (
            "Del's spirit visits your room tonight. You see him sitting on the chair, "
            "looking confused and sad. 'You were the last person I remember clearly.'"
            if passed else
            "You sleep fitfully but nothing manifests. No visit. No dreams. "
            "The silence is worse than whispers."
        ),
    }


# ---------------------------------------------------------------------------
# Green Woman Suppression Mechanics
# ---------------------------------------------------------------------------

@router.post("/suppress/{character_id}")
def suppress_mark(character_id: str):
    """Suppress a character's mark via the Green Woman.
    
    3 uses max. Each use sets mark to 0 and starts a countdown.
    After N long rests, the mark returns WORSE:
    - Suppression 1: 8 long rests → mark jumps to stage 2
    - Suppression 2: 5 long rests → mark jumps to stage 3
    - Suppression 3: 3 long rests → mark stays at 3 permanently (Green Woman dies)
    
    After 3 uses, Merge ending is LOCKED at endgame.
    """
    import json as _json
    
    conn = get_db()
    
    # Count previous suppressions
    rows = conn.execute(
        "SELECT flag_value FROM narrative_flags WHERE character_id = ? AND flag_key LIKE 'green_woman_suppression_%'",
        (character_id,)
    ).fetchall()
    suppression_count = len(rows)
    
    if suppression_count >= 3:
        conn.close()
        raise HTTPException(400, "The Green Woman has no more suppressions to give. She is ash.")
    
    # Verify character exists and is marked
    char = conn.execute(
        "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?",
        (character_id,)
    ).fetchone()
    if not char:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")
    
    if char["mark_of_dreamer_stage"] == 0 and suppression_count == 0:
        conn.close()
        raise HTTPException(400, "Character is not marked. Nothing to suppress.")
    
    use_number = suppression_count + 1
    rest_durations = {1: 8, 2: 5, 3: 3}
    return_stages = {1: 2, 2: 3, 3: 3}
    
    duration = rest_durations[use_number]
    return_stage = return_stages[use_number]
    
    # Set mark to 0
    conn.execute(
        "UPDATE characters SET mark_of_dreamer_stage = 0 WHERE id = ?",
        (character_id,)
    )
    
    # Record suppression use
    conn.execute(
        """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
        (character_id, f"green_woman_suppression_{use_number}", str(duration), "green_woman_ritual")
    )
    
    # Set countdown timer
    conn.execute(
        """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
        (character_id, "mark_suppression_countdown", str(duration), "green_woman_ritual")
    )
    
    # Record what stage the mark will return to
    conn.execute(
        """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
        (character_id, "mark_suppression_return_stage", str(return_stage), "green_woman_ritual")
    )
    
    conn.commit()
    conn.close()
    
    result = {
        "character_id": character_id,
        "suppression_use": use_number,
        "remaining_uses": 3 - use_number,
        "mark_stage": 0,
        "relief_duration": f"{duration} long rests",
        "return_warning": (
            f"The mark will return at stage {return_stage} after {duration} long rests. "
            f"{'The Green Woman will die after this suppression wears off.' if use_number == 3 else ''}"
        ),
    }
    
    if use_number == 3:
        result["merge_ending_locked"] = True
        result["narrative"] = (
            "The Green Woman places her bark-rough hands on your arm. The mark "
            "fades — but you feel her shudder. 'That was the last one I can give. "
            "When it returns... I won't be here to stop it. Use what time I've bought wisely.'"
        )
    else:
        result["narrative"] = (
            f"The Green Woman's fingers trace the mark. It burns — then cools. "
            f"Then it's gone. You feel... normal. She sways. '{3 - use_number} "
            f"more. Then I'm done. Then I'm gone.'"
        )
    
    return result


@router.get("/suppression-status/{character_id}")
def get_suppression_status(character_id: str):
    """Check current suppression countdown and Green Woman availability."""
    conn = get_db()
    
    rows = conn.execute(
        "SELECT flag_key, flag_value FROM narrative_flags WHERE character_id = ? AND flag_key LIKE 'green_woman_suppression%'",
        (character_id,)
    ).fetchall()
    conn.close()
    
    flags = {r["flag_key"]: r["flag_value"] for r in rows}
    suppression_count = sum(1 for k in flags if k.startswith("green_woman_suppression_") and k != "green_woman_suppression_count")
    
    # Check countdown
    countdown = flags.get("mark_suppression_countdown", "0")
    return_stage = flags.get("mark_suppression_return_stage", "0")
    
    return {
        "character_id": character_id,
        "suppressions_used": suppression_count,
        "remaining_uses": max(0, 3 - suppression_count),
        "green_woman_alive": suppression_count < 3,
        "merge_ending_available": suppression_count < 3,
        "countdown_rests_remaining": int(countdown) if countdown.isdigit() else 0,
        "mark_will_return_at_stage": int(return_stage) if return_stage.isdigit() else 0,
    }


# ---------------------------------------------------------------------------
# Endgame — Three Endings
# ---------------------------------------------------------------------------

class EndgameChoice(BaseModel):
    ending: str  # "reseal", "communion", "merge"


@router.post("/endgame/{character_id}")
def resolve_endgame(character_id: str, payload: EndgameChoice):
    """Resolve the endgame at the seal chamber.
    
    Three endings:
    - reseal: Reinforce the seal with 3 keys. Basic ending. Seal holds 50-100 years.
    - commune: Let the Hunger speak through you. Bargain. One NPC is taken.
      Requires: mark_stage >= 1 AND kol_backstory_known.
    - merge: Green Woman merges with seal. Strongest ending. She dies.
      Requires: green_woman_alive (suppressions_used < 3).
    """
    conn = get_db()
    
    # Load character state
    char = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not char:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")
    
    char = dict(char)
    
    # Load all narrative flags
    flag_rows = conn.execute(
        "SELECT flag_key, flag_value FROM narrative_flags WHERE character_id = ?",
        (character_id,)
    ).fetchall()
    flags = {r["flag_key"]: r["flag_value"] for r in flag_rows}
    
    mark_stage = char.get("mark_of_dreamer_stage", 0)
    suppressions_used = sum(1 for k in flags if k.startswith("green_woman_suppression_"))
    kol_backstory_known = flags.get("kol_backstory_known") == "1"
    kol_recruited = flags.get("kol_ally") == "1"
    drenna_saved = flags.get("drenna_child_saved") == "1"
    
    ending = payload.ending.lower()
    
    if ending == "reseal":
        # Always available
        conn.execute(
            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
            (character_id, "ending_reseal", "1", "endgame")
        )
        # Per-character: deactivate this character's front (multi-tenancy)
        conn.execute(
            """UPDATE character_fronts SET is_active = 0, current_portent_index = 7, advanced_at = ?
               WHERE character_id = ? AND front_id = 'dreaming_hunger'""",
            (datetime.utcnow().isoformat(), character_id)
        )
        
        # Mark is cured
        conn.execute("UPDATE characters SET mark_of_dreamer_stage = 4 WHERE id = ?", (character_id,))
        
        conn.commit()
        conn.close()
        
        return {
            "ending": "reseal",
            "title": "The Seal Holds",
            "narrative": (
                "You place the three keys — your mark, the seal stone fragment, and "
                "the Green Woman's acorn — into the seal's fingers. They lock. The "
                "amber glow fades to a dim pulse. The Hunger pushes against the seal "
                "one final time... and stops. It's not gone. It's contained. "
                "For now. The Whisperwood goes quiet. Thornhold survives. "
                "The mark on your arm fades to a pale scar. You are free. "
                "But the seal was never meant to last forever."
            ),
            "consequences": {
                "mark_cured": True,
                "seal_strength": "moderate",
                "estimated_duration": "50-100 years",
                "green_woman_fate": "survives" if suppressions_used < 3 else "already dead",
                "hunger_status": "contained, not destroyed",
            },
            "sequel_hook": "The seal will weaken again. The Hunger remembers your name.",
        }
    
    elif ending == "communion":
        # Requires mark + kol backstory knowledge
        if mark_stage < 1:
            conn.close()
            raise HTTPException(400, "You are not marked. The Hunger cannot speak through an unbonded mind.")
        if not kol_backstory_known:
            conn.close()
            raise HTTPException(400, "You don't understand the cult well enough to commune. Learn more about Brother Kol first.")
        
        # Determine who is taken
        taken_npc = "unknown"
        if kol_recruited and drenna_saved:
            taken_npc = "kol"  # If both are allied, Kol volunteers
        elif kol_recruited:
            taken_npc = "kol"
        elif drenna_saved:
            taken_npc = "drenna"
        else:
            taken_npc = "green_woman"  # If nobody is allied, Green Woman is taken by default
        
        conn.execute(
            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
            (character_id, "ending_communion", taken_npc, "endgame")
        )
        # Per-character: deactivate this character's front (multi-tenancy)
        conn.execute(
            """UPDATE character_fronts SET is_active = 0, current_portent_index = 7, advanced_at = ?
               WHERE character_id = ? AND front_id = 'dreaming_hunger'""",
            (datetime.utcnow().isoformat(), character_id)
        )
        
        # Mark becomes stage 4 (cured but scarred)
        conn.execute("UPDATE characters SET mark_of_dreamer_stage = 4 WHERE id = ?", (character_id,))
        
        conn.commit()
        conn.close()
        
        npc_names = {
            "kol": "Brother Kol",
            "drenna": "Sister Drenna",
            "green_woman": "The Green Woman",
        }
        
        return {
            "ending": "communion",
            "title": "The Bargain",
            "narrative": (
                f"You let the Hunger in. Not all the way — just enough to speak. "
                f"It is vast. It is patient. It does not want destruction. It wants "
                f"connection. You bargain. It agrees to retreat — for a price. "
                f"{npc_names.get(taken_npc, 'Someone')} steps forward. 'I'll go.' "
                f"The Hunger takes them. The seal holds — differently. The amber glow "
                f"is warm now, not cold. The mark on your arm becomes a scar shaped like "
                f"a closed eye. You hear {npc_names.get(taken_npc, 'them')} whisper, "
                f"once, from inside the seal: 'It's not so bad in here. It dreams.'"
            ),
            "consequences": {
                "mark_cured": True,
                "npc_taken": taken_npc,
                "seal_strength": "strong",
                "hunger_status": "retreated, with a foothold",
            },
            "sequel_hook": f"{npc_names.get(taken_npc, 'The taken one')} will return. The Hunger gave them a gift. Or a curse.",
        }
    
    elif ending == "merge":
        # Requires green woman alive
        if suppressions_used >= 3:
            conn.close()
            raise HTTPException(400, "The Green Woman is dead. She cannot merge with the seal. Choose another path.")
        
        conn.execute(
            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
            (character_id, "ending_merge", "1", "endgame")
        )
        # Per-character: deactivate this character's front (multi-tenancy)
        conn.execute(
            """UPDATE character_fronts SET is_active = 0, current_portent_index = 7, advanced_at = ?
               WHERE character_id = ? AND front_id = 'dreaming_hunger'""",
            (datetime.utcnow().isoformat(), character_id)
        )
        
        # Mark is cured
        conn.execute("UPDATE characters SET mark_of_dreamer_stage = 4 WHERE id = ?", (character_id,))
        
        # Green Woman dies
        conn.execute(
            """INSERT INTO narrative_flags (character_id, flag_key, flag_value, source)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(character_id, flag_key) DO UPDATE SET flag_value = excluded.flag_value""",
            (character_id, "green_woman_dead", "1", "endgame_merge")
        )
        
        conn.commit()
        conn.close()
        
        return {
            "ending": "merge",
            "title": "The Last Seal-Keeper",
            "narrative": (
                "The Green Woman looks at you. She's crying — sap, not tears. "
                "'I was always going to end here. I just hoped it would be later.' "
                "She walks to the seal. Places her hands on the stone. Her bark-skin "
                "cracks. Light pours from inside her — green, warm, alive. She "
                "becomes the seal. The stone drinks her in. The amber glow turns "
                "to deep forest green. The Hunger cries out — once — not in rage, "
                "but in something that sounds almost like loss. Then silence. "
                "True silence. The Whisperwood exhales. Birds sing. "
                "The mark on your arm flakes away like dead bark. You are free. "
                "The seal will hold. Maybe forever. But the last seal-keeper is gone."
            ),
            "consequences": {
                "mark_cured": True,
                "green_woman_fate": "merged with seal — dead",
                "seal_strength": "permanent",
                "hunger_status": "fully contained",
            },
            "sequel_hook": "No sequel pressure. But the Whisperwood is now unprotected. Other things stir in the deep places.",
        }
    
    else:
        conn.close()
        raise HTTPException(400, f"Unknown ending: {ending}. Valid: reseal, communion, merge")
