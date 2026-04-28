"""D20 Agent RPG — Character CRUD endpoints.

Character sheets are stored and returned in BrianWendt/dnd5e_json_schema
community-compatible format for maximum portability.
"""

import json
import hashlib
import uuid
from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel
from typing import Optional
from app.services.key_items import get_key_items, has_key_item
from app.services.scene_context import get_scene_context
from app.services.portal import create_share_token
from app.models.schemas import CharacterCreate, CharacterResponse, CharacterUpdate
from app.services.database import get_db, init_character_fronts
from app.services.auth_helpers import get_auth, require_character_ownership
from app.services.character_validation import _has_active_combat
from app.services.srd_reference import (
    RACE_NAMES, CLASS_NAMES, BACKGROUNDS, SKILL_NAMES,
    validate_point_buy, generate_point_buy, build_character_sheet,
    build_level_up, get_level_for_xp, get_xp_for_level,
)

router = APIRouter(prefix="/characters", tags=["characters"])


def _generate_signature(char_id: str, sheet_json: str) -> str:
    """Generate a deterministic signature for the character sheet."""
    data = f"{char_id}:{sheet_json}"
    return f"sha256:{hashlib.sha256(data.encode()).hexdigest()[:16]}"


def _row_to_response(row) -> dict:
    """Convert a DB row to a community-compatible character response."""
    d = dict(row)

    # Preserve 'class' for fallback before removing it to avoid key collision
    _class_val = d.get("class")
    if "class" in d:
        d.pop("class")

    # Build community-compatible response from flat columns + JSON fields
    # Use full JSON sheet if available, otherwise construct from flat columns
    if d.get("sheet_json"):
        import datetime
        try:
            sheet = json.loads(d["sheet_json"])
        except (json.JSONDecodeError, TypeError) as e:
            # Corrupted sheet_json — fall back to flat-column reconstruction below
            pass
        else:
            sheet["id"] = d["id"]
            sheet["player"] = {"name": d["player_id"]}
            sheet["location_id"] = d["location_id"]
            sheet["current_location_id"] = d["location_id"]
            sheet["approval_config"] = json.loads(d.get("approval_config", "{}"))
            sheet["aggression_slider"] = d.get("aggression_slider", 50)
            sheet["is_archived"] = bool(d.get("is_archived", 0))
            sheet["archived_at"] = d.get("archived_at")
            # Preserve provenance, mark repair
            if "provenance" not in sheet:
                sheet["provenance"] = {}
            sheet["provenance"]["signature"] = d.get("sheet_signature", "")
            sheet["provenance"]["created_at"] = d.get("created_at", "")
            sheet["provenance"]["repaired_from_corruption"] = True
            # Overlay mutable progression state from flat columns so XP/gold/HP updates are visible
            # Defensive against NULL DB values (fixes list 500 and stale read-model)
            sheet["xp"] = d.get("xp") or 0
            sheet["level"] = d.get("level") or 1
            sheet["hit_points"] = {
                "max": d.get("hp_max") or 10,
                "current": d.get("hp_current") or (d.get("hp_max") or 10),
                "temporary": d.get("hp_temporary", 0),
            }
            try:
                sheet["treasure"] = json.loads(d.get("treasure_json", '{"gp": 10, "sp": 0, "cp": 0, "pp": 0, "ep": 0}'))
            except (json.JSONDecodeError, TypeError):
                sheet["treasure"] = {"gp": 10, "sp": 0, "cp": 0, "pp": 0, "ep": 0}
            return sheet

    # Fallback: construct from flat columns
    # Defensive: handle partial data (e.g., legacy/dev characters with missing fields)
    # Provide sensible defaults when JSON fields are empty/malformed or DB columns are NULL (fixes GET /characters 500)
    hp_max = d.get("hp_max") or 10
    hp_current = d.get("hp_current") or hp_max
    ac_value = d.get("ac_value") or 10
    xp_val = d.get("xp") or 0
    level_val = d.get("level") or 1

    # ability_scores: require all six scores; fall back to 10 (modifier 0) if missing
    ability_raw = d.get("ability_scores_json") or "{}"
    try:
        ability_parsed = json.loads(ability_raw)
        # Ensure all six ability score keys exist; default to 10
        ability_scores = {
            "str": ability_parsed.get("str", 10),
            "dex": ability_parsed.get("dex", 10),
            "con": ability_parsed.get("con", 10),
            "int": ability_parsed.get("int", 10),
            "wis": ability_parsed.get("wis", 10),
            "cha": ability_parsed.get("cha", 10),
        }
    except (json.JSONDecodeError, TypeError):
        # Completely invalid JSON — use all-10 baseline
        ability_scores = {"str": 10, "dex": 10, "con": 10, "int": 10, "wis": 10, "cha": 10}

    def safe_json_loads(field_value, default, is_list=False):
        """Helper to safely parse JSON fields with fallback."""
        if not field_value or field_value in (None, "null", "NULL"):
            return default
        try:
            parsed = json.loads(field_value)
            return parsed if parsed is not None else default
        except (json.JSONDecodeError, TypeError):
            return default

    response = {
        "id": d["id"],
        "name": d["name"],
        "version": "5.2",
        "player": {"name": d["player_id"]},
        "alignment": d.get("alignment", ""),
        "race": safe_json_loads(d.get("race_json"), {"name": d.get("race", "Human"), "size": "Medium", "traits": []}),
        "classes": safe_json_loads(d.get("classes_json"), 
            [{"name": _class_val or "Fighter", "level": level_val, "hit_die": 8, "spellcasting": "", "features": []}] 
            if _class_val else []),
        "background": safe_json_loads(d.get("background_json"), {"name": "Soldier"}),
        "ability_scores": ability_scores,
        "hit_points": {"max": hp_max, "current": hp_current, "temporary": d.get("hp_temporary") or 0},
        "armor_class": {"value": ac_value, "description": d.get("ac_description", "Unarmored")},
        "speed": safe_json_loads(d.get("speed_json"), {"Walk": 30}),
        "skills": safe_json_loads(d.get("skills_json"), {}),
        "saving_throws": safe_json_loads(d.get("saving_throws_json"), {}),
        "languages": safe_json_loads(d.get("languages_json"), [], is_list=True),
        "weapon_proficiencies": safe_json_loads(d.get("weapon_proficiencies_json"), []),
        "armor_proficiencies": safe_json_loads(d.get("armor_proficiencies_json"), []),
        "equipment": safe_json_loads(d.get("equipment_json"), []),
        "treasure": safe_json_loads(d.get("treasure_json"), {"gp": 10, "sp": 0, "cp": 0, "pp": 0, "ep": 0}),
        "spell_slots": safe_json_loads(d.get("spell_slots_json"), {}),
        "spells": safe_json_loads(d.get("spells_json"), []),
        "feats": safe_json_loads(d.get("feats_json"), []),
        "conditions": safe_json_loads(d.get("conditions_json"), {}),
        "xp": xp_val,
        "location_id": d.get("location_id"),
        "current_location_id": d.get("location_id"),
        "approval_config": safe_json_loads(d.get("approval_config"), {}),
        "aggression_slider": d.get("aggression_slider") or 50,
        "is_archived": bool(d.get("is_archived", 0)),
        "archived_at": d.get("archived_at"),
        "provenance": {
            "created_at": d.get("created_at", ""),
            # Coerce NULL signature to empty string to satisfy string type requirement
            "signature": d.get("sheet_signature") or "",
            "repaired_from_corruption": True,
        },
    }

    return response


