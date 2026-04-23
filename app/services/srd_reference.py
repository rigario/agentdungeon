"""D20 Agent RPG — SRD 5.2 data loader.

Loads reference data from soryy708/dnd5-srd (MIT License).
This is the canonical source for races, classes, monsters, equipment, etc.

Our schema design decisions (nested hit_points, armor_class objects, etc.)
are our own code — not derived from any third-party schema.
"""

import json
import os
from pathlib import Path

# Path to MIT-licensed SRD data
SRD_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "references" / "dnd5-srd"

_cache = {}


def _load(filename: str) -> list | dict:
    """Load and cache a JSON file from the SRD data directory."""
    if filename not in _cache:
        path = SRD_DATA_DIR / filename
        with open(path) as f:
            _cache[filename] = json.load(f)
    return _cache[filename]


# ---------------------------------------------------------------------------
# Races
# ---------------------------------------------------------------------------

def get_races() -> list[dict]:
    """Get all 9 SRD races with speed, size, ability bonuses, languages, traits."""
    return _load("races.json")


def get_race_by_name(name: str) -> dict | None:
    """Find a race by name (case-insensitive)."""
    for race in get_races():
        if race["name"].lower() == name.lower():
            return race
    return None


RACE_NAMES = [r["name"] for r in get_races()]


# ---------------------------------------------------------------------------
# Classes
# ---------------------------------------------------------------------------

def get_classes() -> list[dict]:
    """Get all 12 SRD classes with hit_die, proficiencies, saving throws, spellcasting."""
    return _load("classes.json")


def get_class_by_name(name: str) -> dict | None:
    """Find a class by name (case-insensitive)."""
    for cls in get_classes():
        if cls["name"].lower() == name.lower():
            return cls
    return None


CLASS_NAMES = [c["name"] for c in get_classes()]


# ---------------------------------------------------------------------------
# Monsters
# ---------------------------------------------------------------------------

def get_monsters() -> list[dict]:
    """Get all 325 SRD monsters with full stat blocks."""
    return _load("monsters.json")


def get_monsters_by_cr(max_cr: float = 2, min_cr: float = 0) -> list[dict]:
    """Get monsters filtered by challenge rating range."""
    return [m for m in get_monsters() if min_cr <= m["challenge_rating"] <= max_cr]


def get_monster_by_name(name: str) -> dict | None:
    """Find a monster by name (case-insensitive)."""
    for m in get_monsters():
        if m["name"].lower() == name.lower():
            return m
    return None


# ---------------------------------------------------------------------------
# Skills
# ---------------------------------------------------------------------------

def get_skills() -> list[dict]:
    """Get all 18 SRD skills with their ability score associations."""
    return _load("skills.json")


SKILL_NAMES = [s["name"] for s in get_skills()]

# Map skill name → ability abbreviation
SKILL_ABILITY = {}
for s in get_skills():
    SKILL_ABILITY[s["name"]] = s.get("ability_score", {}).get("name", "DEX")[:3].lower()


# ---------------------------------------------------------------------------
# Equipment
# ---------------------------------------------------------------------------

def get_equipment() -> list[dict]:
    """Get all SRD equipment."""
    return _load("equipment.json")


def get_equipment_by_name(name: str) -> dict | None:
    """Find equipment by name."""
    for item in get_equipment():
        if item["name"].lower() == name.lower():
            return item
    return None


# ---------------------------------------------------------------------------
# Spells
# ---------------------------------------------------------------------------

def get_spells() -> list[dict]:
    """Get all SRD spells."""
    return _load("spells.json")


def get_spells_by_level(level: int) -> list[dict]:
    """Get spells filtered by level."""
    return [s for s in get_spells() if s.get("level") == level]


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------

def get_conditions() -> list[dict]:
    """Get all SRD conditions (Blinded, Charmed, etc.)."""
    return _load("conditions.json")


# ---------------------------------------------------------------------------
# Languages
# ---------------------------------------------------------------------------

def get_languages() -> list[dict]:
    """Get all SRD languages."""
    return _load("languages.json")


