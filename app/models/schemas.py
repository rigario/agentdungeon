"""D20 Agent RPG — Pydantic models (aligned with dnd5e_json_schema).

Field names match BrianWendt/dnd5e_json_schema community standard:
- ability_scores (not stats)
- hit_points (not hp_current/hp_max)
- armor_class (not ac)
- race as object (not string)
- classes as array (not single class)
- speed, skills, saving_throws, languages, treasure, conditions
"""

from pydantic import BaseModel, Field
from typing import Optional


class HealthResponse(BaseModel):
    status: str = "ok"
    service: str = "rigario-d20-agent-rpg"
    version: str = "0.1.0"
    db_connected: bool


# --- Character Sheet Components (community-compatible) ---

class AbilityScores(BaseModel):
    str: int
    dex: int
    con: int
    int: int
    wis: int
    cha: int


class HitPoints(BaseModel):
    max: int
    current: int
    temporary: int = 0


class ArmorClass(BaseModel):
    value: int
    description: str = "Unarmored"


class Speed(BaseModel):
    Walk: int = 30
    Burrow: int = 0
    Climb: int = 0
    Fly: int = 0
    Swim: int = 0


class RaceInfo(BaseModel):
    name: str
    size: str = "Medium"
    traits: list = []


class ClassInfo(BaseModel):
    name: str
    level: int = 1
    hit_die: int
    spellcasting: str = ""
    subtype: str = ""
    features: list = []


class BackgroundInfo(BaseModel):
    name: str


class Treasure(BaseModel):
    gp: int = 0
    sp: int = 0
    cp: int = 0
    pp: int = 0
    ep: int = 0


class PlayerInfo(BaseModel):
    name: str = "default"
    id: Optional[str] = None


class Provenance(BaseModel):
    data_source: str = ""
    created_at: str = ""
    signature: str = ""


# --- Character Create (input) ---

class CharacterCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    race: str = Field(..., min_length=1, max_length=32)
    class_name: str = Field(..., alias="class", min_length=1, max_length=32)
    background: Optional[str] = Field(None, max_length=64)
    stats: Optional[dict] = None  # point-buy: {"str": 14, "dex": 16, ...}
    languages: Optional[list] = None  # extra languages beyond racial defaults
    skills: Optional[list] = None  # 2 class skill choices

    model_config = {"populate_by_name": True}


# --- Character Response (full community-compatible sheet) ---

class CharacterResponse(BaseModel):
    id: str
    name: str
    version: str = "5.2"
    player: PlayerInfo = PlayerInfo()
    alignment: str = ""
    race: RaceInfo
    classes: list[ClassInfo]
    background: BackgroundInfo
    ability_scores: AbilityScores
    hit_points: HitPoints
    armor_class: ArmorClass
    speed: Speed
    skills: dict = {}
    saving_throws: dict = {}
    languages: list = []
    weapon_proficiencies: list = []
    armor_proficiencies: list = []
    equipment: list = []
    treasure: Treasure = Treasure()
    spell_slots: dict = {}
    spells: list = []
    feats: list = []
    conditions: dict = {}
    xp: int = 0
    location_id: Optional[str] = None
    current_location_id: Optional[str] = None
    approval_config: dict = {}
    aggression_slider: int = 50
    is_archived: bool = False
    archived_at: Optional[str] = None
    provenance: Provenance = Provenance()


# --- Character Update ---

class HitPointsUpdate(BaseModel):
    max: Optional[int] = None
    current: Optional[int] = None
    temporary: Optional[int] = None


class CharacterUpdate(BaseModel):
    name: Optional[str] = None
    hit_points: Optional[HitPointsUpdate] = None
    armor_class: Optional[ArmorClass] = None
    ability_scores: Optional[AbilityScores] = None
    treasure: Optional[Treasure] = None
    equipment: Optional[list] = None
    spell_slots: Optional[dict] = None
    spells: Optional[list] = None
    conditions: Optional[dict] = None
    xp: Optional[int] = None
    location_id: Optional[str] = None
    approval_config: Optional[dict] = None
    aggression_slider: Optional[int] = None


# --- Action Models ---

class ActionRequest(BaseModel):
    action_type: str = Field(..., description="move, attack, cast, rest, explore, interact, look, puzzle, quest")
    target: Optional[str] = Field(None, description="target entity or location ID")
    details: Optional[dict] = Field(None, description="extra action parameters")


class ActionResponse(BaseModel):
    success: bool
    narration: str
    events: list
    character_state: dict


# --- Approval Models ---

class ApprovalConfig(BaseModel):
    spell_level_min: int = 3
    hp_threshold_pct: int = 25
    flee_combat: bool = True
    named_npc_interaction: bool = True
    moral_choice: bool = True
    dangerous_area_entry: bool = True
    quest_acceptance: bool = True


# --- Event Log Models ---

class EventLogEntry(BaseModel):
    id: int
    timestamp: str
    event_type: str
    location_id: Optional[str]
    description: str
    data: Optional[dict]
    approval_triggered: bool