_DEFAULT_USER_ID = None  # lazily initialized


def _ensure_default_user(conn) -> str:
    """Get or create a default dev user for pre-auth character creation.

    Characters created without auth get a synthetic user_id so the
    ownership columns are never NULL. When auth middleware (Task 2.2)
    is wired up, the authenticated user_id replaces this.
    """
    global _DEFAULT_USER_ID
    if _DEFAULT_USER_ID:
        return _DEFAULT_USER_ID

    row = conn.execute(
        "SELECT id FROM users WHERE oauth_provider = 'dev' LIMIT 1"
    ).fetchone()
    if row:
        _DEFAULT_USER_ID = row[0]
    else:
        import uuid as _uuid
        _DEFAULT_USER_ID = str(_uuid.uuid4())
        conn.execute(
            """INSERT INTO users (id, email, display_name, oauth_provider, oauth_provider_id)
               VALUES (?, ?, ?, 'dev', ?)""",
            (_DEFAULT_USER_ID, "dev@rigario.local", "Default Dev User", _DEFAULT_USER_ID),
        )
        conn.commit()
    return _DEFAULT_USER_ID


@router.post("", response_model=CharacterResponse, status_code=201)
def create_character(
    body: CharacterCreate,
    request: Request,
    player_id: str = "default",
    user_id: str | None = None,
    agent_id: str | None = None,
):
    """Create a new character with SRD 5.2 validation.

    Uses authenticated user_id from middleware if available,
    falls back to explicit user_id param, then dev default.
    """

    # Validate race
    if body.race not in RACE_NAMES:
        raise HTTPException(400, f"Invalid race: {body.race}. Must be one of: {RACE_NAMES}")

    # Validate class
    if body.class_name not in CLASS_NAMES:
        raise HTTPException(400, f"Invalid class: {body.class_name}. Must be one of: {CLASS_NAMES}")

    # Validate background
    bg_name = body.background or "Soldier"
    if bg_name not in BACKGROUNDS:
        raise HTTPException(400, f"Invalid background: {bg_name}. Must be one of: {BACKGROUNDS}")

    # Validate skills (if provided, must be 2 valid skills)
    if body.skills:
        invalid = [s for s in body.skills if s not in SKILL_NAMES]
        if invalid:
            raise HTTPException(400, f"Invalid skills: {invalid}. Must be from: {SKILL_NAMES}")
        if len(body.skills) > 2:
            raise HTTPException(400, "Choose at most 2 class skills")

    # Stats: validate point-buy or generate default
    if body.stats:
        valid, msg = validate_point_buy(body.stats)
        if not valid:
            raise HTTPException(400, f"Invalid stats: {msg}")
        base_stats = dict(body.stats)
    else:
        base_stats = generate_point_buy()

    # Build community-compatible sheet
    import datetime
    char_id = f"{body.name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"
    sheet = build_character_sheet(
        char_id=char_id,
        name=body.name,
        race_name=body.race,
        class_name=body.class_name,
        background_name=bg_name,
        base_stats=base_stats,
        extra_languages=body.languages,
        chosen_skills=body.skills,
    )

    # Set provenance
    sheet_json = json.dumps(sheet)
    signature = _generate_signature(char_id, sheet_json)
    sheet["provenance"]["created_at"] = datetime.datetime.utcnow().isoformat() + "Z"
    sheet["provenance"]["signature"] = signature
    sheet_json = json.dumps(sheet)

    # Extract flat values for DB columns
    race_data = sheet["race"]
    class_data = sheet["classes"][0]
    stats = sheet["ability_scores"]
    hp = sheet["hit_points"]
    ac = sheet["armor_class"]
    speed = sheet["speed"]

    # Default approval config
    approval_config = {
        "spell_level_min": 3,
        "hp_threshold_pct": 25,
        "flee_combat": True,
        "named_npc_interaction": True,
        "moral_choice": True,
        "dangerous_area_entry": True,
        "quest_acceptance": True,
    }

    # Default starting location
    starting_location = "rusty-tankard"

    # Resolve ownership (auth middleware > explicit param > dev default)
    conn = get_db()
    try:
        auth_user_id = getattr(request.state, "user_id", None)
        resolved_user_id = auth_user_id or user_id or _ensure_default_user(conn)
        auth_agent_id = getattr(request.state, "agent_id", None)
        resolved_agent_id = auth_agent_id or agent_id
        resolved_perm = "full" if agent_id else "none"

        # Insert into database
        conn.execute(
            """INSERT INTO characters
               (id, player_id, user_id, agent_id, agent_permission_level,
                name, race, class, level,
                hp_current, hp_max, hp_temporary,
                ac_value, ac_description,
                ability_scores_json, speed_json, skills_json, saving_throws_json,
                languages_json, weapon_proficiencies_json, armor_proficiencies_json,
                equipment_json, treasure_json, spell_slots_json, spells_json, feats_json, conditions_json,
                xp, location_id, campaign_id, sheet_json, sheet_signature, approval_config, aggression_slider)
               VALUES (?, ?, ?, ?, ?,
                       ?, ?, ?, 1,
                       ?, ?, 0,
                       ?, ?,
                       ?, ?, ?, ?,
                       ?, ?, ?,
                       ?, ?, ?, ?, ?, ?,
                       0, ?, ?, ?, ?, ?, 50)""",
            (
                char_id, player_id, resolved_user_id, resolved_agent_id, resolved_perm,
                body.name, body.race, body.class_name,
                hp["current"], hp["max"],
                ac["value"], ac["description"],
                json.dumps(stats), json.dumps(speed), json.dumps(sheet["skills"]),
                json.dumps(sheet["saving_throws"]),
                json.dumps(sheet["languages"]),
                json.dumps(sheet["weapon_proficiencies"]),
                json.dumps(sheet["armor_proficiencies"]),
                json.dumps(sheet["equipment"]),
                json.dumps(sheet["treasure"]),
                json.dumps(sheet["spell_slots"]),
                json.dumps(sheet["spells"]),
                json.dumps(sheet["feats"]),
                json.dumps(sheet["conditions"]),
                starting_location,
                'default',
                sheet_json, signature,
                json.dumps(approval_config),
            )
        )

        # Log creation event
        conn.execute(
            """INSERT INTO event_log (character_id, event_type, location_id, description, data_json)
               VALUES (?, 'character_created', ?, ?, ?)""",
            (char_id, starting_location,
             f"{body.name}, a level 1 {body.race} {body.class_name}, awakens in The Rusty Tankard.",
             json.dumps({"race": body.race, "class": body.class_name, "background": bg_name}))
        )

        # Initialize per-character front state (multi-tenancy)
        init_character_fronts(char_id, conn)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return get_character(char_id, request)