LANGUAGE_NAMES = [l["name"] for l in get_languages()]


# ---------------------------------------------------------------------------
# Features & Traits
# ---------------------------------------------------------------------------

def get_features() -> list[dict]:
    """Get all SRD class features."""
    return _load("features.json")


def get_traits() -> list[dict]:
    """Get all SRD racial traits."""
    return _load("traits.json")


# ---------------------------------------------------------------------------
# Starting Equipment
# ---------------------------------------------------------------------------

def get_starting_equipment() -> list[dict]:
    """Get starting equipment options per class."""
    return _load("startingEquipment.json")


# ---------------------------------------------------------------------------
# Point-buy (SRD 5.2 core rule — our own implementation, not copied)
# ---------------------------------------------------------------------------

POINT_BUY_COSTS = {
    8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9,
}
POINT_BUY_BUDGET = 27


def ability_modifier(score: int) -> int:
    """Calculate D&D 5E ability modifier from score."""
    return (score - 10) // 2


def validate_point_buy(stats: dict) -> tuple[bool, str]:
    """Validate that stats follow point-buy rules (8-15 base, 27 points)."""
    required = {"str", "dex", "con", "int", "wis", "cha"}
    if set(stats.keys()) != required:
        return False, f"Stats must include exactly: {required}"

    total_cost = 0
    for stat, value in stats.items():
        if value < 8 or value > 15:
            return False, f"{stat} must be between 8 and 15 (point-buy), got {value}"
        if value not in POINT_BUY_COSTS:
            return False, f"Invalid point-buy value: {value}"
        total_cost += POINT_BUY_COSTS[value]

    # Must spend exactly POINT_BUY_BUDGET points (standard 27-point buy)
    if total_cost != POINT_BUY_BUDGET:
        return False, f"Point-buy must total exactly {POINT_BUY_BUDGET} points, got {total_cost}"

    return True, "OK"


def generate_point_buy() -> dict:
    """Generate a balanced default point-buy array."""
    return {"str": 15, "dex": 14, "con": 13, "int": 10, "wis": 12, "cha": 8}


# ---------------------------------------------------------------------------
# HP / AC calculations (SRD 5.2 core rules — our own implementation)
# ---------------------------------------------------------------------------

