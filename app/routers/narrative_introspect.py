"""
Narrative Introspection Router
==============================
API endpoints for runtime narrative debugging and auditing.

Add to app/main.py:
    from app.routers import narrative_introspect
    app.include_router(narrative_introspect.router, prefix="/narrative-introspect", tags=["narrative-introspect"])
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Dict, Optional, Any
import json
import sqlite3

from app.services.database import get_db
from app.services.auth_helpers import get_auth, require_character_ownership

router = APIRouter()


# ============================================================================
# Response Models
# ============================================================================

class FlagInfo(BaseModel):
    flag_key: str
    flag_value: str
    description: str
    category: str
    set_at: Optional[str]


class DialogueStep(BaseModel):
    step_name: str
    description: str
    flag_required: str
    completed: bool


class NPCDialogueChain(BaseModel):
    npc_name: str
    steps: List[DialogueStep]
    progress_pct: float


class EndingStatus(BaseModel):
    ending_name: str
    description: str
    is_reachable: bool
    requirements: List[Dict[str, Any]]
    missing_requirements: List[str]


class PuzzleStatus(BaseModel):
    puzzle_name: str
    status: str  # solved, blocked, in_progress
    details: Dict[str, Any]


class FrontStatus(BaseModel):
    front_id: str
    front_name: str
    current_portent_index: int
    current_portent_name: str
    total_portents: int
    is_active: bool
    impending_doom: str


class NarrativeSummary(BaseModel):
    character_id: str
    character_name: str
    level: int
    mark_stage: int
    location: str
    
    front: FrontStatus
    endings: List[EndingStatus]
    puzzles: List[PuzzleStatus]
    dialogue_chains: List[NPCDialogueChain]
    critical_flags: List[FlagInfo]
    warnings: List[str]


class FlagAuditResult(BaseModel):
    flag_key: str
    is_set: bool
    description: str
    category: str
    issues: List[str]


class GlobalNarrativeState(BaseModel):
    total_characters: int
    characters_by_mark_stage: Dict[int, int]
    active_fronts: int
    average_portent_index: float
    most_common_flags: List[tuple]
    flag_gaps: List[Dict[str, Any]]


# ============================================================================
# Constants (mirrored from audit tool)
# ============================================================================

DREAMING_HUNGER_PORTENTS = [
    "The First Mark",
    "Animals Dying", 
    "Undead Walk",
    "Seal Weeps",
    "Breaking Rite",
    "Hunger Speaks",
    "The Door Opens",
    "The Feast Begins"
]

CRITICAL_FLAGS = {
    # Opening hook
    "del_encounter_fired": ("Del possession encounter completed", "opening"),
    "del_ghost_visited": ("Del's ghost visited (information vector)", "opening"),
    "del_ghost_roll": ("Ghost visit roll result (pass/fail)", "opening"),
    "mark_of_dreamer_stage_1": ("Mark stage 1 applied", "mark"),
    "mark_of_dreamer_stage_2": ("Mark stage 2 applied", "mark"),
    "mark_of_dreamer_stage_3": ("Mark stage 3 applied", "mark"),
    
    # NPC dialogue chains
    "kol_backstory_known": ("Know Brother Kol's identity (Communion ending req)", "npc"),
    "aldric_lying": ("Know Aldric is hiding Hollow Eye knowledge", "npc"),
    "green_woman_seal_knowledge": ("Know Green Woman is seal-keeper", "npc"),
    "maren_seal_knowledge": ("Know Ser Maren guards the seal", "npc"),
    
    # Quests
    "quest_clear_ritual_site": ("Accepted Ser Maren's quest", "quest"),
    "quest_moonpetal": ("Accepted Green Woman's moonpetal quest", "quest"),
    "quest_save_drenna_child": ("Accepted Sister Drenna's quest", "quest"),
    
    # Cave puzzles
    "thornhold_statue_observed": ("Observed Thornhold statue (Antechamber puzzle req)", "puzzle"),
    "bone_gallery_solved": ("Solved Bone Gallery puzzle", "puzzle"),
    "bone_gallery_failed": ("Failed Bone Gallery puzzle (skeletons)", "puzzle"),
    "bone_gallery_poisoned": ("Drank chalice (Hunger Sight)", "puzzle"),
    "seal_keys_placed": ("Placed all 3 keys in seal chamber", "puzzle"),
    
    # Constantine hooks
    "collateral_near_town": ("Caused collateral damage near Thornhold", "consequence"),
    "aldric_betrayal_fired": ("Aldric tipped off Hollow Eye", "consequence"),
    "maren_accompanying": ("Ser Maren is accompanying player", "consequence"),
    "maren_sacrificed": ("Ser Maren sacrificed himself", "consequence"),
    "seal_keeper_badge": ("Has seal-keeper badge (Maren's sacrifice)", "key_item"),
    
    # Green Woman suppression
    "green_woman_suppression_1": ("First suppression used", "suppression"),
    "green_woman_suppression_2": ("Second suppression used", "suppression"),
    "green_woman_suppression_3": ("Third suppression used", "suppression"),
    "green_woman_dead": ("Green Woman died (Merge ending locked)", "suppression"),
    
    # Endings
    "ending_reseal": ("Chose Reseal ending", "ending"),
    "ending_communion": ("Chose Communion ending", "ending"),
    "ending_merge": ("Chose Merge ending", "ending"),
}

NPC_DIALOGUE_CHAINS = {
    "Sister Drenna": [
        ("drenna_initial_contact", "First meeting", ""),
        ("drenna_confession", "Confession about doubts", "drenna_initial_contact"),
        ("drenna_kol_backstory", "Learns Kol's backstory", "drenna_confession"),
        ("drenna_ritual_schedule", "Learns ritual timing", "drenna_kol_backstory"),
    ],
    "Green Woman": [
        ("green_woman_first_meeting", "First meeting", ""),
        ("green_woman_mark_explanation", "Mark explanation", "green_woman_first_meeting"),
        ("green_woman_suppression_offer", "Suppression offer", "green_woman_mark_explanation"),
        ("green_woman_moonpetal_quest", "Moonpetal quest", "green_woman_suppression_offer"),
    ],
    "Ser Maren": [
        ("maren_initial", "First meeting", ""),
        ("maren_mark_reaction", "Mark reaction", "maren_initial"),
        ("maren_seal_knowledge", "Seal knowledge", "maren_mark_reaction"),
    ],
}


# ============================================================================
# Helper Functions
# ============================================================================

def get_character_flags(conn: sqlite3.Connection, char_id: str) -> Dict[str, str]:
    """Get all narrative flags for a character."""
    cursor = conn.execute(
        "SELECT flag_key, flag_value, set_at FROM narrative_flags WHERE character_id = ?",
        (char_id,)
    )
    return {row["flag_key"]: {"value": row["flag_value"], "set_at": row["set_at"]} 
            for row in cursor.fetchall()}


def get_character_front(conn: sqlite3.Connection, char_id: str) -> Optional[Dict]:
    """Get front state for a character."""
    cursor = conn.execute(
        """SELECT f.id, f.name, f.grim_portents_json, f.impending_doom,
                  cf.current_portent_index, cf.is_active
           FROM fronts f
           LEFT JOIN character_fronts cf ON f.id = cf.front_id AND cf.character_id = ?
           WHERE f.id = 'dreaming_hunger'""",
        (char_id,)
    )
    row = cursor.fetchone()
    if row:
        return dict(row)
    return None


def check_ending_reachable(flags: Dict, mark_stage: int) -> List[EndingStatus]:
    """Check which endings are reachable."""
    endings = []
    
    # Reseal - always available
    endings.append(EndingStatus(
        ending_name="Reseal",
        description="Reinforce the seal (standard ending)",
        is_reachable=True,
        requirements=[{"type": "always", "description": "Always available"}],
        missing_requirements=[]
    ))
    
    # Communion
    communion_reqs = []
    communion_met = True
    
    if mark_stage < 1:
        communion_reqs.append("Mark of Dreamer (any stage)")
        communion_met = False
    if "kol_backstory_known" not in flags:
        communion_reqs.append("Kol backstory (from Sister Drenna)")
        communion_met = False
    
    endings.append(EndingStatus(
        ending_name="Communion",
        description="Merge with the Hunger through understanding",
        is_reachable=communion_met,
        requirements=[{"type": "mark", "description": "Any mark stage"},
                     {"type": "flag", "flag": "kol_backstory_known", "description": "Know Kol's backstory"}],
        missing_requirements=communion_reqs
    ))
    
    # Merge
    merge_reqs = []
    merge_met = True
    suppression_count = sum(1 for f in flags if f.startswith("green_woman_suppression_"))
    
    if suppression_count >= 3 or "green_woman_dead" in flags:
        merge_reqs.append("Green Woman must be alive (suppressions < 3)")
        merge_met = False
    
    endings.append(EndingStatus(
        ending_name="Merge",
        description="Full merge with the Hunger (Green Woman alive required)",
        is_reachable=merge_met,
        requirements=[{"type": "suppression", "max": 2, "description": "Green Woman alive"}],
        missing_requirements=merge_reqs
    ))
    
    return endings


def check_puzzle_status(flags: Dict, key_items: List[str], mark_stage: int) -> List[PuzzleStatus]:
    """Check puzzle completion status."""
    puzzles = []
    
    # Antechamber
    if "thornhold_statue_observed" in flags:
        puzzles.append(PuzzleStatus(
            puzzle_name="Antechamber",
            status="solved",
            details={"prerequisite_met": True, "description": "Statue observed, puzzle solvable"}
        ))
    else:
        puzzles.append(PuzzleStatus(
            puzzle_name="Antechamber",
            status="blocked",
            details={"prerequisite_missing": "thornhold_statue_observed", 
                    "description": "Must observe Thornhold statue first"}
        ))
    
    # Bone Gallery
    if "bone_gallery_solved" in flags:
        puzzles.append(PuzzleStatus(
            puzzle_name="Bone Gallery",
            status="solved",
            details={"outcome": "chose_acorn", "description": "Correctly chose the green acorn"}
        ))
    elif "bone_gallery_failed" in flags:
        puzzles.append(PuzzleStatus(
            puzzle_name="Bone Gallery",
            status="failed",
            details={"outcome": "chose_dagger", "description": "Chose dagger/badge, skeletons attacked"}
        ))
    elif "bone_gallery_poisoned" in flags:
        puzzles.append(PuzzleStatus(
            puzzle_name="Bone Gallery",
            status="poisoned",
            details={"outcome": "chose_chalice", "description": "Drank chalice, gained Hunger Sight"}
        ))
    else:
        puzzles.append(PuzzleStatus(
            puzzle_name="Bone Gallery",
            status="unattempted",
            details={"description": "Not yet attempted"}
        ))
    
    # Seal Chamber
    has_mark = mark_stage >= 1
    has_badge = "seal_keeper_badge" in flags
    has_acorn = "green_acorn" in key_items
    
    keys_collected = sum([has_mark, has_badge, has_acorn])
    
    puzzles.append(PuzzleStatus(
        puzzle_name="Seal Chamber",
        status="ready" if keys_collected == 3 else "incomplete",
        details={
            "keys_collected": keys_collected,
            "keys_total": 3,
            "has_mark": has_mark,
            "has_seal_keeper_badge": has_badge,
            "has_green_acorn": has_acorn
        }
    ))
    
    return puzzles


def get_dialogue_progress(flags: Dict) -> List[NPCDialogueChain]:
    """Get dialogue chain progress for all NPCs."""
    chains = []
    
    for npc_name, steps in NPC_DIALOGUE_CHAINS.items():
        dialogue_steps = []
        completed = 0
        
        for flag_key, description, required in steps:
            is_completed = flag_key in flags
            if is_completed:
                completed += 1
            
            dialogue_steps.append(DialogueStep(
                step_name=flag_key,
                description=description,
                flag_required=required or "(initial)",
                completed=is_completed
            ))
        
        chains.append(NPCDialogueChain(
            npc_name=npc_name,
            steps=dialogue_steps,
            progress_pct=(completed / len(steps)) * 100 if steps else 0
        ))
    
    return chains


def generate_warnings(flags: Dict, mark_stage: int, location: str) -> List[str]:
    """Generate narrative warnings."""
    warnings = []
    
    # Check mark consistency
    if mark_stage == 0 and "mark_of_dreamer_stage_1" in flags:
        warnings.append("Inconsistency: mark_stage=0 but stage_1 flag set")
    if mark_stage >= 1 and "mark_of_dreamer_stage_1" not in flags:
        warnings.append("Inconsistency: mark_stage>=1 but stage_1 flag not set")
    
    # Check cave without antechamber
    if location and "cave" in location and "thornhold_statue_observed" not in flags:
        warnings.append("In cave but Antechamber prerequisite not met (possible soft-lock)")
    
    # Check Del ghost
    if "del_ghost_roll" in flags and "del_ghost_visited" not in flags:
        warnings.append("Del ghost roll exists but ghost never visited (roll failed)")
    
    # Check suppression countdown
    if "mark_suppression_countdown" in flags:
        countdown = int(flags.get("mark_suppression_countdown", {}).get("value", 0))
        return_stage = flags.get("mark_suppression_return_stage", {}).get("value", "unknown")
        warnings.append(f"Mark suppression active: {countdown} rests remaining, will return at stage {return_stage}")
    
    return warnings


# ============================================================================
# API Endpoints
# ============================================================================

@router.get("/character/{character_id}/summary", response_model=NarrativeSummary)
def get_character_narrative_summary(character_id: str, conn: sqlite3.Connection = Depends(get_db), auth: dict = Depends(get_auth)):
    """Get complete narrative summary for a character."""
    require_character_ownership(character_id, auth)
    
    # Get character info
    cursor = conn.execute(
        "SELECT id, name, level, mark_of_dreamer_stage, location_id FROM characters WHERE id = ?",
        (character_id,)
    )
    char = cursor.fetchone()
    if not char:
        raise HTTPException(status_code=404, detail="Character not found")
    
    # Get flags
    flags = get_character_flags(conn, character_id)
    
    # Get front
    front_row = get_character_front(conn, character_id)
    front = FrontStatus(
        front_id=front_row["id"] if front_row else "unknown",
        front_name=front_row["name"] if front_row else "Unknown",
        current_portent_index=front_row["current_portent_index"] if front_row else 0,
        current_portent_name=DREAMING_HUNGER_PORTENTS[front_row["current_portent_index"]] if front_row and front_row["current_portent_index"] < len(DREAMING_HUNGER_PORTENTS) else "Unknown",
        total_portents=len(DREAMING_HUNGER_PORTENTS),
        is_active=front_row["is_active"] if front_row else True,
        impending_doom=front_row["impending_doom"] if front_row else "Unknown"
    )
    
    # Get key items from equipment
    cursor = conn.execute("SELECT equipment_json FROM characters WHERE id = ?", (character_id,))
    row = cursor.fetchone()
    key_items = []
    if row and row["equipment_json"]:
        equipment = json.loads(row["equipment_json"])
        for item in equipment:
            if isinstance(item, dict) and item.get("type") == "key_item":
                key_items.append(item.get("name"))
    
    # Build response
    return NarrativeSummary(
        character_id=char["id"],
        character_name=char["name"],
        level=char["level"],
        mark_stage=char["mark_of_dreamer_stage"],
        location=char["location_id"] or "unknown",
        front=front,
        endings=check_ending_reachable(flags, char["mark_of_dreamer_stage"]),
        puzzles=check_puzzle_status(flags, key_items, char["mark_of_dreamer_stage"]),
        dialogue_chains=get_dialogue_progress(flags),
        critical_flags=[
            FlagInfo(
                flag_key=flag,
                flag_value=flags[flag]["value"] if flag in flags else "",
                description=CRITICAL_FLAGS.get(flag, ("Unknown flag", "unknown"))[0],
                category=CRITICAL_FLAGS.get(flag, ("Unknown", "unknown"))[1] if flag in CRITICAL_FLAGS else "unknown",
                set_at=flags[flag]["set_at"] if flag in flags else None
            )
            for flag in CRITICAL_FLAGS.keys()
        ],
        warnings=generate_warnings(flags, char["mark_of_dreamer_stage"], char["location_id"])
    )


@router.get("/character/{character_id}/flags", response_model=List[FlagInfo])
def get_character_flags_endpoint(character_id: str, conn: sqlite3.Connection = Depends(get_db), auth: dict = Depends(get_auth)):
    """Get all narrative flags for a character with descriptions."""
    require_character_ownership(character_id, auth)
    
    # Verify character exists
    cursor = conn.execute("SELECT id FROM characters WHERE id = ?", (character_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Character not found")
    
    flags = get_character_flags(conn, character_id)
    
    result = []
    for flag_key, flag_data in flags.items():
        desc, category = CRITICAL_FLAGS.get(flag_key, ("Custom flag", "custom"))
        result.append(FlagInfo(
            flag_key=flag_key,
            flag_value=flag_data["value"],
            description=desc,
            category=category,
            set_at=flag_data["set_at"]
        ))
    
    return result


@router.get("/character/{character_id}/endings")
def get_character_endings(character_id: str, conn: sqlite3.Connection = Depends(get_db), auth: dict = Depends(get_auth)):
    """Get ending reachability status for a character."""
    require_character_ownership(character_id, auth)
    
    cursor = conn.execute(
        "SELECT mark_of_dreamer_stage FROM characters WHERE id = ?",
        (character_id,)
    )
    row = cursor.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Character not found")
    
    flags = get_character_flags(conn, character_id)
    return check_ending_reachable(flags, row["mark_of_dreamer_stage"])


@router.get("/character/{character_id}/dialogue")
def get_character_dialogue_progress(character_id: str, conn: sqlite3.Connection = Depends(get_db), auth: dict = Depends(get_auth)):
    """Get NPC dialogue chain progress for a character."""
    require_character_ownership(character_id, auth)
    
    cursor = conn.execute("SELECT id FROM characters WHERE id = ?", (character_id,))
    if not cursor.fetchone():
        raise HTTPException(status_code=404, detail="Character not found")
    
    flags = get_character_flags(conn, character_id)
    return get_dialogue_progress(flags)


@router.get("/global/state", response_model=GlobalNarrativeState)
def get_global_narrative_state(conn: sqlite3.Connection = Depends(get_db)):
    """Get global narrative statistics across all characters."""
    
    # Character counts
    cursor = conn.execute("SELECT COUNT(*) as count FROM characters")
    total_chars = cursor.fetchone()["count"]
    
    # Mark stage distribution
    cursor = conn.execute(
        "SELECT mark_of_dreamer_stage, COUNT(*) as count FROM characters GROUP BY mark_of_dreamer_stage"
    )
    mark_distribution = {row["mark_of_dreamer_stage"]: row["count"] for row in cursor.fetchall()}
    
    # Active fronts
    cursor = conn.execute("SELECT COUNT(*) as count FROM fronts WHERE is_active = 1")
    active_fronts = cursor.fetchone()["count"]
    
    # Average portent
    cursor = conn.execute("SELECT AVG(current_portent_index) as avg FROM character_fronts")
    avg_portent = cursor.fetchone()["avg"] or 0
    
    # Most common flags
    cursor = conn.execute(
        """SELECT flag_key, COUNT(*) as count 
           FROM narrative_flags 
           GROUP BY flag_key 
           ORDER BY count DESC 
           LIMIT 10"""
    )
    common_flags = [(row["flag_key"], row["count"]) for row in cursor.fetchall()]
    
    # Flag gaps — flags suspected of being read but never set.
    # Cross-check against DB: if a flag has any rows in narrative_flags, it's wired.
    suspected_gaps = {
        "thornhold_statue_observed": ("Observed Thornhold statue (Antechamber puzzle req)", "Antechamber puzzle path"),
        "collateral_near_town": ("Collateral damage near Thornhold", "Thornhold exile / Constantine branch"),
        "kol_ally": ("Kol redemption / Communion path", "Redemption ending mentioned but no acquisition path"),
    }
    if suspected_gaps:
        placeholders = ",".join("?" * len(suspected_gaps))
        cursor = conn.execute(
            f"SELECT DISTINCT flag_key FROM narrative_flags WHERE flag_key IN ({placeholders})",
            list(suspected_gaps.keys()),
        )
        flags_with_rows = {row["flag_key"] for row in cursor.fetchall()}
    else:
        flags_with_rows = set()
    known_gaps = []
    for flag_key, (description, impact) in suspected_gaps.items():
        if flag_key not in flags_with_rows:
            known_gaps.append({
                "flag": flag_key,
                "issue": "Never set by any code path (zero DB occurrences)",
                "impact": impact,
            })
    # If all suspected gaps have been resolved, note that
    if not known_gaps and suspected_gaps:
        known_gaps = [{"flag": "_all_clear", "issue": "All previously flagged gaps now have DB entries", "impact": "Audit gap list fully resolved"}]
    
    return GlobalNarrativeState(
        total_characters=total_chars,
        characters_by_mark_stage=mark_distribution,
        active_fronts=active_fronts,
        average_portent_index=round(avg_portent, 2),
        most_common_flags=common_flags,
        flag_gaps=known_gaps
    )


@router.get("/flags/reference")
def get_flags_reference():
    """Get reference documentation for all narrative flags."""
    return {
        "critical_flags": [
            {
                "flag_key": flag,
                "description": desc[0],
                "category": desc[1]
            }
            for flag, desc in CRITICAL_FLAGS.items()
        ],
        "dialogue_chains": {
            npc: [
                {
                    "flag": flag,
                    "description": desc,
                    "requires": req or "(initial)"
                }
                for flag, desc, req in steps
            ]
            for npc, steps in NPC_DIALOGUE_CHAINS.items()
        },
        "front_portents": [
            {"index": i, "name": name}
            for i, name in enumerate(DREAMING_HUNGER_PORTENTS)
        ]
    }