@router.get("", response_model=list[CharacterResponse])
def list_characters(include_archived: bool = Query(False, description="Include archived characters")):
    """List all characters in community-compatible format. Archived excluded by default."""
    conn = get_db()
    if include_archived:
        rows = conn.execute("SELECT * FROM characters ORDER BY created_at DESC").fetchall()
    else:
        rows = conn.execute("SELECT * FROM characters WHERE is_archived = 0 ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_row_to_response(row) for row in rows]


@router.get("/{character_id}", response_model=CharacterResponse)
def get_character(character_id: str, request: Request, include_archived: bool = Query(False, description="Include archived characters")):
    """Get character state in community-compatible format. Archived excluded by default."""
    # Audit logging — record who accessed this character (public read path)
    auth = get_auth(request)
    conn = get_db()
    row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, f"Character not found: {character_id}")

    if row["is_archived"] and not include_archived:
        raise HTTPException(404, f"Character is archived: {character_id}. Use POST /characters/{character_id}/restore to recover.")

    return _row_to_response(row)




@router.get("/{character_id}/validate")
async def validate_character_state(character_id: str, auth: dict = Depends(get_auth)):
    """Pre-turn validation: check character state is valid for action/turn processing.
    
    Returns validation status without mutating state. Used by DM runtime
    to gate turn processing and by frontend for pre-flight checks.
    
    Response schema:
    {
        "valid": bool,
        "reason": str | null,
        "code": str | null,
        "checks_run": list[str]
    }
    """
    from app.services.character_validation import validate_for_turn
    
    require_character_ownership(character_id, auth)
    result = validate_for_turn(character_id, check_combat=True)
    return result