def calculate_hp(hit_dice: int, con_score: int, level: int = 1) -> int:
    """Calculate starting HP. Level 1 = max hit dice + CON mod."""
    con_mod = ability_modifier(con_score)
    if level == 1:
        return hit_dice + con_mod
    avg_roll = (hit_dice // 2) + 1
    return hit_dice + con_mod + (level - 1) * (avg_roll + con_mod)


def calculate_ac(dex_score: int, armor: str = "unarmored") -> tuple[int, str]:
    """Calculate AC. Returns (value, description)."""
    dex_mod = ability_modifier(dex_score)
    armor_data = {
        "unarmored":        (10, "Unarmored"),
        "padded":           (11, "Padded Armor"),
        "leather":          (11, "Leather Armor"),
        "studded_leather":  (12, "Studded Leather"),
        "hide":             (12, "Hide Armor"),
        "chain_shirt":      (13, "Chain Shirt"),
        "scale_mail":       (14, "Scale Mail"),
        "ring_mail":        (14, "Ring Mail"),
        "chain_mail":       (16, "Chain Mail"),
        "splint":           (17, "Splint Armor"),
        "plate":            (18, "Plate Armor"),
    }
    base, desc = armor_data.get(armor, (10, "Unarmored"))
    if armor in ("chain_mail", "splint", "plate"):
        return base, desc
    if armor in ("hide", "chain_shirt", "scale_mail", "ring_mail"):
        return base + min(dex_mod, 2), desc
    return base + dex_mod, desc


# ---------------------------------------------------------------------------
# Character sheet builder (our own schema design — not copied from any repo)
# ---------------------------------------------------------------------------

# Background skill proficiencies
BACKGROUND_SKILLS = {
    "Acolyte":        ["Insight", "Religion"],
    "Charlatan":      ["Deception", "Sleight of Hand"],
    "Criminal":       ["Deception", "Stealth"],
    "Entertainer":    ["Acrobatics", "Performance"],
    "Folk Hero":      ["Animal Handling", "Survival"],
    "Guild Artisan":  ["Insight", "Persuasion"],
    "Hermit":         ["Medicine", "Religion"],
    "Noble":          ["History", "Persuasion"],
    "Outlander":      ["Athletics", "Survival"],
    "Sage":           ["Arcana", "History"],
    "Sailor":         ["Athletics", "Perception"],
    "Soldier":        ["Athletics", "Intimidation"],
    "Urchin":         ["Sleight of Hand", "Stealth"],
}

BACKGROUNDS = list(BACKGROUND_SKILLS.keys())

# Default starting equipment (simplified — detailed version uses SRD starting_equipment.json)
DEFAULT_EQUIPMENT = {
    "Barbarian": ["Greataxe", "Handaxe x2", "Javelin x4"],
    "Bard":      ["Rapier", "Leather Armor", "Lute", "Dagger"],
    "Cleric":    ["Mace", "Scale Mail", "Shield", "Light Crossbow", "Holy Symbol"],
    "Druid":     ["Wooden Shield", "Scimitar", "Leather Armor", "Druidic Focus"],
    "Fighter":   ["Longsword", "Shield", "Chain Mail", "Light Crossbow"],
    "Monk":      ["Shortsword", "Dart x10", "Explorer's Pack"],
    "Paladin":   ["Longsword", "Shield", "Chain Mail", "Javelin x5", "Holy Symbol"],
    "Ranger":    ["Longsword", "Shortsword", "Scale Mail", "Longbow", "Arrow x20"],
    "Rogue":     ["Rapier", "Shortbow", "Arrow x20", "Leather Armor", "Thieves' Tools"],
    "Sorcerer":  ["Light Crossbow", "Dagger x2", "Component Pouch"],
    "Warlock":   ["Light Crossbow", "Leather Armor", "Dagger x2", "Arcane Focus"],
    "Wizard":    ["Quarterstaff", "Component Pouch", "Spellbook"],
}

# Class level 1 features (from SRD — simplified)
CLASS_FEATURES_L1 = {
    "Barbarian": [{"name": "Rage", "description": "On your turn, you can enter a rage as a bonus action."}],
    "Bard":      [{"name": "Spellcasting", "description": "You can cast bard spells."}],
    "Cleric":    [{"name": "Spellcasting", "description": "You can cast cleric spells."}, {"name": "Divine Domain", "description": "Choose a domain related to your deity."}],
    "Druid":     [{"name": "Druidic", "description": "You know Druidic, the secret language of druids."}, {"name": "Spellcasting", "description": "You can cast druid spells."}],
    "Fighter":   [{"name": "Fighting Style", "description": "You adopt a particular style of fighting."}, {"name": "Second Wind", "description": "You can use a bonus action to regain hit points."}],
    "Monk":      [{"name": "Unarmored Defense", "description": "AC = 10 + DEX mod + WIS mod when unarmored."}, {"name": "Martial Arts", "description": "You can use DEX for unarmed strikes and monk weapons."}],
    "Paladin":   [{"name": "Divine Sense", "description": "You can detect the presence of celestials, fiends, and undead."}, {"name": "Lay on Hands", "description": "Your blessed touch can heal wounds."}],
    "Ranger":    [{"name": "Favored Enemy", "description": "Choose a type of favored enemy."}, {"name": "Natural Explorer", "description": "Choose a favored terrain."}],
    "Rogue":     [{"name": "Expertise", "description": "Double proficiency bonus for two skills."}, {"name": "Sneak Attack", "description": "Deal extra damage when you have advantage."}, {"name": "Thieves' Cant", "description": "You know the secret language of rogues."}],
    "Sorcerer":  [{"name": "Spellcasting", "description": "You can cast sorcerer spells."}, {"name": "Sorcerous Origin", "description": "Choose the source of your innate magic."}],
    "Warlock":   [{"name": "Otherworldly Patron", "description": "Choose a patron: Archfey, Fiend, or Great Old One."}, {"name": "Pact Magic", "description": "You can cast warlock spells."}],
    "Wizard":    [{"name": "Spellcasting", "description": "You can cast wizard spells."}, {"name": "Arcane Recovery", "description": "You can regain some spell slots during a short rest."}],
}

# Starting spell slots at level 1
STARTING_SPELL_SLOTS = {
    "Bard":     {"1": 2},
    "Cleric":   {"1": 2},
    "Druid":    {"1": 2},
    "Sorcerer": {"1": 2},
    "Warlock":  {"1": 1},
    "Wizard":   {"1": 2},
}


# Spellcasting ability by class (SRD 5.2 — our own mapping)
_SPELLCASTING_ABILITY = {
    "Bard": "cha", "Cleric": "wis", "Druid": "wis",
    "Sorcerer": "cha", "Warlock": "cha", "Wizard": "int",
}


def _spellcasting_ability(class_name: str) -> str:
    """Return spellcasting ability abbreviation or empty string."""
    return _SPELLCASTING_ABILITY.get(class_name, "")


# ---------------------------------------------------------------------------
# Level-up progression (SRD 5.2 core rules — our own implementation)
# ---------------------------------------------------------------------------

# XP thresholds per level (standard D&D 5E)
XP_THRESHOLDS = {
    1: 0, 2: 300, 3: 900, 4: 2700, 5: 6500,
    6: 14000, 7: 23000, 8: 34000, 9: 48000, 10: 64000,
    11: 85000, 12: 100000, 13: 120000, 14: 140000, 15: 165000,
    16: 195000, 17: 225000, 18: 265000, 19: 305000, 20: 355000,
}

# Proficiency bonus by level
PROFICIENCY_BY_LEVEL = {
    1: 2, 2: 2, 3: 2, 4: 2, 5: 3,
    6: 3, 7: 3, 8: 3, 9: 4, 10: 4,
    11: 4, 12: 4, 13: 5, 14: 5, 15: 5,
    16: 5, 17: 6, 18: 6, 19: 6, 20: 6,
}

# ASI levels — standard is 4, 8, 12, 16, 19
# Fighter gets extra at 6, 14
# Rogue gets extra at 10
ASI_LEVELS = {
    "Barbarian": [4, 8, 12, 16, 19],
    "Bard":      [4, 8, 12, 16, 19],
    "Cleric":    [4, 8, 12, 16, 19],
    "Druid":     [4, 8, 12, 16, 19],
    "Fighter":   [4, 6, 8, 12, 14, 16, 19],
    "Monk":      [4, 8, 12, 16, 19],
    "Paladin":   [4, 8, 12, 16, 19],
    "Ranger":    [4, 8, 12, 16, 19],
    "Rogue":     [4, 8, 10, 12, 16, 19],
    "Sorcerer":  [4, 8, 12, 16, 19],
    "Warlock":   [4, 8, 12, 16, 19],
    "Wizard":    [4, 8, 12, 16, 19],
}

# Full caster spell slots by level (Bard, Cleric, Druid, Sorcerer, Wizard)
# Warlock uses Pact Magic (separate progression)
_FULL_CASTER_SPELL_SLOTS = {
    1: {"1": 2},
    2: {"1": 3},
    3: {"1": 4, "2": 2},
    4: {"1": 4, "2": 3},
    5: {"1": 4, "2": 3, "3": 2},
    6: {"1": 4, "2": 3, "3": 3},
    7: {"1": 4, "2": 3, "3": 3, "4": 1},
    8: {"1": 4, "2": 3, "3": 3, "4": 2},
    9: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    10: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
    11: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    12: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1},
    13: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    14: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1},
    15: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    16: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1},
    17: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1, "9": 1},
    18: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 1, "9": 1},
    19: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 1, "7": 1, "8": 2, "9": 1},
    20: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2, "6": 2, "7": 1, "8": 2, "9": 1},
}

# Warlock Pact Magic slots (separate from full caster)
_WARLOCK_PACT_SLOTS = {
    1: {"1": 1},
    2: {"1": 2},
    3: {"2": 2},
    4: {"2": 2},
    5: {"3": 2},
    6: {"3": 2},
    7: {"4": 2},
    8: {"4": 2},
    9: {"5": 2},
    10: {"5": 2},
    11: {"5": 3},
    12: {"5": 3},
    13: {"5": 3},
    14: {"5": 3},
    15: {"5": 3},
    16: {"5": 3},
    17: {"5": 4},
    18: {"5": 4},
    19: {"5": 4},
    20: {"5": 4},
}

# Half-caster slots (Paladin, Ranger) — halved rounded down from full caster
_HALF_CASTER_SPELL_SLOTS = {
    1: {},
    2: {"1": 2},
    3: {"1": 3},
    4: {"1": 3},
    5: {"1": 4, "2": 2},
    6: {"1": 4, "2": 2},
    7: {"1": 4, "2": 3},
    8: {"1": 4, "2": 3},
    9: {"1": 4, "2": 3, "3": 2},
    10: {"1": 4, "2": 3, "3": 2},
    11: {"1": 4, "2": 3, "3": 3},
    12: {"1": 4, "2": 3, "3": 3},
    13: {"1": 4, "2": 3, "3": 3, "4": 1},
    14: {"1": 4, "2": 3, "3": 3, "4": 1},
    15: {"1": 4, "2": 3, "3": 3, "4": 2},
    16: {"1": 4, "2": 3, "3": 3, "4": 2},
    17: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    18: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 1},
    19: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
    20: {"1": 4, "2": 3, "3": 3, "4": 3, "5": 2},
}