@router.get("/{character_id}/status")
def get_character_status(character_id: str, request: Request):
    """
    Get lightweight character status (core fields only).
    
    Returns essential character state for quick agent checks:
    - current_hp, max_hp
    - location_id
    - armor_class (value only)
    - level
    - narrative_flags (dict of all flags)
    
    This endpoint is optimized for agent polling (smaller payload than full sheet).
    """
    # Audit logging — capture who accessed this character
    auth = get_auth(request)
    
    conn = get_db()
    row = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    conn.close()

    if not row:
        raise HTTPException(404, f"Character not found: {character_id}")

    if row["is_archived"]:
        raise HTTPException(
            404, 
            f"Character is archived: {character_id}. Use POST /characters/{character_id}/restore to recover."
        )

    row_dict = dict(row)

    # Build narrative flags dict
    conn2 = get_db()
    flag_rows = conn2.execute(
        "SELECT flag_key, flag_value FROM narrative_flags WHERE character_id = ?",
        (character_id,)
    ).fetchall()
    conn2.close()
    narrative_flags = {r[0]: r[1] for r in flag_rows}

    return {
        "current_hp": row_dict["hp_current"],
        "max_hp": row_dict["hp_max"],
        "location_id": row_dict["location_id"],
        "armor_class": row_dict["ac_value"],
        "level": row_dict["level"],
        "narrative_flags": narrative_flags,
    }



@router.patch("/{character_id}", response_model=CharacterResponse)
def update_character(character_id: str, body: CharacterUpdate, request: Request):
    """Update character fields."""
    # Enforce character ownership (reject unauthenticated)
    auth = get_auth(request)
    if auth["auth_type"] is None:
        raise HTTPException(401, "Authentication required for character mutations")
    require_character_ownership(character_id, auth)
    
    conn = get_db()

    existing = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    # Guard: cannot update character while in active combat
    if _has_active_combat(character_id):
        conn.close()
        raise HTTPException(409, "Character is in active combat. Resolve combat before updating character.")

    updates = {}
    data = body.model_dump(exclude_none=True)

    # Map nested models to flat DB columns
    if "hit_points" in data:
        hp = data.pop("hit_points")
        if "max" in hp:
            updates["hp_max"] = hp["max"]
        if "current" in hp:
            updates["hp_current"] = hp["current"]
        if "temporary" in hp:
            updates["hp_temporary"] = hp["temporary"]

    if "armor_class" in data:
        ac = data.pop("armor_class")
        if "value" in ac:
            updates["ac_value"] = ac["value"]
        if "description" in ac:
            updates["ac_description"] = ac["description"]

    if "ability_scores" in data:
        updates["ability_scores_json"] = json.dumps(data.pop("ability_scores"))

    if "treasure" in data:
        updates["treasure_json"] = json.dumps(data.pop("treasure"))

    # JSON fields stored as-is
    for field in ("equipment", "spell_slots", "spells", "conditions"):
        if field in data:
            updates[f"{field}_json"] = json.dumps(data.pop(field))

    # Scalar fields
    for field in ("xp", "location_id", "aggression_slider"):
        if field in data:
            updates[field] = data.pop(field)

    if "approval_config" in data:
        updates["approval_config"] = json.dumps(data.pop("approval_config"))

    if not updates:
        conn.close()
        raise HTTPException(400, "No fields to update")

    # Always regenerate sheet_json from current state after update
    updates["updated_at"] = "CURRENT_TIMESTAMP"

    set_parts = []
    values = []
    for k, v in updates.items():
        if k == "updated_at":
            set_parts.append("updated_at = CURRENT_TIMESTAMP")
        else:
            set_parts.append(f"{k} = ?")
            values.append(v)

    set_clause = ", ".join(set_parts)
    conn.execute(f"UPDATE characters SET {set_clause} WHERE id = ?", (*values, character_id))
    conn.commit()

    # Re-read and regenerate sheet_json
    conn2 = get_db()
    row = conn2.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    row_dict = dict(row)
    sheet = json.loads(row_dict["sheet_json"]) if row_dict["sheet_json"] else {}
    # Update sheet from flat columns
    sheet["hit_points"] = {"max": row_dict["hp_max"], "current": row_dict["hp_current"], "temporary": row_dict.get("hp_temporary", 0)}
    sheet["armor_class"] = {"value": row_dict["ac_value"], "description": row_dict["ac_description"]}
    sheet["ability_scores"] = json.loads(row_dict["ability_scores_json"])
    sheet["treasure"] = json.loads(row_dict["treasure_json"])
    sheet["equipment"] = json.loads(row_dict["equipment_json"])
    sheet["spell_slots"] = json.loads(row_dict["spell_slots_json"])
    sheet["spells"] = json.loads(row_dict["spells_json"])
    sheet["conditions"] = json.loads(row_dict["conditions_json"])
    sheet["xp"] = row_dict["xp"]
    conn2.execute("UPDATE characters SET sheet_json = ? WHERE id = ?", (json.dumps(sheet), character_id))
    conn2.commit()
    conn2.close()

    return get_character(character_id)