_FULL_CASTER_CLASSES = {"Bard", "Cleric", "Druid", "Sorcerer", "Wizard"}
_HALF_CASTER_CLASSES = {"Paladin", "Ranger"}


def get_spell_slots(class_name: str, level: int) -> dict:
    """Get spell slots for a class at a given level."""
    if class_name in _FULL_CASTER_CLASSES:
        return _FULL_CASTER_SPELL_SLOTS.get(level, {})
    elif class_name in _HALF_CASTER_CLASSES:
        return _HALF_CASTER_SPELL_SLOTS.get(level, {})
    elif class_name == "Warlock":
        return _WARLOCK_PACT_SLOTS.get(level, {})
    return {}


def get_xp_for_level(level: int) -> int:
    """Get the XP threshold for a given level."""
    return XP_THRESHOLDS.get(level, 0)


def get_level_for_xp(xp: int) -> int:
    """Get the level for a given XP amount."""
    level = 1
    for lvl, threshold in sorted(XP_THRESHOLDS.items()):
        if xp >= threshold:
            level = lvl
    return level


def get_proficiency_bonus(level: int) -> int:
    """Get proficiency bonus for a given level."""
    return PROFICIENCY_BY_LEVEL.get(level, 2)


def is_asi_level(class_name: str, level: int) -> bool:
    """Check if a level grants an ASI/feat."""
    return level in ASI_LEVELS.get(class_name, [])