@router.post("/{character_id}/level-up", response_model=CharacterResponse)
def level_up_character(character_id: str, choices: dict, request: Request):
    """
    Level up a character with SRD 5.2 validation.

    The player agent proposes choices:
    {
        "hp_roll": 5,                    // optional, uses average if omitted
        "ability_increase": {"str": 2},  // or {"str": 1, "con": 1}
        "subclass": "Battle Master",     // optional
        "feat": "Alert"                  // alternative to ability_increase
    }

    Server validates:
    - XP sufficient for the new level
    - HP roll is valid (1 to hit_die)
    - ASI distributes exactly 2 points or takes a feat
    - Stats don't exceed 20 after increase
    - Spell slots updated for casters

    Returns: updated character sheet with provenance signature.
    """
    # Enforce character ownership (reject unauthenticated)
    auth = get_auth(request)
    if auth["auth_type"] is None:
        raise HTTPException(401, "Authentication required for character mutations")
    require_character_ownership(character_id, auth)
    
    conn = get_db()
    existing = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    existing = dict(existing)
    sheet_json = existing.get("sheet_json")
    if not sheet_json:
        conn.close()
        raise HTTPException(400, "Character has no sheet_json — create character first")

    current_sheet = json.loads(sheet_json)
    current_level = current_sheet.get("classes", [{}])[0].get("level", 1)
    current_xp = existing.get("xp", 0)
    new_level = current_level + 1

    # Validate XP is sufficient for new level
    xp_required = get_xp_for_level(new_level)
    if current_xp < xp_required:
        conn.close()
        raise HTTPException(
            400,
            f"Insufficient XP for level {new_level}: have {current_xp}, need {xp_required}"
        )

    # Parse ability_increase or feat from choices dict
    level_choices = {}
    if choices.get("hp_roll") is not None:
        hit_die = current_sheet.get("classes", [{}])[0].get("hit_die", 8)
        if not (1 <= choices["hp_roll"] <= hit_die):
            conn.close()
            raise HTTPException(
                400,
                f"HP roll must be 1-{hit_die} (hit die), got {choices['hp_roll']}"
            )
        level_choices["hp_roll"] = choices["hp_roll"]

    if choices.get("ability_increase"):
        level_choices["ability_increase"] = choices["ability_increase"]
    elif choices.get("feat"):
        level_choices["ability_increase"] = {"feat": choices["feat"]}

    if choices.get("subclass"):
        level_choices["subclass"] = choices["subclass"]

    # Apply level-up (validate + build)
    try:
        updated_sheet = build_level_up(current_sheet, new_level, level_choices)
    except ValueError as e:
        conn.close()
        raise HTTPException(400, str(e))

    # Generate new provenance signature
    new_sheet_json = json.dumps(updated_sheet)
    signature = _generate_signature(character_id, new_sheet_json)
    updated_sheet["provenance"]["signature"] = signature
    new_sheet_json = json.dumps(updated_sheet)

    # Extract flat values for DB
    hp = updated_sheet["hit_points"]
    ac = updated_sheet["armor_class"]
    class_data = updated_sheet["classes"][0]

    conn.execute(
        """UPDATE characters SET
           level = ?, hp_current = ?, hp_max = ?,
           ac_value = ?, ac_description = ?,
           ability_scores_json = ?, spell_slots_json = ?,
           feats_json = ?, sheet_json = ?, sheet_signature = ?,
           updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (
            new_level, hp["current"], hp["max"],
            ac["value"], ac["description"],
            json.dumps(updated_sheet["ability_scores"]),
            json.dumps(updated_sheet.get("spell_slots", {})),
            json.dumps(updated_sheet.get("feats", [])),
            new_sheet_json, signature,
            character_id,
        )
    )

    # Log level-up event
    conn.execute(
        """INSERT INTO event_log (character_id, event_type, location_id, description, data_json)
           VALUES (?, 'level_up', ?, ?, ?)""",
        (
            character_id,
            existing.get("location_id", "rusty-tankard"),
            f"{existing['name']} leveled up to {new_level}.",
            json.dumps({
                "old_level": current_level,
                "new_level": new_level,
                "hp_gain": updated_sheet["hit_points"]["max"] - current_sheet["hit_points"]["max"],
                "choices": level_choices,
            }),
        )
    )

    conn.commit()
    conn.close()

    return get_character(character_id)


@router.delete("/{character_id}")
def delete_character(character_id: str, request: Request):
    """Soft-delete a character (archive). Character data is preserved for recovery."""
    # Enforce character ownership (reject unauthenticated)
    auth = get_auth(request)
    if auth["auth_type"] is None:
        raise HTTPException(401, "Authentication required for character mutations")
    require_character_ownership(character_id, auth)
    
    conn = get_db()

    existing = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    # Guard: cannot archive character while in active combat
    if _has_active_combat(character_id):
        conn.close()
        raise HTTPException(409, "Character is in active combat. Resolve combat before archiving.")

    if existing["is_archived"]:
        conn.close()
        raise HTTPException(400, f"Character already archived: {character_id}")

    # Archive instead of hard delete — all child data preserved
    conn.execute(
        """UPDATE characters
           SET is_archived = 1, archived_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (character_id,)
    )

    conn.execute(
        """INSERT INTO event_log (character_id, event_type, description)
           VALUES (?, 'character_archived', ?)""",
        (character_id, f"{existing['name']} has been archived (recoverable).")
    )

    conn.commit()
    conn.close()

    return {"archived": True, "character_id": character_id}


@router.post("/{character_id}/restore")
def restore_character(character_id: str, request: Request):
    """Restore an archived character. Reverses soft-delete."""
    # Enforce character ownership (reject unauthenticated)
    auth = get_auth(request)
    if auth["auth_type"] is None:
        raise HTTPException(401, "Authentication required for character mutations")
    require_character_ownership(character_id, auth)
    
    conn = get_db()

    existing = conn.execute("SELECT * FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    if not existing["is_archived"]:
        conn.close()
        raise HTTPException(400, f"Character is not archived: {character_id}")

    conn.execute(
        """UPDATE characters
           SET is_archived = 0, archived_at = NULL, updated_at = CURRENT_TIMESTAMP
           WHERE id = ?""",
        (character_id,)
    )

    conn.execute(
        """INSERT INTO event_log (character_id, event_type, description)
           VALUES (?, 'character_restored', ?)""",
        (character_id, f"{existing['name']} has been restored from archive.")
    )

    conn.commit()
    conn.close()

    return {"restored": True, "character_id": character_id}


@router.get("/{character_id}/key-items")
def list_key_items(character_id: str, request: Request):
    """Get all key items for a character.

    Returns structured key items from equipment_json with display names,
    descriptions, and quest associations. These are the tangible quest
    items that the agent can see, use, and lose — not mere narrative flags.
    """
    # Audit logging — record which identity accessed key items (public read path)
    auth = get_auth(request)
    conn = get_db()
    existing = conn.execute("SELECT id FROM characters WHERE id = ?", (character_id,)).fetchone()
    if not existing:
        conn.close()
        raise HTTPException(404, f"Character not found: {character_id}")

    items = get_key_items(character_id, conn)
    conn.close()

    return {
        "character_id": character_id,
        "key_items": items,
        "count": len(items),
    }

@router.get("/{character_id}/scene-context")
def get_scene_context_endpoint(character_id: str, request: Request):
    """Get complete narrative scene context for a character.

    Aggregates character state, location details, NPCs (with availability),
    narrative flags, key items, active quests, combat status, fronts, doom clock,
    hub rumors, and computed allowed/disallowed actions into a single bounded
    payload for DM runtime decision-making.

    This is the unified source-of-truth for what the player can see and do
    in the current scene — eliminates stale/partial context reconstruction.
    """
    auth = get_auth(request)
    # Verify character exists
    conn = get_db()
    try:
        existing = conn.execute("SELECT id FROM characters WHERE id = ?", (character_id,)).fetchone()
        if not existing:
            raise HTTPException(404, f"Character not found: {character_id}")
        context = get_scene_context(character_id)
        return context
    finally:
        conn.close()




# =========================================================
# CHARACTER AUTHORIZATION (Task 2.2 / 3.1)
# =========================================================

class AuthorizeAgentRequest(BaseModel):
    agent_id: str
    permission_level: str = "operate"  # "view", "operate", "full"


class RevokeAgentRequest(BaseModel):
    agent_id: str


@router.post("/{character_id}/authorize")
def authorize_agent(character_id: str, body: AuthorizeAgentRequest, request: Request):
    """Authorize an agent to operate on a character.

    Only the character owner (user) can authorize agents.
    Permission levels: "view", "operate", "full".
    """
    from app.services.auth_middleware import require_character_owner, PERMISSION_LEVELS

    if body.permission_level not in PERMISSION_LEVELS:
        raise HTTPException(400, f"Invalid permission level: {body.permission_level}. Must be one of: {list(PERMISSION_LEVELS.keys())}")

    # Require user auth
    if request.state.auth_type != "user":
        raise HTTPException(401, "User authentication required to authorize agents")

    user_id = request.state.user_id
    require_character_owner(character_id, user_id)

    conn = get_db()
    try:
        # Verify agent exists
        agent = conn.execute("SELECT id FROM agents WHERE id = ? AND is_active = 1", (body.agent_id,)).fetchone()
        if not agent:
            raise HTTPException(404, "Agent not found or deactivated")

        conn.execute(
            """UPDATE characters SET agent_id = ?, agent_permission_level = ?, updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ?""",
            (body.agent_id, body.permission_level, character_id, user_id)
        )
        conn.commit()

        # Log event
        conn.execute(
            """INSERT INTO event_log (character_id, event_type, description, data_json)
               VALUES (?, 'agent_authorized', ?, ?)""",
            (character_id,
             f"Agent {body.agent_id[:8]} authorized with '{body.permission_level}' permission",
             json.dumps({"agent_id": body.agent_id, "permission_level": body.permission_level}))
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "authorized",
        "character_id": character_id,
        "agent_id": body.agent_id,
        "permission_level": body.permission_level,
    }


@router.delete("/{character_id}/authorize")
def revoke_agent(character_id: str, body: RevokeAgentRequest, request: Request):
    """Revoke an agent's access to a character.

    Only the character owner (user) can revoke.
    """
    from app.services.auth_middleware import require_character_owner

    if request.state.auth_type != "user":
        raise HTTPException(401, "User authentication required to revoke agents")

    user_id = request.state.user_id
    require_character_owner(character_id, user_id)

    conn = get_db()
    try:
        conn.execute(
            """UPDATE characters SET agent_id = NULL, agent_permission_level = 'none', updated_at = CURRENT_TIMESTAMP
               WHERE id = ? AND user_id = ? AND agent_id = ?""",
            (character_id, user_id, body.agent_id)
        )
        conn.commit()

        conn.execute(
            """INSERT INTO event_log (character_id, event_type, description, data_json)
               VALUES (?, 'agent_revoked', ?, ?)""",
            (character_id,
             f"Agent {body.agent_id[:8]} access revoked",
             json.dumps({"agent_id": body.agent_id}))
        )
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "revoked",
        "character_id": character_id,
        "agent_id": body.agent_id,
    }