def calculate_level_hp(hit_die: int, con_score: int, level: int, hp_roll: int = None) -> int:
    """
    Calculate HP for a given level.
    If hp_roll is None, use average (rounded up).
    """
    con_mod = ability_modifier(con_score)
    if level == 1:
        return hit_die + con_mod
    if hp_roll is None:
        # Average: (hit_die // 2) + 1, rounded up
        avg = (hit_die // 2) + 1
        return avg + con_mod
    return max(1, hp_roll + con_mod)  # Minimum 1 HP per level


def validate_level_up(current_sheet: dict, new_level: int, choices: dict) -> tuple[bool, str, dict]:
    """
    Validate a level-up against SRD 5.2 rules.

    Args:
        current_sheet: The current character sheet
        new_level: The target level
        choices: Dict with level-up choices:
            - hp_roll: int (optional, uses average if not provided)
            - ability_increase: dict (optional, e.g. {"str": 1, "con": 1} or {"feat": "Alert"})
            - subclass: str (optional, name of subclass)
            - new_spells: list (optional, spell names to add)

    Returns:
        (is_valid, error_message, updates_to_apply)
    """
    current_level = current_sheet.get("classes", [{}])[0].get("level", 1)
    class_name = current_sheet.get("classes", [{}])[0].get("name", "")

    if new_level != current_level + 1:
        return False, f"Can only level up one at a time: {current_level} → {new_level}", {}

    if new_level > 20:
        return False, "Cannot exceed level 20", {}

    if new_level < 1:
        return False, "Level must be at least 1", {}

    updates = {}

    # HP increase
    hit_die = current_sheet.get("classes", [{}])[0].get("hit_die", 8)
    con_score = current_sheet.get("ability_scores", {}).get("con", 10)
    hp_roll = choices.get("hp_roll")
    hp_gain = calculate_level_hp(hit_die, con_score, new_level, hp_roll)
    updates["hp_gain"] = hp_gain

    # ASI / Feat
    if is_asi_level(class_name, new_level):
        asi_choice = choices.get("ability_increase")
        if not asi_choice:
            return False, f"Level {new_level} grants ASI — must choose ability_increase or feat", {}

        if "feat" in asi_choice:
            # Feat choice — we store it, DM agent validates narrative
            updates["feat"] = asi_choice["feat"]
        else:
            # Ability score increase — must be exactly 2 points to one stat,
            # or 1 point to two different stats
            total_increase = sum(asi_choice.values())
            if total_increase != 2:
                return False, f"ASI must distribute exactly 2 points, got {total_increase}", {}

            # Check individual stats don't exceed 20
            current_stats = current_sheet.get("ability_scores", {})
            for stat, increase in asi_choice.items():
                if stat not in {"str", "dex", "con", "int", "wis", "cha"}:
                    return False, f"Invalid stat: {stat}", {}
                new_score = current_stats.get(stat, 10) + increase
                if new_score > 20:
                    return False, f"{stat} would exceed 20 (beyond racial cap)", {}

            updates["ability_increase"] = asi_choice

    # Spell slots for casters
    if class_name in _FULL_CASTER_CLASSES or class_name in _HALF_CASTER_CLASSES or class_name == "Warlock":
        new_slots = get_spell_slots(class_name, new_level)
        updates["spell_slots"] = new_slots

    # Subclass (usually chosen at level 3 for most classes)
    if choices.get("subclass"):
        updates["subclass"] = choices["subclass"]

    return True, "OK", updates


def build_level_up(
    current_sheet: dict,
    new_level: int,
    choices: dict,
) -> dict:
    """Apply level-up changes to a character sheet. Returns updated sheet."""
    is_valid, msg, updates = validate_level_up(current_sheet, new_level, choices)
    if not is_valid:
        raise ValueError(f"Invalid level-up: {msg}")

    sheet = dict(current_sheet)
    class_data = dict(sheet.get("classes", [{}])[0])
    class_data["level"] = new_level

    # Apply HP gain
    old_hp = sheet.get("hit_points", {})
    new_max = old_hp.get("max", 10) + updates.get("hp_gain", 0)
    sheet["hit_points"] = {
        "max": new_max,
        "current": old_hp.get("current", new_max),
        "temporary": old_hp.get("temporary", 0),
    }

    # Apply ability increase
    if "ability_increase" in updates:
        stats = dict(sheet.get("ability_scores", {}))
        for stat, increase in updates["ability_increase"].items():
            stats[stat] = stats.get(stat, 10) + increase
        sheet["ability_scores"] = stats

    # Apply feat
    if "feat" in updates:
        feats = list(sheet.get("feats", []))
        feats.append({"name": updates["feat"], "source": f"level_{new_level}"})
        sheet["feats"] = feats

    # Apply subclass
    if "subclass" in updates:
        class_data["subclass"] = updates["subclass"]

    # Apply spell slots
    if "spell_slots" in updates:
        sheet["spell_slots"] = updates["spell_slots"]

    # Update class level
    sheet["classes"] = [class_data]

    # Update proficiency bonus (stored in sheet for convenience)
    sheet["proficiency_bonus"] = get_proficiency_bonus(new_level)

    return sheet


def build_character_sheet(char_id: str, name: str, race_name: str, class_name: str,
                          background_name: str, base_stats: dict,
                          extra_languages: list = None, chosen_skills: list = None) -> dict:
    """Build a character sheet. Schema is our own design — not copied from any repo."""
    race = get_race_by_name(race_name)
    cls = get_class_by_name(class_name)

    if not race:
        raise ValueError(f"Unknown race: {race_name}")
    if not cls:
        raise ValueError(f"Unknown class: {class_name}")

    # Apply racial ability bonuses
    final_stats = dict(base_stats)
    for bonus in race.get("ability_bonuses", []):
        # SRD format: {"name": "CON", "bonus": 2, "url": "..."}
        stat_name = bonus.get("name", "").lower()
        if stat_name and len(stat_name) == 3:
            final_stats[stat_name] = final_stats.get(stat_name, 10) + bonus.get("bonus", 0)

    # Calculate derived values
    hit_die = cls.get("hit_die", 8)
    hp_max = calculate_hp(hit_die, final_stats["con"])
    ac_value, ac_desc = calculate_ac(final_stats["dex"])

    # Speed from race data
    speed_val = race.get("speed", 30)
    speed = {"Walk": speed_val, "Burrow": 0, "Climb": 0, "Fly": 0, "Swim": 0}

    # Skills: background + class choices
    skills = {}
    for sk in BACKGROUND_SKILLS.get(background_name, []):
        skills[sk] = True
    if chosen_skills:
        for sk in chosen_skills[:2]:
            if sk in SKILL_NAMES and sk not in skills:
                skills[sk] = True

    # Saving throw proficiencies (from class data)
    saving_throws = {}
    for st in cls.get("saving_throws", []):
        # SRD format: {"name": "CON", "url": "..."}
        stat_name = st.get("name", "").lower()
        if stat_name and len(stat_name) == 3:
            saving_throws[stat_name] = True

    # Languages from race
    languages = []
    for lang in race.get("languages", []):
        languages.append(lang["name"])
    if extra_languages:
        languages.extend(extra_languages)

    # Weapon/armor proficiencies from class
    weapon_profs = []
    armor_profs = []
    for prof in cls.get("proficiencies", []):
        pname = prof["name"]
        if any(k in pname.lower() for k in ["armor", "shield"]):
            armor_profs.append(pname)
        else:
            weapon_profs.append(pname)

    # Class features at level 1
    features = CLASS_FEATURES_L1.get(class_name, [])

    # Spell slots
    spell_slots = STARTING_SPELL_SLOTS.get(class_name, {})

    # Racial traits
    race_traits = []
    for trait in race.get("traits", []):
        race_traits.append({"name": trait["name"], "description": trait.get("desc", "")})

    return {
        "version": "5.2",
        "name": name,
        "player": {"name": "default"},
        "alignment": race.get("alignment", ""),
        "race": {
            "name": race["name"],
            "size": race.get("size", "Medium"),
            "speed": speed_val,
            "traits": race_traits,
        },
        "classes": [{
            "name": class_name,
            "level": 1,
            "hit_die": hit_die,
            "spellcasting": _spellcasting_ability(class_name),
            "features": features,
        }],
        "background": {"name": background_name},
        "ability_scores": final_stats,
        "hit_points": {"max": hp_max, "current": hp_max, "temporary": 0},
        "armor_class": {"value": ac_value, "description": ac_desc},
        "speed": speed,
        "skills": skills,
        "saving_throws": saving_throws,
        "languages": languages,
        "weapon_proficiencies": weapon_profs,
        "armor_proficiencies": armor_profs,
        "equipment": DEFAULT_EQUIPMENT.get(class_name, ["Dagger", "Backpack"]),
        "treasure": {"gp": 10, "sp": 0, "cp": 0, "pp": 0, "ep": 0},
        "spell_slots": spell_slots,
        "spells": [],
        "feats": [],
        "conditions": {},
        "xp": 0,
        "provenance": {
            "data_source": "soryy708/dnd5-srd (MIT License)",
            "created_at": "",
            "signature": "",
        },
    }