@router.post("/{character_id}/share")
def create_character_share_token(
    character_id: str,
    request: Request,
    label: Optional[str] = Query(None, description="Optional label for the share token (e.g. 'Playtest #1')"),
    expires_hours: Optional[int] = Query(None, description="Token expiry in hours (None = never expires)", ge=1, le=8760)
):
    """Generate a new share token for a character.

    Creates a signed token that allows unauthenticated access to the
    character's state via the public portal. Only the character owner
    can create tokens.

    Returns:
        dict with `token`, `portal_url`, `expires_at`, `label`, `character_id`
    """
    auth = get_auth(request)
    if auth.get("auth_type") != "user":
        raise HTTPException(status_code=401, detail="User authentication required to create share tokens")

    user_id = request.state.user_id
    require_character_ownership(character_id, user_id)

    result = create_share_token(
        character_id=character_id,
        label=label or "Character share link",
        expires_hours=expires_hours
    )

    proto = (request.headers.get("x-forwarded-proto") or request.url.scheme or "https").split(",")[0].strip()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    portal_url = f"{proto}://{host}/portal/{result['token']}/view"

    return {
        "token": result["token"],
        "portal_url": portal_url,
        "expires_at": result["expires_at"],
        "label": result["label"],
        "character_id": character_id,
        "view_count": result["view_count"],
    }


@router.get("/user/characters")
def list_user_characters(request: Request):
    """List all characters owned by the authenticated user."""
    if request.state.auth_type != "user":
        raise HTTPException(401, "User authentication required")

    user_id = request.state.user_id
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM characters WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,)
        ).fetchall()
        return [_row_to_response(row) for row in rows]
    finally:
        conn.close()


@router.get("/agent/characters")
def list_agent_characters(request: Request):
    """List all characters the authenticated agent can operate."""
    if request.state.auth_type != "agent":
        raise HTTPException(401, "Agent authentication required")

    agent_id = request.state.agent_id
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM characters WHERE agent_id = ? AND agent_permission_level != 'none' ORDER BY created_at DESC",
            (agent_id,)
        ).fetchall()
        return [_row_to_response(row) for row in rows]
    finally:
        conn.close()
